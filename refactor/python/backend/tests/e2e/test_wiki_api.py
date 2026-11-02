"""Phase 6B 自测：Wiki 页面树 / 版本回滚 / 文件夹 / 图谱。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.helpers import register_and_login


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _create_wiki_kb(client: AsyncClient, headers: dict[str, str], name: str = "Wiki 库") -> dict:
    response = await client.post(
        "/api/v1/knowledge-bases",
        headers=headers,
        json={"name": name, "type": "wiki"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_page(
    client: AsyncClient, headers: dict[str, str], kb_id: str, slug: str, **overrides
) -> dict:
    payload = {"slug": slug, "title": slug.title().replace("-", " "), "content": f"正文 {slug}"}
    payload.update(overrides)
    response = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/wiki/pages", headers=headers, json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_create_and_get_page(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "wiki-owner@example.com")
    kb = await _create_wiki_kb(client, headers)

    page = await _create_page(
        client, headers, kb["id"], "nebula", content="Nebula 模块负责知识入库。[[graph]]"
    )
    assert page["slug"] == "nebula"
    assert page["version"] == 1
    assert page["status"] == "published"
    assert page["page_type"] == "summary"
    assert page["out_links"] == ["graph"]

    detail = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/pages/nebula", headers=headers
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["content"] == "Nebula 模块负责知识入库。[[graph]]"

    pages = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/pages", headers=headers
    )
    assert pages.status_code == 200
    assert pages.json()["data"]["total"] == 1


async def test_update_version_and_revision(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "wiki-version@example.com")
    kb = await _create_wiki_kb(client, headers)
    await _create_page(client, headers, kb["id"], "alpha", content="v1")

    updated = await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/pages/alpha",
        headers=headers,
        json={"content": "v2", "version": 1},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["version"] == 2
    assert updated.json()["data"]["content"] == "v2"

    # 无内容变化的更新不应推进版本
    same = await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/pages/alpha",
        headers=headers,
        json={"content": "v2", "version": 2},
    )
    assert same.json()["data"]["version"] == 2

    revisions = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/revisions/alpha", headers=headers
    )
    assert revisions.status_code == 200
    data = revisions.json()["data"]
    assert data["current_version"] == 2
    assert len(data["revisions"]) == 1
    assert data["revisions"][0]["version"] == 1

    content = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/revisions/alpha?content_version=1",
        headers=headers,
    )
    assert content.status_code == 200
    assert content.json()["data"]["revisions"][0]["content"] == "v1"


async def test_revert_page(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "wiki-revert@example.com")
    kb = await _create_wiki_kb(client, headers)
    await _create_page(client, headers, kb["id"], "beta", content="原始")

    await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/pages/beta",
        headers=headers,
        json={"content": "改动", "version": 1},
    )

    revert = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/revert",
        headers=headers,
        json={"slug": "beta", "version": 1},
    )
    assert revert.status_code == 200, revert.text
    data = revert.json()["data"]
    assert data["content"] == "原始"
    assert data["version"] == 3

    # 回滚到当前版本应报错
    same = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/revert",
        headers=headers,
        json={"slug": "beta", "version": 3},
    )
    assert same.status_code == 400


async def test_folders_and_move_page(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "wiki-folder@example.com")
    kb = await _create_wiki_kb(client, headers)

    folder = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/folders",
        headers=headers,
        json={"parent_id": "", "name": "归档"},
    )
    assert folder.status_code == 201, folder.text
    folder_id = folder.json()["data"]["id"]

    folders = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/folders", headers=headers
    )
    assert folders.status_code == 200
    assert folders.json()["data"]["folders"][0]["name"] == "归档"

    await _create_page(client, headers, kb["id"], "gamma")
    moved = await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/move-page",
        headers=headers,
        json={"slug": "gamma", "folder_id": folder_id},
    )
    assert moved.status_code == 200
    assert moved.json()["data"]["folder_id"] == folder_id
    assert moved.json()["data"]["category_path"] == ["归档"]

    # 文件夹内有页面时无法删除
    delete = await client.delete(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/folders/{folder_id}", headers=headers
    )
    assert delete.status_code == 409


async def test_graph_and_stats(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "wiki-graph@example.com")
    kb = await _create_wiki_kb(client, headers)

    await _create_page(client, headers, kb["id"], "a", content="[[b]]")
    await _create_page(client, headers, kb["id"], "b", content="[[c]]")
    await _create_page(client, headers, kb["id"], "c", content="")

    graph = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/graph", headers=headers
    )
    assert graph.status_code == 200
    data = graph.json()["data"]
    assert data["meta"]["total"] == 3
    assert len(data["nodes"]) == 3
    assert len(data["edges"]) == 2

    ego = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/graph?mode=ego&center=b&depth=1",
        headers=headers,
    )
    assert ego.status_code == 200
    assert ego.json()["data"]["meta"]["center"] == "b"

    stats = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/stats", headers=headers
    )
    assert stats.status_code == 200
    assert stats.json()["data"]["total_pages"] == 3
    assert stats.json()["data"]["total_links"] == 2


async def test_validation_and_errors(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "wiki-errors@example.com")
    kb = await _create_wiki_kb(client, headers)

    # 非 wiki 库被拒绝
    doc_kb = await client.post(
        "/api/v1/knowledge-bases",
        headers=headers,
        json={"name": "文档库", "type": "document"},
    )
    rejected = await client.get(
        f"/api/v1/knowledge-bases/{doc_kb.json()['data']['id']}/wiki/pages",
        headers=headers,
    )
    assert rejected.status_code == 400

    # 空 slug
    empty = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/pages",
        headers=headers,
        json={"slug": "  ", "title": "x"},
    )
    assert empty.status_code == 400

    await _create_page(client, headers, kb["id"], "dup")
    dup = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/pages",
        headers=headers,
        json={"slug": "dup", "title": "重复"},
    )
    assert dup.status_code == 409

    # 版本冲突
    await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/pages/dup",
        headers=headers,
        json={"content": "新", "version": 1},
    )
    conflict = await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/pages/dup",
        headers=headers,
        json={"content": "并发写", "version": 1},
    )
    assert conflict.status_code == 409

    # 不存在的页面
    missing = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/wiki/pages/not-exist", headers=headers
    )
    assert missing.status_code == 404
