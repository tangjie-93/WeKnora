"""Phase 7A 自测：Agent CRUD + 编辑器元数据（工具/类型预设/占位符）。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.helpers import register_and_login


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _create_agent(client: AsyncClient, headers: dict[str, str], **overrides) -> dict:
    payload = {"name": "研究助手", "description": "用于测试"}
    payload.update(overrides)
    response = await client.post("/api/v1/agents", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_list_includes_builtin_agents(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "agent-owner@example.com")
    response = await client.get("/api/v1/agents", headers=headers)
    assert response.status_code == 200, response.text
    items = response.json()["data"]
    ids = {item["id"] for item in items}
    assert "builtin-quick-answer" in ids
    assert "builtin-smart-reasoning" in ids
    builtin = next(item for item in items if item["id"] == "builtin-quick-answer")
    assert builtin["is_builtin"] is True


async def test_create_and_get_agent(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "agent-create@example.com")
    agent = await _create_agent(client, headers, config={"agent_mode": "smart-reasoning"})

    assert agent["name"] == "研究助手"
    assert agent["is_builtin"] is False
    assert agent["config"]["agent_mode"] == "smart-reasoning"
    assert agent["config"]["max_iterations"] == 10
    assert agent["config"]["multi_turn_enabled"] is True
    assert "search_knowledge" in agent["config"]["allowed_tools"]

    detail = await client.get(f"/api/v1/agents/{agent['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["name"] == "研究助手"


async def test_update_agent(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "agent-update@example.com")
    agent = await _create_agent(client, headers)

    updated = await client.put(
        f"/api/v1/agents/{agent['id']}",
        headers=headers,
        json={
            "name": "改名后的助手",
            "description": "新描述",
            "config": {"agent_mode": "quick-answer", "temperature": 0.3},
        },
    )
    assert updated.status_code == 200, updated.text
    data = updated.json()["data"]
    assert data["name"] == "改名后的助手"
    assert data["config"]["agent_mode"] == "quick-answer"
    assert data["config"]["temperature"] == 0.3


async def test_patch_agent(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "agent-patch@example.com")
    agent = await _create_agent(client, headers, config={"agent_mode": "quick-answer"})

    patched = await client.patch(
        f"/api/v1/agents/{agent['id']}",
        headers=headers,
        json={"agent_mode": "smart-reasoning", "system_prompt": "你是一个助手"},
    )
    assert patched.status_code == 200, patched.text
    data = patched.json()["data"]
    assert data["config"]["agent_mode"] == "smart-reasoning"
    assert data["config"]["system_prompt"] == "你是一个助手"
    # 未修改字段保持
    assert data["name"] == "研究助手"


async def test_delete_and_copy_agent(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "agent-delete@example.com")
    agent = await _create_agent(client, headers)

    copied = await client.post(f"/api/v1/agents/{agent['id']}/copy", headers=headers)
    assert copied.status_code == 201, copied.text
    assert copied.json()["data"]["name"] == "研究助手（副本）"
    assert copied.json()["data"]["id"] != agent["id"]

    deleted = await client.delete(f"/api/v1/agents/{agent['id']}", headers=headers)
    assert deleted.status_code == 200

    missing = await client.get(f"/api/v1/agents/{agent['id']}", headers=headers)
    assert missing.status_code == 404


async def test_builtin_agent_protected(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "agent-builtin@example.com")

    put = await client.put(
        "/api/v1/agents/builtin-quick-answer",
        headers=headers,
        json={"name": "x", "config": {}},
    )
    assert put.status_code == 400

    delete = await client.delete("/api/v1/agents/builtin-quick-answer", headers=headers)
    assert delete.status_code == 400


async def test_metadata_endpoints(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "agent-meta@example.com")

    tools = await client.get("/api/v1/agents/tools", headers=headers)
    assert tools.status_code == 200
    catalog = tools.json()["data"]
    names = {tool["name"] for tool in catalog["tools"]}
    assert "search_knowledge" in names
    assert "wiki_read_page" in names
    assert catalog["default_tools"]
    assert "web_search" in catalog["switch_managed_tools"]

    presets = await client.get("/api/v1/agents/type-presets", headers=headers)
    assert presets.status_code == 200
    preset_ids = {item["id"] for item in presets.json()["data"]}
    assert {"rag-qa", "wiki-qa", "hybrid-rag-wiki", "custom"} <= preset_ids

    placeholders = await client.get("/api/v1/agents/placeholders", headers=headers)
    assert placeholders.status_code == 200
    data = placeholders.json()["data"]
    assert "all" in data
    assert "system_prompt" in data
    assert any(item["name"] == "query" for item in data["all"])


async def test_validation_errors(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "agent-validate@example.com")

    no_name = await client.post("/api/v1/agents", headers=headers, json={"name": "  "})
    assert no_name.status_code == 400

    bad_mode = await client.post(
        "/api/v1/agents",
        headers=headers,
        json={"name": "x", "config": {"agent_mode": "bogus"}},
    )
    assert bad_mode.status_code == 400

    bad_kb_mode = await client.post(
        "/api/v1/agents",
        headers=headers,
        json={"name": "x", "config": {"kb_selection_mode": "bogus"}},
    )
    assert bad_kb_mode.status_code == 400

    long_avatar = await client.post(
        "/api/v1/agents", headers=headers, json={"name": "x", "avatar": "a" * 100}
    )
    assert long_avatar.status_code == 400

    # 未认证
    unauthorized = await client.get("/api/v1/agents")
    assert unauthorized.status_code == 401
