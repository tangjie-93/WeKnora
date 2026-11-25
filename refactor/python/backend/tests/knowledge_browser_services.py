"""Owned temporary KB browser services; private envDir, no user env files or existing ports."""

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
BACKEND = ROOT / "python/backend"
FRONTEND = ROOT / "python/frontend"
EVIDENCE = ROOT / "artifacts/weknora-knowledge-base-management/04-e2e"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    stop = [False]
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__(0, True))
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__(0, True))
    owned = []
    with tempfile.TemporaryDirectory(prefix="weknora-kb-independent-") as temporary:
        work = Path(temporary).resolve()
        database = work / "browser.sqlite3"
        initialize_auth_database(database)
        backend_port, frontend_port = free_port(), free_port()
        env = {key: value for key, value in os.environ.items()
               if key not in ("JWT_SECRET", "WEKNORA_AUTH_DB_PATH", "STORAGE_ALLOW_LIST")}
        env.update(WEKNORA_AUTH_DB_PATH=str(database), STORAGE_ALLOW_LIST="s3,local")
        backend_command = [str(BACKEND / ".venv/bin/python"), "-m", "uvicorn", "app.main:app",
                           "--host", "127.0.0.1", "--port", str(backend_port),
                           "--no-proxy-headers", "--no-access-log"]
        # Import existing pure plugins only, never the user Vite config that calls loadEnv(cwd).
        config = work / "vite.config.mjs"
        config.write_text(
            f"import vue from {json.dumps(str(FRONTEND / 'node_modules/@vitejs/plugin-vue/dist/index.mjs'))};\n"
            f"import tailwind from {json.dumps(str(FRONTEND / 'node_modules/@tailwindcss/vite/dist/index.mjs'))};\n"
            f"export default {{root:{json.dumps(str(FRONTEND))},envDir:{json.dumps(str(work))},"
            f"plugins:[vue(),tailwind()],build:{{outDir:{json.dumps(str(work / 'build'))}}},"
            f"server:{{host:'127.0.0.1',port:{frontend_port},strictPort:true,proxy:{{"
            f"'^/api/v1(?:/|$)':{{target:'http://127.0.0.1:{backend_port}',changeOrigin:true}},"
            f"'^/health$':{{target:'http://127.0.0.1:{backend_port}',changeOrigin:true}}}}}}}};\n"
        )
        frontend_command = ["node", str(FRONTEND / "node_modules/vite/bin/vite.js"), "--config", str(config)]
        info = {"supervisor_pid": os.getpid(), "backend": f"http://127.0.0.1:{backend_port}",
                "frontend": f"http://127.0.0.1:{frontend_port}", "restart_count": 0,
                "backend_command": backend_command, "frontend_command": frontend_command,
                "private_env_config": str(config), "status": "starting"}
        record = EVIDENCE / "owned-services.json"
        logs = []

        def start(command, name, url):
            log = (EVIDENCE / "logs" / f"{name}-service.log").open("a")
            logs.append(log)
            child = subprocess.Popen(command, cwd=BACKEND if name == "backend" else work,
                                     env=env, stdout=log, stderr=log)
            owned.append(child)
            with httpx.Client(trust_env=False, timeout=0.5) as client:
                for _ in range(200):
                    if child.poll() is not None:
                        raise RuntimeError(f"Owned {name} process exited")
                    try:
                        if client.get(url).status_code == 200:
                            return child
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.05)
            raise RuntimeError(f"Owned {name} readiness failed")

        try:
            backend = start(backend_command, "backend", info["backend"] + "/health")
            frontend = start(frontend_command, "frontend", info["frontend"])
            info.update(backend_pid=backend.pid, frontend_pid=frontend.pid, status="running")
            record.write_text(json.dumps(info, indent=2))
            while not stop[0]:
                restart = EVIDENCE / "restart-request"
                if restart.exists():
                    restart.unlink()
                    backend.terminate()
                    backend.wait(timeout=5)
                    backend = start(backend_command, "backend", info["backend"] + "/health")
                    info.update(backend_pid=backend.pid, restart_count=info["restart_count"] + 1)
                    record.write_text(json.dumps(info, indent=2))
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
            for log in logs:
                log.close()
            info.update(status="stopped", private_database_and_secret="deleted by TemporaryDirectory")
            record.write_text(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
