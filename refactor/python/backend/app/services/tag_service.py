"""标签服务：增删改查、名称解析、引用统计，语义对齐 Go `knowledgeTagService`。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, conflict, not_found
from app.domain.entities import KB_TYPE_DOCUMENT, UNTAGGED_TAG_NAME, KnowledgeTag
from app.repositories import knowledge_repository, tag_repository


def page_result(total: int, page: int, page_size: int, data: list[Any]) -> dict[str, Any]:
    return {"total": total, "page": page, "page_size": page_size, "data": data}


async def _require_kb(session: AsyncSession, tenant_id: int, kb_id: str):
    kb = await knowledge_repository.get_kb(session, tenant_id, kb_id)
    if kb is None:
        raise not_found("knowledge base not found")
    return kb


async def list_tags(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    keyword: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    await _require_kb(session, tenant_id, kb_id)
    page = max(1, page)
    page_size = min(max(1, page_size), 1000)
    tags, total = await tag_repository.list_tags(
        session, tenant_id, kb_id, keyword.strip(), page, page_size
    )
    counts = await tag_repository.counts_by_tag(
        session, tenant_id, kb_id, [tag.id for tag in tags]
    )
    return page_result(
        total,
        page,
        page_size,
        [tag_repository.tag_payload(tag, counts.get(tag.id)) for tag in tags],
    )


async def create_tag(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    name: str,
    color: str = "",
    sort_order: int = 0,
) -> dict[str, Any]:
    name = (name or "").strip()
    if not kb_id or not name:
        raise bad_request("知识库ID和标签名称不能为空")
    await _require_kb(session, tenant_id, kb_id)

    if await tag_repository.get_tag_by_name(session, tenant_id, kb_id, name) is not None:
        raise conflict("标签名称已存在")

    tag = KnowledgeTag(
        tenant_id=tenant_id,
        knowledge_base_id=kb_id,
        name=name,
        color=(color or "").strip(),
        # 「未分类」固定排在最前
        sort_order=-1 if name == UNTAGGED_TAG_NAME else sort_order,
        seq_id=await tag_repository.next_seq_id(session),
    )
    await tag_repository.save_tag(session, tag)
    await session.commit()
    await session.refresh(tag)
    return tag_repository.tag_payload(tag)


async def resolve_tag(
    session: AsyncSession, tenant_id: int, kb_id: str, tag_ref: str
) -> KnowledgeTag:
    """tag_ref 既可为 UUID，也可为 seq_id（前端多用 seq_id）。"""
    tag = await tag_repository.get_tag(session, tenant_id, tag_ref)
    if tag is None and str(tag_ref).isdigit():
        tag = await tag_repository.get_tag_by_seq_id(session, tenant_id, int(tag_ref))
    if tag is None or tag.knowledge_base_id != kb_id:
        raise not_found("标签不存在")
    return tag


async def update_tag(
    session: AsyncSession, tenant_id: int, kb_id: str, tag_ref: str, payload: dict[str, Any]
) -> dict[str, Any]:
    tag = await resolve_tag(session, tenant_id, kb_id, tag_ref)
    if payload.get("name") is not None:
        new_name = str(payload["name"]).strip()
        if not new_name:
            raise bad_request("标签名称不能为空")
        if new_name != tag.name:
            if await tag_repository.get_tag_by_name(
                session, tenant_id, kb_id, new_name
            ) is not None:
                raise conflict("标签名称已存在")
            tag.name = new_name
    if payload.get("color") is not None:
        tag.color = str(payload["color"]).strip()
    if payload.get("sort_order") is not None:
        tag.sort_order = int(payload["sort_order"])
    tag.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(tag)
    counts = await tag_repository.counts_by_tag(session, tenant_id, kb_id, [tag.id])
    return tag_repository.tag_payload(tag, counts.get(tag.id))


async def delete_tag(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    tag_ref: str,
    force: bool = False,
    content_only: bool = False,
    exclude_ids: list[int] | None = None,
) -> dict[str, Any]:
    kb = await _require_kb(session, tenant_id, kb_id)
    tag = await resolve_tag(session, tenant_id, kb_id, tag_ref)
    knowledge_count, chunk_count = await tag_repository.count_references(
        session, tenant_id, kb_id, tag.id
    )
    excluded = {int(item) for item in (exclude_ids or [])}

    async def clear_contents() -> None:
        if kb.type == KB_TYPE_DOCUMENT and knowledge_count > 0:
            knowledge_ids = await knowledge_repository.knowledge_ids_by_tag(
                session, tag.id
            )
            knowledge_ids = [kid for kid in knowledge_ids if kid not in excluded]
            if knowledge_ids:
                await knowledge_repository.soft_delete_chunks_by_knowledge(
                    session, kb_id, knowledge_ids
                )
                now = datetime.now(UTC)
                for knowledge_id in knowledge_ids:
                    item = await knowledge_repository.get_knowledge(
                        session, tenant_id, knowledge_id
                    )
                    if item is not None:
                        item.deleted_at = now
            await tag_repository.clear_tag_relations(session, tag.id)
        elif chunk_count > 0:
            for chunk in await knowledge_repository.chunks_by_tag(session, tag.id):
                if chunk.seq_id is not None and int(chunk.seq_id) in excluded:
                    continue
                chunk.deleted_at = datetime.now(UTC)
                chunk.tag_id = ""
            await session.flush()

    if content_only:
        await clear_contents()
        await session.commit()
        return {"success": True}

    if not force and (knowledge_count > 0 or chunk_count > 0):
        raise bad_request("标签仍有知识或FAQ条目引用，无法删除")

    if force:
        await clear_contents()

    if not excluded:
        await tag_repository.clear_tag_relations(session, tag.id)
        await tag_repository.delete_tag(session, tag)
    await session.commit()
    return {"success": True}


async def ensure_tag(
    session: AsyncSession, tenant_id: int, kb_id: str, name: str
) -> KnowledgeTag:
    """按名称取标签，不存在则创建（对齐 `FindOrCreateTagByName`）。"""
    name = (name or "").strip()
    if not name:
        raise bad_request("标签名称不能为空")
    tag = await tag_repository.get_tag_by_name(session, tenant_id, kb_id, name)
    if tag is not None:
        return tag
    await _require_kb(session, tenant_id, kb_id)
    tag = KnowledgeTag(
        tenant_id=tenant_id,
        knowledge_base_id=kb_id,
        name=name,
        color="",
        sort_order=-1 if name == UNTAGGED_TAG_NAME else 0,
        seq_id=await tag_repository.next_seq_id(session),
    )
    await tag_repository.save_tag(session, tag)
    return tag


async def ensure_untagged(session: AsyncSession, tenant_id: int, kb_id: str) -> KnowledgeTag:
    return await ensure_tag(session, tenant_id, kb_id, UNTAGGED_TAG_NAME)


async def set_knowledge_tags(
    session: AsyncSession, tenant_id: int, kb_id: str, updates: dict[str, list[str]]
) -> None:
    """批量替换知识的标签；标签必须属于同一知识库。"""
    if not updates:
        return
    items = await knowledge_repository.get_knowledge_in_kb(
        session, kb_id, list(updates.keys())
    )
    if len(items) != len(updates):
        raise bad_request("部分知识不存在或不属于该知识库")

    resolved_cache: dict[str, str] = {}
    for knowledge_id, tag_refs in updates.items():
        resolved: list[str] = []
        for tag_ref in tag_refs:
            if not tag_ref:
                continue
            if tag_ref not in resolved_cache:
                resolved_cache[tag_ref] = (await resolve_tag(
                    session, tenant_id, kb_id, tag_ref
                )).id
            tag_id = resolved_cache[tag_ref]
            if tag_id not in resolved:
                resolved.append(tag_id)
        await tag_repository.replace_knowledge_tags(session, knowledge_id, resolved)
    await session.commit()


MAX_TAG_BATCH_DOCUMENTS = 20
MAX_TAG_BATCH_TAGS = 50


async def set_knowledge_tags_from_request(
    session: AsyncSession, tenant_id: int, payload: dict[str, Any]
) -> None:
    """对齐 `applyKnowledgeTagBatch`：支持 updates，或 knowledge_ids + tag_ids。"""
    knowledge_ids = [str(item).strip() for item in payload.get("knowledge_ids") or []]
    updates: dict[str, list[str]] = {
        str(key): list(value or []) for key, value in (payload.get("updates") or {}).items()
    }
    kb_id = str(payload.get("kb_id") or "")

    if knowledge_ids:
        if updates:
            raise bad_request("knowledge_ids and updates cannot both be set")
        if payload.get("tag_ids") is None:
            raise bad_request("tag_ids is required when knowledge_ids is set")
        tag_ids = [str(item) for item in payload.get("tag_ids") or []]
        if len(knowledge_ids) > MAX_TAG_BATCH_DOCUMENTS:
            raise bad_request("at most 20 documents")
        if len(tag_ids) > MAX_TAG_BATCH_TAGS:
            raise bad_request("at most 50 tags")
        if len(set(knowledge_ids)) != len(knowledge_ids):
            raise bad_request("duplicate knowledge id")
        if not all(knowledge_ids):
            raise bad_request("knowledge id cannot be empty")
        updates = {knowledge_id: tag_ids for knowledge_id in knowledge_ids}
    elif not updates:
        raise bad_request("updates is required")

    if not kb_id:
        first = next(iter(updates))
        knowledge = await knowledge_repository.get_knowledge(session, tenant_id, first)
        if knowledge is None:
            raise not_found("knowledge not found")
        kb_id = knowledge.knowledge_base_id

    await set_knowledge_tags(session, tenant_id, kb_id, updates)
