"""Phase 2 自测：模型网关 `/api/v1/models`。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.helpers import create_models, register_and_login


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_models_lifecycle(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "owner@example.com", "owner")

    empty = await client.get("/api/v1/models", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["data"] == []

    chat, embedding = await create_models(client, headers, fake_llm_base_url)

    assert chat["type"] == "chat"
    assert chat["is_default"] is True
    assert chat["parameters"]["api_key"] == "******"
    assert embedding["parameters"]["embedding_parameters"]["dimension"] == 64

    listed = await client.get("/api/v1/models", headers=headers)
    assert [item["name"] for item in listed.json()["data"]] == ["fake-chat", "fake-embedding"]

    detail = await client.get(f"/api/v1/models/{chat['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["name"] == "fake-chat"

    updated = await client.put(
        f"/api/v1/models/{chat['id']}",
        headers=headers,
        json={"display_name": "更新后的模型", "parameters": {"api_key": "******"}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["display_name"] == "更新后的模型"
    # 掩码值不能被写回数据库
    assert updated.json()["data"]["parameters"]["api_key"] == "******"

    again = await client.get(f"/api/v1/models/{chat['id']}", headers=headers)
    assert again.json()["data"]["display_name"] == "更新后的模型"


async def test_model_connectivity(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "owner@example.com")
    chat, embedding = await create_models(client, headers, fake_llm_base_url)

    chat_result = await client.post(f"/api/v1/models/{chat['id']}/test", headers=headers)
    assert chat_result.status_code == 200, chat_result.text
    chat_data = chat_result.json()["data"]
    assert chat_data["ok"] is True
    assert chat_data["reply"] == "pong"

    embedding_result = await client.post(
        f"/api/v1/models/{embedding['id']}/test", headers=headers
    )
    assert embedding_result.status_code == 200, embedding_result.text
    embedding_data = embedding_result.json()["data"]
    assert embedding_data["ok"] is True
    assert embedding_data["dimension"] == 64


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "bad", "type": "audio-magic", "parameters": {"base_url": "http://x/v1"}},
        {"name": "bad", "type": "chat", "parameters": {}},
        {"name": "", "type": "chat", "parameters": {"base_url": "http://x/v1"}},
    ],
)
async def test_create_model_validation(client: AsyncClient, payload: dict) -> None:
    headers = await register_and_login(client, "owner@example.com")
    response = await client.post("/api/v1/models", headers=headers, json=payload)
    assert response.status_code == 400, response.text
    assert response.json()["success"] is False
    assert response.json()["error"]["message"]


async def test_switch_default_chat_model(client: AsyncClient, fake_llm_base_url: str) -> None:
    """切换默认对话模型后，必须且只能有一个 chat 模型是默认。"""
    headers = await register_and_login(client, "owner@example.com")
    first, _ = await create_models(client, headers, fake_llm_base_url)
    second = await client.post(
        "/api/v1/models",
        headers=headers,
        json={
            "name": "fake-chat-2",
            "type": "chat",
            "is_default": False,
            "parameters": {"base_url": fake_llm_base_url, "api_key": "fake-key"},
        },
    )
    assert second.status_code == 201, second.text
    second_id = second.json()["data"]["id"]

    switched = await client.put(
        f"/api/v1/models/{second_id}", headers=headers, json={"is_default": True}
    )
    assert switched.status_code == 200, switched.text

    models = (await client.get("/api/v1/models", headers=headers)).json()["data"]
    defaults = [item for item in models if item["type"] == "chat" and item["is_default"]]
    assert [item["id"] for item in defaults] == [second_id]
    assert next(item for item in models if item["id"] == first["id"])["is_default"] is False


async def test_models_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/models")).status_code == 401
    assert (await client.post("/api/v1/models", json={"name": "x"})).status_code == 401


async def test_delete_model(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "owner@example.com")
    chat, _ = await create_models(client, headers, fake_llm_base_url)

    deleted = await client.delete(f"/api/v1/models/{chat['id']}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    assert (await client.get(f"/api/v1/models/{chat['id']}", headers=headers)).status_code == 404

    remaining = await client.get("/api/v1/models", headers=headers)
    assert [item["name"] for item in remaining.json()["data"]] == ["fake-embedding"]
