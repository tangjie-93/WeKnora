"""Phase 3 自测：知识库与入库 `/api/v1/knowledge-bases`、`/knowledge`、`/chunks`。"""

from __future__ import annotations

import os
import sqlite3

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.helpers import create_kb, create_models, register_and_login, upload_sample


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_create_kb_uses_default_embedding_model(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    headers = await register_and_login(client, "owner@example.com")
    _, embedding = await create_models(client, headers, fake_llm_base_url)

    kb = await create_kb(client, headers)
    assert kb["name"] == "测试知识库"
    assert kb["embedding_model_id"] == embedding["id"]
    assert kb["chunking_config"]["chunk_size"] == 120

    listed = await client.get("/api/v1/knowledge-bases", headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["data"]] == [kb["id"]]

    detail = await client.get(f"/api/v1/knowledge-bases/{kb['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["name"] == kb["name"]


@pytest.mark.parametrize("payload", [{}, {"name": "   "}])
async def test_create_kb_requires_name(client: AsyncClient, payload: dict) -> None:
    headers = await register_and_login(client, "owner@example.com")
    response = await client.post("/api/v1/knowledge-bases", headers=headers, json=payload)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["message"]


async def test_upload_parse_and_chunks(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "owner@example.com")
    await create_models(client, headers, fake_llm_base_url)
    kb = await create_kb(client, headers)

    knowledge = await upload_sample(client, headers, kb["id"])
    assert knowledge["parse_status"] == "completed"
    assert knowledge["title"] == "guide.txt"
    assert knowledge["file_size"] > 0

    detail = await client.get(f"/api/v1/knowledge/{knowledge['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["parse_status"] == "completed"

    listing = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/knowledge", headers=headers
    )
    assert listing.status_code == 200
    assert len(listing.json()["data"]) == 1

    chunks = await client.get(f"/api/v1/chunks/{knowledge['id']}", headers=headers)
    assert chunks.status_code == 200
    rows = chunks.json()["data"]
    assert len(rows) >= 2
    assert any("8080" in row["content"] for row in rows)

    # 向量必须落库到 chunks.metadata.embedding
    db = sqlite3.connect(os.environ["DB_PATH"])
    stored = db.execute(
        "select count(1) from chunks where deleted_at is null and metadata like '%embedding%'"
    ).fetchone()[0]
    db.close()
    assert stored == len(rows)


async def test_reparse_rebuilds_chunks(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "owner@example.com")
    await create_models(client, headers, fake_llm_base_url)
    kb = await create_kb(client, headers)
    knowledge = await upload_sample(client, headers, kb["id"])

    response = await client.post(f"/api/v1/knowledge/{knowledge['id']}/reparse", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["parse_status"] == "completed"

    chunks = await client.get(f"/api/v1/chunks/{knowledge['id']}", headers=headers)
    assert len(chunks.json()["data"]) >= 2


async def test_manual_knowledge_and_delete(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "owner@example.com")
    await create_models(client, headers, fake_llm_base_url)
    kb = await create_kb(client, headers)

    created = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/knowledge/manual",
        headers=headers,
        json={"title": "常见问题", "content": "问：默认端口？\n答：8080。"},
    )
    assert created.status_code == 201, created.text
    manual = created.json()["data"]
    assert manual["type"] == "manual"
    assert manual["parse_status"] == "completed"

    deleted = await client.delete(f"/api/v1/knowledge/{manual['id']}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    listing = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/knowledge", headers=headers
    )
    assert listing.json()["data"] == []
    assert (
        await client.get(f"/api/v1/knowledge/{manual['id']}", headers=headers)
    ).status_code == 404


async def test_cross_tenant_kb_is_invisible(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    owner = await register_and_login(client, "owner@example.com")
    await create_models(client, owner, fake_llm_base_url)
    kb = await create_kb(client, owner)

    other = await register_and_login(client, "intruder@example.com")
    assert (
        await client.get(f"/api/v1/knowledge-bases/{kb['id']}", headers=other)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/knowledge-bases/{kb['id']}/knowledge", headers=other)
    ).status_code == 404


async def test_knowledge_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/knowledge-bases")).status_code == 401
