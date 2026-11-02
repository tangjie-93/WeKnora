"""Phase 6A 自测：知识库标签 `/knowledge-bases/{id}/tags` 与知识批量打标。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
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
        json={"title": title, "content": f"{title} 的正文内容，用于标签关联测试。"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_create_list_and_paginate_tags(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    headers = await register_and_login(client, "tag-owner@example.com")
    kb = await create_kb(client, headers)

    created = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/tags",
        headers=headers,
        json={"name": "售后", "color": "#3B82F6"},
    )
    assert created.status_code == 201, created.text
    tag = created.json()["data"]
    assert tag["name"] == "售后"
    assert tag["color"] == "#3B82F6"
    assert tag["seq_id"] >= 1

    listed = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=headers, params={"page": 1, "page_size": 10}
    )
    assert listed.status_code == 200, listed.text
    page = listed.json()["data"]
    assert page["total"] == 1
    assert page["page"] == 1
    assert page["page_size"] == 10
    assert len(page["data"]) == 1
    assert page["data"][0]["knowledge_count"] == 0
    assert page["data"][0]["chunk_count"] == 0

    searched = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/tags",
        headers=headers,
        params={"keyword": "售"},
    )
    assert len(searched.json()["data"]["data"]) == 1
    missing = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/tags",
        headers=headers,
        params={"keyword": "不存在"},
    )
    assert missing.json()["data"]["total"] == 0


async def test_duplicate_tag_name_is_rejected(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    headers = await register_and_login(client, "tag-dup@example.com")
    kb = await create_kb(client, headers)
    body = {"name": "产品"}

    first = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=headers, json=body
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=headers, json=body
    )
    assert second.status_code == 409, second.text
    assert "已存在" in second.json()["error"]["message"]


async def test_untagged_tag_sorts_first(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    headers = await register_and_login(client, "tag-untagged@example.com")
    kb = await create_kb(client, headers)

    await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/tags",
        headers=headers,
        json={"name": "普通", "sort_order": 5},
    )
    untagged = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/tags",
        headers=headers,
        json={"name": "未分类", "sort_order": 9},
    )
    assert untagged.status_code == 201, untagged.text
    assert untagged.json()["data"]["sort_order"] == -1

    listed = await client.get(f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=headers)
    assert next(item["name"] for item in listed.json()["data"]["data"]) == "未分类"


async def test_update_tag_by_seq_id_and_uuid(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    headers = await register_and_login(client, "tag-update@example.com")
    kb = await create_kb(client, headers)
    tag = (
        await client.post(
            f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=headers, json={"name": "旧名"}
        )
    ).json()["data"]

    by_seq = await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/tags/{tag['seq_id']}",
        headers=headers,
        json={"name": "新名"},
    )
    assert by_seq.status_code == 200, by_seq.text
    assert by_seq.json()["data"]["name"] == "新名"
    # 未提供的字段保持不变
    assert by_seq.json()["data"]["color"] == tag["color"]

    by_uuid = await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/tags/{tag['id']}",
        headers=headers,
        json={"color": "#EF4444"},
    )
    assert by_uuid.status_code == 200
    assert by_uuid.json()["data"]["color"] == "#EF4444"

    missing = await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/tags/999999",
        headers=headers,
        json={"name": "无"},
    )
    assert missing.status_code == 404


async def test_set_knowledge_tags_and_counts(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    headers = await register_and_login(client, "tag-bind@example.com")
    kb = await create_kb(client, headers)
    knowledge = await _manual_knowledge(client, headers, kb["id"], "退款流程")
    other = await _manual_knowledge(client, headers, kb["id"], "物流说明")

    tag = (
        await client.post(
            f"/api/v1/knowledge-bases/{kb['id']}/tags",
            headers=headers,
            json={"name": "售后"},
        )
    ).json()["data"]
    finance = (
        await client.post(
            f"/api/v1/knowledge-bases/{kb['id']}/tags",
            headers=headers,
            json={"name": "财务"},
        )
    ).json()["data"]

    response = await client.put(
        "/api/v1/knowledge/tags",
        headers=headers,
        json={"kb_id": kb["id"], "updates": {knowledge["id"]: [tag["id"], finance["id"]]}},
    )
    assert response.status_code == 200, response.text

    counts = (
        await client.get(f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=headers)
    ).json()["data"]["data"]
    by_name = {item["name"]: item for item in counts}
    assert by_name["售后"]["knowledge_count"] == 1
    assert by_name["财务"]["knowledge_count"] == 1

    listing = (
        await client.get(f"/api/v1/knowledge-bases/{kb['id']}/knowledge", headers=headers)
    ).json()["data"]
    tagged = next(item for item in listing if item["id"] == knowledge["id"])
    assert set(tagged["tag_ids"]) == {tag["id"], finance["id"]}
    untagged_item = next(item for item in listing if item["id"] == other["id"])
    assert untagged_item["tag_ids"] == []

    # 空列表表示清空
    cleared = await client.put(
        "/api/v1/knowledge/tags",
        headers=headers,
        json={"kb_id": kb["id"], "knowledge_ids": [knowledge["id"]], "tag_ids": []},
    )
    assert cleared.status_code == 200, cleared.text
    listing = (
        await client.get(f"/api/v1/knowledge-bases/{kb['id']}/knowledge", headers=headers)
    ).json()["data"]
    assert next(i for i in listing if i["id"] == knowledge["id"])["tag_ids"] == []


async def test_delete_tag_requires_force_when_referenced(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    headers = await register_and_login(client, "tag-delete@example.com")
    kb = await create_kb(client, headers)
    knowledge = await _manual_knowledge(client, headers, kb["id"], "退换货")
    tag = (
        await client.post(
            f"/api/v1/knowledge-bases/{kb['id']}/tags",
            headers=headers,
            json={"name": "售后"},
        )
    ).json()["data"]
    await client.put(
        "/api/v1/knowledge/tags",
        headers=headers,
        json={"kb_id": kb["id"], "updates": {knowledge["id"]: [tag["id"]]}},
    )

    blocked = await client.delete(
        f"/api/v1/knowledge-bases/{kb['id']}/tags/{tag['seq_id']}", headers=headers
    )
    assert blocked.status_code == 400, blocked.text
    assert "无法删除" in blocked.json()["error"]["message"]

    forced = await client.delete(
        f"/api/v1/knowledge-bases/{kb['id']}/tags/{tag['seq_id']}",
        headers=headers,
        params={"force": "true"},
    )
    assert forced.status_code == 200, forced.text

    listed = await client.get(f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=headers)
    assert listed.json()["data"]["total"] == 0

    # 删除后可以重建同名标签（唯一索引不含 deleted_at）
    rebuilt = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=headers, json={"name": "售后"}
    )
    assert rebuilt.status_code == 201, rebuilt.text


async def test_tags_are_tenant_scoped(client: AsyncClient, fake_llm_base_url: str) -> None:
    owner = await register_and_login(client, "tag-scope@example.com")
    kb = await create_kb(client, owner)
    await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=owner, json={"name": "私有"}
    )

    intruder = await register_and_login(client, "tag-intruder@example.com")
    assert (
        await client.get(f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=intruder)
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=intruder, json={"name": "越权"}
        )
    ).status_code == 404


async def test_create_tag_requires_name(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "tag-empty@example.com")
    kb = await create_kb(client, headers)
    response = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=headers, json={"name": "   "}
    )
    assert response.status_code == 400, response.text


async def test_tags_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/knowledge-bases/any/tags")).status_code == 401
