"""FAQ 条目服务：FAQ 条目即 `chunks.chunk_type='faq'`，字段存 `metadata` JSON。

对齐 Go `internal/application/service/knowledge_faq.go`：
- 条目对外 ID 用 `chunks.seq_id`
- `metadata` 存 `FAQChunkMetadata`
- `content` 由标准问/相似问/答案按索引模式拼装，`content_hash` 用于去重
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, not_found
from app.domain.entities import (
    CHUNK_FLAG_RECOMMENDED,
    CHUNK_TYPE_FAQ,
    KB_TYPE_FAQ,
    KNOWLEDGE_TYPE_FAQ,
    PARSE_COMPLETED,
    Chunk,
    Knowledge,
    KnowledgeBase,
)
from app.llm import OpenAICompatibleClient
from app.repositories import knowledge_repository, model_repository, tag_repository
from app.services import tag_service

ANSWER_STRATEGY_ALL = "all"
ANSWER_STRATEGY_RANDOM = "random"
FAQ_INDEX_MODE_QUESTION_ONLY = "question_only"
FAQ_INDEX_MODE_QUESTION_ANSWER = "question_answer"

_URL_RE = re.compile(r"https?://[^\s]+")
_SPACE_RE = re.compile(r"\s+")
# Go 端 `types.NormalizeQuestion` 负责去掉首尾标点，这里保持同一集合
_TRIM_CHARS = "？。，；、：\"“”‘’！?.,;:!:'\""


# --------------------------------------------------------------------------
# 元数据与文本处理
# --------------------------------------------------------------------------


def sanitize_strings(values: list[str] | None) -> list[str]:
    """TrimSpace + 去空 + 去重，对齐 `types.SanitizeStrings`。"""
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        trimmed = str(value).strip()
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        result.append(trimmed)
    return result


def _to_half_width(text: str) -> str:
    chars = []
    for char in text:
        if char == "\u3000":
            chars.append(" ")
        elif "\uff01" <= char <= "\uff5e":
            chars.append(chr(ord(char) - 0xFF01 + 0x21))
        else:
            chars.append(char)
    return "".join(chars)


def _collapse_spaces(text: str) -> str:
    text = _SPACE_RE.sub(" ", text)
    chars = list(text)
    out: list[str] = []
    for index, char in enumerate(chars):
        if char != " ":
            out.append(char)
            continue
        prev = chars[index - 1] if index > 0 else ""
        nxt = ""
        for cursor in range(index + 1, len(chars)):
            if chars[cursor] != " ":
                nxt = chars[cursor]
                break
        # 仅英文/数字之间保留空格，中文之间去空格
        if prev.isascii() and prev.isalnum() and nxt.isascii() and nxt.isalnum():
            out.append(" ")
    return "".join(out)


def normalize_question(text: str) -> str:
    normalized = (text or "").strip()
    if not normalized:
        return ""
    normalized = _URL_RE.sub("", normalized)
    normalized = normalized.lower()
    normalized = normalized.strip(_TRIM_CHARS)
    normalized = _to_half_width(normalized)
    return _collapse_spaces(normalized).strip()


def sanitize_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    meta["standard_question"] = str(meta.get("standard_question") or "").strip()
    meta["similar_questions"] = sanitize_strings(meta.get("similar_questions"))
    meta["negative_questions"] = sanitize_strings(meta.get("negative_questions"))
    meta["answers"] = sanitize_strings(meta.get("answers"))
    if int(meta.get("version") or 0) <= 0:
        meta["version"] = 1
    return meta


def content_hash(meta: dict[str, Any]) -> str:
    """标准问 + 相似问（排序）+ 反例（排序）+ 答案（排序），对齐 `CalculateFAQContentHash`。"""
    normalized = {
        "standard_question": normalize_question(meta.get("standard_question") or ""),
        "similar_questions": sorted(
            normalize_question(item) for item in meta.get("similar_questions") or []
        ),
        "negative_questions": sorted(
            normalize_question(item) for item in meta.get("negative_questions") or []
        ),
        "answers": sorted(sanitize_strings(meta.get("answers"))),
    }
    raw = "|".join(
        [
            normalized["standard_question"],
            ",".join(normalized["similar_questions"]),
            ",".join(normalized["negative_questions"]),
            ",".join(normalized["answers"]),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_content(meta: dict[str, Any], index_mode: str) -> str:
    """对齐 `buildFAQChunkContent`：负例与答案是否入正文取决于索引模式。"""
    lines = [f"Q: {meta.get('standard_question') or ''}"]
    similar = meta.get("similar_questions") or []
    if similar:
        lines.append("Similar Questions:")
        lines.extend(f"- {item}" for item in similar)
    if index_mode == FAQ_INDEX_MODE_QUESTION_ANSWER:
        answers = meta.get("answers") or []
        if answers:
            lines.append("Answers:")
            lines.extend(f"- {item}" for item in answers)
    return "\n".join(lines) + "\n"


def index_mode_of(kb: KnowledgeBase) -> str:
    config = kb.faq_config or {}
    mode = str(config.get("index_mode") or "")
    return mode or FAQ_INDEX_MODE_QUESTION_ANSWER


def _iso(value) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------
# 知识库与容器知识
# --------------------------------------------------------------------------


async def _require_faq_kb(
    session: AsyncSession, tenant_id: int, kb_id: str
) -> KnowledgeBase:
    kb = await knowledge_repository.get_kb(session, tenant_id, kb_id)
    if kb is None:
        raise not_found("知识库不存在")
    if kb.type != KB_TYPE_FAQ:
        raise bad_request("仅 FAQ 知识库支持该操作")
    return kb


async def _ensure_faq_knowledge(
    session: AsyncSession, tenant_id: int, kb: KnowledgeBase
) -> Knowledge:
    existing = await knowledge_repository.find_faq_knowledge(session, tenant_id, kb.id)
    if existing is not None:
        return existing
    knowledge = Knowledge(
        tenant_id=tenant_id,
        knowledge_base_id=kb.id,
        type=KNOWLEDGE_TYPE_FAQ,
        channel="web",
        title=(kb.name or "").strip() or "FAQ",
        description="FAQ 条目容器",
        source=KNOWLEDGE_TYPE_FAQ,
        parse_status=PARSE_COMPLETED,
        enable_status="enabled",
        embedding_model_id=kb.embedding_model_id or "",
    )
    return await knowledge_repository.save_knowledge(session, knowledge)


# --------------------------------------------------------------------------
# 序列化
# --------------------------------------------------------------------------


def entry_payload(
    chunk: Chunk, index_mode: str, tag_seq_map: dict[str, int], tag_name_map: dict[str, str]
) -> dict[str, Any]:
    meta = dict(chunk.metadata_json or {})
    sanitize_metadata(meta)
    return {
        "id": int(chunk.seq_id or 0),
        "chunk_id": chunk.id,
        "knowledge_id": chunk.knowledge_id,
        "knowledge_base_id": chunk.knowledge_base_id,
        "tag_id": tag_seq_map.get(chunk.tag_id or "", 0),
        "tag_name": tag_name_map.get(chunk.tag_id or "", ""),
        "is_enabled": bool(chunk.is_enabled),
        "is_recommended": bool((chunk.flags or 0) & CHUNK_FLAG_RECOMMENDED),
        "standard_question": meta.get("standard_question") or "",
        "similar_questions": meta.get("similar_questions") or [],
        "negative_questions": meta.get("negative_questions") or [],
        "answers": meta.get("answers") or [],
        "answer_strategy": meta.get("answer_strategy") or ANSWER_STRATEGY_ALL,
        "index_mode": index_mode,
        "chunk_type": chunk.chunk_type,
        "created_at": _iso(chunk.created_at),
        "updated_at": _iso(chunk.updated_at),
    }


async def _tag_maps(
    session: AsyncSession, tenant_id: int, chunks: list[Chunk]
) -> tuple[dict[str, int], dict[str, str]]:
    tag_ids = [chunk.tag_id for chunk in chunks if chunk.tag_id]
    seq_map: dict[str, int] = {}
    name_map: dict[str, str] = {}
    for tag_id in set(tag_ids):
        tag = await tag_repository.get_tag(session, tenant_id, tag_id)
        if tag is not None:
            seq_map[tag.id] = int(tag.seq_id or 0)
            name_map[tag.id] = tag.name
    return seq_map, name_map


async def _embed(
    session: AsyncSession, tenant_id: int, texts: list[str], model_id: str
) -> list[list[float]]:
    """FAQ 条目入库时尽量生成向量；模型不可用时留空，不影响条目管理。"""
    if not texts or not model_id:
        return [[] for _ in texts]
    model = await model_repository.get_model(session, tenant_id, model_id)
    if model is None:
        return [[] for _ in texts]
    try:
        return await OpenAICompatibleClient(model).embed(texts)
    except Exception:  # noqa: BLE001 - 索引失败不应阻断 FAQ 管理
        return [[] for _ in texts]


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    strategy = payload.get("answer_strategy") or ANSWER_STRATEGY_ALL
    if strategy not in (ANSWER_STRATEGY_ALL, ANSWER_STRATEGY_RANDOM):
        raise bad_request("answer_strategy 必须是 'all' 或 'random'")
    meta = sanitize_metadata(
        {
            "standard_question": payload.get("standard_question") or "",
            "similar_questions": list(payload.get("similar_questions") or []),
            "negative_questions": list(payload.get("negative_questions") or []),
            "answers": list(payload.get("answers") or []),
            "answer_strategy": strategy,
            "version": 1,
            "source": "faq",
        }
    )
    if not meta["standard_question"]:
        raise bad_request("标准问不能为空")
    if not meta["answers"]:
        raise bad_request("至少提供一个答案")
    return meta


async def _check_duplicate(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    meta: dict[str, Any],
    exclude_seq_id: int = 0,
) -> None:
    standard = meta["standard_question"]
    similar = meta["similar_questions"]

    for question in similar:
        if question == standard:
            raise bad_request(f"相似问「{question}」不能与标准问相同")
    if len(set(similar)) != len(similar):
        raise bad_request("相似问存在重复")

    positives = {standard, *similar}
    negative_seen: set[str] = set()
    for question in meta["negative_questions"]:
        if question == standard:
            raise bad_request(f"反例问题「{question}」不能与标准问相同")
        if question in positives:
            raise bad_request(f"反例问题「{question}」不能与相似问相同")
        if question in negative_seen:
            raise bad_request(f"反例问题「{question}」重复")
        negative_seen.add(question)

    others = await knowledge_repository.list_faq_chunks(session, kb_id)
    for chunk in others:
        if chunk.seq_id is not None and int(chunk.seq_id) == exclude_seq_id:
            continue
        other_meta = dict(chunk.metadata_json or {})
        sanitize_metadata(other_meta)
        existing_standard = other_meta.get("standard_question") or ""
        existing_similar = set(other_meta.get("similar_questions") or [])
        if standard and (standard == existing_standard or standard in existing_similar):
            raise bad_request(f"标准问「{standard}」已存在")
        for question in similar:
            if question == existing_standard or question in existing_similar:
                raise bad_request(f"相似问「{question}」已存在")


async def _resolve_tag_id(
    session: AsyncSession, tenant_id: int, kb_id: str, payload: dict[str, Any]
) -> str:
    tag_seq = int(payload.get("tag_id") or 0)
    if tag_seq:
        tag = await tag_repository.get_tag_by_seq_id(session, tenant_id, tag_seq)
        if tag is None or tag.knowledge_base_id != kb_id:
            raise bad_request("标签不存在或不属于当前知识库")
        return tag.id
    name = str(payload.get("tag_name") or "").strip()
    if name:
        tag = await tag_service.ensure_tag(session, tenant_id, kb_id, name)
        return tag.id
    tag = await tag_service.ensure_untagged(session, tenant_id, kb_id)
    return tag.id


async def _write_chunk(
    session: AsyncSession,
    tenant_id: int,
    kb: KnowledgeBase,
    chunk: Chunk,
    meta: dict[str, Any],
    enabled: bool,
    recommended: bool,
    tag_id: str,
) -> Chunk:
    index_mode = index_mode_of(kb)
    chunk.metadata_json = meta
    chunk.content = build_content(meta, index_mode)
    chunk.source_content = chunk.content
    chunk.content_hash = content_hash(meta)
    chunk.chunk_type = CHUNK_TYPE_FAQ
    chunk.is_enabled = enabled
    chunk.flags = CHUNK_FLAG_RECOMMENDED if recommended else 0
    chunk.tag_id = tag_id
    chunk.chunk_index = int(chunk.seq_id or 0)

    vectors = await _embed(session, tenant_id, [chunk.content], kb.embedding_model_id or "")
    if vectors and vectors[0]:
        chunk.metadata_json = {
            **meta,
            "embedding": vectors[0],
            "char_count": len(chunk.content),
        }
        chunk.status = 2
    return chunk


async def _get_faq_chunk(
    session: AsyncSession, tenant_id: int, kb_id: str, entry_seq_id: int
) -> Chunk:
    await _require_faq_kb(session, tenant_id, kb_id)
    chunk = await knowledge_repository.get_chunk_by_seq_id(session, kb_id, entry_seq_id)
    if chunk is None or chunk.chunk_type != CHUNK_TYPE_FAQ:
        raise not_found("FAQ 条目不存在")
    return chunk


# --------------------------------------------------------------------------
# 对外操作
# --------------------------------------------------------------------------


async def create_entry(
    session: AsyncSession, tenant_id: int, kb_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    kb = await _require_faq_kb(session, tenant_id, kb_id)
    meta = _sanitize_payload(payload)
    await _check_duplicate(session, tenant_id, kb_id, meta)

    knowledge = await _ensure_faq_knowledge(session, tenant_id, kb)
    tag_id = await _resolve_tag_id(session, tenant_id, kb_id, payload)
    chunk = Chunk(
        tenant_id=tenant_id,
        knowledge_base_id=kb.id,
        knowledge_id=knowledge.id,
        seq_id=await knowledge_repository.next_chunk_seq_id(session),
        start_at=0,
        end_at=0,
    )
    chunk = await _write_chunk(
        session,
        tenant_id,
        kb,
        chunk,
        meta,
        enabled=bool(payload.get("is_enabled", True)),
        recommended=bool(payload.get("is_recommended", True)),
        tag_id=tag_id,
    )
    await knowledge_repository.save_chunk(session, chunk)
    await session.commit()
    await session.refresh(chunk)
    tag_maps = await _tag_maps(session, tenant_id, [chunk])
    return entry_payload(chunk, index_mode_of(kb), tag_maps[0], tag_maps[1])


async def update_entry(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    entry_seq_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    kb = await _require_faq_kb(session, tenant_id, kb_id)
    chunk = await _get_faq_chunk(session, tenant_id, kb_id, entry_seq_id)
    meta = _sanitize_payload(payload)
    await _check_duplicate(session, tenant_id, kb_id, meta, exclude_seq_id=entry_seq_id)

    tag_id = await _resolve_tag_id(session, tenant_id, kb_id, payload)
    chunk = await _write_chunk(
        session,
        tenant_id,
        kb,
        chunk,
        meta,
        enabled=bool(payload.get("is_enabled", chunk.is_enabled)),
        recommended=bool(
            payload.get("is_recommended", bool(chunk.flags & CHUNK_FLAG_RECOMMENDED))
        ),
        tag_id=tag_id,
    )
    chunk.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(chunk)
    tag_maps = await _tag_maps(session, tenant_id, [chunk])
    return entry_payload(chunk, index_mode_of(kb), tag_maps[0], tag_maps[1])


async def get_entry(
    session: AsyncSession, tenant_id: int, kb_id: str, entry_seq_id: int
) -> dict[str, Any]:
    kb = await _require_faq_kb(session, tenant_id, kb_id)
    chunk = await _get_faq_chunk(session, tenant_id, kb_id, entry_seq_id)
    tag_maps = await _tag_maps(session, tenant_id, [chunk])
    return entry_payload(chunk, index_mode_of(kb), tag_maps[0], tag_maps[1])


async def list_entries(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    keyword: str = "",
    tag_ids: list[str] | None = None,
    is_enabled: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    kb = await _require_faq_kb(session, tenant_id, kb_id)
    page = max(1, page)
    page_size = min(max(1, page_size), 1000)

    resolved_tags: list[str] = []
    for tag_ref in tag_ids or []:
        resolved_tags.append((await tag_service.resolve_tag(session, tenant_id, kb_id, tag_ref)).id)

    chunks = await knowledge_repository.list_faq_chunks(
        session, kb_id, keyword.strip(), resolved_tags or None, is_enabled
    )
    total = len(chunks)
    start = (page - 1) * page_size
    window = chunks[start : start + page_size]
    seq_map, name_map = await _tag_maps(session, tenant_id, window)
    return tag_service.page_result(
        total,
        page,
        page_size,
        [entry_payload(chunk, index_mode_of(kb), seq_map, name_map) for chunk in window],
    )


async def delete_entries(
    session: AsyncSession, tenant_id: int, kb_id: str, entry_ids: list[int]
) -> dict[str, Any]:
    await _require_faq_kb(session, tenant_id, kb_id)
    ids = [int(item) for item in entry_ids]
    if not ids:
        raise bad_request("entry_ids 不能为空")
    now = datetime.now(UTC)
    deleted = 0
    for seq_id in ids:
        chunk = await knowledge_repository.get_chunk_by_seq_id(session, kb_id, seq_id)
        if chunk is None or chunk.chunk_type != CHUNK_TYPE_FAQ or chunk.deleted_at is not None:
            continue
        chunk.deleted_at = now
        deleted += 1
    await session.commit()
    return {"deleted": deleted}


async def update_fields_batch(
    session: AsyncSession, tenant_id: int, kb_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    await _require_faq_kb(session, tenant_id, kb_id)
    by_id = {str(key): value for key, value in (payload.get("by_id") or {}).items()}
    by_tag = {str(key): value for key, value in (payload.get("by_tag") or {}).items()}
    exclude_ids = {int(item) for item in payload.get("exclude_ids") or []}
    updated = 0

    for chunk in await knowledge_repository.list_faq_chunks(session, kb_id):
        seq_key = str(chunk.seq_id)
        changes = by_id.get(seq_key)
        if changes is None and chunk.tag_id and by_tag:
            tag = await tag_repository.get_tag(session, tenant_id, chunk.tag_id)
            if tag is not None and str(tag.seq_id) in by_tag:
                if int(chunk.seq_id or 0) in exclude_ids:
                    continue
                changes = by_tag[str(tag.seq_id)]
        if not changes:
            continue
        if changes.get("is_enabled") is not None:
            chunk.is_enabled = bool(changes["is_enabled"])
        if changes.get("is_recommended") is not None:
            chunk.flags = (
                CHUNK_FLAG_RECOMMENDED
                if bool(changes["is_recommended"])
                else (chunk.flags & ~CHUNK_FLAG_RECOMMENDED)
            )
        if changes.get("tag_id") is not None:
            tag = await tag_repository.get_tag_by_seq_id(
                session, tenant_id, int(changes["tag_id"])
            )
            if tag is None or tag.knowledge_base_id != kb_id:
                raise bad_request("标签不存在或不属于当前知识库")
            chunk.tag_id = tag.id
        chunk.updated_at = datetime.now(UTC)
        updated += 1
    await session.commit()
    return {"updated": updated}


async def update_tags_batch(
    session: AsyncSession, tenant_id: int, kb_id: str, updates: dict[str, Any]
) -> dict[str, Any]:
    await _require_faq_kb(session, tenant_id, kb_id)
    if not updates:
        raise bad_request("updates 不能为空")
    updated = 0
    for entry_key, tag_seq in updates.items():
        seq_id = int(entry_key)
        chunk = await _get_faq_chunk(session, tenant_id, kb_id, seq_id)
        target = int(tag_seq or 0)
        if target == 0:
            tag = await tag_service.ensure_untagged(session, tenant_id, kb_id)
            chunk.tag_id = tag.id
        else:
            tag = await tag_repository.get_tag_by_seq_id(session, tenant_id, target)
            if tag is None or tag.knowledge_base_id != kb_id:
                raise bad_request("标签不存在或不属于当前知识库")
            chunk.tag_id = tag.id
        chunk.updated_at = datetime.now(UTC)
        updated += 1
    await session.commit()
    return {"updated": updated}


async def search(
    session: AsyncSession, tenant_id: int, kb_id: str, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """FAQ 检索：标准问归一化精确命中 + 正文关键词兜底，分数按命中方式排序。"""
    kb = await _require_faq_kb(session, tenant_id, kb_id)
    query = normalize_question(str(payload.get("query_text") or ""))
    if not query:
        raise bad_request("query_text 不能为空")
    match_count = int(payload.get("match_count") or 10)
    only_recommended = bool(payload.get("only_recommended") or False)

    first = {int(item) for item in payload.get("first_priority_tag_ids") or []}
    second = {int(item) for item in payload.get("second_priority_tag_ids") or []}

    chunks = await knowledge_repository.list_faq_chunks(session, kb_id)
    seq_map, name_map = await _tag_maps(session, tenant_id, chunks)
    results: list[dict[str, Any]] = []
    for chunk in chunks:
        if not chunk.is_enabled:
            continue
        if only_recommended and not (chunk.flags & CHUNK_FLAG_RECOMMENDED):
            continue
        tag_seq = seq_map.get(chunk.tag_id or "", 0)
        priority = 0
        if first:
            if tag_seq not in first:
                continue
            priority = 2
        elif second:
            if tag_seq in second:
                priority = 1

        meta = dict(chunk.metadata_json or {})
        sanitize_metadata(meta)
        standard = normalize_question(meta.get("standard_question") or "")
        similar = [normalize_question(item) for item in meta.get("similar_questions") or []]
        matched = ""
        score = 0.0
        if standard == query:
            score, matched = 1.0, meta.get("standard_question") or ""
        elif query in similar:
            score, matched = 0.92, meta.get("standard_question") or ""
        elif query and query in (chunk.content or "").lower():
            score = 0.5
        if score <= 0:
            continue
        entry = entry_payload(chunk, index_mode_of(kb), seq_map, name_map)
        entry["score"] = score
        entry["match_type"] = "faq"
        entry["matched_question"] = matched
        results.append({**entry, "_priority": priority})

    results.sort(key=lambda item: (-item["_priority"], -item["score"], item["id"]))
    for item in results:
        item.pop("_priority", None)
    return results[:match_count]
