"""Single-operation connections and explicit rollback boundaries."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.config import AuthSettings, check_owned_file, checked_path
from app.core.migrations import PROFILE, verify_migration_manifest
from app.domain.auth import AuthFailure, unavailable


def validate_auth_profile(connection: sqlite3.Connection) -> None:
    digest, _ = verify_migration_manifest()
    try:
        rows = connection.execute("SELECT profile, manifest_sha256 FROM _python_auth_schema").fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            raise unavailable() from None
        raise
    if len(rows) != 1 or tuple(rows[0]) != (PROFILE, digest):
        raise unavailable()


@contextmanager
def connect_auth_database(settings: AuthSettings) -> Iterator[sqlite3.Connection]:
    connection = None
    try:
        try:
            path = checked_path(settings.db_path)
            check_owned_file(path)
        except (OSError, ValueError):
            raise unavailable() from None
        connection = sqlite3.connect(f"{path.as_uri()}?mode=rw", uri=True, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        validate_auth_profile(connection)
        yield connection
    except sqlite3.Error as exc:
        if getattr(exc, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED,
                                                     sqlite3.SQLITE_CANTOPEN):
            raise unavailable() from None
        raise AuthFailure(500, 1007, "Authentication storage failure") from None
    finally:
        if connection is not None:
            connection.close()


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
