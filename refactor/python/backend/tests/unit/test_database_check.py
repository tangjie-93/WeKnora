"""Isolated SQLite filesystem contracts and real-resource failure regression tests."""

import builtins
import hashlib
import os
import sqlite3
import stat
from pathlib import Path

import pytest

from app import database_check as db


def make_database(path, *, wal=False):
    connection = sqlite3.connect(path)
    try:
        if wal:
            assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel (value) VALUES (?)", ("private-sentinel",))
        connection.commit()
    finally:
        connection.close()
    return path


def snapshot(directory):
    return {p.name: (p.read_bytes(), stat.S_IMODE(p.stat().st_mode)) for p in directory.iterdir()}


def expect_error(code, function, *args, **kwargs):
    with pytest.raises(db.DatabaseCheckError) as caught:
        function(*args, **kwargs)
    assert caught.value.code == code
    assert str(caught.value) == db.ERROR_DETAILS[code][1]
    assert "private-sentinel" not in str(caught.value)
    return caught.value


def no_connect(*args, **kwargs):
    pytest.fail("Rejected input must never reach SQLite")


@pytest.mark.parametrize("name", ["normal.sqlite", " 私密 ?#&mode=rw.sqlite ", "百分%25.sqlite"])
def test_read_only_preserves_two_databases_and_sentinel(tmp_path, name):
    a = make_database(tmp_path / name)
    b = make_database(tmp_path / "other.sqlite")
    before = snapshot(tmp_path)
    for path in (b, a, b):
        result = db.check_database(str(path)).to_dict()
        assert result["checks"] == ["select_1", "schema_read"]
        assert result["target"] == "local-file:" + hashlib.sha256(str(path).encode()).hexdigest()[:12]
        assert result["created"] is False
        assert snapshot(tmp_path) == before
    connection = sqlite3.connect(a.as_uri() + "?mode=ro", uri=True)
    try:
        assert connection.execute("SELECT value FROM sentinel LIMIT 1").fetchone() == ("private-sentinel",)
    finally:
        connection.close()
    assert snapshot(tmp_path) == before


def test_empty_and_create_are_not_schema_initialization(tmp_path):
    existing = tmp_path / "empty.sqlite"
    existing.touch()
    assert db.check_database(str(existing)).created is False
    new = tmp_path / "new.sqlite"
    assert db.check_database(str(new), create=True).created is True
    assert new.read_bytes() == existing.read_bytes() == b""
    assert stat.S_IMODE(new.stat().st_mode) == 0o600
    before = snapshot(tmp_path)
    expect_error("target_exists", db.check_database, str(new), create=True)
    assert snapshot(tmp_path) == before


