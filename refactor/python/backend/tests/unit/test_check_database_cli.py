"""Real subprocess CLI contracts; all database paths belong to pytest tmp_path."""

import hashlib
import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
FIELDS = {"engine", "status", "mode", "target", "created", "checks", "code", "message"}
CONTRACT = {
    "ok": (0, "Connection check passed; business schema not verified."),
    "invalid_arguments": (2, "Use --path PATH with optional --create and --json; see --help."),
    "invalid_target": (3, "Use an explicit standalone local regular file with an existing parent directory."),
    "target_not_found": (
        3,
        (
            "The explicit target or its parent does not exist; create the parent yourself "
            "and use --create only for a new file."
        ),
    ),
    "target_exists": (3, "Creation refused because the target already exists; choose a new file."),
    "access_failed": (4, "Cannot access the explicit target; check permissions and availability."),
    "database_check_failed": (4, "Read-only SQLite checks failed; use a valid standalone SQLite file."),
    "close_failed": (5, "Resource release failed; the connection check is not successful."),
    "internal_error": (6, "Unexpected local check failure; no successful check is reported."),
    "interrupted": (130, "Connection check interrupted; no successful check is reported."),
}


def run_cli(cwd, *arguments, script=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND)
    # A trap value, never an actual user database. Missing --path must not fall back to it.
    env["DATABASE_URL"] = "sqlite:///PRIVATE_TOKEN_ENV_DO_NOT_READ"
    command = [sys.executable, "-m", "app.cli.check_database"]
    if script is not None:
        command = [sys.executable, "-c", script]
    return subprocess.run(
        command + list(arguments), cwd=cwd, env=env, text=True, capture_output=True, timeout=15, check=False
    )


def assert_result(process, code, *, mode="read_only", created=False):
    exit_code, message = CONTRACT[code]
    assert process.returncode == exit_code
    success = code == "ok"
    assert (process.stderr if success else process.stdout) == ""
    output = process.stdout if success else process.stderr
    assert len(output.splitlines()) == 1
    payload = json.loads(output)
    assert set(payload) == FIELDS
    assert payload["engine"] == "sqlite"
    assert payload["status"] == ("ok" if success else "error")
    assert payload["mode"] == mode
    assert payload["created"] is created
    assert payload["checks"] == (["select_1", "schema_read"] if success else [])
    assert payload["code"] == code
    assert payload["message"] == message
    assert payload["target"] is None or re.fullmatch(r"local-file:[0-9a-f]{12}", payload["target"])
    assert "Traceback" not in output and "PRIVATE_TOKEN" not in output
    return payload


def test_create_default_and_refuse_overwrite_subprocess(tmp_path):
    target = tmp_path / "PRIVATE_TOKEN 新 ?#&mode=rw.sqlite"
    result = assert_result(
        run_cli(tmp_path, "--path", target.name, "--create", "--json"), "ok", mode="create", created=True
    )
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert target.read_bytes() == b""
    assert_result(run_cli(tmp_path, "--path", target.name, "--json"), "ok")
    assert_result(
        run_cli(tmp_path, "--path", target.name, "--create", "--json"), "target_exists", mode="create"
    )
    assert result["target"] == "local-file:" + hashlib.sha256(str(target).encode()).hexdigest()[:12]
    assert list(tmp_path.iterdir()) == [target] and target.read_bytes() == b""


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--path"],
        ["--pa", "PRIVATE_TOKEN"],
        ["--path", "x", "--sql", "PRIVATE_TOKEN"],
        ["PRIVATE_TOKEN"],
        ["--path", "x", "--create=PRIVATE_TOKEN"],
        ["--json=PRIVATE_TOKEN"],
        ["--path", "x", "--unknown=/PRIVATE_TOKEN/secret"],
    ],
)
def test_argument_errors_are_safe_and_never_fallback(tmp_path, arguments):
    assert_result(run_cli(tmp_path, *arguments, "--json"), "invalid_arguments", mode=None)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "raw",
    ["", " \t", ":memory:", "file:PRIVATE_TOKEN?mode=rw", "postgresql://user:PRIVATE_TOKEN@localhost/db"],
)
def test_illegal_local_target_subprocess(tmp_path, raw):
    payload = assert_result(run_cli(tmp_path, "--path", raw, "--json"), "invalid_target")
    assert payload["target"] is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("create", [False, True])
def test_missing_parent_and_target_subprocess(tmp_path, create):
    options = ["--create"] if create else []
    assert_result(
        run_cli(tmp_path, "--path", "absent/PRIVATE_TOKEN.sqlite", *options, "--json"),
        "target_not_found",
        mode="create" if create else "read_only",
    )
    assert list(tmp_path.iterdir()) == []
    if not create:
        assert_result(run_cli(tmp_path, "--path", "PRIVATE_TOKEN.sqlite", "--json"), "target_not_found")


