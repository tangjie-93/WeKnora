"""Phase 7B 自测：ReAct 引擎 + 内置工具 + agent-chat SSE 全链路。"""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.helpers import create_kb, create_models, register_and_login, upload_sample


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _create_agent(client: AsyncClient, headers: dict[str, str]) -> dict:
    response = await client.post(
        "/api/v1/agents",
        headers=headers,
        json={
            "name": "检索助手",
            "description": "ReAct 测试",
            "config": {
                "agent_mode": "smart-reasoning",
                "allowed_tools": ["search_knowledge", "read_document", "list_documents"],
                "max_iterations": 5,
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_agent_chat_stream_with_tools(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "agent-chat@example.com")
    await create_models(client, headers, fake_llm_base_url)
    kb = await create_kb(client, headers, name="Agent 问答库")
    await upload_sample(client, headers, kb["id"])
    agent = await _create_agent(client, headers)

    session = (
        await client.post(
            "/api/v1/sessions",
            headers=headers,
            json={"title": "Agent 会话", "knowledge_base_id": kb["id"]},
        )
    ).json()["data"]

    events: list[dict] = []
    async with client.stream(
        "POST",
        f"/api/v1/agent-chat/{session['id']}",
        headers=headers,
        json={"query": "Nebula 默认端口是多少", "agent_id": agent["id"]},
    ) as response:
        assert response.status_code == 200, await response.aread()
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    types = [event["response_type"] for event in events]
    assert "agent_query" in types
    # ReAct 引擎应至少调用一次工具
    assert "tool_call" in types
    assert "tool_result" in types
    assert "answer" in types
    assert types[-1] == "complete"

    complete = events[-1]
    assert complete["data"]["content"]
    assert complete["data"]["tool_calls"], "期望记录工具调用历史"
    assert complete["data"]["tool_calls"][0]["name"] == "search_knowledge"

    # 落库 user + assistant 消息
    loaded = await client.get(f"/api/v1/messages/{session['id']}/load", headers=headers)
    assert loaded.status_code == 200
    rows = loaded.json()["data"]
    assert [row["role"] for row in rows] == ["user", "assistant"]
    assert rows[1]["content"] == complete["data"]["content"]


async def test_agent_chat_falls_back_to_builtin(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "agent-fallback@example.com")
    await create_models(client, headers, fake_llm_base_url)
    kb = await create_kb(client, headers, name="回退库")
    await upload_sample(client, headers, kb["id"])

    session = (
        await client.post(
            "/api/v1/sessions",
            headers=headers,
            json={"knowledge_base_id": kb["id"]},
        )
    ).json()["data"]

    # 不带 agent_id 时回退到内置 quick-answer
    events: list[dict] = []
    async with client.stream(
        "POST",
        f"/api/v1/agent-chat/{session['id']}",
        headers=headers,
        json={"query": "部署需要什么"},
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    assert events[-1]["response_type"] == "complete"
    assert events[-1]["data"]["content"]


async def test_agent_chat_requires_agent_kb(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "agent-nokb@example.com")
    await create_models(client, headers, fake_llm_base_url)
    agent = await _create_agent(client, headers)

    # 会话不关联 KB，agent 也未配置 knowledge_bases：检索工具会返回「没有可检索的知识库」
    session = (
        await client.post("/api/v1/sessions", headers=headers, json={"title": "无库"})
    ).json()["data"]

    events: list[dict] = []
    async with client.stream(
        "POST",
        f"/api/v1/agent-chat/{session['id']}",
        headers=headers,
        json={"query": "你好", "agent_id": agent["id"]},
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    assert events[-1]["response_type"] == "complete"


async def test_agent_chat_requires_query(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "agent-query@example.com")
    await create_models(client, headers, fake_llm_base_url)
    session = (
        await client.post("/api/v1/sessions", headers=headers, json={})
    ).json()["data"]

    response = await client.post(
        f"/api/v1/agent-chat/{session['id']}", headers=headers, json={"query": "  "}
    )
    assert response.status_code == 400


async def test_agent_chat_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/api/v1/agent-chat/any", json={"query": "x"})
    assert response.status_code == 401