def test_cwd_base_dir_and_literal_names(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    for directory in (a, b):
        (directory / "~$DATABASE_PATH.sqlite").touch()
    monkeypatch.setenv("DATABASE_PATH", "must-not-be-expanded")
    monkeypatch.chdir(a)
    first = db.check_database("~$DATABASE_PATH.sqlite")
    monkeypatch.chdir(b)
    second = db.check_database("~$DATABASE_PATH.sqlite")
    assert first.target != second.target
    assert db.check_database("~$DATABASE_PATH.sqlite", base_dir=a).target == first.target


@pytest.mark.parametrize("raw", ["", " \t", "\x00", ":memory:", "file:secret?mode=rw", "https://secret"])
def test_invalid_raw_targets_do_not_connect(tmp_path, monkeypatch, raw):
    monkeypatch.setattr(db.sqlite3, "connect", no_connect)
    expect_error("invalid_target", db.check_database, raw, base_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["directory", "fifo", "link", "dangling", "-wal", "-shm", "-journal"])
def test_nonstandalone_targets_rejected_without_mutation(tmp_path, monkeypatch, kind):
    target = tmp_path / "private.sqlite"
    if kind == "directory":
        target.mkdir()
    elif kind == "fifo":
        os.mkfifo(target)
    elif kind in ("link", "dangling"):
        source = tmp_path / "owned-source"
        if kind == "link":
            source.write_bytes(b"sentinel")
        target.symlink_to(source)
    else:
        target.touch()
        (tmp_path / (target.name + kind)).write_bytes(b"sidecar-sentinel")
    before = {p.name: p.lstat() for p in tmp_path.iterdir()}
    monkeypatch.setattr(db.sqlite3, "connect", no_connect)
    expect_error("invalid_target", db.check_database, str(target))
    assert {p.name: p.lstat() for p in tmp_path.iterdir()} == before
    if kind.startswith("-"):
        assert (tmp_path / (target.name + kind)).read_bytes() == b"sidecar-sentinel"


@pytest.mark.parametrize("create", [False, True])
def test_missing_parent_never_created(tmp_path, monkeypatch, create):
    monkeypatch.setattr(db.sqlite3, "connect", no_connect)
    expect_error("target_not_found", db.check_database, str(tmp_path / "absent" / "new"), create=create)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("dangling", [False, True])
def test_create_rejects_final_links(tmp_path, dangling):
    source = tmp_path / "source"
    if not dangling:
        source.write_bytes(b"sentinel")
    target = tmp_path / "link"
    target.symlink_to(source)
    error = expect_error("target_exists", db.check_database, str(target), create=True)
    assert not error.created
    assert target.is_symlink()
    assert not source.exists() if dangling else source.read_bytes() == b"sentinel"


def test_exclusive_create_race_never_overwrites(tmp_path, monkeypatch):
    target = tmp_path / "race.sqlite"
    real_open = os.open

    def raced_open(path, flags, mode):
        assert flags == os.O_WRONLY | os.O_CREAT | os.O_EXCL
        assert mode == 0o600
        Path(path).write_bytes(b"concurrent-owner")
        return real_open(path, flags, mode)

    monkeypatch.setattr(db.os, "open", raced_open)
    error = expect_error("target_exists", db.check_database, str(target), create=True)
    assert not error.created
    assert target.read_bytes() == b"concurrent-owner"


@pytest.mark.parametrize("stage", ["create", "descriptor_close"])
def test_create_access_and_descriptor_release_failures(tmp_path, monkeypatch, stage):
    target = tmp_path / "new.sqlite"
    real_close = os.close
    descriptors = []

    def denied(*args):
        raise PermissionError("private-sentinel")

    def close_then_fail(fd):
        descriptors.append(fd)
        real_close(fd)
        raise OSError("private-sentinel")

    monkeypatch.setattr(db.sqlite3, "connect", no_connect)
    if stage == "create":
        monkeypatch.setattr(db.os, "open", denied)
    else:
        monkeypatch.setattr(db.os, "close", close_then_fail)
    error = expect_error(
        "access_failed" if stage == "create" else "close_failed", db.check_database, str(target), create=True
    )
    assert error.created is (stage == "descriptor_close")
    assert target.exists() is error.created
    if error.created:
        assert target.read_bytes() == b""
        with pytest.raises(OSError):
            os.fstat(descriptors[0])


def test_legitimate_closed_wal_refused_before_connect(tmp_path, monkeypatch):
    target = make_database(tmp_path / "closed-wal.sqlite", wal=True)
    assert {p.name for p in tmp_path.iterdir()} == {target.name}
    assert target.read_bytes()[18:20] == b"\x02\x02"
    before = snapshot(tmp_path)
    monkeypatch.setattr(db.sqlite3, "connect", no_connect)
    error = expect_error("invalid_target", db.check_database, str(target))
    assert db.ERROR_DETAILS[error.code][0] == 3
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("versions", [(2, 2), (1, 2), (2, 1), (0, 1), (1, 0), (255, 1), (1, 255)])
def test_unsupported_header_versions_refused(tmp_path, monkeypatch, versions):
    target = make_database(tmp_path / "owned.sqlite")
    data = bytearray(target.read_bytes())
    data[18:20] = bytes(versions)
    target.write_bytes(data)
    before = snapshot(tmp_path)
    monkeypatch.setattr(db.sqlite3, "connect", no_connect)
    expect_error("invalid_target", db.check_database, str(target))
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "data", [b"not sqlite", b"SQLite format 3\x00", b"x" * 100, b"SQLite format 3\x00" + b"x" * 83]
)
def test_bad_magic_and_short_header_fail_before_connect(tmp_path, monkeypatch, data):
    target = tmp_path / "bad.sqlite"
    target.write_bytes(data)
    before = snapshot(tmp_path)
    monkeypatch.setattr(db.sqlite3, "connect", no_connect)
    expect_error("database_check_failed", db.check_database, str(target))
    assert snapshot(tmp_path) == before


