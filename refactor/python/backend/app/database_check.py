"""Check one explicit standalone SQLite file without application database state."""

import hashlib
import os
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path

ERROR_DETAILS = {
    "ok": (0, "Connection check passed; business schema not verified."),
    "invalid_arguments": (2, "Use --path PATH with optional --create and --json; see --help."),
    "invalid_target": (3, "Use an explicit standalone local regular file with an existing parent directory."),
    "target_not_found": (
        3,
        (
            "The explicit target or its parent does not exist; create the parent yourself and use --create "
            "only for a new file."
        ),
    ),
    "target_exists": (3, "Creation refused because the target already exists; choose a new file."),
    "access_failed": (4, "Cannot access the explicit target; check permissions and availability."),
    "database_check_failed": (4, "Read-only SQLite checks failed; use a valid standalone SQLite file."),
    "close_failed": (5, "Resource release failed; the connection check is not successful."),
    "internal_error": (6, "Unexpected local check failure; no successful check is reported."),
    "interrupted": (130, "Connection check interrupted; no successful check is reported."),
}


class DatabaseCheckError(Exception):
    """Carry only stable public error metadata, never raw filesystem/SQLite errors."""

    def __init__(self, code: str, *, created: bool = False, target: str | None = None) -> None:
        self.code = code
        self.created = created
        self.target = target
        super().__init__(ERROR_DETAILS[code][1])


@dataclass(frozen=True)
class DatabaseCheckResult:
    """Represent a safe result after all owned resources have been released."""

    mode: str | None
    target: str | None
    created: bool = False
    code: str = "ok"

    def to_dict(self) -> dict[str, object]:
        """Return the frozen public result fields for both text and JSON output."""
        return {
            "engine": "sqlite",
            "status": "ok" if self.code == "ok" else "error",
            "mode": self.mode,
            "target": self.target,
            "created": self.created,
            "checks": ["select_1", "schema_read"] if self.code == "ok" else [],
            "code": self.code,
            "message": ERROR_DETAILS[self.code][1],
        }


def _target_id(path: Path) -> str:
    return "local-file:" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]


def resolve_database_target(raw_path: str, *, create: bool, base_dir: Path | None = None) -> Path:
    """Validate a local target without following its final link or creating anything."""
    if (
        not raw_path
        or not raw_path.strip()
        or "\x00" in raw_path
        or raw_path == ":memory:"
        or raw_path.startswith("file:")
        or "://" in raw_path
    ):
        raise DatabaseCheckError("invalid_target")
    try:
        path = Path(raw_path)
        if not path.is_absolute():
            path = (Path.cwd() if base_dir is None else Path(base_dir)) / path
        parent = path.parent.resolve(strict=True)
        if not parent.is_dir():
            raise DatabaseCheckError("invalid_target")
        target = parent / path.name
        target_id = _target_id(target)
        try:
            info = target.lstat()
        except FileNotFoundError:
            if not create:
                raise DatabaseCheckError("target_not_found", target=target_id) from None
        else:
            if create:
                raise DatabaseCheckError("target_exists", target=target_id)
            if not stat.S_ISREG(info.st_mode):
                raise DatabaseCheckError("invalid_target", target=target_id)
        for suffix in ("-wal", "-shm", "-journal"):
            try:
                target.with_name(target.name + suffix).lstat()
            except FileNotFoundError:
                continue
            raise DatabaseCheckError("invalid_target", target=target_id)
        return target
    except FileNotFoundError:
        raise DatabaseCheckError("target_not_found") from None
    except NotADirectoryError:
        raise DatabaseCheckError("invalid_target") from None
    except OSError:
        raise DatabaseCheckError("access_failed") from None


def _validate_database_header(target: Path) -> None:
    """Reject unsupported journal formats before SQLite can create side files."""
    try:
        source = open(target, "rb")  # noqa: SIM115 - explicit close maps failures before any SQLite connect
        try:
            header = source.read(100)
            if header:
                if len(header) != 100 or header[:16] != b"SQLite format 3\x00":
                    raise DatabaseCheckError("database_check_failed")
                if header[18] != 1 or header[19] != 1:
                    raise DatabaseCheckError("invalid_target")
        finally:
            try:
                source.close()
            except (Exception, KeyboardInterrupt):  # noqa: BLE001 - release failure overrides rejection
                raise DatabaseCheckError("close_failed") from None
    except OSError:
        raise DatabaseCheckError("access_failed") from None


def _read_checks(target: Path) -> None:
    connection = None
    cursor = None
    try:
        connection = sqlite3.connect(target.as_uri() + "?mode=ro", uri=True, timeout=1.0)
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
        if row is None or row[0] != 1:
            raise DatabaseCheckError("database_check_failed")
        cursor.execute("SELECT name FROM sqlite_schema LIMIT 1")
        cursor.fetchone()
    finally:
        # A failed cursor close must not prevent the connection close attempt.
        close_failed = False
        if cursor is not None:
            try:
                cursor.close()
            except (Exception, KeyboardInterrupt):  # noqa: BLE001 - release failure must override success
                close_failed = True
        if connection is not None:
            try:
                connection.close()
            except (Exception, KeyboardInterrupt):  # noqa: BLE001 - release failure must override success
                close_failed = True
        if close_failed:
            raise DatabaseCheckError("close_failed") from None


def check_database(
    raw_path: str, *, create: bool = False, base_dir: Path | None = None
) -> DatabaseCheckResult:
    """Check fixed read-only probes; retain a newly created file even on failure."""
    created = False
    target_id = None
    try:
        target = resolve_database_target(raw_path, create=create, base_dir=base_dir)
        target_id = _target_id(target)
        if create:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                created = True
            finally:
                try:
                    os.close(descriptor)
                except (Exception, KeyboardInterrupt):  # noqa: BLE001 - release failure must override success
                    raise DatabaseCheckError("close_failed") from None
        _validate_database_header(target)
        _read_checks(target)
        return DatabaseCheckResult("create" if create else "read_only", target_id, created)
    except DatabaseCheckError as exc:
        raise DatabaseCheckError(
            exc.code, created=created or exc.created, target=target_id or exc.target
        ) from None
    except FileExistsError:
        raise DatabaseCheckError("target_exists", created=created, target=target_id) from None
    except FileNotFoundError:
        raise DatabaseCheckError("target_not_found", created=created, target=target_id) from None
    except sqlite3.Error:
        raise DatabaseCheckError("database_check_failed", created=created, target=target_id) from None
    except OSError:
        raise DatabaseCheckError("access_failed", created=created, target=target_id) from None
    except KeyboardInterrupt:
        raise DatabaseCheckError("interrupted", created=created, target=target_id) from None
    except Exception:  # noqa: BLE001 - frozen safe boundary forbids exposing unexpected errors
        raise DatabaseCheckError("internal_error", created=created, target=target_id) from None
