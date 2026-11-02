"""测试基座：使用 SQLite 文件库，避免依赖 PostgreSQL。"""

from __future__ import annotations

import importlib.util
import os
import socket
import threading
import time
from pathlib import Path

os.environ.setdefault("DB_DRIVER", "sqlite")
# 每个 pytest 进程独立库文件，避免并行跑阶段验收时互相清表
os.environ.setdefault("DB_PATH", f"./data/test_{os.getpid()}.db")
os.environ.setdefault("AUTO_MIGRATE", "false")
os.environ.setdefault("JWT_SECRET", "test-secret-for-pytest-only-32-bytes")

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.database import engine
from app.domain.entities import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
async def prepare_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _load_fake_app():
    path = BACKEND_DIR / "scripts" / "fake_openai.py"
    spec = importlib.util.spec_from_file_location("fake_openai_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


def _build_fake_mcp_app():
    """本地假 MCP 服务器（HTTP-streamable），供 MCP Client 测试连接。"""
    app = FastAPI()
    tools = [
        {
            "name": "echo",
            "description": "Echo back the input",
            "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        },
        {
            "name": "add",
            "description": "Add two numbers",
            "inputSchema": {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]},
        },
    ]
    resources = [
        {"uri": "resource://hello", "name": "hello", "description": "a test resource", "mimeType": "text/plain"},
    ]

    @app.post("/mcp")
    async def mcp(request: Request):
        body = await request.json()
        method = body.get("method")
        msg_id = body.get("id")
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "fake-mcp", "version": "1.0.0", "description": "fake mcp server"},
                "instructions": "use echo",
            }
        elif method == "notifications/initialized":
            return JSONResponse(status_code=202, content={})
        elif method == "tools/list":
            result = {"tools": tools}
        elif method == "resources/list":
            result = {"resources": resources}
        elif method == "tools/call":
            result = {"content": [{"type": "text", "text": "ok"}], "isError": False}
        else:
            result = {}
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    return app


@pytest.fixture(scope="session")
def fake_mcp_base_url() -> str:
    """在独立线程里启动本地假 MCP 服务器，供 MCP Client 测试连接。"""
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(_build_fake_mcp_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 30
    while time.time() < deadline and not server.started:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("fake MCP server failed to start")

    yield f"http://127.0.0.1:{port}/mcp"

    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="session")
def fake_llm_base_url() -> str:
    """在独立线程里启动本地假 OpenAI，供模型/检索/对话测试使用。"""
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(_load_fake_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 30
    while time.time() < deadline and not server.started:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("fake OpenAI server failed to start")

    yield f"http://127.0.0.1:{port}/v1"

    server.should_exit = True
    thread.join(timeout=10)