def test_correct_header_is_not_full_schema_validation(tmp_path):
    target = make_database(tmp_path / "corrupt.sqlite")
    data = bytearray(target.read_bytes())
    data[100] = 255  # Corrupt the first b-tree page, leaving the validated header intact.
    target.write_bytes(data)
    before = snapshot(tmp_path)
    expect_error("database_check_failed", db.check_database, str(target))
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("create", [False, True])
@pytest.mark.parametrize(
    "fault,close_fault,expected",
    [
        ("open", False, "access_failed"),
        ("read", False, "access_failed"),
        ("interrupt", False, "interrupted"),
        (None, True, "close_failed"),
        ("read", True, "close_failed"),
        ("interrupt", True, "close_failed"),
        ("format", True, "close_failed"),
        ("version", True, "close_failed"),
    ],
)
def test_header_faults_close_real_file_and_never_connect(
    tmp_path, monkeypatch, create, fault, close_fault, expected
):
    target = tmp_path / "owned.sqlite"
    if not create:
        target.touch()
    sources = []
    events = []

    class Reader:
        def __init__(self, source):
            self.source = source

        def read(self, size):
            assert size == 100
            events.append("read")
            if fault == "read":
                raise OSError("private-sentinel")
            if fault == "interrupt":
                raise KeyboardInterrupt
            if fault == "format":
                return b"bad"
            if fault == "version":
                return b"SQLite format 3\x00" + b"\x00\x00\x02\x02" + bytes(80)
            return self.source.read(size)

        def close(self):
            events.append("close")
            self.source.close()
            if close_fault:
                raise OSError("private-sentinel")

    def header_open(path, mode):
        assert mode == "rb"
        if fault == "open":
            raise PermissionError("private-sentinel")
        source = builtins.open(path, mode)  # noqa: SIM115 - production owns and must close this resource
        sources.append(source)
        return Reader(source)

    monkeypatch.setattr(db, "open", header_open, raising=False)
    monkeypatch.setattr(db.sqlite3, "connect", no_connect)
    error = expect_error(expected, db.check_database, str(target), create=create)
    assert error.created is create
    assert target.exists() and target.read_bytes() == b""
    assert all(source.closed for source in sources)
    assert events == ([] if fault == "open" else ["read", "close"])


