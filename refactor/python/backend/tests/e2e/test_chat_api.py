"""Phase 5 自测：会话 CRUD、SSE 流式问答、引用与消息落库。"""

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


@pytest.fixture
async def chat_ready(client: AsyncClient, fake_llm_base_url: str):
    headers = await register_and_login(client, "owner@example.com")
    await create_models(client, headers, fake_llm_base_url)
    kb = await create_kb(client, headers, name="问答库")
    await upload_sample(client, headers, kb["id"])
    return headers, kb


async def test_session_lifecycle(chat_ready, client: AsyncClient) -> None:
    headers, kb = chat_ready

    created = await client.post(
        "/api/v1/sessions",
        headers=headers,
        json={"title": "问答测试", "knowledge_base_id": kb["id"]},
    )
    assert created.status_code == 201, created.text
    session = created.json()["data"]
    assert session["title"] == "问答测试"
    assert session["knowledge_base_id"] == kb["id"]

    default = await client.post("/api/v1/sessions", headers=headers, json={})
    assert default.status_code == 201
    assert default.json()["data"]["title"] == "新会话"

    listed = await client.get("/api/v1/sessions", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 2

    detail = await client.get(f"/api/v1/sessions/{session['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["title"] == "问答测试"

    updated = await client.put(
        f"/api/v1/sessions/{session['id']}",
        headers=headers,
        json={"title": "改名后的会话"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["title"] == "改名后的会话"

    deleted = await client.delete(f"/api/v1/sessions/{session['id']}", headers=headers)
    assert deleted.status_code == 200
    assert (
        await client.get(f"/api/v1/sessions/{session['id']}", headers=headers)
    ).status_code == 404
    assert len((await client.get("/api/v1/sessions", headers=headers)).json()["data"]) == 1


async def test_sse_stream_and_references(chat_ready, client: AsyncClient) -> None:
    headers, kb = chat_ready
    session = (
        await client.post(
            "/api/v1/sessions",
            headers=headers,
            json={"title": "流式", "knowledge_base_id": kb["id"]},
        )
    ).json()["data"]

    events: list[dict] = []
    async with client.stream(
        "POST",
        f"/api/v1/knowledge-chat/{session['id']}",
        headers=headers,
        json={"query": "Nebula 默认端口是多少"},
    ) as response:
        assert response.status_code == 200, await response.aread()
        assert "text/event-stream" in response.headers["content-type"]
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    types = [event["response_type"] for event in events]
    assert "agent_query" in types
    assert "references" in types
    assert "answer" in types
    assert types[-1] == "complete"

    answer = "".join(
        str(event["data"].get("content") or "")
        for event in events
        if event["response_type"] == "answer" and "content" in event["data"]
    )
    assert answer.startswith("根据知识库资料")

    complete = events[-1]
    assert complete["data"]["knowledge_references"]
    assert complete["assistant_message_id"]
    assert isinstance(complete["data"]["total_duration_ms"], int)

    # 历史消息落库
    loaded = await client.get(f"/api/v1/messages/{session['id']}/load", headers=headers)
    assert loaded.status_code == 200
    rows = loaded.json()["data"]
    assert [row["role"] for row in rows] == ["user", "assistant"]
    assert rows[1]["content"] == answer
    assert rows[1]["knowledge_references"]


async def test_stream_requires_query(chat_ready, client: AsyncClient) -> None:
    headers, kb = chat_ready
    session = (
        await client.post("/api/v1/sessions", headers=headers, json={"knowledge_base_id": kb["id"]})
    ).json()["data"]

    response = await client.post(
        f"/api/v1/knowledge-chat/{session['id']}", headers=headers, json={"query": ""}
    )
    assert response.status_code == 400
    assert response.json()["error"]["message"]


async def test_clear_messages(chat_ready, client: AsyncClient) -> None:
    headers, kb = chat_ready
    session = (
        await client.post("/api/v1/sessions", headers=headers, json={"knowledge_base_id": kb["id"]})
    ).json()["data"]

    async with client.stream(
        "POST",
        f"/api/v1/knowledge-chat/{session['id']}",
        headers=headers,
        json={"query": "Nebula 默认端口是多少"},
    ) as response:
        assert response.status_code == 200
        async for _ in response.aiter_lines():
            pass

    cleared = await client.delete(f"/api/v1/sessions/{session['id']}/messages", headers=headers)
    assert cleared.status_code == 200
    assert cleared.json()["data"]["deleted"] == 2
    loaded = await client.get(f"/api/v1/messages/{session['id']}/load", headers=headers)
    assert loaded.json()["data"] == []


async def test_session_is_tenant_private(chat_ready, client: AsyncClient) -> None:
    headers, kb = chat_ready
    session = (
        await client.post("/api/v1/sessions", headers=headers, json={"knowledge_base_id": kb["id"]})
    ).json()["data"]

    other = await register_and_login(client, "intruder@example.com")
    assert (
        await client.get(f"/api/v1/sessions/{session['id']}", headers=other)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/messages/{session['id']}/load", headers=other)
    ).status_code == 404


async def test_chat_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/sessions")).status_code == 401
    assert (
        await client.post("/api/v1/knowledge-chat/any", json={"query": "x"})
    ).status_code == 401
