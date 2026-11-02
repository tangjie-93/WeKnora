"""知识库 / 知识 / 分块持久化。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Chunk, Knowledge, KnowledgeBase, KnowledgeTagRelation


async def list_kbs(session: AsyncSession, tenant_id: int) -> list[KnowledgeBase]:
    stmt = (
        select(KnowledgeBase)
        .where(KnowledgeBase.tenant_id == tenant_id, KnowledgeBase.deleted_at.is_(None))
        .order_by(KnowledgeBase.created_at.desc())
    )
    return list((await session.scalars(stmt)).all())


async def get_kb(session: AsyncSession, tenant_id: int, kb_id: str) -> KnowledgeBase | None:
    stmt = select(KnowledgeBase).where(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.tenant_id == tenant_id,
        KnowledgeBase.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def save_kb(session: AsyncSession, kb: KnowledgeBase) -> KnowledgeBase:
    session.add(kb)
    await session.flush()
    return kb


async def list_knowledge(
    session: AsyncSession,
    kb_id: str,
    folder_path: str = "",
    folder_scope: str = "",
    tag_ids: list[str] | None = None,
) -> list[Knowledge]:
    stmt = select(Knowledge).where(
        Knowledge.knowledge_base_id == kb_id, Knowledge.deleted_at.is_(None)
    )
    if folder_scope == "exact":
        stmt = stmt.where(Knowledge.folder_path == folder_path)
    elif folder_scope == "subtree" and folder_path:
        stmt = stmt.where(
            or_(
                Knowledge.folder_path == folder_path,
                Knowledge.folder_path.like(f"{folder_path}/%"),
            )
        )
    if tag_ids:
        stmt = stmt.where(
            Knowledge.id.in_(
                select(KnowledgeTagRelation.knowledge_id).where(
                    KnowledgeTagRelation.tag_id.in_(tag_ids)
                )
            )
        )
    stmt = stmt.order_by(Knowledge.created_at.desc())
    return list((await session.scalars(stmt)).all())


async def get_knowledge(
    session: AsyncSession, tenant_id: int, knowledge_id: str
) -> Knowledge | None:
    stmt = select(Knowledge).where(
        Knowledge.id == knowledge_id,
        Knowledge.tenant_id == tenant_id,
        Knowledge.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def save_knowledge(session: AsyncSession, knowledge: Knowledge) -> Knowledge:
    session.add(knowledge)
    await session.flush()
    return knowledge


async def list_chunks(session: AsyncSession, knowledge_id: str) -> list[Chunk]:
    stmt = (
        select(Chunk)
        .where(Chunk.knowledge_id == knowledge_id, Chunk.deleted_at.is_(None))
        .order_by(Chunk.chunk_index)
    )
    return list((await session.scalars(stmt)).all())


async def list_kb_chunks(session: AsyncSession, kb_id: str) -> list[Chunk]:
    stmt = (
        select(Chunk)
        .where(
            Chunk.knowledge_base_id == kb_id,
            Chunk.is_enabled.is_(True),
            Chunk.deleted_at.is_(None),
        )
        .order_by(Chunk.chunk_index)
    )
    return list((await session.scalars(stmt)).all())


async def delete_chunks_of_knowledge(session: AsyncSession, knowledge_id: str) -> None:
    chunks = await list_chunks(session, knowledge_id)
    now = datetime.now(UTC)
    for chunk in chunks:
        chunk.deleted_at = now
    await session.flush()


async def folder_paths(session: AsyncSession, kb_id: str) -> list[str]:
    stmt = (
        select(Knowledge.folder_path)
        .where(Knowledge.knowledge_base_id == kb_id, Knowledge.deleted_at.is_(None))
        .group_by(Knowledge.folder_path)
        .order_by(Knowledge.folder_path)
    )
    return [path or "" for path in (await session.scalars(stmt)).all()]


async def count_under_folder(
    session: AsyncSession, kb_id: str, folder_path: str, include_subtree: bool = True
) -> int:
    stmt = select(func.count()).select_from(Knowledge).where(
        Knowledge.knowledge_base_id == kb_id, Knowledge.deleted_at.is_(None)
    )
    if folder_path:
        if include_subtree:
            stmt = stmt.where(
                or_(
                    Knowledge.folder_path.like(f"{folder_path}/%"),
                    Knowledge.folder_path == folder_path,
                )
            )
        else:
            stmt = stmt.where(Knowledge.folder_path == folder_path)
    count = await session.scalar(stmt)
    return int(count or 0)


async def count_root_knowledge(session: AsyncSession, kb_id: str) -> int:
    stmt = select(func.count()).select_from(Knowledge).where(
        Knowledge.knowledge_base_id == kb_id,
        Knowledge.deleted_at.is_(None),
        Knowledge.folder_path == "",
    )
    return int(await session.scalar(stmt) or 0)


async def move_knowledge(
    session: AsyncSession, kb_id: str, knowledge_ids: list[str], folder_path: str
) -> int:
    if not knowledge_ids:
        return 0
    result = await session.execute(
        update(Knowledge)
        .where(
            Knowledge.knowledge_base_id == kb_id,
            Knowledge.id.in_(knowledge_ids),
            Knowledge.deleted_at.is_(None),
        )
        .values(folder_path=folder_path, updated_at=datetime.now(UTC))
    )
    await session.flush()
    return int(result.rowcount or 0)


async def rename_folder(
    session: AsyncSession, kb_id: str, old_path: str, new_path: str
) -> int:
    stmt = (
        select(Knowledge)
        .where(
            Knowledge.knowledge_base_id == kb_id,
            Knowledge.deleted_at.is_(None),
            or_(
                Knowledge.folder_path == old_path,
                Knowledge.folder_path.like(f"{old_path}/%"),
            ),
        )
    )
    items = list((await session.scalars(stmt)).all())
    now = datetime.now(UTC)
    for item in items:
        if item.folder_path == old_path:
            item.folder_path = new_path
        else:
            item.folder_path = new_path + item.folder_path[len(old_path) :]
        item.updated_at = now
    await session.flush()
    return len(items)


async def get_knowledge_in_kb(
    session: AsyncSession, kb_id: str, knowledge_ids: list[str]
) -> list[Knowledge]:
    if not knowledge_ids:
        return []
    stmt = select(Knowledge).where(
        Knowledge.knowledge_base_id == kb_id,
        Knowledge.id.in_(knowledge_ids),
        Knowledge.deleted_at.is_(None),
    )
    return list((await session.scalars(stmt)).all())


async def next_chunk_seq_id(session: AsyncSession) -> int:
    current = await session.scalar(select(func.max(Chunk.seq_id)))
    return int(current or 0) + 1


async def get_chunk_by_seq_id(
    session: AsyncSession, kb_id: str, seq_id: int
) -> Chunk | None:
    stmt = select(Chunk).where(
        Chunk.knowledge_base_id == kb_id,
        Chunk.seq_id == seq_id,
        Chunk.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def list_faq_chunks(
    session: AsyncSession,
    kb_id: str,
    keyword: str = "",
    tag_ids: list[str] | None = None,
    is_enabled: bool | None = None,
) -> list[Chunk]:
    stmt = select(Chunk).where(
        Chunk.knowledge_base_id == kb_id,
        Chunk.chunk_type == "faq",
        Chunk.deleted_at.is_(None),
    )
    if keyword:
        stmt = stmt.where(Chunk.content.like(f"%{keyword}%"))
    if tag_ids:
        stmt = stmt.where(Chunk.tag_id.in_(tag_ids))
    if is_enabled is not None:
        stmt = stmt.where(Chunk.is_enabled.is_(is_enabled))
    stmt = stmt.order_by(Chunk.seq_id.asc())
    return list((await session.scalars(stmt)).all())


async def list_chunks_by_knowledge(session: AsyncSession, knowledge_id: str) -> list[Chunk]:
    return await list_chunks(session, knowledge_id)


async def find_faq_knowledge(
    session: AsyncSession, tenant_id: int, kb_id: str
) -> Knowledge | None:
    stmt = select(Knowledge).where(
        Knowledge.tenant_id == tenant_id,
        Knowledge.knowledge_base_id == kb_id,
        Knowledge.type == "faq",
        Knowledge.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def save_chunk(session: AsyncSession, chunk: Chunk) -> Chunk:
    session.add(chunk)
    await session.flush()
    return chunk


async def soft_delete_chunks_by_knowledge(
    session: AsyncSession, kb_id: str, knowledge_ids: list[str]
) -> int:
    if not knowledge_ids:
        return 0
    stmt = select(Chunk).where(
        Chunk.knowledge_base_id == kb_id,
        Chunk.knowledge_id.in_(knowledge_ids),
        Chunk.deleted_at.is_(None),
    )
    chunks = list((await session.scalars(stmt)).all())
    now = datetime.now(UTC)
    for chunk in chunks:
        chunk.deleted_at = now
    await session.flush()
    return len(chunks)


async def knowledge_ids_by_tag(session: AsyncSession, tag_id: str) -> list[str]:
    stmt = (
        select(KnowledgeTagRelation.knowledge_id)
        .join(Knowledge, Knowledge.id == KnowledgeTagRelation.knowledge_id)
        .where(KnowledgeTagRelation.tag_id == tag_id, Knowledge.deleted_at.is_(None))
    )
    return list((await session.scalars(stmt)).all())


async def chunks_by_tag(session: AsyncSession, tag_id: str) -> list[Chunk]:
    stmt = select(Chunk).where(Chunk.tag_id == tag_id, Chunk.deleted_at.is_(None))
    return list((await session.scalars(stmt)).all())
