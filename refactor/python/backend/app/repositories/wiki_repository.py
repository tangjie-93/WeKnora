"""Wiki 页面 / 版本 / 文件夹持久化。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import WikiFolder, WikiPage, WikiPageRevision


async def get_page_by_slug(session: AsyncSession, kb_id: str, slug: str) -> WikiPage | None:
    stmt = select(WikiPage).where(
        WikiPage.knowledge_base_id == kb_id,
        WikiPage.slug == slug,
        WikiPage.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def list_pages(
    session: AsyncSession,
    kb_id: str,
    page_types: list[str] | None = None,
    status: str = "",
    query: str = "",
    folder_id: str | None = None,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[WikiPage], int]:
    conditions = [WikiPage.knowledge_base_id == kb_id, WikiPage.deleted_at.is_(None)]
    if page_types:
        conditions.append(WikiPage.page_type.in_(page_types))
    if status:
        conditions.append(WikiPage.status == status)
    if folder_id is not None:
        conditions.append(WikiPage.folder_id == folder_id)
    if query:
        like = f"%{query.strip()}%"
        conditions.append(or_(WikiPage.title.like(like), WikiPage.content.like(like)))

    total = int(
        await session.scalar(select(func.count()).select_from(WikiPage).where(*conditions)) or 0
    )

    column = {
        "title": WikiPage.title,
        "created_at": WikiPage.created_at,
        "updated_at": WikiPage.updated_at,
    }.get(sort_by, WikiPage.updated_at)
    ordering = column.asc() if sort_order == "asc" else column.desc()
    stmt = (
        select(WikiPage)
        .where(*conditions)
        .order_by(ordering, WikiPage.slug.asc())
        .offset(offset)
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all()), total


async def list_all_pages(session: AsyncSession, kb_id: str) -> list[WikiPage]:
    stmt = (
        select(WikiPage)
        .where(WikiPage.knowledge_base_id == kb_id, WikiPage.deleted_at.is_(None))
        .order_by(WikiPage.slug.asc())
    )
    return list((await session.scalars(stmt)).all())


async def list_pages_by_slugs(
    session: AsyncSession, kb_id: str, slugs: list[str]
) -> list[WikiPage]:
    if not slugs:
        return []
    stmt = select(WikiPage).where(
        WikiPage.knowledge_base_id == kb_id,
        WikiPage.slug.in_(slugs),
        WikiPage.deleted_at.is_(None),
    )
    return list((await session.scalars(stmt)).all())


async def save_page(session: AsyncSession, page: WikiPage) -> WikiPage:
    session.add(page)
    await session.flush()
    return page


async def count_pages_by_type(session: AsyncSession, kb_id: str) -> dict[str, int]:
    stmt = (
        select(WikiPage.page_type, func.count())
        .where(WikiPage.knowledge_base_id == kb_id, WikiPage.deleted_at.is_(None))
        .group_by(WikiPage.page_type)
    )
    return {str(row[0]): int(row[1]) for row in (await session.execute(stmt)).all()}


# ---------------------------------------------------------------- 版本快照


async def save_revision(
    session: AsyncSession, revision: WikiPageRevision
) -> WikiPageRevision:
    session.add(revision)
    await session.flush()
    return revision


async def list_revisions(
    session: AsyncSession, kb_id: str, page_id: str, limit: int = 50, offset: int = 0
) -> tuple[list[WikiPageRevision], int]:
    conditions = [
        WikiPageRevision.knowledge_base_id == kb_id,
        WikiPageRevision.page_id == page_id,
    ]
    total = int(
        await session.scalar(
            select(func.count()).select_from(WikiPageRevision).where(*conditions)
        )
        or 0
    )
    stmt = (
        select(WikiPageRevision)
        .where(*conditions)
        .order_by(WikiPageRevision.version.desc())
        .offset(offset)
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all()), total


async def get_revision(
    session: AsyncSession, kb_id: str, page_id: str, version: int
) -> WikiPageRevision | None:
    stmt = select(WikiPageRevision).where(
        WikiPageRevision.knowledge_base_id == kb_id,
        WikiPageRevision.page_id == page_id,
        WikiPageRevision.version == version,
    )
    return await session.scalar(stmt)


async def delete_revisions_by_page(session: AsyncSession, page_id: str) -> None:
    await session.execute(
        delete(WikiPageRevision).where(WikiPageRevision.page_id == page_id)
    )
    await session.flush()


async def prune_revisions(
    session: AsyncSession,
    page_id: str,
    keep_from_version: int,
    prunable_sources: list[str],
    hard_keep_from_version: int,
) -> int:
    """两级保留：机器版本按 keep_from_version 截断，所有版本按硬上限截断。"""
    stmt = select(WikiPageRevision).where(WikiPageRevision.page_id == page_id)
    rows = list((await session.scalars(stmt)).all())
    removed = 0
    for row in rows:
        prunable = keep_from_version > 0 and row.version < keep_from_version and (
            row.edit_source or ""
        ) in prunable_sources
        hard = hard_keep_from_version > 0 and row.version < hard_keep_from_version
        if prunable or hard:
            await session.delete(row)
            removed += 1
    if removed:
        await session.flush()
    return removed


# ---------------------------------------------------------------- 文件夹


async def get_folder(
    session: AsyncSession, kb_id: str, folder_id: str
) -> WikiFolder | None:
    if not folder_id:
        return None
    stmt = select(WikiFolder).where(
        WikiFolder.id == folder_id,
        WikiFolder.knowledge_base_id == kb_id,
        WikiFolder.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def list_all_folders(session: AsyncSession, kb_id: str) -> list[WikiFolder]:
    stmt = (
        select(WikiFolder)
        .where(WikiFolder.knowledge_base_id == kb_id, WikiFolder.deleted_at.is_(None))
        .order_by(WikiFolder.path.asc(), WikiFolder.sort_order.asc(), WikiFolder.name.asc())
    )
    return list((await session.scalars(stmt)).all())


async def get_child_folder_by_name(
    session: AsyncSession, kb_id: str, parent_id: str, name: str
) -> WikiFolder | None:
    stmt = select(WikiFolder).where(
        WikiFolder.knowledge_base_id == kb_id,
        WikiFolder.parent_id == parent_id,
        WikiFolder.name == name,
        WikiFolder.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def save_folder(session: AsyncSession, folder: WikiFolder) -> WikiFolder:
    session.add(folder)
    await session.flush()
    return folder


async def count_pages_in_folder(
    session: AsyncSession, kb_id: str, folder_id: str
) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(WikiPage)
            .where(
                WikiPage.knowledge_base_id == kb_id,
                WikiPage.folder_id == folder_id,
                WikiPage.deleted_at.is_(None),
            )
        )
        or 0
    )


async def count_pages_by_folder(
    session: AsyncSession, kb_id: str, page_types: list[str] | None = None
) -> dict[str, int]:
    conditions = [WikiPage.knowledge_base_id == kb_id, WikiPage.deleted_at.is_(None)]
    if page_types:
        conditions.append(WikiPage.page_type.in_(page_types))
    stmt = (
        select(WikiPage.folder_id, func.count())
        .where(*conditions)
        .group_by(WikiPage.folder_id)
    )
    return {str(row[0] or ""): int(row[1]) for row in (await session.execute(stmt)).all()}



async def pages_in_folder(session: AsyncSession, kb_id: str, folder_id: str) -> list[WikiPage]:
    stmt = select(WikiPage).where(
        WikiPage.knowledge_base_id == kb_id,
        WikiPage.folder_id == folder_id,
        WikiPage.deleted_at.is_(None),
    )
    return list((await session.scalars(stmt)).all())


async def soft_delete_folder(session: AsyncSession, folder: WikiFolder) -> None:
    folder.deleted_at = datetime.now(UTC)
    await session.flush()


async def count_folders_children(session: AsyncSession, kb_id: str, parent_id: str) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(WikiFolder)
            .where(
                WikiFolder.knowledge_base_id == kb_id,
                WikiFolder.parent_id == parent_id,
                WikiFolder.deleted_at.is_(None),
            )
        )
        or 0
    )
