"""标签持久化：knowledge_tags 与 knowledge_tag_relations。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Chunk, Knowledge, KnowledgeTag, KnowledgeTagRelation


async def next_seq_id(session: AsyncSession) -> int:
    current = await session.scalar(select(func.max(KnowledgeTag.seq_id)))
    return int(current or 0) + 1


async def list_tags(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    keyword: str = "",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[KnowledgeTag], int]:
    conditions = [
        KnowledgeTag.tenant_id == tenant_id,
        KnowledgeTag.knowledge_base_id == kb_id,
        KnowledgeTag.deleted_at.is_(None),
    ]
    if keyword:
        conditions.append(KnowledgeTag.name.like(f"%{keyword}%"))

    total = await session.scalar(
        select(func.count()).select_from(KnowledgeTag).where(*conditions)
    )
    stmt = (
        select(KnowledgeTag)
        .where(*conditions)
        .order_by(
            KnowledgeTag.sort_order.asc(),
            KnowledgeTag.created_at.desc(),
            KnowledgeTag.seq_id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await session.scalars(stmt)).all()), int(total or 0)


async def get_tag(session: AsyncSession, tenant_id: int, tag_id: str) -> KnowledgeTag | None:
    stmt = select(KnowledgeTag).where(
        KnowledgeTag.id == tag_id,
        KnowledgeTag.tenant_id == tenant_id,
        KnowledgeTag.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def get_tag_by_seq_id(
    session: AsyncSession, tenant_id: int, seq_id: int
) -> KnowledgeTag | None:
    stmt = select(KnowledgeTag).where(
        KnowledgeTag.seq_id == seq_id,
        KnowledgeTag.tenant_id == tenant_id,
        KnowledgeTag.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def get_tag_by_name(
    session: AsyncSession, tenant_id: int, kb_id: str, name: str
) -> KnowledgeTag | None:
    stmt = select(KnowledgeTag).where(
        KnowledgeTag.tenant_id == tenant_id,
        KnowledgeTag.knowledge_base_id == kb_id,
        KnowledgeTag.name == name,
        KnowledgeTag.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def save_tag(session: AsyncSession, tag: KnowledgeTag) -> KnowledgeTag:
    session.add(tag)
    await session.flush()
    return tag


async def delete_tag(session: AsyncSession, tag: KnowledgeTag) -> None:
    """硬删标签行：knowledge_tags 的 (tenant_id, kb, name) 唯一索引不含 deleted_at，
    软删会让同名的标签永远无法重建。"""
    await session.delete(tag)
    await session.flush()


async def counts_by_tag(
    session: AsyncSession, tenant_id: int, kb_id: str, tag_ids: list[str]
) -> dict[str, dict[str, int]]:
    """返回 {tag_id: {knowledge_count, chunk_count}}。"""
    result = {tag_id: {"knowledge_count": 0, "chunk_count": 0} for tag_id in tag_ids}
    if not tag_ids:
        return result

    rows = (
        await session.execute(
            select(KnowledgeTagRelation.tag_id, func.count())
            .join(Knowledge, Knowledge.id == KnowledgeTagRelation.knowledge_id)
            .where(
                KnowledgeTagRelation.tag_id.in_(tag_ids),
                Knowledge.deleted_at.is_(None),
                Knowledge.tenant_id == tenant_id,
                Knowledge.knowledge_base_id == kb_id,
            )
            .group_by(KnowledgeTagRelation.tag_id)
        )
    ).all()
    for tag_id, count in rows:
        result.setdefault(tag_id, {"knowledge_count": 0, "chunk_count": 0})
        result[tag_id]["knowledge_count"] = int(count)

    rows = (
        await session.execute(
            select(Chunk.tag_id, func.count())
            .where(
                Chunk.tenant_id == tenant_id,
                Chunk.knowledge_base_id == kb_id,
                Chunk.deleted_at.is_(None),
                Chunk.tag_id.in_(tag_ids),
            )
            .group_by(Chunk.tag_id)
        )
    ).all()
    for tag_id, count in rows:
        result.setdefault(tag_id, {"knowledge_count": 0, "chunk_count": 0})
        result[tag_id]["chunk_count"] = int(count)
    return result


async def count_references(
    session: AsyncSession, tenant_id: int, kb_id: str, tag_id: str
) -> tuple[int, int]:
    counts = await counts_by_tag(session, tenant_id, kb_id, [tag_id])
    item = counts.get(tag_id, {})
    return int(item.get("knowledge_count", 0)), int(item.get("chunk_count", 0))


async def tag_ids_for_knowledge(session: AsyncSession, knowledge_ids: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {knowledge_id: [] for knowledge_id in knowledge_ids}
    if not knowledge_ids:
        return result
    rows = (
        await session.execute(
            select(KnowledgeTagRelation.knowledge_id, KnowledgeTagRelation.tag_id)
            .where(KnowledgeTagRelation.knowledge_id.in_(knowledge_ids))
            .order_by(KnowledgeTagRelation.created_at)
        )
    ).all()
    for knowledge_id, tag_id in rows:
        result.setdefault(knowledge_id, []).append(tag_id)
    return result


async def replace_knowledge_tags(
    session: AsyncSession, knowledge_id: str, tag_ids: list[str]
) -> None:
    existing = (
        await session.execute(
            select(KnowledgeTagRelation).where(
                KnowledgeTagRelation.knowledge_id == knowledge_id
            )
        )
    ).scalars()
    for relation in existing:
        await session.delete(relation)
    now = datetime.now(UTC)
    for tag_id in tag_ids:
        session.add(
            KnowledgeTagRelation(knowledge_id=knowledge_id, tag_id=tag_id, created_at=now)
        )
    await session.flush()


async def clear_tag_relations(session: AsyncSession, tag_id: str) -> None:
    relations = (
        await session.execute(
            select(KnowledgeTagRelation).where(KnowledgeTagRelation.tag_id == tag_id)
        )
    ).scalars()
    for relation in relations:
        await session.delete(relation)
    await session.flush()


def tag_payload(tag: KnowledgeTag, stats: dict[str, Any] | None = None) -> dict[str, Any]:
    counts = stats or {}
    return {
        "id": tag.id,
        "seq_id": int(tag.seq_id or 0),
        "tenant_id": tag.tenant_id,
        "knowledge_base_id": tag.knowledge_base_id,
        "name": tag.name,
        "color": tag.color or "",
        "sort_order": tag.sort_order,
        "knowledge_count": int(counts.get("knowledge_count", 0)),
        "chunk_count": int(counts.get("chunk_count", 0)),
        "created_at": _iso(tag.created_at),
        "updated_at": _iso(tag.updated_at),
    }


def _iso(value) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat().replace("+00:00", "Z")
