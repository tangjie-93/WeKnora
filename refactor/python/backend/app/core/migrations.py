"""Initialize only exclusively created, owned SQLite databases."""

import hashlib
import json
import os
import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import checked_path

MIGRATION_ROOT = Path(__file__).resolve().parents[1] / "migrations/sqlite"
PROFILE = "auth-sqlite-prefix-v7"
FROZEN_HASHES = (
    "57597ca2cc42742dc39ed923ac032e0c128f5ecfd990120a0c8c95e618e8e2c9",
    "251798a1e630bef789780d94a66a7244ba7f538dbf5ee14b22ccf74c92f23ee8",
    "79db4c6c3050e90dfa02606c62d0249af6f8d330c628fc1af43169068d5ae75e",
    "8adf60ae347c2568031885303e4704b06594ae61d3ff8e4329f1463fe669f075",
    "f782a241012fdec21743b194c3a0ab6db8d6e1a0304779c38664ce4d6d1b2ff8",
    "f0cc24aa80dd4b2c0654c186cf0e0ad5ccca65541ee3a035488a9e2e0304cbb0",
    "bdb930e6b3f46404f93c3a1f06760d81610d32b9b57844098f1ee2c29e3f839b",
    "860d0b4503d6a99d8c683c8008bdd7e27a1bfb013a53070d2d39aef19972181d",
)


def verify_migration_manifest() -> tuple[str, list[str]]:
    raw = (MIGRATION_ROOT / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    entries = manifest["migrations"]
    if manifest["profile"] != PROFILE or len(entries) != 8:
        raise ValueError("Unsupported migration manifest")
    scripts = []
    for version, entry in enumerate(entries):
        name = entry["file"]
        if entry["version"] != version or Path(name).name != name or not name.startswith(f"{version:06}_"):
            raise ValueError("Invalid migration order")
        data = (MIGRATION_ROOT / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"] or entry["sha256"] != FROZEN_HASHES[version]:
            raise ValueError("Migration checksum mismatch")
        scripts.append(data.decode("utf-8"))
    return hashlib.sha256(raw).hexdigest(), scripts


def initialize_auth_database(path: Path) -> None:
    """Never overwrite an existing file; rollback and remove only owned new files."""
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("An absolute new database path is required")
    path = checked_path(path)
    secret_path = checked_path(Path(f"{path}.jwt-secret"))
    if path.exists() or secret_path.exists() or not path.parent.is_dir():
        raise ValueError("Database and secret must be new files in an existing directory")
    digest, scripts = verify_migration_manifest()
    owned: list[tuple[Path, int, int]] = []
    connection = None
    try:
        for target in (path, secret_path):
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                info = os.fstat(stream.fileno())
                owned.append((target, info.st_dev, info.st_ino))
                if target == secret_path:
                    stream.write(secrets.token_urlsafe(48).encode("ascii"))
                    stream.flush()
                    os.fsync(stream.fileno())
        connection = sqlite3.connect(f"{path.as_uri()}?mode=rw", uri=True, timeout=5, isolation_level=None)
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA foreign_keys=ON")
        # executescript implicitly commits an existing transaction, so BEGIN belongs inside its text.
        connection.executescript("BEGIN IMMEDIATE;\n" + "\n".join(scripts) + "\n"
                                 "CREATE TABLE _python_auth_schema (profile TEXT PRIMARY KEY NOT NULL, "
                                 "manifest_sha256 TEXT NOT NULL, initialized_at TEXT NOT NULL);")
        connection.execute("INSERT INTO _python_auth_schema VALUES (?, ?, ?)",
                           (PROFILE, digest, datetime.now(UTC).isoformat()))
        connection.commit()
    except BaseException:
        if connection is not None:
            connection.rollback()
            connection.close()
            connection = None
        for target, device, inode in reversed(owned):
            try:
                info = target.lstat()
                if (info.st_dev, info.st_ino) == (device, inode):
                    target.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        if connection is not None:
            connection.close()
