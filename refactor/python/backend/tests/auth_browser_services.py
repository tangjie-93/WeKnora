"""Owned browser-test services. Run explicitly; never touches existing listeners."""

import json
import os
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

from app.core.migrations import initialize_auth_database

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "artifacts/weknora-product-auth/04-e2e"
BACKEND = ROOT / "python/backend"
FRONTEND = ROOT / "python/frontend"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    owned = []
    stop = [False]
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__(0, True))
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__(0, True))
    with tempfile.TemporaryDirectory(prefix="weknora-task04-") as temporary:
        work = Path(temporary).resolve()
        database = work / "browser.sqlite3"
        initialize_auth_database(database)
        backend_port, frontend_port = free_port(), free_port()
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in ("JWT_SECRET", "WEKNORA_AUTH_DB_PATH")
        }
        env.update(
            WEKNORA_AUTH_DB_PATH=str(database),
            FRONTEND_PORT=str(frontend_port),
            BACKEND_PROXY_TARGET=f"http://127.0.0.1:{backend_port}",
        )
        command = [
            str(BACKEND / ".venv/bin/python"),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(backend_port),
            "--no-proxy-headers",
            "--no-access-log",
        ]

        def start_backend():
            child = subprocess.Popen(
                command, cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            owned.append(child)
            with httpx.Client(trust_env=False, timeout=0.5) as client:
                for _ in range(200):
                    try:
                        if client.get(f"http://127.0.0.1:{backend_port}/health").status_code == 200:
                            return child
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.05)
            raise RuntimeError("Owned backend readiness failed")

        try:
            backend = start_backend()
            frontend = subprocess.Popen(
                [
                    "node",
                    str(FRONTEND / "node_modules/vite/bin/vite.js"),
                    str(FRONTEND),
                    "--config",
                    str(FRONTEND / "vite.config.ts"),
                ],
                cwd=work,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            owned.append(frontend)
            info = {
                "supervisor_pid": os.getpid(),
                "backend_pid": backend.pid,
                "frontend_pid": frontend.pid,
                "backend": f"http://127.0.0.1:{backend_port}",
                "frontend": f"http://127.0.0.1:{frontend_port}",
                "restart_count": 0,
            }
            (EVIDENCE / "owned-services.json").write_text(json.dumps(info))
            while not stop[0]:
                restart = EVIDENCE / "restart-request"
                if restart.exists():
                    restart.unlink()
                    backend.terminate()
                    backend.wait(timeout=5)
                    backend = start_backend()
                    info.update(backend_pid=backend.pid, restart_count=info["restart_count"] + 1)
                    (EVIDENCE / "owned-services.json").write_text(json.dumps(info))
                time.sleep(0.1)
        finally:
            for child in reversed(owned):
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)


if __name__ == "__main__":
    main()
