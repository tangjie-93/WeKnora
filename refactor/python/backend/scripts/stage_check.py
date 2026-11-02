"""阶段验收脚本：真实启动服务 + 全链路功能验证。

每个阶段结束时执行：
    .\\.venv\\Scripts\\python.exe scripts\\stage_check.py --stage phase1

执行内容（任一失败则退出码为 1）：
  1. ruff 静态检查
  2. pytest 单元/接口测试
  3. 用独立 SQLite 库真实启动 uvicorn（走迁移，不建内存表）
  4. 通过 HTTP 覆盖该阶段全部已实现接口（含异常分支、权限分支）
  5. 直接读库校验数据落盘
  6. 生成 tests/contract/stage_report.md

新增阶段时，在 STAGES 里追加一个场景函数即可。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Self

import httpx

PYTHON_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PYTHON_DIR / "data"
REPORT_DIR = PYTHON_DIR / "tests" / "contract"
SERVER_LOG = DATA_DIR / "stage_server.log"
TEMPLATE_DB = DATA_DIR / "schema_template.db"

JWT_SECRET = "stage-check-secret-32-bytes-minimum"
FAKE_BASE_URL = ""  # phase2-5 场景运行时由 main() 注入本地假 OpenAI 的地址

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class Result:
    key: str
    name: str
    ok: bool
    detail: str = ""


class Scenario:
    """收集步骤结果；单步失败不中断，便于一次看到全部问题。"""

    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self.results: list[Result] = []
        self.state: dict[str, object] = {}

    def step(self, key: str, name: str, fn) -> None:
        try:
            detail = fn()
            self.results.append(Result(key, name, True, str(detail or "")))
            print(f"  [PASS] {key}")
        except Exception as exc:  # noqa: BLE001 - 验收脚本需要记录所有失败
            detail = f"{type(exc).__name__}: {exc}"
            self.results.append(Result(key, name, False, detail))
            print(f"  [FAIL] {key} -> {detail}")


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_status(response: httpx.Response, code: int) -> None:
    if response.status_code != code:
        raise AssertionError(f"expected {code}, got {response.status_code}: {response.text[:300]}")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def ensure_template_db() -> None:
    """预先生成一份已迁移的空库；各阶段直接复制，避免每次启动重跑全部迁移。"""
    if TEMPLATE_DB.exists():
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    code = (
        "import asyncio\n"
        "from app.core.config import get_settings\n"
        "from app.core.migrations import run_migrations\n"
        "asyncio.run(run_migrations(get_settings()))\n"
    )
    env = os.environ.copy()
    env.update(
        {
            "DB_DRIVER": "sqlite",
            "DB_PATH": str(TEMPLATE_DB),
            "AUTO_MIGRATE": "false",
            "JWT_SECRET": JWT_SECRET,
        }
    )
    print("preparing schema template db ...")
    subprocess.run(
        [sys.executable, "-c", code], cwd=PYTHON_DIR, env=env, check=True
    )


def run_static_checks(env_for_pytest: dict[str, str], stage: str) -> list[Result]:
    results: list[Result] = []

    required = PHASE_TESTS.get(stage, [])
    missing = [item for item in required if not (PYTHON_DIR / item).exists()]
    results.append(
        Result(
            "phase_tests",
            f"{stage} 阶段测试用例已编写",
            not missing,
            "、".join(required) if not missing else f"缺少：{'、'.join(missing)}",
        )
    )
    print(f"{'[PASS]' if not missing else '[FAIL]'} phase tests: {required}")

    lint = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "app", "tests", "scripts"],
        cwd=PYTHON_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    results.append(
        Result(
            "lint",
            "ruff 静态检查",
            lint.returncode == 0,
            "All checks passed" if lint.returncode == 0 else lint.stdout.strip()[-500:],
        )
    )
    print(f"{'[PASS]' if lint.returncode == 0 else '[FAIL]'} lint")

    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=PYTHON_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env_for_pytest,
        check=False,
    )
    tail = (tests.stdout or "").strip().splitlines()[-1:] or ["no output"]
    results.append(
        Result("pytest", "pytest 自动化测试", tests.returncode == 0, tail[0])
    )
    print(f"{'[PASS]' if tests.returncode == 0 else '[FAIL]'} pytest: {tail[0]}")
    return results


class Server:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.port = free_port()
        self.proc: subprocess.Popen | None = None
        self.log_handle = None

    def __enter__(self) -> Self:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        ensure_template_db()
        if self.db_path.exists():
            self.db_path.unlink()
        shutil.copy2(TEMPLATE_DB, self.db_path)
        self.log_handle = SERVER_LOG.open("w", encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "DB_DRIVER": "sqlite",
                "DB_PATH": str(self.db_path),
                "AUTO_MIGRATE": "true",
                "JWT_SECRET": JWT_SECRET,
                "LOG_LEVEL": "info",
                "PYTHONUNBUFFERED": "1",
            }
        )
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            cwd=PYTHON_DIR,
            env=env,
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
        )
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._wait_ready()
        print(f"server started on {self.base_url} (db={self.db_path.name})")
        return self

    def _wait_ready(self, timeout: float = 180.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc and self.proc.poll() is not None:
                raise RuntimeError(f"server exited early:\n{self.log_tail()}")
            try:
                if httpx.get(f"{self.base_url}/health", timeout=1.0).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.3)
        raise RuntimeError(f"server not ready in {timeout}s:\n{self.log_tail()}")

    def log_tail(self, lines: int = 40) -> str:
        if not SERVER_LOG.exists():
            return "<no log>"
        return "\n".join(SERVER_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])

    def __exit__(self, *_: object) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.log_handle:
            self.log_handle.close()


class FakeOpenAI:
    """本地 OpenAI 兼容假服务（`scripts/fake_openai.py`），用于离线验证模型链路。"""

    def __init__(self) -> None:
        self.port = free_port()
        self.proc: subprocess.Popen | None = None
        self.log_handle = None
        self.base_url = f"http://127.0.0.1:{self.port}/v1"

    def __enter__(self) -> Self:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        log_path = DATA_DIR / "fake_openai.log"
        self.log_handle = log_path.open("w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [
                sys.executable,
                str(PYTHON_DIR / "scripts" / "fake_openai.py"),
                "--port",
                str(self.port),
            ],
            cwd=PYTHON_DIR,
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"fake openai exited early:\n{self._log_tail()}")
            try:
                if httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=1.0).status_code == 200:
                    print(f"fake openai started on {self.base_url}")
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise RuntimeError(f"fake openai not ready:\n{self._log_tail()}")

    def _log_tail(self, lines: int = 40) -> str:
        log_path = DATA_DIR / "fake_openai.log"
        if not log_path.exists():
            return "<no log>"
        content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])

    def __exit__(self, *_: object) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.log_handle:
            self.log_handle.close()


# --------------------------------------------------------------------------
# 场景公共辅助
# --------------------------------------------------------------------------


def login(client: httpx.Client, email: str = "alice@example.com") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Abcdef12"}
    )
    expect_status(response, 200)
    return {"Authorization": f"Bearer {response.json()['token']}"}


def ensure_alice(client: httpx.Client) -> dict[str, str]:
    """每个阶段使用独立数据库，因此先注册（或复用）alice 再登录。"""
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": "Abcdef12"},
    )
    if response.status_code not in (201, 400):
        raise AssertionError(f"register failed: {response.status_code}: {response.text[:300]}")
    return login(client)


def ensure_bob(client: httpx.Client) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "email": "bob@example.com", "password": "Abcdef12"},
    )
    if response.status_code not in (201, 400):
        raise AssertionError(f"register failed: {response.status_code}: {response.text[:300]}")
    return login(client, "bob@example.com")


def create_models(
    client: httpx.Client, headers: dict[str, str], dimension: int = 64
) -> tuple[dict, dict]:
    """创建 chat + embedding 两个指向假服务的模型，返回 (chat, embedding)。"""
    chat = client.post(
        "/api/v1/models",
        headers=headers,
        json={
            "name": "fake-chat",
            "display_name": "假聊天模型",
            "type": "chat",
            "is_default": True,
            "parameters": {"base_url": FAKE_BASE_URL, "api_key": "test-key"},
        },
    )
    expect_status(chat, 201)
    embedding = client.post(
        "/api/v1/models",
        headers=headers,
        json={
            "name": "fake-embedding",
            "display_name": "假向量模型",
            "type": "embedding",
            "is_default": True,
            "parameters": {
                "base_url": FAKE_BASE_URL,
                "api_key": "test-key",
                "embedding_parameters": {"dimension": dimension},
            },
        },
    )
    expect_status(embedding, 201)
    return chat.json()["data"], embedding.json()["data"]


def create_kb(client: httpx.Client, headers: dict[str, str], name: str = "产品手册") -> dict:
    response = client.post(
        "/api/v1/knowledge-bases",
        headers=headers,
        json={
            "name": name,
            "description": "阶段验收知识库",
            "chunking_config": {"chunk_size": 120, "chunk_overlap": 20},
        },
    )
    expect_status(response, 201)
    return response.json()["data"]


def upload_text(client: httpx.Client, headers: dict[str, str], kb_id: str) -> dict:
    text = (
        "WeKnora 是一个企业级知识管理平台，支持文档解析、向量检索与关键词检索。\n\n"
        "Nebula 模块负责知识入库：上传文档后会自动解析、分块并写入向量索引。\n\n"
        "Nebula 默认端口是 8080，管理后台通过 /swagger/index.html 访问。\n\n"
        "部署时需要 PostgreSQL 存储业务数据，Redis 用于缓存与任务队列。\n\n"
        "问答阶段会先做混合检索，再结合大模型生成带引用的答案。"
    ).encode()
    response = client.post(
        f"/api/v1/knowledge-bases/{kb_id}/knowledge/file",
        headers=headers,
        files={"file": ("guide.txt", text, "text/plain")},
    )
    expect_status(response, 201)
    return response.json()["data"]



# --------------------------------------------------------------------------
# 阶段场景
# --------------------------------------------------------------------------


def scenario_phase0(client: httpx.Client) -> Scenario:
    sc = Scenario(client)

    def health() -> str:
        response = client.get("/health")
        expect_status(response, 200)
        expect(response.json() == {"status": "ok"}, "health body mismatch")
        return response.text

    def openapi() -> str:
        response = client.get("/swagger/doc.json")
        expect_status(response, 200)
        expect("/api/v1/auth/login" in response.text, "openapi missing auth route")
        return "openapi ok"

    def migrations() -> str:
        count = sqlite3.connect(DATA_DIR / "stage_phase0.db").execute(
            "select count(1) from schema_migrations"
        ).fetchone()[0]
        expect(count > 0, "no migrations applied")
        return f"{count} migrations"

    sc.step("health", "健康检查 /health", health)
    sc.step("openapi", "OpenAPI 文档可访问", openapi)
    sc.step("migrate", "迁移已执行", migrations)
    return sc


def scenario_phase1(client: httpx.Client) -> Scenario:
    sc = Scenario(client)
    state = sc.state

    def auth_config() -> str:
        response = client.get("/api/v1/auth/config")
        expect_status(response, 200)
        body = response.json()
        expect(body["success"] is True, "success flag missing")
        expect(bool(body["registration_mode"]), "registration_mode empty")
        return body["registration_mode"]

    def register_alice() -> str:
        response = client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "email": "alice@example.com", "password": "Abcdef12"},
        )
        expect_status(response, 201)
        body = response.json()
        expect(body["user"]["email"] == "alice@example.com", "email mismatch")
        expect(body["user"]["tenant_id"] > 0, "personal tenant not created")
        state["alice_tenant"] = body["user"]["tenant_id"]
        return f"user={body['user']['id']} tenant={body['user']['tenant_id']}"

    def register_duplicate() -> str:
        response = client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "email": "alice@example.com", "password": "Abcdef12"},
        )
        expect_status(response, 400)
        expect(response.json()["success"] is False, "should fail")
        return response.json()["error"]["message"]

    def register_weak_password() -> str:
        response = client.post(
            "/api/v1/auth/register",
            json={"username": "weak", "email": "weak@example.com", "password": "short1"},
        )
        expect_status(response, 400)
        return response.json()["error"]["message"]

    def login_alice() -> str:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "Abcdef12"},
        )
        expect_status(response, 200)
        body = response.json()
        expect(body["token"], "access token missing")
        expect(body["refresh_token"], "refresh token missing")
        expect(body["active_tenant"]["name"] == "alice", "active tenant mismatch")
        expect(body["memberships"][0]["role"] == "owner", "role should be owner")
        state["alice_token"] = body["token"]
        state["alice_refresh"] = body["refresh_token"]
        state["alice_headers"] = {"Authorization": f"Bearer {body['token']}"}
        state["alice_tenant_id"] = body["active_tenant"]["id"]
        return f"tenant={body['active_tenant']['id']} role=owner"

    def login_wrong_password() -> str:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "WrongPass9"},
        )
        expect_status(response, 401)
        expect(response.json()["success"] is False, "should fail")
        return response.json()["error"]["message"]

    def login_unknown_user() -> str:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "Abcdef12"},
        )
        expect_status(response, 401)
        return "401 as expected"

    def validate_token() -> str:
        response = client.get("/api/v1/auth/validate", headers=state["alice_headers"])
        expect_status(response, 200)
        expect(response.json()["valid"] is True, "token should be valid")
        return "valid=true"

    def me() -> str:
        response = client.get("/api/v1/auth/me", headers=state["alice_headers"])
        expect_status(response, 200)
        data = response.json()["data"]
        expect(data["user"]["username"] == "alice", "me user mismatch")
        expect(data["tenant"]["id"] == state["alice_tenant_id"], "me tenant mismatch")
        expect(data["memberships"][0]["role"] == "owner", "me role mismatch")
        expect(data["tenant_required"] is False, "tenant_required should be false")
        return f"tenant={data['tenant']['id']}"

    def tenant_info() -> str:
        response = client.get("/api/v1/auth/tenant", headers=state["alice_headers"])
        expect_status(response, 200)
        expect(response.json()["data"]["name"] == "alice", "tenant name mismatch")
        return response.json()["data"]["name"]

    def refresh_token() -> str:
        response = client.post(
            "/api/v1/auth/refresh", json={"refreshToken": state["alice_refresh"]}
        )
        expect_status(response, 200)
        body = response.json()
        expect(body["access_token"], "new access token missing")
        expect(body["refresh_token"], "new refresh token missing")
        # 与 Go 端一致：claims 无 jti，同一秒内签发的令牌字符串可能相同，
        # 因此以「新令牌可用 + 旧刷新令牌已吊销」作为轮换判据。
        validate = client.get(
            "/api/v1/auth/validate",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        expect_status(validate, 200)
        state["alice_headers"] = {"Authorization": f"Bearer {body['access_token']}"}
        state["alice_refresh"] = body["refresh_token"]
        return "new access token valid"

    def refresh_again() -> str:
        response = client.post(
            "/api/v1/auth/refresh", json={"refreshToken": state["alice_refresh"]}
        )
        expect_status(response, 200)
        state["alice_refresh"] = response.json()["refresh_token"]
        return "second refresh ok"

    def refresh_invalid() -> str:
        response = client.post("/api/v1/auth/refresh", json={"refreshToken": "not-a-token"})
        expect_status(response, 401)
        return "401 as expected"

    def register_bob() -> str:
        response = client.post(
            "/api/v1/auth/register",
            json={"username": "bob", "email": "bob@example.com", "password": "Abcdef12"},
        )
        expect_status(response, 201)
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "bob@example.com", "password": "Abcdef12"},
        )
        expect_status(login, 200)
        state["bob_headers"] = {"Authorization": f"Bearer {login.json()['token']}"}
        return f"bob tenant={login.json()['active_tenant']['id']}"

    def cross_tenant_forbidden() -> str:
        headers = dict(state["bob_headers"])
        headers["X-Tenant-ID"] = str(state["alice_tenant_id"])
        response = client.get("/api/v1/auth/me", headers=headers)
        expect_status(response, 403)
        return "403 as expected"

    def no_token() -> str:
        response = client.get("/api/v1/auth/me")
        expect_status(response, 401)
        return "401 as expected"

    def logout() -> str:
        response = client.post(
            "/api/v1/auth/logout", headers=state["alice_headers"], json={}
        )
        expect_status(response, 200)
        expect(response.json()["success"] is True, "logout should succeed")
        return "logged out"

    def me_after_logout() -> str:
        response = client.get("/api/v1/auth/me", headers=state["alice_headers"])
        expect_status(response, 401)
        return "401 as expected"

    def persistence() -> str:
        db = sqlite3.connect(DATA_DIR / "stage_phase1.db")
        users = db.execute("select count(1) from users").fetchone()[0]
        tenants = db.execute("select count(1) from tenants").fetchone()[0]
        members = db.execute("select count(1) from tenant_members").fetchone()[0]
        tokens = db.execute("select count(1) from auth_tokens").fetchone()[0]
        revoked = db.execute(
            "select count(1) from auth_tokens where is_revoked = 1"
        ).fetchone()[0]
        expect(users == 2, f"users expected 2, got {users}")
        expect(tenants == 2, f"tenants expected 2, got {tenants}")
        expect(members == 2, f"tenant_members expected 2, got {members}")
        expect(tokens >= 6, f"auth_tokens expected >=6, got {tokens}")
        expect(revoked >= 1, "logout/refresh should revoke tokens")
        return f"users={users} tenants={tenants} members={members} tokens={tokens} revoked={revoked}"

    sc.step("auth_config", "读取认证配置", auth_config)
    sc.step("register", "注册用户并自动建空间", register_alice)
    sc.step("register_dup", "重复注册被拒绝", register_duplicate)
    sc.step("register_weak", "弱密码被拒绝", register_weak_password)
    sc.step("login", "登录并签发双令牌", login_alice)
    sc.step("login_wrong", "错误密码返回 401", login_wrong_password)
    sc.step("login_unknown", "不存在用户返回 401", login_unknown_user)
    sc.step("validate", "令牌校验接口", validate_token)
    sc.step("me", "当前用户信息", me)
    sc.step("tenant", "当前空间信息", tenant_info)
    sc.step("refresh", "刷新令牌并轮换", refresh_token)
    sc.step("refresh_again", "刷新令牌可重复使用", refresh_again)
    sc.step("refresh_invalid", "非法刷新令牌返回 401", refresh_invalid)
    sc.step("register_bob", "注册第二用户", register_bob)
    sc.step("rbac_cross", "跨空间访问返回 403", cross_tenant_forbidden)
    sc.step("no_token", "未带令牌返回 401", no_token)
    sc.step("logout", "登出并吊销令牌", logout)
    sc.step("after_logout", "登出后令牌失效", me_after_logout)
    sc.step("persistence", "数据库落盘校验", persistence)
    return sc


def scenario_phase2(client: httpx.Client) -> Scenario:
    sc = Scenario(client)
    headers = ensure_alice(client)

    def list_empty() -> str:
        response = client.get("/api/v1/models", headers=headers)
        expect_status(response, 200)
        expect(response.json()["data"] == [], "models should start empty")
        return "0 models"

    def create_chat() -> str:
        response = client.post(
            "/api/v1/models",
            headers=headers,
            json={
                "name": "fake-chat",
                "display_name": "假聊天模型",
                "type": "chat",
                "is_default": True,
                "parameters": {"base_url": FAKE_BASE_URL, "api_key": "test-key"},
            },
        )
        expect_status(response, 201)
        data = response.json()["data"]
        expect(data["parameters"]["api_key"] == "******", "api_key must be masked")
        expect(data["is_default"] is True, "chat model should be default")
        sc.state["chat_id"] = data["id"]
        return data["id"]

    def create_embedding() -> str:
        response = client.post(
            "/api/v1/models",
            headers=headers,
            json={
                "name": "fake-embedding",
                "type": "embedding",
                "is_default": True,
                "parameters": {
                    "base_url": FAKE_BASE_URL,
                    "api_key": "test-key",
                    "embedding_parameters": {"dimension": 64},
                },
            },
        )
        expect_status(response, 201)
        data = response.json()["data"]
        expect(data["parameters"]["embedding_parameters"]["dimension"] == 64, "dimension mismatch")
        sc.state["embedding_id"] = data["id"]
        return data["id"]

    def list_models() -> str:
        response = client.get("/api/v1/models", headers=headers)
        expect_status(response, 200)
        expect(len(response.json()["data"]) == 2, "expected 2 models")
        return "2 models"

    def get_model() -> str:
        response = client.get(f"/api/v1/models/{sc.state['chat_id']}", headers=headers)
        expect_status(response, 200)
        expect(response.json()["data"]["name"] == "fake-chat", "name mismatch")
        return response.json()["data"]["display_name"]

    def update_model() -> str:
        response = client.put(
            f"/api/v1/models/{sc.state['chat_id']}",
            headers=headers,
            json={"display_name": "更新后的聊天模型", "parameters": {"api_key": "******"}},
        )
        expect_status(response, 200)
        data = response.json()["data"]
        expect(data["display_name"] == "更新后的聊天模型", "display_name not updated")
        expect(data["parameters"]["api_key"] == "******", "masked api_key must be kept")
        return data["display_name"]

    def test_chat_model() -> str:
        response = client.post(f"/api/v1/models/{sc.state['chat_id']}/test", headers=headers)
        expect_status(response, 200)
        data = response.json()["data"]
        expect(data["ok"] is True, "test should be ok")
        expect(data["reply"].strip() == "pong", f"unexpected reply: {data['reply']}")
        return data["reply"]

    def test_embedding_model() -> str:
        response = client.post(
            f"/api/v1/models/{sc.state['embedding_id']}/test", headers=headers
        )
        expect_status(response, 200)
        data = response.json()["data"]
        expect(data["ok"] is True, "test should be ok")
        expect(data["dimension"] == 64, f"dimension expected 64, got {data['dimension']}")
        return f"dimension={data['dimension']}"

    def invalid_type() -> str:
        response = client.post(
            "/api/v1/models",
            headers=headers,
            json={"name": "bad", "type": "audio-magic", "parameters": {"base_url": FAKE_BASE_URL}},
        )
        expect_status(response, 400)
        return response.json()["error"]["message"]

    def missing_base_url() -> str:
        response = client.post(
            "/api/v1/models",
            headers=headers,
            json={"name": "bad", "type": "chat", "parameters": {}},
        )
        expect_status(response, 400)
        return response.json()["error"]["message"]

    def unauthorized() -> str:
        response = client.get("/api/v1/models")
        expect_status(response, 401)
        return "401 as expected"

    def delete_model() -> str:
        response = client.delete(f"/api/v1/models/{sc.state['chat_id']}", headers=headers)
        expect_status(response, 200)
        after = client.get(f"/api/v1/models/{sc.state['chat_id']}", headers=headers)
        expect_status(after, 404)
        return "deleted"

    def persistence() -> str:
        db = sqlite3.connect(DATA_DIR / "stage_phase2.db")
        active = db.execute("select count(1) from models where deleted_at is null").fetchone()[0]
        raw = db.execute(
            "select parameters from models where id = ?", (sc.state["embedding_id"],)
        ).fetchone()[0]
        expect(active == 1, f"active models expected 1, got {active}")
        expect("test-key" in raw, "masked update must not overwrite stored api_key")
        return f"active={active}"

    sc.step("list_empty", "模型列表初始为空", list_empty)
    sc.step("create_chat", "创建 chat 模型（密钥掩码）", create_chat)
    sc.step("create_embedding", "创建 embedding 模型", create_embedding)
    sc.step("list", "模型列表返回 2 条", list_models)
    sc.step("get", "查询模型详情", get_model)
    sc.step("update", "更新模型且掩码不覆盖", update_model)
    sc.step("test_chat", "连通性测试 chat", test_chat_model)
    sc.step("test_embedding", "连通性测试 embedding", test_embedding_model)
    sc.step("invalid_type", "非法模型类型返回 400", invalid_type)
    sc.step("missing_base_url", "缺少 base_url 返回 400", missing_base_url)
    sc.step("unauthorized", "未认证访问返回 401", unauthorized)
    sc.step("delete", "删除模型后不可见", delete_model)
    sc.step("persistence", "数据库落盘校验", persistence)
    return sc


def scenario_phase3(client: httpx.Client) -> Scenario:
    sc = Scenario(client)
    headers = ensure_alice(client)
    _, embedding = create_models(client, headers)

    def create_kb_step() -> str:
        kb = create_kb(client, headers)
        expect(kb["embedding_model_id"] == embedding["id"], "kb should use default embedding model")
        sc.state["kb_id"] = kb["id"]
        return f"kb={kb['id']}"

    def create_kb_missing_name() -> str:
        response = client.post(
            "/api/v1/knowledge-bases", headers=headers, json={"description": "no name"}
        )
        expect_status(response, 400)
        return response.json()["error"]["message"]

    def upload() -> str:
        knowledge = upload_text(client, headers, str(sc.state["kb_id"]))
        expect(knowledge["parse_status"] == "completed", f"parse_status={knowledge['parse_status']}")
        expect(knowledge["file_size"] > 0, "file_size should be > 0")
        sc.state["knowledge_id"] = knowledge["id"]
        return f"knowledge={knowledge['id']} status={knowledge['parse_status']}"

    def get_knowledge() -> str:
        response = client.get(f"/api/v1/knowledge/{sc.state['knowledge_id']}", headers=headers)
        expect_status(response, 200)
        expect(response.json()["data"]["title"] == "guide.txt", "title mismatch")
        return response.json()["data"]["parse_status"]

    def list_knowledge() -> str:
        response = client.get(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/knowledge", headers=headers
        )
        expect_status(response, 200)
        expect(len(response.json()["data"]) == 1, "expected 1 knowledge")
        return "1 knowledge"

    def list_chunks() -> str:
        response = client.get(f"/api/v1/chunks/{sc.state['knowledge_id']}", headers=headers)
        expect_status(response, 200)
        chunks = response.json()["data"]
        expect(len(chunks) >= 2, f"expected >=2 chunks, got {len(chunks)}")
        sc.state["chunk_count"] = len(chunks)
        return f"{len(chunks)} chunks"

    def reparse() -> str:
        response = client.post(
            f"/api/v1/knowledge/{sc.state['knowledge_id']}/reparse", headers=headers
        )
        expect_status(response, 200)
        expect(response.json()["data"]["parse_status"] == "completed", "reparse failed")
        after = client.get(f"/api/v1/chunks/{sc.state['knowledge_id']}", headers=headers)
        expect(len(after.json()["data"]) > 0, "chunks should exist after reparse")
        return "reparsed"

    def create_manual() -> str:
        response = client.post(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/knowledge/manual",
            headers=headers,
            json={
                "title": "常见问题",
                "content": "问：Nebula 默认端口是什么？\n答：默认端口是 8080。",
            },
        )
        expect_status(response, 201)
        data = response.json()["data"]
        expect(data["parse_status"] == "completed", "manual knowledge should be parsed")
        sc.state["manual_id"] = data["id"]
        return data["type"]

    def delete_manual() -> str:
        response = client.delete(f"/api/v1/knowledge/{sc.state['manual_id']}", headers=headers)
        expect_status(response, 200)
        listing = client.get(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/knowledge", headers=headers
        )
        expect(len(listing.json()["data"]) == 1, "manual knowledge should be hidden")
        return "deleted"

    def cross_tenant() -> str:
        bob = ensure_bob(client)
        response = client.get(f"/api/v1/knowledge-bases/{sc.state['kb_id']}", headers=bob)
        expect_status(response, 404)
        return "404 as expected"

    def persistence() -> str:
        db = sqlite3.connect(DATA_DIR / "stage_phase3.db")
        kbs = db.execute("select count(1) from knowledge_bases where deleted_at is null").fetchone()[0]
        knowledges = db.execute(
            "select count(1) from knowledges where deleted_at is null"
        ).fetchone()[0]
        chunks = db.execute("select count(1) from chunks where deleted_at is null").fetchone()[0]
        embedded = db.execute(
            "select count(1) from chunks where deleted_at is null and metadata like '%embedding%'"
        ).fetchone()[0]
        expect(kbs == 1, f"kb expected 1, got {kbs}")
        expect(knowledges == 1, f"knowledge expected 1, got {knowledges}")
        expect(chunks >= 2, f"chunks expected >=2, got {chunks}")
        expect(embedded == chunks, "every chunk should carry an embedding")
        return f"kb={kbs} knowledge={knowledges} chunks={chunks} embedded={embedded}"

    sc.step("create_kb", "创建知识库（绑定默认向量模型）", create_kb_step)
    sc.step("create_kb_invalid", "缺少名称返回 400", create_kb_missing_name)
    sc.step("upload", "上传文档并完成解析入库", upload)
    sc.step("get", "查询知识详情", get_knowledge)
    sc.step("list", "知识库文档列表", list_knowledge)
    sc.step("chunks", "分块列表", list_chunks)
    sc.step("reparse", "重新解析文档", reparse)
    sc.step("manual", "手工知识入库", create_manual)
    sc.step("delete", "删除知识", delete_manual)
    sc.step("cross_tenant", "跨空间访问返回 404", cross_tenant)
    sc.step("persistence", "数据库落盘校验（含向量）", persistence)
    return sc


def scenario_phase4(client: httpx.Client) -> Scenario:
    sc = Scenario(client)
    headers = ensure_alice(client)
    create_models(client, headers)
    kb = create_kb(client, headers, name="检索库")
    sc.state["kb_id"] = kb["id"]
    upload_text(client, headers, kb["id"])

    def hybrid_search() -> str:
        response = client.post(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/hybrid-search",
            headers=headers,
            json={"query": "Nebula 默认端口是多少", "top_k": 3},
        )
        expect_status(response, 200)
        hits = response.json()["data"]
        expect(len(hits) > 0, "hybrid search should return hits")
        expect(hits[0]["score"] > 0, "top hit score should be > 0")
        expect("vector_score" in hits[0], "vector_score missing")
        expect("keyword_score" in hits[0], "keyword_score missing")
        expect(any("8080" in hit["content"] for hit in hits), "expected port chunk in hits")
        expect(hits[0]["vector_score"] > 0, "vector score should be positive")
        sc.state["top_hit"] = hits[0]["content"]
        return f"{len(hits)} hits, top score={hits[0]['score']}"

    def knowledge_search() -> str:
        response = client.post(
            "/api/v1/knowledge-search",
            headers=headers,
            json={"query": "部署需要哪些组件", "knowledge_base_id": sc.state["kb_id"]},
        )
        expect_status(response, 200)
        hits = response.json()["data"]
        expect(len(hits) > 0, "knowledge search should return hits")
        expect(any("PostgreSQL" in hit["content"] for hit in hits), "expected deployment chunk")
        return f"{len(hits)} hits"

    def empty_query() -> str:
        response = client.post(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/hybrid-search",
            headers=headers,
            json={"query": "   "},
        )
        expect_status(response, 400)
        return response.json()["error"]["message"]

    def search_missing_kb() -> str:
        response = client.post(
            "/api/v1/knowledge-search", headers=headers, json={"query": "端口"}
        )
        expect_status(response, 400)
        return response.json()["error"]["message"]

    def unknown_kb() -> str:
        response = client.post(
            "/api/v1/knowledge-bases/not-exist/hybrid-search",
            headers=headers,
            json={"query": "端口"},
        )
        expect_status(response, 404)
        return "404 as expected"

    def top_k() -> str:
        response = client.post(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/hybrid-search",
            headers=headers,
            json={"query": "Nebula", "top_k": 1},
        )
        expect_status(response, 200)
        expect(len(response.json()["data"]) == 1, "top_k=1 should return 1 hit")
        return "top_k respected"

    sc.step("hybrid", "混合检索返回排序结果", hybrid_search)
    sc.step("search", "knowledge-search 命中部署资料", knowledge_search)
    sc.step("empty_query", "空查询返回 400", empty_query)
    sc.step("missing_kb", "缺少知识库返回 400", search_missing_kb)
    sc.step("unknown_kb", "未知知识库返回 404", unknown_kb)
    sc.step("top_k", "top_k 生效", top_k)
    return sc


def scenario_phase5(client: httpx.Client) -> Scenario:
    sc = Scenario(client)
    headers = ensure_alice(client)
    create_models(client, headers)
    kb = create_kb(client, headers, name="问答库")
    upload_text(client, headers, kb["id"])

    def create_session() -> str:
        response = client.post(
            "/api/v1/sessions",
            headers=headers,
            json={"title": "问答测试", "knowledge_base_id": kb["id"]},
        )
        expect_status(response, 201)
        data = response.json()["data"]
        expect(data["knowledge_base_id"] == kb["id"], "kb binding mismatch")
        sc.state["session_id"] = data["id"]
        return data["id"]

    def create_default_session() -> str:
        response = client.post("/api/v1/sessions", headers=headers, json={})
        expect_status(response, 201)
        data = response.json()["data"]
        expect(data["title"] == "新会话", f"unexpected default title: {data['title']}")
        sc.state["default_session"] = data["id"]
        return data["title"]

    def list_sessions() -> str:
        response = client.get("/api/v1/sessions", headers=headers)
        expect_status(response, 200)
        expect(len(response.json()["data"]) == 2, "expected 2 sessions")
        return "2 sessions"

    def get_session() -> str:
        response = client.get(f"/api/v1/sessions/{sc.state['session_id']}", headers=headers)
        expect_status(response, 200)
        expect(response.json()["data"]["title"] == "问答测试", "session title mismatch")
        return response.json()["data"]["title"]

    def update_session() -> str:
        response = client.put(
            f"/api/v1/sessions/{sc.state['session_id']}",
            headers=headers,
            json={"title": "改名后的会话"},
        )
        expect_status(response, 200)
        expect(response.json()["data"]["title"] == "改名后的会话", "title not updated")
        return response.json()["data"]["title"]

    def chat_stream() -> str:
        events: list[dict] = []
        with client.stream(
            "POST",
            f"/api/v1/knowledge-chat/{sc.state['session_id']}",
            headers=headers,
            json={"query": "Nebula 默认端口是多少"},
        ) as response:
            expect_status(response, 200)
            expect(
                "text/event-stream" in response.headers.get("content-type", ""),
                "content-type should be text/event-stream",
            )
            for line in response.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))

        types = [event["response_type"] for event in events]
        expect("agent_query" in types, f"agent_query missing: {types}")
        expect("references" in types, f"references missing: {types}")
        expect("answer" in types, f"answer missing: {types}")
        expect(types[-1] == "complete", f"last event should be complete: {types}")

        answer = "".join(
            str(event["data"].get("content") or "")
            for event in events
            if event["response_type"] == "answer" and "content" in event["data"]
        )
        expect(answer.startswith("根据知识库资料"), f"unexpected answer: {answer[:60]}")
        complete = events[-1]["data"]
        expect(bool(complete.get("knowledge_references")), "references must not be empty")
        expect(complete.get("total_duration_ms") is not None, "duration missing")
        sc.state["answer"] = answer
        sc.state["reference_count"] = len(complete["knowledge_references"])
        return f"{len(events)} events, answer={len(answer)} chars"

    def load_messages() -> str:
        response = client.get(
            f"/api/v1/messages/{sc.state['session_id']}/load", headers=headers
        )
        expect_status(response, 200)
        rows = response.json()["data"]
        expect(len(rows) == 2, f"expected 2 messages, got {len(rows)}")
        expect(rows[0]["role"] == "user", "first message should be user")
        expect(rows[1]["role"] == "assistant", "second message should be assistant")
        expect(rows[1]["content"] == sc.state["answer"], "assistant content mismatch")
        expect(bool(rows[1]["knowledge_references"]), "references should be persisted")
        return f"2 messages, refs={len(rows[1]['knowledge_references'])}"

    def cross_tenant() -> str:
        bob = ensure_bob(client)
        response = client.get(f"/api/v1/sessions/{sc.state['session_id']}", headers=bob)
        expect_status(response, 404)
        return "404 as expected"

    def clear_messages() -> str:
        response = client.delete(
            f"/api/v1/sessions/{sc.state['session_id']}/messages", headers=headers
        )
        expect_status(response, 200)
        expect(response.json()["data"]["deleted"] == 2, "should delete 2 messages")
        after = client.get(f"/api/v1/messages/{sc.state['session_id']}/load", headers=headers)
        expect(after.json()["data"] == [], "messages should be empty after clear")
        return "cleared"

    def delete_session() -> str:
        response = client.delete(f"/api/v1/sessions/{sc.state['session_id']}", headers=headers)
        expect_status(response, 200)
        after = client.get(f"/api/v1/sessions/{sc.state['session_id']}", headers=headers)
        expect_status(after, 404)
        listing = client.get("/api/v1/sessions", headers=headers)
        expect(len(listing.json()["data"]) == 1, "one session should remain")
        return "deleted"

    def persistence() -> str:
        db = sqlite3.connect(DATA_DIR / "stage_phase5.db")
        sessions = db.execute("select count(1) from sessions where deleted_at is null").fetchone()[0]
        messages = db.execute("select count(1) from messages where deleted_at is null").fetchone()[0]
        expect(sessions == 1, f"sessions expected 1, got {sessions}")
        expect(messages == 0, f"messages expected 0 after clear, got {messages}")
        return f"sessions={sessions} messages={messages}"

    sc.step("create_session", "创建会话并绑定知识库", create_session)
    sc.step("create_default", "默认会话标题", create_default_session)
    sc.step("list", "会话列表", list_sessions)
    sc.step("get", "会话详情", get_session)
    sc.step("update", "更新会话标题", update_session)
    sc.step("stream", "SSE 流式问答（含引用）", chat_stream)
    sc.step("messages", "历史消息与引用落库", load_messages)
    sc.step("cross_tenant", "跨空间访问会话返回 404", cross_tenant)
    sc.step("clear", "清空会话消息", clear_messages)
    sc.step("delete", "删除会话", delete_session)
    sc.step("persistence", "数据库落盘校验", persistence)
    return sc


def scenario_phase6(client: httpx.Client) -> Scenario:
    sc = Scenario(client)
    headers = ensure_alice(client)
    create_models(client, headers)
    kb = create_kb(client, headers, name="组织库")
    sc.state["kb_id"] = kb["id"]

    def create_docs() -> str:
        ids = []
        for title in ("退款流程", "物流说明", "发票指引"):
            response = client.post(
                f"/api/v1/knowledge-bases/{kb['id']}/knowledge/manual",
                headers=headers,
                json={"title": title, "content": f"{title}：企业知识库中的说明文档。"},
            )
            expect_status(response, 201)
            ids.append(response.json()["data"]["id"])
        sc.state["knowledge_ids"] = ids
        return f"{len(ids)} documents"

    def create_tags() -> str:
        first = client.post(
            f"/api/v1/knowledge-bases/{kb['id']}/tags",
            headers=headers,
            json={"name": "售后", "color": "#3B82F6"},
        )
        expect_status(first, 201)
        second = client.post(
            f"/api/v1/knowledge-bases/{kb['id']}/tags",
            headers=headers,
            json={"name": "财务"},
        )
        expect_status(second, 201)
        untagged = client.post(
            f"/api/v1/knowledge-bases/{kb['id']}/tags",
            headers=headers,
            json={"name": "未分类", "sort_order": 8},
        )
        expect_status(untagged, 201)
        expect(
            untagged.json()["data"]["sort_order"] == -1,
            "untagged tag must sort first",
        )
        sc.state["tag_id"] = first.json()["data"]["id"]
        sc.state["tag_seq"] = first.json()["data"]["seq_id"]
        sc.state["tag2_id"] = second.json()["data"]["id"]
        return f"tags={sc.state['tag_id']},{sc.state['tag2_id']}"

    def duplicate_tag() -> str:
        response = client.post(
            f"/api/v1/knowledge-bases/{kb['id']}/tags",
            headers=headers,
            json={"name": "售后"},
        )
        expect_status(response, 409)
        return response.json()["error"]["message"]

    def list_tags() -> str:
        response = client.get(
            f"/api/v1/knowledge-bases/{kb['id']}/tags",
            headers=headers,
            params={"page": 1, "page_size": 2},
        )
        expect_status(response, 200)
        page = response.json()["data"]
        expect(page["total"] == 3, f"total expected 3, got {page['total']}")
        expect(page["page_size"] == 2, "page_size mismatch")
        expect(len(page["data"]) == 2, "pagination not applied")
        expect(page["data"][0]["name"] == "未分类", "untagged tag should be first")
        return f"total={page['total']}"

    def keyword_filter() -> str:
        response = client.get(
            f"/api/v1/knowledge-bases/{kb['id']}/tags",
            headers=headers,
            params={"keyword": "售后"},
        )
        expect_status(response, 200)
        expect(response.json()["data"]["total"] == 1, "keyword filter failed")
        return "1 tag"

    def update_tag() -> str:
        response = client.put(
            f"/api/v1/knowledge-bases/{kb['id']}/tags/{sc.state['tag_seq']}",
            headers=headers,
            json={"color": "#EF4444"},
        )
        expect_status(response, 200)
        expect(response.json()["data"]["name"] == "售后", "name should be preserved")
        expect(response.json()["data"]["color"] == "#EF4444", "color not updated")
        return "updated by seq_id"

    def bind_tags() -> str:
        response = client.put(
            "/api/v1/knowledge/tags",
            headers=headers,
            json={
                "kb_id": kb["id"],
                "updates": {
                    sc.state["knowledge_ids"][0]: [sc.state["tag_id"]],
                    sc.state["knowledge_ids"][2]: [sc.state["tag2_id"]],
                },
            },
        )
        expect_status(response, 200)
        counts = client.get(
            f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=headers
        ).json()["data"]["data"]
        by_name = {item["name"]: item for item in counts}
        expect(by_name["售后"]["knowledge_count"] == 1, "knowledge_count mismatch")
        expect(by_name["财务"]["knowledge_count"] == 1, "knowledge_count mismatch")
        return "2 bindings"

    def list_by_tag() -> str:
        response = client.get(
            f"/api/v1/knowledge-bases/{kb['id']}/knowledge",
            headers=headers,
            params={"tag_id": sc.state["tag_id"]},
        )
        expect_status(response, 200)
        items = response.json()["data"]
        expect(len(items) == 1, f"expected 1 knowledge, got {len(items)}")
        expect(
            items[0]["tag_ids"] == [sc.state["tag_id"]], "tag_ids missing in payload"
        )
        return "1 knowledge by tag"

    def move_documents() -> str:
        first = client.post(
            "/api/v1/knowledge/move",
            headers=headers,
            json={
                "kb_id": kb["id"],
                "knowledge_ids": [sc.state["knowledge_ids"][0]],
                "folder_path": "售后/退款",
            },
        )
        expect_status(first, 200)
        second = client.post(
            "/api/v1/knowledge/move",
            headers=headers,
            json={
                "kb_id": kb["id"],
                "knowledge_ids": [sc.state["knowledge_ids"][1]],
                "folder_path": "售后",
            },
        )
        expect_status(second, 200)
        expect(first.json()["data"]["folder_path"] == "售后/退款", "path not normalized")
        return "2 moved"

    def folder_tree() -> str:
        response = client.get(
            f"/api/v1/knowledge-bases/{kb['id']}/knowledge/folders", headers=headers
        )
        expect_status(response, 200)
        data = response.json()["data"]
        expect(data["root_document_count"] == 1, "root_document_count mismatch")
        expect(data["total_document_count"] == 3, "total_document_count mismatch")
        expect(len(data["folders"]) == 1, "expected 1 root folder")
        root = data["folders"][0]
        expect(root["path"] == "售后", f"unexpected root path: {root['path']}")
        expect(root["total_count"] == 2, "folder total_count mismatch")
        expect([item["path"] for item in root["children"]] == ["售后/退款"], "child missing")
        sc.state["tree_root"] = root["path"]
        return f"root={root['path']} children={len(root['children'])}"

    def rename_folder() -> str:
        response = client.put(
            f"/api/v1/knowledge-bases/{kb['id']}/knowledge/folders",
            headers=headers,
            json={"from": "售后", "to": "客户服务"},
        )
        expect_status(response, 200)
        expect(response.json()["data"]["moved_count"] == 2, "rename should move subtree")
        tree = client.get(
            f"/api/v1/knowledge-bases/{kb['id']}/knowledge/folders", headers=headers
        ).json()["data"]
        expect([item["path"] for item in tree["folders"]] == ["客户服务"], "rename failed")
        expect(
            [child["path"] for child in tree["folders"][0]["children"]] == ["客户服务/退款"],
            "subtree rename failed",
        )
        return "renamed"

    def delete_referenced_tag() -> str:
        response = client.delete(
            f"/api/v1/knowledge-bases/{kb['id']}/tags/{sc.state['tag_seq']}",
            headers=headers,
        )
        expect_status(response, 400)
        return response.json()["error"]["message"]

    def force_delete_tag() -> str:
        response = client.delete(
            f"/api/v1/knowledge-bases/{kb['id']}/tags/{sc.state['tag_seq']}",
            headers=headers,
            params={"force": "true"},
        )
        expect_status(response, 200)
        remaining = client.get(
            f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=headers
        ).json()["data"]["total"]
        expect(remaining == 2, f"tags expected 2 after force delete, got {remaining}")
        rebuilt = client.post(
            f"/api/v1/knowledge-bases/{kb['id']}/tags",
            headers=headers,
            json={"name": "售后"},
        )
        expect_status(rebuilt, 201)
        sc.state["tag_id"] = rebuilt.json()["data"]["id"]
        sc.state["tag_seq"] = rebuilt.json()["data"]["seq_id"]
        return f"remaining={remaining}"

    def create_faq_kb() -> str:
        response = client.post(
            "/api/v1/knowledge-bases",
            headers=headers,
            json={"name": "FAQ 库", "type": "faq", "description": "FAQ 知识库"},
        )
        expect_status(response, 201)
        data = response.json()["data"]
        expect(data["type"] == "faq", "kb type mismatch")
        sc.state["faq_kb_id"] = data["id"]
        return data["id"]

    def create_entries() -> str:
        first = client.post(
            f"/api/v1/knowledge-bases/{sc.state['faq_kb_id']}/faq/entry",
            headers=headers,
            json={
                "standard_question": "如何申请退款？",
                "similar_questions": ["退款怎么操作"],
                "answers": ["在订单详情页提交退款申请。"],
            },
        )
        expect_status(first, 201)
        entry = first.json()["data"]
        expect(entry["id"] >= 1, "entry id should be seq_id")
        expect(entry["tag_name"] == "未分类", "default tag should be 未分类")
        expect(entry["index_mode"] == "question_answer", "index_mode mismatch")

        second = client.post(
            f"/api/v1/knowledge-bases/{sc.state['faq_kb_id']}/faq/entry",
            headers=headers,
            json={
                "standard_question": "怎么开具发票？",
                "similar_questions": ["发票申请入口"],
                "answers": ["在个人中心-发票管理中申请。"],
                "tag_name": "财务",
            },
        )
        expect_status(second, 201)
        sc.state["entry"] = entry["id"]
        sc.state["entry2"] = second.json()["data"]["id"]
        return f"entries={entry['id']},{sc.state['entry2']}"

    def entry_duplicate() -> str:
        response = client.post(
            f"/api/v1/knowledge-bases/{sc.state['faq_kb_id']}/faq/entry",
            headers=headers,
            json={"standard_question": "如何申请退款？", "answers": ["重复答案"]},
        )
        expect_status(response, 400)
        return response.json()["error"]["message"]

    def entry_bad_kb() -> str:
        response = client.post(
            f"/api/v1/knowledge-bases/{kb['id']}/faq/entry",
            headers=headers,
            json={"standard_question": "问", "answers": ["答"]},
        )
        expect_status(response, 400)
        return response.json()["error"]["message"]

    def list_entries() -> str:
        response = client.get(
            f"/api/v1/knowledge-bases/{sc.state['faq_kb_id']}/faq/entries",
            headers=headers,
            params={"page": 1, "page_size": 10},
        )
        expect_status(response, 200)
        page = response.json()["data"]
        expect(page["total"] == 2, f"entries expected 2, got {page['total']}")
        names = {item["tag_name"] for item in page["data"]}
        expect(names == {"未分类", "财务"}, f"unexpected tag names: {names}")

        keyword = client.get(
            f"/api/v1/knowledge-bases/{sc.state['faq_kb_id']}/faq/entries",
            headers=headers,
            params={"keyword": "发票"},
        )
        expect(
            [item["id"] for item in keyword.json()["data"]["data"]]
            == [sc.state["entry2"]],
            "keyword filter failed",
        )
        return f"total={page['total']}"

    def batch_tags() -> str:
        tags = client.get(
            f"/api/v1/knowledge-bases/{sc.state['faq_kb_id']}/tags", headers=headers
        ).json()["data"]["data"]
        finance = next(item for item in tags if item["name"] == "财务")
        response = client.put(
            f"/api/v1/knowledge-bases/{sc.state['faq_kb_id']}/faq/entries/tags",
            headers=headers,
            json={"updates": {str(sc.state["entry"]): finance["seq_id"]}},
        )
        expect_status(response, 200)
        expect(response.json()["data"]["updated"] == 1, "should update 1 entry")

        filtered = client.get(
            f"/api/v1/knowledge-bases/{sc.state['faq_kb_id']}/faq/entries",
            headers=headers,
            params={"tag_id": finance["seq_id"]},
        )
        expect(
            sorted(item["id"] for item in filtered.json()["data"]["data"])
            == sorted([sc.state["entry"], sc.state["entry2"]]),
            "tag filter failed",
        )
        return "1 updated"

    def batch_fields() -> str:
        response = client.put(
            f"/api/v1/knowledge-bases/{sc.state['faq_kb_id']}/faq/entries/fields",
            headers=headers,
            json={"by_id": {str(sc.state["entry"]): {"is_recommended": False}}},
        )
        expect_status(response, 200)
        detail = client.get(
            f"/api/v1/knowledge-bases/{sc.state['faq_kb_id']}/faq/entries/{sc.state['entry']}",
            headers=headers,
        ).json()["data"]
        expect(detail["is_recommended"] is False, "is_recommended not updated")
        return "fields updated"

    def faq_search() -> str:
        response = client.post(
            f"/api/v1/knowledge-bases/{sc.state['faq_kb_id']}/faq/search",
            headers=headers,
            json={"query_text": "发票申请入口"},
        )
        expect_status(response, 200)
        hits = response.json()["data"]
        expect(len(hits) == 1, f"expected 1 hit, got {len(hits)}")
        expect(hits[0]["match_type"] == "faq", "match_type mismatch")
        expect(hits[0]["score"] == 0.92, f"score mismatch: {hits[0]['score']}")

        exact = client.post(
            f"/api/v1/knowledge-bases/{sc.state['faq_kb_id']}/faq/search",
            headers=headers,
            json={"query_text": "如何申请退款"},
        )
        expect(exact.json()["data"][0]["score"] == 1.0, "exact match should score 1.0")
        return f"{len(hits)} hit"

    def delete_entries() -> str:
        response = client.request(
            "DELETE",
            f"/api/v1/knowledge-bases/{sc.state['faq_kb_id']}/faq/entries",
            headers=headers,
            json={"ids": [sc.state["entry"], sc.state["entry2"]]},
        )
        expect_status(response, 200)
        expect(response.json()["data"]["deleted"] == 2, "should delete 2 entries")
        after = client.get(
            f"/api/v1/knowledge-bases/{sc.state['faq_kb_id']}/faq/entries", headers=headers
        ).json()["data"]
        expect(after["total"] == 0, f"entries should be 0, got {after['total']}")
        return "deleted"

    def cross_tenant() -> str:
        bob = ensure_bob(client)
        response = client.get(
            f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=bob
        )
        expect_status(response, 404)
        return "404 as expected"

    def unauthorized() -> str:
        response = client.get(f"/api/v1/knowledge-bases/{kb['id']}/tags")
        expect_status(response, 401)
        return "401 as expected"

    def persistence() -> str:
        db = sqlite3.connect(DATA_DIR / "stage_phase6.db")
        tags = db.execute("select count(1) from knowledge_tags").fetchone()[0]
        relations = db.execute("select count(1) from knowledge_tag_relations").fetchone()[0]
        folders = {
            row[0]
            for row in db.execute(
                "select folder_path from knowledges where deleted_at is null and folder_path <> ''"
            )
        }
        # force 删除标签会连带软删该标签下的文档（对齐 Go），被删文档仍保留原 folder_path
        subtree = {
            row[0]
            for row in db.execute(
                "select folder_path from knowledges where folder_path like '客户服务/%'"
            )
        }
        faq_rows = db.execute(
            "select count(1) from chunks where chunk_type = 'faq' and deleted_at is null"
        ).fetchone()[0]
        faq_meta_rows = db.execute(
            "select count(1) from chunks where chunk_type = 'faq' "
            "and metadata like '%standard_question%'"
        ).fetchone()[0]
        expect(tags >= 4, f"tags expected >=4, got {tags}")
        expect(relations >= 1, f"relations expected >=1, got {relations}")
        expect("客户服务" in folders, f"folder path not persisted: {folders}")
        expect(
            "客户服务/退款" in subtree, f"subtree rename not persisted: {subtree}"
        )
        expect(faq_rows == 0, f"faq chunks expected 0 after delete, got {faq_rows}")
        expect(faq_meta_rows >= 2, f"faq metadata rows expected >=2, got {faq_meta_rows}")
        return f"tags={tags} relations={relations} folders={sorted(folders)}"

    sc.step("docs", "创建 3 篇手工文档", create_docs)
    sc.step("tags", "创建标签（未分类置顶）", create_tags)
    sc.step("tag_dup", "重名标签返回 409", duplicate_tag)
    sc.step("tag_list", "标签分页列表", list_tags)
    sc.step("tag_keyword", "标签关键词过滤", keyword_filter)
    sc.step("tag_update", "按 seq_id 更新标签", update_tag)
    sc.step("bind", "批量给知识打标", bind_tags)
    sc.step("filter_tag", "按标签筛选知识", list_by_tag)
    sc.step("move", "移动知识到文件夹", move_documents)
    sc.step("tree", "文件夹树聚合计数", folder_tree)
    sc.step("rename", "重命名文件夹并同步子树", rename_folder)
    sc.step("tag_delete_blocked", "被引用的标签禁止删除", delete_referenced_tag)
    sc.step("tag_force_delete", "force 删除后可重建同名标签", force_delete_tag)
    sc.step("faq_kb", "创建 FAQ 知识库", create_faq_kb)
    sc.step("faq_create", "创建 FAQ 条目（自动建容器知识）", create_entries)
    sc.step("faq_dup", "重复标准问返回 400", entry_duplicate)
    sc.step("faq_bad_kb", "非 FAQ 知识库拒绝写条目", entry_bad_kb)
    sc.step("faq_list", "FAQ 条目分页与关键词过滤", list_entries)
    sc.step("faq_tags", "FAQ 条目批量换标签", batch_tags)
    sc.step("faq_fields", "FAQ 条目批量改字段", batch_fields)
    sc.step("faq_search", "FAQ 检索（精确/相似问）", faq_search)
    sc.step("faq_delete", "批量删除 FAQ 条目", delete_entries)
    sc.step("cross_tenant", "跨空间访问返回 404", cross_tenant)
    sc.step("unauthorized", "未认证访问返回 401", unauthorized)
    sc.step("persistence", "数据库落盘校验", persistence)
    return sc


def scenario_phase6b(client: httpx.Client) -> Scenario:
    """Phase 6B：Wiki 页面树 / 版本回滚 / 文件夹 / 图谱。"""
    sc = Scenario(client)
    headers = ensure_alice(client)

    def create_wiki_kb() -> str:
        response = client.post(
            "/api/v1/knowledge-bases",
            headers=headers,
            json={"name": "Wiki 库", "type": "wiki"},
        )
        expect_status(response, 201)
        kb = response.json()["data"]
        sc.state["kb_id"] = kb["id"]
        return kb["id"]

    def create_pages() -> str:
        for slug, content in (
            ("overview", "平台总览。[[entities]] [[concepts]]"),
            ("entities", "核心实体。[[nebula]]"),
            ("concepts", "核心概念。[[nebula]]"),
            ("nebula", "Nebula 模块负责知识入库。"),
        ):
            response = client.post(
                f"/api/v1/knowledge-bases/{sc.state['kb_id']}/wiki/pages",
                headers=headers,
                json={"slug": slug, "title": slug, "content": content},
            )
            expect_status(response, 201)
        return "4 pages"

    def get_page_with_backlinks() -> str:
        response = client.get(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/wiki/pages/nebula",
            headers=headers,
        )
        expect_status(response, 200)
        data = response.json()["data"]
        expect(len(data["in_links"]) == 2, f"nebula in_links expected 2, got {data['in_links']}")
        return f"in_links={len(data['in_links'])}"

    def update_advances_version() -> str:
        response = client.put(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/wiki/pages/nebula",
            headers=headers,
            json={"content": "Nebula 模块负责知识入库与向量索引。", "version": 1},
        )
        expect_status(response, 200)
        data = response.json()["data"]
        expect(data["version"] == 2, f"version expected 2, got {data['version']}")
        sc.state["page_version"] = data["version"]
        return f"version={data['version']}"

    def list_revisions() -> str:
        response = client.get(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/wiki/revisions/nebula",
            headers=headers,
        )
        expect_status(response, 200)
        data = response.json()["data"]
        expect(data["current_version"] == 2, "current_version mismatch")
        expect(len(data["revisions"]) == 1, "expected 1 revision snapshot")
        return f"revisions={len(data['revisions'])}"

    def revert_page() -> str:
        response = client.post(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/wiki/revert",
            headers=headers,
            json={"slug": "nebula", "version": 1},
        )
        expect_status(response, 200)
        data = response.json()["data"]
        expect(data["content"].startswith("Nebula 模块负责知识入库。"), "revert content mismatch")
        expect(data["version"] == 3, f"revert version expected 3, got {data['version']}")
        return f"reverted to v1 -> v{data['version']}"

    def create_folder_and_move() -> str:
        folder = client.post(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/wiki/folders",
            headers=headers,
            json={"parent_id": "", "name": "归档"},
        )
        expect_status(folder, 201)
        folder_id = folder.json()["data"]["id"]
        sc.state["folder_id"] = folder_id

        moved = client.put(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/wiki/move-page",
            headers=headers,
            json={"slug": "nebula", "folder_id": folder_id},
        )
        expect_status(moved, 200)
        expect(moved.json()["data"]["category_path"] == ["归档"], "category_path mismatch")
        return "nebula -> 归档"

    def folder_delete_blocked() -> str:
        response = client.delete(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/wiki/folders/{sc.state['folder_id']}",
            headers=headers,
        )
        expect_status(response, 409)
        return "folder with page cannot delete"

    def graph() -> str:
        response = client.get(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/wiki/graph",
            headers=headers,
        )
        expect_status(response, 200)
        data = response.json()["data"]
        expect(data["meta"]["total"] == 4, f"graph total expected 4, got {data['meta']['total']}")
        expect(len(data["edges"]) == 4, f"edges expected 4, got {len(data['edges'])}")
        return f"nodes={len(data['nodes'])}, edges={len(data['edges'])}"

    def stats() -> str:
        response = client.get(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/wiki/stats",
            headers=headers,
        )
        expect_status(response, 200)
        data = response.json()["data"]
        expect(data["total_pages"] == 4, "total_pages mismatch")
        expect(data["total_links"] == 4, "total_links mismatch")
        return f"total_pages={data['total_pages']}"

    def non_wiki_rejected() -> str:
        doc_kb = client.post(
            "/api/v1/knowledge-bases",
            headers=headers,
            json={"name": "文档库", "type": "document"},
        )
        expect_status(doc_kb, 201)
        response = client.get(
            f"/api/v1/knowledge-bases/{doc_kb.json()['data']['id']}/wiki/pages",
            headers=headers,
        )
        expect_status(response, 400)
        return "non-wiki kb rejected"

    def duplicate_slug_conflict() -> str:
        response = client.post(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/wiki/pages",
            headers=headers,
            json={"slug": "nebula", "title": "重复"},
        )
        expect_status(response, 409)
        return "duplicate slug 409"

    def version_conflict() -> str:
        response = client.put(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/wiki/pages/nebula",
            headers=headers,
            json={"content": "并发写", "version": 1},
        )
        expect_status(response, 409)
        return "stale version 409"

    def unauthorized() -> str:
        response = client.get(
            f"/api/v1/knowledge-bases/{sc.state['kb_id']}/wiki/pages"
        )
        expect_status(response, 401)
        return "401"

    def persistence() -> str:
        db = sqlite3.connect(DATA_DIR / "stage_phase6b.db")
        try:
            row = db.execute(
                "SELECT COUNT(*) FROM wiki_pages WHERE knowledge_base_id = ?",
                (sc.state["kb_id"],),
            ).fetchone()
        finally:
            db.close()
        expect(row and row[0] == 4, f"wiki_pages expected 4, got {row}")
        return f"wiki_pages={row[0]}"

    sc.step("wiki_kb", "创建 Wiki 知识库", create_wiki_kb)
    sc.step("create_pages", "创建带内链的页面", create_pages)
    sc.step("backlinks", "页面反向链接维护", get_page_with_backlinks)
    sc.step("version_advance", "更新推进版本号", update_advances_version)
    sc.step("revisions", "版本快照列表", list_revisions)
    sc.step("revert", "回滚到历史版本", revert_page)
    sc.step("folder_move", "文件夹创建与页面移动", create_folder_and_move)
    sc.step("folder_blocked", "含页面的文件夹禁止删除", folder_delete_blocked)
    sc.step("graph", "图谱节点与边", graph)
    sc.step("stats", "Wiki 统计", stats)
    sc.step("non_wiki_rejected", "非 Wiki 库拒绝访问", non_wiki_rejected)
    sc.step("duplicate_slug", "重复 slug 返回 409", duplicate_slug_conflict)
    sc.step("version_conflict", "过期版本写返回 409", version_conflict)
    sc.step("unauthorized", "未认证访问返回 401", unauthorized)
    sc.step("persistence", "数据库落盘校验", persistence)
    return sc


def scenario_phase7a(client: httpx.Client) -> Scenario:
    """Phase 7A：自定义 Agent CRUD + 编辑器元数据（工具/类型预设/占位符）。"""
    sc = Scenario(client)
    headers = ensure_alice(client)

    def list_builtins() -> str:
        response = client.get("/api/v1/agents", headers=headers)
        expect_status(response, 200)
        items = response.json()["data"]
        ids = {item["id"] for item in items}
        expect("builtin-quick-answer" in ids, "missing builtin-quick-answer")
        expect("builtin-smart-reasoning" in ids, "missing builtin-smart-reasoning")
        return f"builtins={len([i for i in items if i['is_builtin']])}"

    def create_agent() -> str:
        response = client.post(
            "/api/v1/agents",
            headers=headers,
            json={
                "name": "研究助手",
                "description": "阶段验收智能体",
                "config": {"agent_mode": "smart-reasoning"},
            },
        )
        expect_status(response, 201)
        data = response.json()["data"]
        expect(data["config"]["agent_mode"] == "smart-reasoning", "agent_mode mismatch")
        expect(data["config"]["max_iterations"] == 10, "max_iterations default mismatch")
        sc.state["agent_id"] = data["id"]
        return data["id"]

    def get_agent() -> str:
        response = client.get(f"/api/v1/agents/{sc.state['agent_id']}", headers=headers)
        expect_status(response, 200)
        expect(response.json()["data"]["name"] == "研究助手", "name mismatch")
        return "ok"

    def update_agent() -> str:
        response = client.put(
            f"/api/v1/agents/{sc.state['agent_id']}",
            headers=headers,
            json={
                "name": "改名助手",
                "description": "更新",
                "config": {"agent_mode": "quick-answer", "temperature": 0.3},
            },
        )
        expect_status(response, 200)
        data = response.json()["data"]
        expect(data["name"] == "改名助手", "name not updated")
        expect(data["config"]["temperature"] == 0.3, "temperature not updated")
        return data["name"]

    def patch_agent() -> str:
        response = client.patch(
            f"/api/v1/agents/{sc.state['agent_id']}",
            headers=headers,
            json={"system_prompt": "你是助手"},
        )
        expect_status(response, 200)
        expect(response.json()["data"]["config"]["system_prompt"] == "你是助手", "patch failed")
        return "ok"

    def copy_agent() -> str:
        response = client.post(
            f"/api/v1/agents/{sc.state['agent_id']}/copy", headers=headers
        )
        expect_status(response, 201)
        data = response.json()["data"]
        expect(data["id"] != sc.state["agent_id"], "copy id should differ")
        sc.state["copy_id"] = data["id"]
        return data["name"]

    def builtin_protected() -> str:
        response = client.put(
            "/api/v1/agents/builtin-quick-answer",
            headers=headers,
            json={"name": "x", "config": {}},
        )
        expect_status(response, 400)
        return "400 as expected"

    def metadata() -> str:
        tools = client.get("/api/v1/agents/tools", headers=headers)
        expect_status(tools, 200)
        names = {tool["name"] for tool in tools.json()["data"]["tools"]}
        expect("search_knowledge" in names and "wiki_read_page" in names, "tools missing")

        presets = client.get("/api/v1/agents/type-presets", headers=headers)
        expect_status(presets, 200)
        ids = {item["id"] for item in presets.json()["data"]}
        expect({"rag-qa", "wiki-qa", "custom"} <= ids, "presets missing")

        placeholders = client.get("/api/v1/agents/placeholders", headers=headers)
        expect_status(placeholders, 200)
        expect("all" in placeholders.json()["data"], "placeholders missing all")
        return f"tools={len(names)}, presets={len(ids)}"

    def validation() -> str:
        no_name = client.post("/api/v1/agents", headers=headers, json={"name": "  "})
        expect_status(no_name, 400)
        bad_mode = client.post(
            "/api/v1/agents", headers=headers, json={"name": "x", "config": {"agent_mode": "bad"}}
        )
        expect_status(bad_mode, 400)
        return "400 as expected"

    def delete_agent() -> str:
        response = client.delete(f"/api/v1/agents/{sc.state['agent_id']}", headers=headers)
        expect_status(response, 200)
        missing = client.get(f"/api/v1/agents/{sc.state['agent_id']}", headers=headers)
        expect_status(missing, 404)
        return "deleted"

    def unauthorized() -> str:
        response = client.get("/api/v1/agents")
        expect_status(response, 401)
        return "401"

    def persistence() -> str:
        db = sqlite3.connect(DATA_DIR / "stage_phase7a.db")
        try:
            row = db.execute(
                "SELECT COUNT(*) FROM custom_agents WHERE deleted_at IS NULL"
            ).fetchone()
        finally:
            db.close()
        # copy 仍存在，源已删除
        expect(row and row[0] == 1, f"custom_agents expected 1 (copy), got {row}")
        return f"custom_agents={row[0]}"

    sc.step("builtins", "列表包含内置智能体", list_builtins)
    sc.step("create", "创建自定义 Agent", create_agent)
    sc.step("get", "按 ID 获取 Agent", get_agent)
    sc.step("update", "PUT 全量更新", update_agent)
    sc.step("patch", "PATCH 部分更新", patch_agent)
    sc.step("copy", "复制 Agent", copy_agent)
    sc.step("builtin_protected", "内置智能体禁止修改", builtin_protected)
    sc.step("metadata", "工具/类型预设/占位符元数据", metadata)
    sc.step("validation", "参数校验返回 400", validation)
    sc.step("delete", "删除自定义 Agent", delete_agent)
    sc.step("unauthorized", "未认证访问返回 401", unauthorized)
    sc.step("persistence", "数据库落盘校验", persistence)
    return sc


def scenario_phase7b(client: httpx.Client) -> Scenario:
    """Phase 7B：ReAct 引擎 + 内置工具 + agent-chat SSE 全链路。"""
    sc = Scenario(client)
    headers = ensure_alice(client)
    create_models(client, headers)

    def prepare_kb() -> str:
        kb = create_kb(client, headers, name="Agent 验收库")
        upload_text(client, headers, kb["id"])
        sc.state["kb_id"] = kb["id"]
        return kb["id"]

    def create_agent() -> str:
        response = client.post(
            "/api/v1/agents",
            headers=headers,
            json={
                "name": "检索助手",
                "description": "ReAct 验收",
                "config": {
                    "agent_mode": "smart-reasoning",
                    "allowed_tools": ["search_knowledge", "read_document", "list_documents"],
                    "max_iterations": 5,
                },
            },
        )
        expect_status(response, 201)
        sc.state["agent_id"] = response.json()["data"]["id"]
        return sc.state["agent_id"]

    def create_session() -> str:
        response = client.post(
            "/api/v1/sessions",
            headers=headers,
            json={"title": "Agent 会话", "knowledge_base_id": sc.state["kb_id"]},
        )
        expect_status(response, 201)
        sc.state["session_id"] = response.json()["data"]["id"]
        return sc.state["session_id"]

    def agent_chat_stream() -> str:
        events: list[dict] = []
        with client.stream(
            "POST",
            f"/api/v1/agent-chat/{sc.state['session_id']}",
            headers=headers,
            json={"query": "Nebula 默认端口是多少", "agent_id": sc.state["agent_id"]},
        ) as response:
            expect_status(response, 200)
            expect(
                "text/event-stream" in response.headers.get("content-type", ""),
                "content-type should be text/event-stream",
            )
            for line in response.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))

        types = [event["response_type"] for event in events]
        expect("agent_query" in types, f"agent_query missing: {types}")
        expect("tool_call" in types, f"tool_call missing: {types}")
        expect("tool_result" in types, f"tool_result missing: {types}")
        expect("answer" in types, f"answer missing: {types}")
        expect(types[-1] == "complete", f"last event should be complete: {types}")

        complete = events[-1]["data"]
        expect(bool(complete.get("content")), "answer content must not be empty")
        expect(bool(complete.get("tool_calls")), "tool_calls history must not be empty")
        expect(
            complete["tool_calls"][0]["name"] == "search_knowledge",
            f"first tool should be search_knowledge: {complete['tool_calls']}",
        )
        sc.state["answer"] = complete["content"]
        return f"{len(events)} events, tools={len(complete['tool_calls'])}"

    def load_messages() -> str:
        response = client.get(
            f"/api/v1/messages/{sc.state['session_id']}/load", headers=headers
        )
        expect_status(response, 200)
        rows = response.json()["data"]
        expect(len(rows) == 2, f"expected 2 messages, got {len(rows)}")
        expect(rows[0]["role"] == "user", "first message should be user")
        expect(rows[1]["role"] == "assistant", "second message should be assistant")
        expect(rows[1]["content"] == sc.state["answer"], "assistant content mismatch")
        return "2 messages persisted"

    def persistence() -> str:
        db = sqlite3.connect(DATA_DIR / "stage_phase7b.db")
        try:
            messages = db.execute(
                "SELECT COUNT(*) FROM messages WHERE deleted_at IS NULL"
            ).fetchone()[0]
            agents = db.execute(
                "SELECT COUNT(*) FROM custom_agents WHERE deleted_at IS NULL"
            ).fetchone()[0]
        finally:
            db.close()
        expect(messages == 2, f"messages expected 2, got {messages}")
        expect(agents == 1, f"custom_agents expected 1, got {agents}")
        return f"messages={messages} agents={agents}"

    sc.step("kb", "创建知识库并上传文档", prepare_kb)
    sc.step("create_agent", "创建 ReAct Agent", create_agent)
    sc.step("create_session", "创建 Agent 会话", create_session)
    sc.step("agent_chat", "agent-chat SSE 多步工具调用", agent_chat_stream)
    sc.step("messages", "Agent 问答落库", load_messages)
    sc.step("persistence", "数据库落盘校验", persistence)
    return sc


def scenario_phase8a(client: httpx.Client) -> Scenario:
    """Phase 8A：MCP Endpoint 管理 API + 公开 MCP Streamable HTTP 面。"""
    sc = Scenario(client)
    headers = ensure_alice(client)

    def prepare_kb() -> str:
        kb = create_kb(client, headers, name="MCP 验收库")
        upload_text(client, headers, kb["id"])
        sc.state["kb_id"] = kb["id"]
        return kb["id"]

    def tool_catalog() -> str:
        response = client.get("/api/v1/mcp-endpoints/tools", headers=headers)
        expect_status(response, 200)
        data = response.json()["data"]
        expect(data["groups"] == ["retrieve", "chat", "wiki", "ingest"], f"groups={data['groups']}")
        names = {item["name"] for item in data["tools"]}
        expect("search_knowledge" in names, "catalog missing search_knowledge")
        expect("add_document" not in data["default_tools"], "destructive tool in defaults")
        return f"tools={len(names)}"

    def create_endpoint() -> str:
        response = client.post(
            "/api/v1/mcp-endpoints",
            headers=headers,
            json={
                "name": "workspace-mcp",
                "description": "验收端点",
                "knowledge_base_ids": [sc.state["kb_id"]],
            },
        )
        expect_status(response, 201)
        data = response.json()["data"]
        expect(data["token"].startswith("mcp_"), f"token prefix: {data['token'][:8]}")
        expect(data["path"] == f"/mcp/{data['id']}", f"path={data['path']}")
        sc.state["endpoint_id"] = data["id"]
        sc.state["token"] = data["token"]
        return data["id"]

    def manage_crud() -> str:
        detail = client.get(f"/api/v1/mcp-endpoints/{sc.state['endpoint_id']}", headers=headers)
        expect_status(detail, 200)
        expect("token" not in detail.json()["data"], "detail must not expose token")

        updated = client.put(
            f"/api/v1/mcp-endpoints/{sc.state['endpoint_id']}",
            headers=headers,
            json={"name": "改名端点"},
        )
        expect_status(updated, 200)
        expect(updated.json()["data"]["name"] == "改名端点", "name not updated")

        listing = client.get("/api/v1/mcp-endpoints", headers=headers)
        expect_status(listing, 200)
        expect(any(item["id"] == sc.state["endpoint_id"] for item in listing.json()["data"]), "endpoint missing in list")
        return "get/update/list ok"

    def rpc(method: str, params: dict | None = None) -> httpx.Response:
        return client.post(
            f"/mcp/{sc.state['endpoint_id']}",
            headers={"Authorization": f"Bearer {sc.state['token']}"},
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        )

    def public_initialize() -> str:
        response = rpc("initialize", {"protocolVersion": "2024-11-05"})
        expect_status(response, 200)
        result = response.json()["result"]
        expect(result["serverInfo"]["name"] == "weknora", f"serverInfo={result.get('serverInfo')}")
        expect(result["protocolVersion"] == "2024-11-05", "protocolVersion mismatch")
        return result["serverInfo"]["name"]

    def public_tools_list() -> str:
        response = rpc("tools/list")
        expect_status(response, 200)
        names = {tool["name"] for tool in response.json()["result"]["tools"]}
        expect("list_knowledge_bases" in names, "tools/list missing list_knowledge_bases")
        expect("add_document" not in names, "write tool exposed by default")
        return f"tools={len(names)}"

    def public_tool_calls() -> str:
        kbs = rpc("tools/call", {"name": "list_knowledge_bases"})
        expect_status(kbs, 200)
        expect(sc.state["kb_id"] in kbs.json()["result"]["content"][0]["text"], "kb not listed")

        search = rpc("tools/call", {"name": "search_knowledge", "arguments": {"query": "Nebula"}})
        expect_status(search, 200)
        expect("Nebula" in search.json()["result"]["content"][0]["text"], "search missed Nebula")

        docs = rpc(
            "tools/call",
            {"name": "list_documents", "arguments": {"knowledge_base_id": sc.state["kb_id"]}},
        )
        expect_status(docs, 200)
        expect("guide.txt" in docs.json()["result"]["content"][0]["text"], "document not listed")
        return "3 tools called"

    def rotate_and_old_invalid() -> str:
        old_token = sc.state["token"]
        response = client.post(
            f"/api/v1/mcp-endpoints/{sc.state['endpoint_id']}/rotate-token", headers=headers
        )
        expect_status(response, 200)
        sc.state["token"] = response.json()["data"]["token"]
        expect(sc.state["token"] != old_token, "token unchanged after rotate")

        bad = client.post(
            f"/mcp/{sc.state['endpoint_id']}",
            headers={"Authorization": f"Bearer {old_token}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        expect_status(bad, 401)
        return "rotate ok, old token rejected"

    def disabled_forbidden() -> str:
        client.put(
            f"/api/v1/mcp-endpoints/{sc.state['endpoint_id']}",
            headers=headers,
            json={"enabled": False},
        )
        response = rpc("initialize")
        expect_status(response, 403)
        client.put(
            f"/api/v1/mcp-endpoints/{sc.state['endpoint_id']}",
            headers=headers,
            json={"enabled": True},
        )
        return "disabled -> 403"

    def persistence() -> str:
        db = sqlite3.connect(DATA_DIR / "stage_phase8a.db")
        try:
            rows = db.execute(
                "SELECT COUNT(*) FROM mcp_endpoints WHERE deleted_at IS NULL"
            ).fetchone()[0]
            tools = db.execute(
                "SELECT tools FROM mcp_endpoints WHERE id = ?", (sc.state["endpoint_id"],)
            ).fetchone()[0]
        finally:
            db.close()
        expect(rows == 1, f"mcp_endpoints expected 1, got {rows}")
        expect("list_knowledge_bases" in tools, f"tools json missing: {tools}")
        return f"mcp_endpoints={rows}"

    def delete_endpoint() -> str:
        response = client.delete(
            f"/api/v1/mcp-endpoints/{sc.state['endpoint_id']}", headers=headers
        )
        expect_status(response, 200)
        gone = client.get(f"/api/v1/mcp-endpoints/{sc.state['endpoint_id']}", headers=headers)
        expect_status(gone, 404)
        return "deleted"

    sc.step("kb", "创建知识库并上传文档", prepare_kb)
    sc.step("catalog", "MCP 端点工具目录", tool_catalog)
    sc.step("create", "创建 MCP 端点", create_endpoint)
    sc.step("crud", "端点详情/更新/列表", manage_crud)
    sc.step("initialize", "MCP initialize", public_initialize)
    sc.step("tools_list", "MCP tools/list", public_tools_list)
    sc.step("tool_calls", "MCP tools/call（检索/列表）", public_tool_calls)
    sc.step("rotate", "轮换 token 后旧 token 失效", rotate_and_old_invalid)
    sc.step("disabled", "禁用端点返回 403", disabled_forbidden)
    sc.step("persistence", "数据库落盘校验", persistence)
    sc.step("delete", "删除端点", delete_endpoint)
    return sc


def scenario_phase8b(client: httpx.Client) -> Scenario:
    """Phase 8B：MCP Client 管理 API + 凭证/工具审批/持久化目录 + 测试连接。

    自举闭环：用 Phase 8A 发布的 MCP 端点作为外部服务，让 MCP Client 反向连接，
    在同一真实服务内端到端验证 initialize/tools/list/metadata。
    """
    sc = Scenario(client)
    headers = ensure_alice(client)
    base = str(client.base_url).rstrip("/")

    def prepare_kb() -> str:
        kb = create_kb(client, headers, name="MCP Client 验收库")
        upload_text(client, headers, kb["id"])
        sc.state["kb_id"] = kb["id"]
        return kb["id"]

    def create_endpoint() -> str:
        response = client.post(
            "/api/v1/mcp-endpoints",
            headers=headers,
            json={
                "name": "self-mcp-endpoint",
                "knowledge_base_ids": [sc.state["kb_id"]],
                "tools": ["list_knowledge_bases", "search_knowledge", "list_documents", "read_document"],
            },
        )
        expect_status(response, 201)
        sc.state["endpoint_id"] = response.json()["data"]["id"]
        sc.state["endpoint_token"] = response.json()["data"]["token"]
        return sc.state["endpoint_id"]

    def create_service() -> str:
        response = client.post(
            "/api/v1/mcp-services",
            headers=headers,
            json={
                "name": "self-mcp-client",
                "transport_type": "http-streamable",
                "url": f"{base}/mcp/{sc.state['endpoint_id']}",
                "auth_config": {"auth_type": "bearer", "token": sc.state["endpoint_token"]},
            },
        )
        expect_status(response, 200)
        data = response.json()["data"]
        expect("endpoint_token" not in str(data), "credential leaked in response")
        expect(data["credentials"]["token"]["configured"] is True, "token not configured")
        sc.state["service_id"] = data["id"]
        return data["id"]

    def test_connection() -> str:
        response = client.post(
            f"/api/v1/mcp-services/{sc.state['service_id']}/test", headers=headers
        )
        expect_status(response, 200)
        result = response.json()["data"]
        expect(result["success"] is True, f"test failed: {result.get('message')}")
        names = {tool["name"] for tool in result["tools"]}
        expect("search_knowledge" in names, f"tools missing search_knowledge: {names}")
        return f"tools={len(names)}"

    def list_tools() -> str:
        response = client.get(
            f"/api/v1/mcp-services/{sc.state['service_id']}/tools", headers=headers
        )
        expect_status(response, 200)
        names = {tool["name"] for tool in response.json()["data"]}
        expect("list_knowledge_bases" in names, "tools missing list_knowledge_bases")
        return f"tools={len(names)}"

    def metadata_refresh() -> str:
        response = client.post(
            f"/api/v1/mcp-services/{sc.state['service_id']}/metadata/refresh", headers=headers
        )
        expect_status(response, 200)
        data = response.json()["data"]
        expect(data["server_name"] == "weknora", f"server_name={data.get('server_name')}")
        expect(len(data["tools"]) >= 4, f"metadata tools={len(data['tools'])}")
        got = client.get(
            f"/api/v1/mcp-services/{sc.state['service_id']}/metadata", headers=headers
        )
        expect_status(got, 200)
        expect(got.json()["data"]["service_id"] == sc.state["service_id"], "metadata not persisted")
        return f"metadata tools={len(data['tools'])}"

    def credentials_flow() -> str:
        put = client.put(
            f"/api/v1/mcp-services/{sc.state['service_id']}/credentials",
            headers=headers,
            json={"client_secret": "cs-secret"},
        )
        expect_status(put, 200)
        expect(put.json()["data"]["fields"]["client_secret"]["configured"] is True, "client_secret not set")
        cleared = client.delete(
            f"/api/v1/mcp-services/{sc.state['service_id']}/credentials/client_secret", headers=headers
        )
        expect_status(cleared, 200)
        return "credentials put/clear ok"

    def tool_approval_flow() -> str:
        put = client.put(
            f"/api/v1/mcp-services/{sc.state['service_id']}/tool-approvals/search_knowledge",
            headers=headers,
            json={"require_approval": True, "enabled": False},
        )
        expect_status(put, 200)
        rows = client.get(
            f"/api/v1/mcp-services/{sc.state['service_id']}/tool-approvals", headers=headers
        )
        expect_status(rows, 200)
        row = rows.json()["data"][0]
        expect(row["tool_name"] == "search_knowledge" and row["require_approval"] is True, f"row={row}")
        return "tool approval set"

    def persistence() -> str:
        db = sqlite3.connect(DATA_DIR / "stage_phase8b.db")
        try:
            services = db.execute(
                "SELECT COUNT(*) FROM mcp_services WHERE deleted_at IS NULL"
            ).fetchone()[0]
            metadata = db.execute(
                "SELECT COUNT(*) FROM mcp_metadata WHERE service_id = ?", (sc.state["service_id"],)
            ).fetchone()[0]
            approvals = db.execute(
                "SELECT COUNT(*) FROM mcp_tool_approvals WHERE service_id = ?", (sc.state["service_id"],)
            ).fetchone()[0]
        finally:
            db.close()
        expect(services == 1, f"mcp_services expected 1, got {services}")
        expect(metadata == 1, f"mcp_metadata expected 1, got {metadata}")
        expect(approvals == 1, f"mcp_tool_approvals expected 1, got {approvals}")
        return f"services={services} metadata={metadata} approvals={approvals}"

    def delete_service() -> str:
        response = client.delete(
            f"/api/v1/mcp-services/{sc.state['service_id']}", headers=headers
        )
        expect_status(response, 200)
        gone = client.get(f"/api/v1/mcp-services/{sc.state['service_id']}", headers=headers)
        expect_status(gone, 404)
        return "deleted"

    sc.step("kb", "创建知识库并上传文档", prepare_kb)
    sc.step("endpoint", "创建自举 MCP 端点", create_endpoint)
    sc.step("service", "创建 MCP 服务（指向自举端点）", create_service)
    sc.step("test", "MCP 服务测试连接", test_connection)
    sc.step("tools", "MCP 服务工具列表", list_tools)
    sc.step("metadata", "持久化目录 refresh/get", metadata_refresh)
    sc.step("credentials", "凭证子资源 put/clear", credentials_flow)
    sc.step("approval", "工具审批策略", tool_approval_flow)
    sc.step("persistence", "数据库落盘校验", persistence)
    sc.step("delete", "删除 MCP 服务", delete_service)
    return sc


PHASE_TESTS = {
    "phase0": ["tests/e2e/test_auth_flow.py"],
    "phase1": [
        "tests/e2e/test_auth_flow.py",
        "tests/unit/test_security.py",
        "tests/unit/test_password_policy.py",
    ],
    "phase2": ["tests/e2e/test_models_api.py"],
    "phase3": ["tests/e2e/test_knowledge_api.py"],
    "phase4": ["tests/e2e/test_retrieval_api.py"],
    "phase5": ["tests/e2e/test_chat_api.py"],
    "phase6": [
        "tests/e2e/test_tags_api.py",
        "tests/e2e/test_faq_api.py",
        "tests/e2e/test_folders_api.py",
    ],
    "phase6b": ["tests/e2e/test_wiki_api.py"],
    "phase7a": ["tests/e2e/test_agent_api.py"],
    "phase7b": ["tests/e2e/test_agent_engine.py"],
    "phase8a": ["tests/e2e/test_mcp_endpoint_api.py"],
    "phase8b": ["tests/e2e/test_mcp_service_api.py"],
}

STAGES = {
    "phase0": ("Phase 0 工程骨架", scenario_phase0),
    "phase1": ("Phase 1 基础设施与认证", scenario_phase1),
    "phase2": ("Phase 2 模型网关", scenario_phase2),
    "phase3": ("Phase 3 知识库与入库", scenario_phase3),
    "phase4": ("Phase 4 混合检索", scenario_phase4),
    "phase5": ("Phase 5 对话与引用", scenario_phase5),
    "phase6": ("Phase 6A 知识组织：标签 / 文件夹 / FAQ", scenario_phase6),
    "phase6b": ("Phase 6B 知识组织：Wiki 页面树 / 版本回滚 / 图谱", scenario_phase6b),
    "phase7a": ("Phase 7A Agent：自定义 Agent CRUD + 编辑器元数据", scenario_phase7a),
    "phase7b": ("Phase 7B Agent：ReAct 引擎 + 内置工具 + agent-chat", scenario_phase7b),
    "phase8a": ("Phase 8A 集成：MCP Endpoint（Server）+ 公开 Streamable HTTP", scenario_phase8a),
    "phase8b": ("Phase 8B 集成：MCP Client（Service）管理 + 凭证/审批/目录", scenario_phase8b),
}


# --------------------------------------------------------------------------
# 报告与主流程
# --------------------------------------------------------------------------


def write_report(stage: str, title: str, results: list[Result], log_tail: str) -> None:
    passed = sum(1 for r in results if r.ok)
    total = len(results)
    lines = [
        f"# 阶段验收报告 · {stage}",
        "",
        f"- 阶段：**{title}**",
        f"- 执行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 结果：**{passed}/{total} 通过**",
        "",
        "| # | 步骤 | 结果 | 详情 |",
        "|---|---|---|---|",
    ]
    for index, item in enumerate(results, start=1):
        detail = item.detail.replace("|", "\\|").replace("\n", " ")
        if len(detail) > 160:
            detail = detail[:160] + "…"
        lines.append(f"| {index} | {item.name} | {'✅' if item.ok else '❌'} | {detail} |")

    if passed != total:
        lines += ["", "## 服务端日志（尾部）", "", "```", log_tail, "```"]

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"stage_report_{stage}.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report written: {report_path}")


def main() -> int:
    global FAKE_BASE_URL

    parser = argparse.ArgumentParser(description="阶段验收：真实启动系统并全链路验证")
    parser.add_argument("--stage", default="phase1", choices=sorted(STAGES))
    parser.add_argument("--skip-static", action="store_true", help="跳过 ruff / pytest")
    args = parser.parse_args()

    title, scenario_fn = STAGES[args.stage]
    print(f"===== 阶段验收：{args.stage} - {title} =====")

    pytest_env = os.environ.copy()
    pytest_env.update(
        {
            "DB_DRIVER": "sqlite",
            # 每次验收用独立库文件，避免与前一次/并行验收互相干扰
            "DB_PATH": f"./data/pytest_{os.getpid()}.db",
            "AUTO_MIGRATE": "false",
        }
    )

    results: list[Result] = []
    if not args.skip_static:
        results.extend(run_static_checks(pytest_env, args.stage))

    needs_model = args.stage in {"phase2", "phase3", "phase4", "phase5", "phase6", "phase7b"}
    db_path = DATA_DIR / f"stage_{args.stage}.db"
    server = Server(db_path)
    log_tail = ""
    try:
        if needs_model:
            with FakeOpenAI() as fake:
                FAKE_BASE_URL = fake.base_url
                with server:
                    with httpx.Client(base_url=server.base_url, timeout=30.0) as client:
                        scenario = scenario_fn(client)
                    results.extend(scenario.results)
        else:
            with server:
                with httpx.Client(base_url=server.base_url, timeout=30.0) as client:
                    scenario = scenario_fn(client)
                results.extend(scenario.results)
    except Exception:  # noqa: BLE001 - 启动失败需要记录而不是中断报告
        traceback.print_exc()
        results.append(Result("server", "服务启动", False, "见服务端日志"))
    finally:
        log_tail = server.log_tail()

    failed = [r for r in results if not r.ok]
    write_report(args.stage, title, results, log_tail)

    print()
    print(f"===== 结果：{len(results) - len(failed)}/{len(results)} 通过 =====")
    for item in failed:
        print(f"FAILED {item.key}: {item.detail}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
