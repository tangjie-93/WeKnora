"""Phase 6A 自测：FAQ 条目 `/knowledge-bases/{id}/faq/*`。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.helpers import create_models, register_and_login


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _create_faq_kb(client: AsyncClient, headers: dict[str, str], name: str = "FAQ 库") -> dict:
    response = await client.post(
        "/api/v1/knowledge-bases", headers=headers, json={"name": name, "type": "faq"}
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_entry(
    client: AsyncClient, headers: dict[str, str], kb_id: str, **overrides
) -> dict:
    payload = {
        "standard_question": "如何申请退款？",
        "similar_questions": ["退款怎么操作", "退款流程是什么"],
        "answers": ["在订单详情页点击申请退款，客服会在 24 小时内处理。"],
        "answer_strategy": "all",
    }
    payload.update(overrides)
    response = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/faq/entry", headers=headers, json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_create_entry_returns_seq_id_and_defaults(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    headers = await register_and_login(client, "faq-owner@example.com")
    kb = await _create_faq_kb(client, headers)

    entry = await _create_entry(client, headers, kb["id"])
    assert entry["id"] >= 1
    assert entry["knowledge_base_id"] == kb["id"]
    assert entry["standard_question"] == "如何申请退款？"
    assert entry["similar_questions"] == ["退款怎么操作", "退款流程是什么"]
    assert entry["answers"]
    assert entry["tag_name"] == "未分类"
    assert entry["is_enabled"] is True
    assert entry["is_recommended"] is True
    assert entry["index_mode"] == "question_answer"
    assert entry["chunk_id"]

    # FAQ 条目会挂在一个自动创建的 FAQ 知识下
    knowledge = await client.get(
        f"/api/v1/knowledge/{entry['knowledge_id']}", headers=headers
    )
    assert knowledge.status_code == 200
    assert knowledge.json()["data"]["type"] == "faq"

    detail = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entries/{entry['id']}", headers=headers
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["chunk_id"] == entry["chunk_id"]


async def test_entry_validation(client: AsyncClient, fake_llm_base_url: str) -> None:
    headers = await register_and_login(client, "faq-validate@example.com")
    kb = await _create_faq_kb(client, headers)

    no_answer = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entry",
        headers=headers,
        json={"standard_question": "问", "answers": []},
    )
    assert no_answer.status_code == 400, no_answer.text

    no_question = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entry",
        headers=headers,
        json={"standard_question": "  ", "answers": ["答"]},
    )
    assert no_question.status_code == 400

    bad_strategy = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entry",
        headers=headers,
        json={"standard_question": "问", "answers": ["答"], "answer_strategy": "unknown"},
    )
    assert bad_strategy.status_code == 400

    duplicate_positive = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entry",
        headers=headers,
        json={"standard_question": "问", "similar_questions": ["问"], "answers": ["答"]},
    )
    assert duplicate_positive.status_code == 400


async def test_duplicate_questions_are_rejected(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    headers = await register_and_login(client, "faq-dup@example.com")
    kb = await _create_faq_kb(client, headers)
    first = await _create_entry(client, headers, kb["id"])

    dup_standard = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entry",
        headers=headers,
        json={"standard_question": first["standard_question"], "answers": ["答"]},
    )
    assert dup_standard.status_code == 400, dup_standard.text
    assert "已存在" in dup_standard.json()["error"]["message"]

    dup_similar = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entry",
        headers=headers,
        json={"standard_question": "另一个问题", "answers": ["答"],
              "similar_questions": [first["similar_questions"][0]]},
    )
    assert dup_similar.status_code == 400


async def test_entries_work_on_faq_kb_only(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    headers = await register_and_login(client, "faq-kbtype@example.com")
    document_kb = (
        await client.post(
            "/api/v1/knowledge-bases", headers=headers, json={"name": "文档库"}
        )
    ).json()["data"]

    response = await client.post(
        f"/api/v1/knowledge-bases/{document_kb['id']}/faq/entry",
        headers=headers,
        json={"standard_question": "问", "answers": ["答"]},
    )
    assert response.status_code == 400, response.text
    assert "FAQ" in response.json()["error"]["message"]


async def test_list_entries_with_filters(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    headers = await register_and_login(client, "faq-list@example.com")
    kb = await _create_faq_kb(client, headers)
    first = await _create_entry(client, headers, kb["id"])
    second = await _create_entry(
        client,
        headers,
        kb["id"],
        standard_question="怎么开具发票？",
        similar_questions=["发票申请入口"],
        answers=["在个人中心-发票管理中申请。"],
    )

    listed = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entries",
        headers=headers,
        params={"page": 1, "page_size": 2},
    )
    assert listed.status_code == 200, listed.text
    page = listed.json()["data"]
    assert page["total"] == 2
    assert {item["id"] for item in page["data"]} == {first["id"], second["id"]}

    keyword = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entries",
        headers=headers,
        params={"keyword": "发票"},
    )
    assert [item["id"] for item in keyword.json()["data"]["data"]] == [second["id"]]

    tag = (
        await client.post(
            f"/api/v1/knowledge-bases/{kb['id']}/tags", headers=headers, json={"name": "财务"}
        )
    ).json()["data"]
    updated = await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entries/tags",
        headers=headers,
        json={"updates": {str(second["id"]): tag["seq_id"]}},
    )
    assert updated.status_code == 200, updated.text

    filtered = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entries",
        headers=headers,
        params={"tag_id": tag["seq_id"]},
    )
    assert [item["id"] for item in filtered.json()["data"]["data"]] == [second["id"]]
    assert filtered.json()["data"]["data"][0]["tag_name"] == "财务"

    disabled = await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entries/{first['id']}",
        headers=headers,
        json={**first, "is_enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["data"]["is_enabled"] is False

    enabled_only = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entries",
        headers=headers,
        params={"is_enabled": "true"},
    )
    assert [item["id"] for item in enabled_only.json()["data"]["data"]] == [second["id"]]

    bad_flag = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entries",
        headers=headers,
        params={"is_enabled": "invalid"},
    )
    assert bad_flag.status_code == 400


async def test_update_entry_and_batch_fields(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    headers = await register_and_login(client, "faq-update@example.com")
    kb = await _create_faq_kb(client, headers)
    entry = await _create_entry(client, headers, kb["id"])

    updated = await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entries/{entry['id']}",
        headers=headers,
        json={
            "standard_question": "如何申请退款？",
            "similar_questions": ["退款怎么操作"],
            "answers": ["新的答案：在订单详情页申请。"],
            "is_recommended": False,
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()["data"]
    assert body["answers"] == ["新的答案：在订单详情页申请。"]
    assert body["is_recommended"] is False

    batch = await client.put(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entries/fields",
        headers=headers,
        json={"by_id": {str(entry["id"]): {"is_enabled": False, "is_recommended": True}}},
    )
    assert batch.status_code == 200, batch.text
    assert batch.json()["data"]["updated"] == 1

    detail = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entries/{entry['id']}", headers=headers
    )
    assert detail.json()["data"]["is_enabled"] is False
    assert detail.json()["data"]["is_recommended"] is True


async def test_search_and_delete_entries(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    headers = await register_and_login(client, "faq-search@example.com")
    kb = await _create_faq_kb(client, headers)
    first = await _create_entry(client, headers, kb["id"])
    second = await _create_entry(
        client,
        headers,
        kb["id"],
        standard_question="怎么开具发票？",
        similar_questions=["发票申请入口"],
        answers=["在个人中心-发票管理中申请。"],
    )

    hit = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/search",
        headers=headers,
        json={"query_text": "发票申请入口"},
    )
    assert hit.status_code == 200, hit.text
    results = hit.json()["data"]
    assert results and results[0]["id"] == second["id"]
    assert results[0]["match_type"] == "faq"
    assert results[0]["score"] == 0.92

    exact = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/search",
        headers=headers,
        json={"query_text": "如何申请退款"},
    )
    assert exact.json()["data"][0]["id"] == first["id"]
    assert exact.json()["data"][0]["score"] == 1.0

    empty = await client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/search",
        headers=headers,
        json={"query_text": " "},
    )
    assert empty.status_code == 400

    deleted = await client.request(
        "DELETE",
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entries",
        headers=headers,
        json={"ids": [first["id"], second["id"]]},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["deleted"] == 2

    remaining = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entries", headers=headers
    )
    assert remaining.json()["data"]["total"] == 0
    assert (
        await client.get(
            f"/api/v1/knowledge-bases/{kb['id']}/faq/entries/{first['id']}", headers=headers
        )
    ).status_code == 404


async def test_faq_is_tenant_scoped(client: AsyncClient, fake_llm_base_url: str) -> None:
    owner = await register_and_login(client, "faq-scope@example.com")
    kb = await _create_faq_kb(client, owner)
    await _create_entry(client, owner, kb["id"])

    intruder = await register_and_login(client, "faq-intruder@example.com")
    response = await client.get(
        f"/api/v1/knowledge-bases/{kb['id']}/faq/entries", headers=intruder
    )
    assert response.status_code == 404


async def test_entry_indexes_with_embedding_model(
    client: AsyncClient, fake_llm_base_url: str
) -> None:
    """绑定向量模型后 FAQ 条目仍可创建，且分块带上向量元数据。"""
    headers = await register_and_login(client, "faq-embed@example.com")
    await create_models(client, headers, fake_llm_base_url)
    kb = await _create_faq_kb(client, headers)
    entry = await _create_entry(client, headers, kb["id"])

    chunks = await client.get(f"/api/v1/chunks/{entry['knowledge_id']}", headers=headers)
    assert chunks.status_code == 200, chunks.text
    rows = chunks.json()["data"]
    faq_rows = [row for row in rows if str(row.get("chunk_type")) == "faq"]
    assert faq_rows, f"faq chunk missing: {rows}"
    assert "Q: " in faq_rows[0]["content"]