@pytest.mark.parametrize("kind", ["directory", "link", "bad", "wal", "-wal", "-shm", "-journal"])
def test_real_file_rejections_subprocess(tmp_path, kind):
    target = tmp_path / "PRIVATE_TOKEN.sqlite"
    code = "invalid_target"
    if kind == "directory":
        target.mkdir()
    elif kind == "link":
        target.symlink_to(tmp_path / "not-present")
    elif kind == "bad":
        target.write_bytes(b"not a sqlite file")
        code = "database_check_failed"
    elif kind == "wal":
        connection = sqlite3.connect(target)
        try:
            assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
            connection.execute("CREATE TABLE owned_sentinel (value TEXT)")
            connection.commit()
        finally:
            connection.close()
        assert list(tmp_path.iterdir()) == [target]
        assert target.read_bytes()[18:20] == b"\x02\x02"
    else:
        target.touch()
        (tmp_path / (target.name + kind)).write_bytes(b"owned-sidecar")
    before = {
        p.name: (
            (p.lstat().st_mode, p.lstat().st_ino, p.lstat().st_mtime_ns, p.lstat().st_size),
            p.read_bytes() if p.is_file() and not p.is_symlink() else None,
        )
        for p in tmp_path.iterdir()
    }
    assert_result(run_cli(tmp_path, "--path", str(target), "--json"), code)
    after = {
        p.name: (
            (p.lstat().st_mode, p.lstat().st_ino, p.lstat().st_mtime_ns, p.lstat().st_size),
            p.read_bytes() if p.is_file() and not p.is_symlink() else None,
        )
        for p in tmp_path.iterdir()
    }
    assert before == after


def test_cwd_is_call_time_not_source_directory(tmp_path):
    targets = []
    for name in ("a", "b"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "same.sqlite").touch()
        result = assert_result(run_cli(directory, "--path", "same.sqlite", "--json"), "ok")
        targets.append(result["target"])
        absolute = assert_result(run_cli(tmp_path, "--path", str(directory / "same.sqlite"), "--json"), "ok")
        assert absolute["target"] == result["target"]
    assert targets[0] != targets[1]


def test_text_and_static_help_are_safe(tmp_path):
    target = tmp_path / "PRIVATE_TOKEN.sqlite"
    target.touch()
    process = run_cli(tmp_path, "--path", str(target))
    assert process.returncode == 0 and process.stderr == ""
    assert len(process.stdout.splitlines()) == 1 and 'code="ok"' in process.stdout
    assert "PRIVATE_TOKEN" not in process.stdout and str(tmp_path) not in process.stdout
    failure = run_cli(tmp_path, "--unknown=PRIVATE_TOKEN")
    assert failure.returncode == 2 and failure.stdout == ""
    assert "PRIVATE_TOKEN" not in failure.stderr and "Traceback" not in failure.stderr
    assert len(failure.stderr.splitlines()) == 1
    for help_flag in ("--help", "-h"):
        help_result = run_cli(tmp_path, help_flag, "--json")
        assert help_result.returncode == 0 and help_result.stderr == ""
        assert "--path PATH" in help_result.stdout and "--create" in help_result.stdout
        assert not help_result.stdout.startswith("{")


@pytest.mark.parametrize(
    "fault,code",
    [
        ("access", "access_failed"),
        ("close", "close_failed"),
        ("unexpected", "internal_error"),
        ("interrupt", "interrupted"),
    ],
)
def test_fault_exit_codes_and_redaction_in_independent_process(tmp_path, fault, code):
    target = tmp_path / "PRIVATE_TOKEN.sqlite"
    script = """
import os
from app import database_check as db
from app.cli.check_database import main
fault = __import__('sys').argv[1]
if fault == 'access':
    def fail(*args): raise PermissionError('PRIVATE_TOKEN hidden path')
    db.os.open = fail
elif fault == 'close':
    real_close = os.close
    def fail(fd):
        real_close(fd)
        raise OSError('PRIVATE_TOKEN hidden path')
    db.os.close = fail
else:
    def fail(*args, **kwargs):
        if fault == 'interrupt': raise KeyboardInterrupt
        raise RuntimeError('PRIVATE_TOKEN hidden path')
    db.sqlite3.connect = fail
raise SystemExit(main(__import__('sys').argv[2:]))
"""
    payload = assert_result(
        run_cli(tmp_path, fault, "--path", str(target), "--create", "--json", script=script),
        code,
        mode="create",
        created=fault != "access",
    )
    assert payload["target"] is not None
    assert target.exists() is (fault != "access")
    if target.exists():
        assert target.read_bytes() == b""
