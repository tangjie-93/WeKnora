"""Phase 6A 自测：文件夹树与知识移动 `/knowledge-bases/{id}/knowledge/folders`、`/knowledge/move`。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.knowledge_service import normalize_folder_path
from tests.helpers import create_kb, register_and_login


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _manual_knowledge(
    client: AsyncClient, headers: dict[str, str], kb_id: str, title: str
) -> dict:
    response = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/knowledge/manual",
        headers=headers,
        json={"title": title, "content": f"{title} 的正文内容，用于文件夹测试。"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("docs", "docs"),
        (" docs\\spec\\ ", "docs/spec"),
        ("a//b/../c", "a/b/c"),
        ("docs/.", "docs"),
        ("trailing.", "trailing"),
    ],
)
def test_normalize_folder_path(raw: str, expected: str) -> None:
    assert normalize_folder_path(raw) == expected


async def test_move_and_folder_tree(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "folder-owner@example.com")
    kb = await create_kb(client, headers)
    await _manual_knowledge(client, headers, kb["id"], "根目录文档")
    spec = await _manual_knowledge(client, headers, kb["id"], "规格文档")
    design = await _manual_knowledge(client, headers, kb["id"], "设计文档")

    moved = await client.post(
        "/api/v1/knowledge/move",
        headers=headers,
        json={"kb_id": kb["id"], "knowledge_ids": [spec["id"]], "folder_path": "docs/spec"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["data"]["moved_count"] == 1
    assert moved.json()["data"]["folder_path"] == "docs/spec"

    moved_design = await client.post(
        "/api/v1/knowledge/move",
        headers=headers,
        json={"kb_id": kb["id"], "knowledge_ids": [design["id"]], "folder_path": "docs"},
    )
    assert moved_design.json()["data"]["folder_path"] == "docs"

    tree = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/knowledge/folders", headers=headers
    )
    assert tree.status_code == 200, tree.text
    data = tree.json()["data"]
    assert data["root_document_count"] == 1
    assert data["total_document_count"] == 3
    assert [folder["path"] for folder in data["folders"]] == ["docs"]
    docs = data["folders"][0]
    assert docs["document_count"] == 1
    assert docs["total_count"] == 2
    assert [child["path"] for child in docs["children"]] == ["docs/spec"]
    assert docs["children"][0]["document_count"] == 1
    assert docs["children"][0]["name"] == "spec"


async def test_list_knowledge_by_folder_scope(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    headers = await register_and_login(client, "folder-scope@example.com")
    kb = await create_kb(client, headers)
    root = await _manual_knowledge(client, headers, kb["id"], "根文档")
    spec = await _manual_knowledge(client, headers, kb["id"], "规格文档")
    design = await _manual_knowledge(client, headers, kb["id"], "设计文档")

    await client.post(
        "/api/v1/knowledge/move",
        headers=headers,
        json={"kb_id": kb["id"], "knowledge_ids": [spec["id"], design["id"]], "folder_path": "docs"},
    )

    exact = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/knowledge",
        headers=headers,
        params={"folder_path": "docs", "folder_scope": "exact"},
    )
    assert sorted(item["id"] for item in exact.json()["data"]) == sorted(
        [spec["id"], design["id"]]
    )

    subtree = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/knowledge",
        headers=headers,
        params={"folder_path": "docs", "folder_scope": "subtree"},
    )
    assert sorted(item["id"] for item in subtree.json()["data"]) == sorted(
        [spec["id"], design["id"]]
    )

    plain = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/knowledge", headers=headers
    )
    folder_map = {item["id"]: item["folder_path"] for item in plain.json()["data"]}
    assert folder_map[root["id"]] == ""
    assert folder_map[design["id"]] == "docs"


async def test_rename_folder_moves_subtree(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    headers = await register_and_login(client, "folder-rename@example.com")
    kb = await create_kb(client, headers)
    child = await _manual_knowledge(client, headers, kb["id"], "子目录文档")
    parent_doc = await _manual_knowledge(client, headers, kb["id"], "父目录文档")

    await client.post(
        "/api/v1/knowledge/move",
        headers=headers,
        json={"kb_id": kb["id"], "knowledge_ids": [child["id"]], "folder_path": "docs/spec"},
    )
    await client.post(
        "/api/v1/knowledge/move",
        headers=headers,
        json={"kb_id": kb["id"], "knowledge_ids": [parent_doc["id"]], "folder_path": "docs"},
    )

    renamed = await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/knowledge/folders",
        headers=headers,
        json={"from": "docs", "to": "文档"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["data"]["moved_count"] == 2
    assert renamed.json()["data"]["folder_path"] == "文档"

    tree = (
        await client.get(f"/api/v1/knowledge-bases/{kb['id']}/knowledge/folders", headers=headers)
    ).json()["data"]
    assert [folder["path"] for folder in tree["folders"]] == ["文档"]
    assert [child_node["path"] for child_node in tree["folders"][0]["children"]] == ["文档/spec"]


async def test_invalid_folder_requests(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "folder-invalid@example.com")
    kb = await create_kb(client, headers)
    knowledge = await _manual_knowledge(client, headers, kb["id"], "文档")

    empty_ids = await client.post(
        "/api/v1/knowledge/move",
        headers=headers,
        json={"kb_id": kb["id"], "knowledge_ids": [], "folder_path": "docs"},
    )
    assert empty_ids.status_code == 400, empty_ids.text

    missing_kb = await client.post(
        "/api/v1/knowledge/move",
        headers=headers,
        json={"knowledge_ids": [knowledge["id"]], "folder_path": "docs"},
    )
    assert missing_kb.status_code == 400

    unknown_id = await client.post(
        "/api/v1/knowledge/move",
        headers=headers,
        json={"kb_id": kb["id"], "knowledge_ids": ["no-such-id"], "folder_path": "docs"},
    )
    assert unknown_id.status_code == 400

    await client.post(
        "/api/v1/knowledge/move",
        headers=headers,
        json={"kb_id": kb["id"], "knowledge_ids": [knowledge["id"]], "folder_path": "docs"},
    )
    into_child = await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/knowledge/folders",
        headers=headers,
        json={"from": "docs", "to": "docs/spec"},
    )
    assert into_child.status_code == 400, into_child.text

    empty_from = await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/knowledge/folders",
        headers=headers,
        json={"from": "", "to": "x"},
    )
    assert empty_from.status_code == 400


async def test_move_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/knowledge/move", json={"kb_id": "kb", "knowledge_ids": ["id"]}
    )
    assert response.status_code == 401
