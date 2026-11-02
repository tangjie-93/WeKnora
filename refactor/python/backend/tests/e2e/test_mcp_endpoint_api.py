"""Phase 8A 自测：MCP Endpoint 管理 API + 公开 MCP Streamable HTTP 面。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.helpers import create_kb, register_and_login, upload_sample


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _create_endpoint(client: AsyncClient, headers: dict[str, str], **overrides) -> dict:
    payload: dict = {"name": "workspace-mcp"}
    payload.update(overrides)
    response = await client.post("/api/v1/mcp-endpoints", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _rpc(client: AsyncClient, token: str, endpoint_id: str, msg_id, method: str, params=None):
    response = await client.post(
        f"/mcp/{endpoint_id}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}},
    )
    return response


# --------------------------------------------------------------------------
# 管理 API
# --------------------------------------------------------------------------


async def test_tool_catalog(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "mcp-catalog@example.com")
    response = await client.get("/api/v1/mcp-endpoints/tools", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["groups"] == ["retrieve", "chat", "wiki", "ingest"]
    names = {item["name"] for item in data["tools"]}
    assert "list_knowledge_bases" in names
    assert "search_knowledge" in names
    assert "ask" in names
    assert "add_document" in names
    assert "add_document" not in data["default_tools"]


async def test_create_get_list(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "mcp-crud@example.com")
    created = await _create_endpoint(client, headers, description="验收端点")
    assert created["token"].startswith("mcp_")
    assert created["token_hint"] == created["token"][:12]
    assert created["path"] == f"/mcp/{created['id']}"
    assert "list_knowledge_bases" in created["tools"]

    detail = await client.get(f"/api/v1/mcp-endpoints/{created['id']}", headers=headers)
    assert detail.status_code == 200
    assert "token" not in detail.json()["data"]

    listing = await client.get("/api/v1/mcp-endpoints", headers=headers)
    assert listing.status_code == 200
    assert any(item["id"] == created["id"] for item in listing.json()["data"])


async def test_update_and_rotate(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "mcp-update@example.com")
    created = await _create_endpoint(client, headers)
    old_token = created["token"]

    updated = await client.put(
        f"/api/v1/mcp-endpoints/{created['id']}",
        headers=headers,
        json={"name": "改名端点", "tools": ["list_knowledge_bases", "search_knowledge"]},
    )
    assert updated.status_code == 200, updated.text
    data = updated.json()["data"]
    assert data["name"] == "改名端点"
    assert data["tools"] == ["list_knowledge_bases", "search_knowledge"]

    rotated = await client.post(
        f"/api/v1/mcp-endpoints/{created['id']}/rotate-token", headers=headers
    )
    assert rotated.status_code == 200
    new_token = rotated.json()["data"]["token"]
    assert new_token != old_token

    # 旧 token 立即失效
    bad = await _rpc(client, old_token, created["id"], 1, "initialize")
    assert bad.status_code == 401


async def test_delete_endpoint(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "mcp-delete@example.com")
    created = await _create_endpoint(client, headers)
    deleted = await client.delete(f"/api/v1/mcp-endpoints/{created['id']}", headers=headers)
    assert deleted.status_code == 200
    gone = await client.get(f"/api/v1/mcp-endpoints/{created['id']}", headers=headers)
    assert gone.status_code == 404


async def test_create_requires_auth(client: AsyncClient, fake_llm_base_url: str) -> None:
    response = await client.post("/api/v1/mcp-endpoints", json={"name": "x"})
    assert response.status_code == 401


async def test_cross_tenant_not_found(client: AsyncClient, fake_llm_base_url: str) -> None:
    alice = await register_and_login(client, "mcp-alice@example.com")
    created = await _create_endpoint(client, alice)
    bob = await register_and_login(client, "mcp-bob@example.com")
    response = await client.get(f"/api/v1/mcp-endpoints/{created['id']}", headers=bob)
    assert response.status_code == 404


# --------------------------------------------------------------------------
# 公开 MCP 面
# --------------------------------------------------------------------------


async def _prepare_kb(client: AsyncClient, headers: dict[str, str]) -> str:
    kb = await create_kb(client, headers, name="MCP 验收库")
    await upload_sample(client, headers, kb["id"])
    return kb["id"]


async def test_initialize_and_tools_list(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "mcp-proto@example.com")
    created = await _create_endpoint(client, headers)

    init = await _rpc(client, created["token"], created["id"], 1, "initialize", {"protocolVersion": "2024-11-05"})
    assert init.status_code == 200, init.text
    result = init.json()["result"]
    assert result["serverInfo"]["name"] == "weknora"
    assert result["protocolVersion"] == "2024-11-05"

    listing = await _rpc(client, created["token"], created["id"], 2, "tools/list")
    assert listing.status_code == 200
    names = {tool["name"] for tool in listing.json()["result"]["tools"]}
    assert "list_knowledge_bases" in names
    assert "add_document" not in names  # 默认白名单不含写工具


async def test_public_tool_calls(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "mcp-tools@example.com")
    kb_id = await _prepare_kb(client, headers)
    created = await _create_endpoint(client, headers, knowledge_base_ids=[kb_id])

    kbs = await _rpc(client, created["token"], created["id"], 1, "tools/call", {"name": "list_knowledge_bases"})
    assert kbs.status_code == 200
    content = kbs.json()["result"]["content"][0]["text"]
    assert kb_id in content

    search = await _rpc(
        client, created["token"], created["id"], 2, "tools/call",
        {"name": "search_knowledge", "arguments": {"query": "Nebula"}},
    )
    assert search.status_code == 200
    assert "Nebula" in search.json()["result"]["content"][0]["text"]

    docs = await _rpc(
        client, created["token"], created["id"], 3, "tools/call",
        {"name": "list_documents", "arguments": {"knowledge_base_id": kb_id}},
    )
    assert docs.status_code == 200
    assert "guide.txt" in docs.json()["result"]["content"][0]["text"]

    grep = await _rpc(
        client, created["token"], created["id"], 4, "tools/call",
        {"name": "grep_chunks", "arguments": {"query": "8080|PostgreSQL"}},
    )
    assert grep.status_code == 200
    assert "results" in grep.json()["result"]["content"][0]["text"]


async def test_public_invalid_token(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "mcp-auth@example.com")
    created = await _create_endpoint(client, headers)
    bad = await _rpc(client, "mcp_wrong_token", created["id"], 1, "initialize")
    assert bad.status_code == 401


async def test_public_disabled(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "mcp-disabled@example.com")
    created = await _create_endpoint(client, headers)
    await client.put(
        f"/api/v1/mcp-endpoints/{created['id']}", headers=headers, json={"enabled": False}
    )
    response = await _rpc(client, created["token"], created["id"], 1, "initialize")
    assert response.status_code == 403


async def test_tool_not_enabled_is_error(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "mcp-scope@example.com")
    created = await _create_endpoint(client, headers, tools=["list_knowledge_bases"])
    response = await _rpc(
        client, created["token"], created["id"], 1, "tools/call",
        {"name": "search_knowledge", "arguments": {"query": "x"}},
    )
    assert response.status_code == 200
    assert response.json()["result"]["isError"] is True