@pytest.mark.parametrize(
    "fault,close_fault,expected",
    [
        (None, None, None),
        ("connect", None, "database_check_failed"),
        ("cursor", None, "database_check_failed"),
        ("execute1", None, "database_check_failed"),
        ("execute2", None, "database_check_failed"),
        ("fetch1", None, "database_check_failed"),
        ("fetch2", None, "database_check_failed"),
        ("row_none", None, "database_check_failed"),
        ("row_wrong", None, "database_check_failed"),
        ("interrupt", None, "interrupted"),
        ("unexpected", None, "internal_error"),
        (None, "cursor", "close_failed"),
        (None, "connection", "close_failed"),
        ("execute1", "cursor", "close_failed"),
        ("interrupt", "both", "close_failed"),
        ("cursor", "connection", "close_failed"),
    ],
)
@pytest.mark.parametrize("create", [False, True])
def test_sqlite_faults_release_actual_objects(tmp_path, monkeypatch, fault, close_fault, expected, create):
    target = tmp_path / "owned.sqlite"
    if not create:
        target.touch()
    real_connect = sqlite3.connect
    connections, cursors, sources, events = [], [], [], []

    class Cursor:
        def __init__(self, cursor):
            self.real = cursor
            self.query = 0

        def execute(self, sql):
            self.query += 1
            events.append(sql)
            if fault == f"execute{self.query}":
                raise sqlite3.OperationalError("private-sentinel")
            if fault == "interrupt":
                raise KeyboardInterrupt
            if fault == "unexpected":
                raise RuntimeError("private-sentinel")
            return self.real.execute(sql)

        def fetchone(self):
            if fault == f"fetch{self.query}":
                raise sqlite3.DatabaseError("private-sentinel")
            if fault == "row_none":
                return None
            if fault == "row_wrong":
                return (0,)
            return self.real.fetchone()

        def close(self):
            events.append("cursor.close")
            self.real.close()
            if close_fault in ("cursor", "both"):
                raise sqlite3.Error("private-sentinel")

    class Connection:
        def __init__(self, connection):
            self.real = connection

        def cursor(self):
            if fault == "cursor":
                raise sqlite3.Error("private-sentinel")
            cursor = self.real.cursor()
            cursors.append(cursor)
            return Cursor(cursor)

        def close(self):
            events.append("connection.close")
            self.real.close()
            if close_fault in ("connection", "both"):
                raise sqlite3.Error("private-sentinel")

    def header_open(path, mode):
        source = builtins.open(path, mode)  # noqa: SIM115 - production owns and must close this resource
        sources.append(source)
        return source

    def connect(database, **kwargs):
        assert sources and all(source.closed for source in sources)
        assert database == target.as_uri() + "?mode=ro"
        assert kwargs == {"uri": True, "timeout": 1.0}
        if fault == "connect":
            raise sqlite3.OperationalError("private-sentinel")
        connection = real_connect(database, **kwargs)
        connections.append(connection)
        return Connection(connection)

    monkeypatch.setattr(db, "open", header_open, raising=False)
    monkeypatch.setattr(db.sqlite3, "connect", connect)
    if expected:
        error = expect_error(expected, db.check_database, str(target), create=create)
        assert error.created is create
    else:
        assert db.check_database(str(target), create=create).created is create
        assert events[:2] == ["SELECT 1", "SELECT name FROM sqlite_schema LIMIT 1"]
    assert target.read_bytes() == b""
    assert all(source.closed for source in sources)
    for cursor in cursors:
        with pytest.raises(sqlite3.ProgrammingError):
            cursor.execute("SELECT 1")
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
    if cursors:
        assert events[-2:] == ["cursor.close", "connection.close"]
    elif connections:
        assert events[-1] == "connection.close"


def test_successful_create_closes_real_descriptor_before_header(tmp_path, monkeypatch):
    target = tmp_path / "owned.sqlite"
    real_open = os.open
    descriptors = []

    def capture_open(path, flags, mode):
        descriptor = real_open(path, flags, mode)
        descriptors.append(descriptor)
        return descriptor

    def header_open(path, mode):
        with pytest.raises(OSError):
            os.fstat(descriptors[0])
        return builtins.open(path, mode)

    monkeypatch.setattr(db.os, "open", capture_open)
    monkeypatch.setattr(db, "open", header_open, raising=False)
    assert db.check_database(str(target), create=True).created
    with pytest.raises(OSError):
        os.fstat(descriptors[0])
    assert target.read_bytes() == b""


def test_parent_file_is_not_a_directory(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    parent.write_bytes(b"owned-sentinel")
    monkeypatch.setattr(db.sqlite3, "connect", no_connect)
    expect_error("invalid_target", db.check_database, str(parent / "child"), create=True)
    assert parent.read_bytes() == b"owned-sentinel"
