"""Phase 4 自测：混合检索 `/knowledge-bases/:id/hybrid-search` 与 `/knowledge-search`。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.helpers import create_kb, create_models, register_and_login, upload_sample


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def searchable_kb(client: AsyncClient, fake_llm_base_url: str):
    headers = await register_and_login(client, "owner@example.com")
    await create_models(client, headers, fake_llm_base_url)
    kb = await create_kb(client, headers, name="检索库")
    await upload_sample(client, headers, kb["id"])
    return headers, kb


async def test_hybrid_search_returns_ranked_hits(searchable_kb, client: AsyncClient) -> None:
    headers, kb = searchable_kb

    response = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/hybrid-search",
        headers=headers,
        json={"query": "Nebula 默认端口是多少", "top_k": 3},
    )
    assert response.status_code == 200, response.text
    hits = response.json()["data"]
    assert hits, "混合检索必须返回结果"

    first = hits[0]
    for key in ("content", "score", "vector_score", "keyword_score", "chunk_index", "knowledge_id"):
        assert key in first, f"缺少字段 {key}"
    assert first["score"] > 0
    assert first["vector_score"] > 0
    assert any("8080" in hit["content"] for hit in hits)
    scores = [hit["score"] for hit in hits]
    assert scores == sorted(scores, reverse=True), "结果必须按得分降序"


async def test_hybrid_search_top_k(searchable_kb, client: AsyncClient) -> None:
    headers, kb = searchable_kb
    response = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/hybrid-search",
        headers=headers,
        json={"query": "Nebula", "top_k": 1},
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


async def test_knowledge_search_endpoint(searchable_kb, client: AsyncClient) -> None:
    headers, kb = searchable_kb
    response = await client.post(
        "/api/v1/knowledge-search",
        headers=headers,
        json={"query": "部署需要哪些组件", "knowledge_base_id": kb["id"]},
    )
    assert response.status_code == 200, response.text
    hits = response.json()["data"]
    assert hits
    assert any("PostgreSQL" in hit["content"] for hit in hits)


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/knowledge-bases/{kb}/hybrid-search", {"query": "   "}),
        ("/api/v1/knowledge-search", {"query": "端口"}),
        ("/api/v1/knowledge-search", {"query": "", "knowledge_base_id": "{kb}"}),
    ],
)
async def test_search_rejects_bad_input(
    searchable_kb, client: AsyncClient, path: str, payload: dict
) -> None:
    headers, kb = searchable_kb
    payload = {key: (kb["id"] if value == "{kb}" else value) for key, value in payload.items()}
    response = await client.post(path.format(kb=kb["id"]), headers=headers, json=payload)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["message"]


async def test_search_unknown_kb(client: AsyncClient) -> None:
    headers = await register_and_login(client, "owner@example.com")
    response = await client.post(
        "/api/v1/knowledge-bases/not-exist/hybrid-search",
        headers=headers,
        json={"query": "端口"},
    )
    assert response.status_code == 404


async def test_search_requires_auth(client: AsyncClient) -> None:
    assert (
        await client.post("/api/v1/knowledge-search", json={"query": "x"})
    ).status_code == 401
