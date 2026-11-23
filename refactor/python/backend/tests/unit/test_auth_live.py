"""Actual Uvicorn and Vite transports; TestClient cannot prove proxy trust."""

import json
import os
import socket
import subprocess
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from app.core.migrations import initialize_auth_database

BACKEND = Path(__file__).resolve().parents[2]
FRONTEND = BACKEND.parent / "frontend"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def running(command, cwd, env, probe):
    # Only terminate the exact child this fixture creates, never a discovered listener.
    process = subprocess.Popen(
        command, cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        deadline = time.monotonic() + 15
        with httpx.Client(timeout=0.5, trust_env=False) as client:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail("Owned service exited before readiness")
                try:
                    if client.get(probe).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.05)
            else:
                pytest.fail("Owned service readiness timed out")
        yield process
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture
def live(tmp_path):
    path = tmp_path.resolve() / "live.sqlite3"
    initialize_auth_database(path)
    env = {
        key: value for key, value in os.environ.items() if key not in ("JWT_SECRET", "WEKNORA_AUTH_DB_PATH")
    }
    env["WEKNORA_AUTH_DB_PATH"] = str(path)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    command = [
        str(BACKEND / ".venv/bin/python"),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--no-proxy-headers",
        "--no-access-log",
    ]
    with (
        running(command, BACKEND, env, base + "/health"),
        httpx.Client(base_url=base, trust_env=False) as client,
    ):
        yield client


def test_actual_uvicorn_changed_xff_cannot_escape_peer_rate_bucket(live):
    statuses = []
    for index in range(12):
        response = live.post(
            "/api/v1/auth/login",
            json={"email": "socket-test@example.com", "password": "test-only-8"},
            headers={"X-Forwarded-For": f"192.0.2.{index + 1}", "Forwarded": f"for=192.0.2.{index + 1}"},
        )
        statuses.append(response.status_code)
        if index >= 10:
            assert response.json()["error"]["code"] == 1006
            assert response.headers["retry-after"] == "60"
    assert statuses == [401] * 10 + [429] * 2


@pytest.mark.parametrize("body", [b'{"email":"\xff"}', b"[" * 4000 + b"]" * 4000, b"{"])
def test_socket_real_encoding_natural_depth_and_malformed_json(live, body):
    for operation in ("register", "login", "refresh"):
        response = live.post(
            f"/api/v1/auth/{operation}", content=body, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400
        assert response.json() == {
            "success": False,
            "error": {"code": 1010, "message": "Invalid request parameters", "details": None},
        }
        assert response.headers["cache-control"] == "no-store"
    assert live.get("/api/v1/auth/unknown").json() == {"detail": "Not Found"}
    response = live.post("/health")
    assert response.status_code == 405 and response.headers["allow"] == "GET"
    response = live.get("/health")
    assert (
        response.json() == {"status": "ok"}
        and response.headers["x-weknora-implementation"] == "python-fastapi"
    )


def test_actual_vite_strips_forwarding_headers_on_both_proxies(tmp_path):
    captured = []

    class Capture(BaseHTTPRequestHandler):
        def do_GET(self):
            captured.append((self.path, {key.lower(): value for key, value in self.headers.items()}))
            body = json.dumps({"status": "ok"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Capture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "FRONTEND_PORT": str(port),
        "BACKEND_PROXY_TARGET": f"http://127.0.0.1:{server.server_port}",
    }
    command = [
        "node",
        str(FRONTEND / "node_modules/vite/bin/vite.js"),
        str(FRONTEND),
        "--config",
        str(FRONTEND / "vite.config.ts"),
    ]
    forged = {
        "Forwarded": "for=192.0.2.1",
        "X-Forwarded-For": "192.0.2.2",
        "X-Forwarded-Host": "forged.test",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Arbitrary": "untrusted",
        "X-Real-IP": "192.0.2.3",
        "X-Client-IP": "192.0.2.4",
        "Client-IP": "192.0.2.5",
        "True-Client-IP": "192.0.2.6",
        "CF-Connecting-IP": "192.0.2.7",
        "X-Test-Sentinel": "preserved",
    }
    try:
        # Isolated cwd prevents Vite loadEnv from consulting any user .env file.
        with running(command, tmp_path, env, base), httpx.Client(base_url=base, trust_env=False) as client:
            for path in ("/health", "/api/v1/auth/me"):
                assert client.get(path, headers=forged).status_code == 200
            assert [path for path, _ in captured] == ["/health", "/api/v1/auth/me"]
            for _, headers in captured:
                assert headers["x-test-sentinel"] == "preserved"
                assert not (set(headers) & {key.lower() for key in forged if key != "X-Test-Sentinel"})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
