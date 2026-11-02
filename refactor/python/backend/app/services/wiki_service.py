"""Wiki 服务：页面树、页面 CRUD、版本回滚、图谱与统计。

对齐 Go `internal/application/service/wiki_page.go` 的关键语义：
- `version` 只在标题/正文/摘要/类型/状态真正变化时自增，并快照旧版本
- 文件夹是页面归属的唯一来源，`category_path` / `wiki_path` / `depth` 为派生缓存
- 页面正文中的 `[[slug]]` / `[[slug|显示名]]` 解析为出链，并维护目标页的入链
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, conflict, not_found
from app.domain.entities import (
    KB_TYPE_WIKI,
    WIKI_EDIT_SOURCE_REVERT,
    WIKI_EDIT_SOURCE_USER,
    WIKI_PAGE_TYPE_SUMMARY,
    WIKI_PAGE_TYPES,
    WIKI_STATUS_PUBLISHED,
    WIKI_STATUSES,
    WikiFolder,
    WikiPage,
    WikiPageRevision,
)
from app.repositories import knowledge_repository, wiki_repository

WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
WIKI_PRUNE_SOURCES = ("", "pipeline")
WIKI_MAX_REVISIONS_PER_PAGE = 50
WIKI_MAX_REVISIONS_HARD_CAP = 200
GRAPH_DEFAULT_LIMIT = 500
GRAPH_MAX_LIMIT = 2000
GRAPH_MAX_DEPTH = 3


# --------------------------------------------------------------------------
# 序列化与文本处理
# --------------------------------------------------------------------------


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat().replace("+00:00", "Z")


def page_payload(page: WikiPage) -> dict[str, Any]:
    return {
        "id": page.id,
        "tenant_id": page.tenant_id,
        "knowledge_base_id": page.knowledge_base_id,
        "slug": page.slug,
        "title": page.title or "",
        "page_type": page.page_type,
        "status": page.status,
        "content": page.content or "",
        "summary": page.summary or "",
        "parent_slug": page.parent_slug or "",
        "folder_id": page.folder_id or "",
        "category_path": list(page.category_path or []),
        "wiki_path": page.wiki_path or "",
        "depth": int(page.depth or 0),
        "sort_order": int(page.sort_order or 0),
        "source_refs": list(page.source_refs or []),
        "chunk_refs": list(page.chunk_refs or []),
        "in_links": list(page.in_links or []),
        "out_links": list(page.out_links or []),
        "aliases": list(page.aliases or []),
        "page_metadata": dict(page.page_metadata or {}),
        "version": int(page.version or 1),
        "last_edit_source": page.last_edit_source or "",
        "last_editor_id": page.last_editor_id or "",
        "created_at": _iso(page.created_at),
        "updated_at": _iso(page.updated_at),
    }


def summary_payload(page: WikiPage) -> dict[str, Any]:
    data = page_payload(page)
    data.pop("content", None)
    return data


def revision_payload(revision: WikiPageRevision, include_content: bool = False) -> dict[str, Any]:
    data = {
        "id": revision.id,
        "tenant_id": revision.tenant_id,
        "knowledge_base_id": revision.knowledge_base_id,
        "page_id": revision.page_id,
        "slug": revision.slug,
        "version": int(revision.version or 1),
        "title": revision.title or "",
        "page_type": revision.page_type,
        "status": revision.status,
        "summary": revision.summary or "",
        "aliases": list(revision.aliases or []),
        "edit_source": revision.edit_source or "",
        "editor_id": revision.editor_id or "",
        "edited_at": _iso(revision.edited_at),
        "created_at": _iso(revision.created_at),
    }
    if include_content:
        data["content"] = revision.content or ""
    return data


def folder_payload(folder: WikiFolder) -> dict[str, Any]:
    return {
        "id": folder.id,
        "tenant_id": folder.tenant_id,
        "knowledge_base_id": folder.knowledge_base_id,
        "parent_id": folder.parent_id or "",
        "name": folder.name,
        "path": folder.path or "",
        "depth": int(folder.depth or 0),
        "sort_order": int(folder.sort_order or 0),
        "created_at": _iso(folder.created_at),
        "updated_at": _iso(folder.updated_at),
    }


def normalize_slug(slug: str) -> str:
    return (slug or "").strip().lower().replace(" ", "-")


def parse_out_links(content: str) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for match in WIKI_LINK_RE.finditer(content or ""):
        slug = match.group(1).strip()
        if "|" in slug:
            slug = slug.split("|", 1)[0].strip()
        slug = normalize_slug(slug)
        if slug and slug not in seen:
            seen.add(slug)
            links.append(slug)
    return links


def _folder_segments(path: str) -> list[str]:
    return [item.strip() for item in (path or "").split("/") if item.strip()]


def _build_wiki_path(page_type: str, category_path: list[str], title: str) -> str:
    parts = [page_type] if page_type else []
    parts.extend(category_path)
    if title:
        parts.append(title)
    return "/".join(parts)


def _normalize_hierarchy(page: WikiPage) -> None:
    page.parent_slug = (page.parent_slug or "").strip()
    path = [item.strip() for item in (page.category_path or []) if str(item).strip()]
    page.category_path = path
    page.depth = len(path)
    display = (page.title or "").strip() or (page.slug or "").strip()
    page.wiki_path = _build_wiki_path(page.page_type, path, display)


def is_wiki_enabled(kb) -> bool:
    if kb.type == KB_TYPE_WIKI:
        return True
    return bool((kb.indexing_strategy or {}).get("wiki_enabled"))


# --------------------------------------------------------------------------
# 校验与公共查询
# --------------------------------------------------------------------------


async def _require_wiki_kb(session: AsyncSession, tenant_id: int, kb_id: str):
    kb = await knowledge_repository.get_kb(session, tenant_id, kb_id)
    if kb is None:
        raise not_found("知识库不存在")
    if not is_wiki_enabled(kb):
        raise bad_request("该知识库未启用 Wiki 功能")
    return kb


async def _get_page(session: AsyncSession, kb_id: str, slug: str) -> WikiPage:
    page = await wiki_repository.get_page_by_slug(session, kb_id, normalize_slug(slug))
    if page is None:
        raise not_found("Wiki 页面不存在")
    return page


def _validate_page_type(page_type: str) -> str:
    page_type = (page_type or "").strip()
    if page_type and page_type not in WIKI_PAGE_TYPES:
        raise bad_request(f"无效的 page_type: {page_type}")
    return page_type


def _validate_status(status: str) -> str:
    status = (status or "").strip()
    if status and status not in WIKI_STATUSES:
        raise bad_request(f"无效的 status: {status}")
    return status


async def _apply_folder(session: AsyncSession, kb_id: str, page: WikiPage) -> None:
    folder_id = (page.folder_id or "").strip()
    page.folder_id = folder_id
    if not folder_id:
        page.category_path = []
        return
    folder = await wiki_repository.get_folder(session, kb_id, folder_id)
    if folder is None:
        raise bad_request("页面引用了不存在的文件夹")
    page.category_path = _folder_segments(folder.path)


async def _refresh_in_links(
    session: AsyncSession,
    kb_id: str,
    source_slug: str,
    old_targets: list[str],
    new_targets: list[str],
) -> None:
    removed = set(old_targets) - set(new_targets)
    added = set(new_targets) - set(old_targets)
    for slug in removed:
        target = await wiki_repository.get_page_by_slug(session, kb_id, slug)
        if target is not None and source_slug in (target.in_links or []):
            target.in_links = [item for item in target.in_links if item != source_slug]
    for slug in added:
        target = await wiki_repository.get_page_by_slug(session, kb_id, slug)
        if target is not None and source_slug not in (target.in_links or []):
            target.in_links = [*(target.in_links or []), source_slug]


async def _incoming_links(
    session: AsyncSession, kb_id: str, slug: str, exclude_page_id: str = ""
) -> list[str]:
    """返回所有已存在、且正文链到 `slug` 的页面 slug（新建页面时补反向链）。"""
    pages = await wiki_repository.list_all_pages(session, kb_id)
    result: list[str] = []
    for page in pages:
        if page.id == exclude_page_id:
            continue
        if slug in (page.out_links or []) and page.slug not in result:
            result.append(page.slug)
    return result


def _snapshot(page: WikiPage) -> WikiPageRevision:
    now = datetime.now(UTC)
    return WikiPageRevision(
        id=str(uuid.uuid4()),
        tenant_id=page.tenant_id,
        knowledge_base_id=page.knowledge_base_id,
        page_id=page.id,
        slug=page.slug,
        version=int(page.version or 1),
        title=page.title or "",
        page_type=page.page_type,
        status=page.status,
        content=page.content or "",
        summary=page.summary or "",
        aliases=list(page.aliases or []),
        edit_source=page.last_edit_source or "pipeline",
        editor_id=page.last_editor_id or "",
        edited_at=page.updated_at or now,
        created_at=now,
    )


async def _prune(session: AsyncSession, page_id: str, current_version: int) -> None:
    keep = current_version - WIKI_MAX_REVISIONS_PER_PAGE
    hard = current_version - WIKI_MAX_REVISIONS_HARD_CAP
    if keep <= 0 and hard <= 0:
        return
    await wiki_repository.prune_revisions(
        session, page_id, keep, list(WIKI_PRUNE_SOURCES), hard
    )


# --------------------------------------------------------------------------
# 页面 CRUD 与版本
# --------------------------------------------------------------------------


async def list_pages(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    page_type: str = "",
    status: str = "",
    query: str = "",
    folder_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
) -> dict[str, Any]:
    await _require_wiki_kb(session, tenant_id, kb_id)
    page_types = [item.strip() for item in (page_type or "").split(",") if item.strip()]
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    items, total = await wiki_repository.list_pages(
        session,
        kb_id,
        page_types or None,
        status.strip(),
        query.strip(),
        folder_id,
        sort_by,
        sort_order,
        (page - 1) * page_size,
        page_size,
    )
    for item in items:
        _normalize_hierarchy(item)
    total_pages = (total + page_size - 1) // page_size
    return {
        "pages": [page_payload(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


async def get_page(
    session: AsyncSession, tenant_id: int, kb_id: str, slug: str
) -> dict[str, Any]:
    await _require_wiki_kb(session, tenant_id, kb_id)
    page = await _get_page(session, kb_id, slug)
    backlinks = await wiki_repository.list_pages_by_slugs(session, kb_id, list(page.in_links or []))
    data = page_payload(page)
    data["in_link_titles"] = {item.slug: item.title for item in backlinks}
    return data


async def create_page(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    payload: dict[str, Any],
    editor_id: str = "",
) -> dict[str, Any]:
    await _require_wiki_kb(session, tenant_id, kb_id)
    slug = normalize_slug(str(payload.get("slug") or ""))
    if not slug:
        raise bad_request("页面 slug 不能为空")
    if await wiki_repository.get_page_by_slug(session, kb_id, slug) is not None:
        raise conflict("同名 Wiki 页面已存在")

    page_type = _validate_page_type(str(payload.get("page_type") or "")) or WIKI_PAGE_TYPE_SUMMARY
    status = _validate_status(str(payload.get("status") or "")) or WIKI_STATUS_PUBLISHED
    now = datetime.now(UTC)
    page = WikiPage(
        tenant_id=tenant_id,
        knowledge_base_id=kb_id,
        slug=slug,
        title=str(payload.get("title") or "").strip(),
        page_type=page_type,
        status=status,
        content=str(payload.get("content") or ""),
        summary=str(payload.get("summary") or ""),
        parent_slug=str(payload.get("parent_slug") or "").strip(),
        folder_id=str(payload.get("folder_id") or "").strip(),
        category_path=[str(item) for item in payload.get("category_path") or []],
        sort_order=int(payload.get("sort_order") or 0),
        source_refs=[str(item) for item in payload.get("source_refs") or []],
        chunk_refs=[str(item) for item in payload.get("chunk_refs") or []],
        aliases=[str(item) for item in payload.get("aliases") or []],
        page_metadata=payload.get("page_metadata") or {},
        version=1,
        last_edit_source=WIKI_EDIT_SOURCE_USER,
        last_editor_id=editor_id,
        in_links=[],
        out_links=parse_out_links(str(payload.get("content") or "")),
        created_at=now,
        updated_at=now,
    )
    await _apply_folder(session, kb_id, page)
    _normalize_hierarchy(page)
    await wiki_repository.save_page(session, page)
    await _refresh_in_links(session, kb_id, page.slug, [], list(page.out_links))
    page.in_links = await _incoming_links(session, kb_id, page.slug, page.id)
    await session.commit()
    await session.refresh(page)
    return page_payload(page)


async def update_page(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    slug: str,
    payload: dict[str, Any],
    editor_id: str = "",
    edit_source: str = WIKI_EDIT_SOURCE_USER,
) -> dict[str, Any]:
    await _require_wiki_kb(session, tenant_id, kb_id)
    page = await _get_page(session, kb_id, slug)

    requested_version = int(payload.get("version") or 0)
    if requested_version > 0 and requested_version != int(page.version or 1):
        raise conflict(
            "Wiki 页面已被其他人修改",
            {"current_version": int(page.version or 1)},
        )

    page_type = page.page_type
    if payload.get("page_type") is not None:
        page_type = _validate_page_type(str(payload["page_type"]))
        if not page_type:
            raise bad_request("page_type 不能为空")
    status = page.status
    if payload.get("status") is not None:
        status = _validate_status(str(payload["status"]))
        if not status:
            raise bad_request("status 不能为空")

    new_title = page.title if payload.get("title") is None else str(payload["title"]).strip()
    new_content = page.content if payload.get("content") is None else str(payload["content"])
    new_summary = page.summary if payload.get("summary") is None else str(payload["summary"])
    new_aliases = (
        list(page.aliases or [])
        if payload.get("aliases") is None
        else [str(item) for item in payload["aliases"]]
    )
    content_changed = any(
        [
            new_title != (page.title or ""),
            new_content != (page.content or ""),
            new_summary != (page.summary or ""),
            page_type != page.page_type,
            status != page.status,
        ]
    )

    if content_changed:
        await wiki_repository.save_revision(session, _snapshot(page))
        page.version = int(page.version or 1) + 1

    old_out_links = list(page.out_links or [])
    page.title = new_title
    page.content = new_content
    page.summary = new_summary
    page.page_type = page_type
    page.status = status
    page.aliases = new_aliases
    page.out_links = parse_out_links(new_content)
    if payload.get("folder_id") is not None:
        page.folder_id = str(payload["folder_id"]).strip()
        await _apply_folder(session, kb_id, page)
    if payload.get("sort_order") is not None:
        page.sort_order = int(payload["sort_order"])
    page.last_edit_source = edit_source
    page.last_editor_id = editor_id
    page.updated_at = datetime.now(UTC)
    _normalize_hierarchy(page)

    await _refresh_in_links(
        session, kb_id, page.slug, old_out_links, list(page.out_links)
    )
    await session.commit()
    if content_changed:
        await _prune(session, page.id, int(page.version or 1))
        await session.commit()
    await session.refresh(page)
    return page_payload(page)


async def delete_page(session: AsyncSession, tenant_id: int, kb_id: str, slug: str) -> None:
    await _require_wiki_kb(session, tenant_id, kb_id)
    page = await _get_page(session, kb_id, slug)
    await _refresh_in_links(session, kb_id, page.slug, list(page.out_links or []), [])
    page.deleted_at = datetime.now(UTC)
    await wiki_repository.delete_revisions_by_page(session, page.id)
    await session.commit()


async def list_revisions(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    slug: str,
    limit: int = 50,
    offset: int = 0,
    content_version: int = 0,
) -> dict[str, Any]:
    await _require_wiki_kb(session, tenant_id, kb_id)
    page = await _get_page(session, kb_id, slug)
    if content_version > 0:
        revision = await wiki_repository.get_revision(session, kb_id, page.id, content_version)
        if revision is None:
            raise not_found("Wiki 页面版本不存在")
        return {
            "revisions": [revision_payload(revision, include_content=True)],
            "total": 1,
            "current_version": int(page.version or 1),
        }
    revisions, total = await wiki_repository.list_revisions(
        session, kb_id, page.id, min(max(1, limit), 200), max(0, offset)
    )
    return {
        "revisions": [revision_payload(item) for item in revisions],
        "total": total,
        "current_version": int(page.version or 1),
    }


async def revert_page(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    slug: str,
    version: int,
    editor_id: str = "",
) -> dict[str, Any]:
    await _require_wiki_kb(session, tenant_id, kb_id)
    page = await _get_page(session, kb_id, slug)
    if int(page.version or 1) == version:
        raise bad_request("不能回滚到当前版本")
    revision = await wiki_repository.get_revision(session, kb_id, page.id, version)
    if revision is None:
        raise not_found("Wiki 页面版本不存在")
    return await update_page(
        session,
        tenant_id,
        kb_id,
        slug,
        {
            "title": revision.title,
            "content": revision.content,
            "summary": revision.summary,
            "page_type": revision.page_type,
            "status": revision.status,
            "aliases": list(revision.aliases or []),
        },
        editor_id=editor_id,
        edit_source=WIKI_EDIT_SOURCE_REVERT,
    )


# --------------------------------------------------------------------------
# 文件夹页面树
# --------------------------------------------------------------------------


def _recursive_counts(folders: list[WikiFolder], direct: dict[str, int]) -> dict[str, int]:
    result: dict[str, int] = {}
    for folder in folders:
        total = direct.get(folder.id, 0)
        prefix = f"{folder.path}/"
        for other in folders:
            if other.id != folder.id and (other.path or "").startswith(prefix):
                total += direct.get(other.id, 0)
        result[folder.id] = total
    return result


async def list_child_folders(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    parent_id: str = "",
    page_types: list[str] | None = None,
) -> dict[str, Any]:
    await _require_wiki_kb(session, tenant_id, kb_id)
    folders = await wiki_repository.list_all_folders(session, kb_id)
    direct = await wiki_repository.count_pages_by_folder(session, kb_id, page_types)
    recursive = _recursive_counts(folders, direct)
    show_empty = len(page_types or []) == 0 or len(page_types or []) > 1

    def relevant(folder_id: str) -> bool:
        if recursive.get(folder_id, 0) > 0:
            return True
        return show_empty

    nodes = []
    for folder in folders:
        if (folder.parent_id or "") != (parent_id or "") or not relevant(folder.id):
            continue
        has_children = any(
            (other.parent_id or "") == folder.id and relevant(other.id) for other in folders
        )
        node = folder_payload(folder)
        node["page_count"] = recursive.get(folder.id, 0)
        node["has_children"] = has_children
        nodes.append(node)
    return {"parent_id": parent_id or "", "folders": nodes}


def _validate_folder_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise bad_request("文件夹名称不能为空")
    if any(sep in name for sep in ("/", "｜", "|", "／")):
        raise bad_request(f"文件夹名称 {name} 不能包含路径分隔符")
    return name


async def create_folder(
    session: AsyncSession, tenant_id: int, kb_id: str, parent_id: str, name: str
) -> dict[str, Any]:
    await _require_wiki_kb(session, tenant_id, kb_id)
    name = _validate_folder_name(name)
    parent_id = (parent_id or "").strip()
    parent_path = ""
    depth = 1
    if parent_id:
        parent = await wiki_repository.get_folder(session, kb_id, parent_id)
        if parent is None:
            raise not_found("父文件夹不存在")
        parent_path = parent.path
        depth = int(parent.depth or 0) + 1
    if await wiki_repository.get_child_folder_by_name(session, kb_id, parent_id, name):
        raise conflict("同级文件夹名称已存在")

    now = datetime.now(UTC)
    folder = WikiFolder(
        tenant_id=tenant_id,
        knowledge_base_id=kb_id,
        parent_id=parent_id,
        name=name,
        path=f"{parent_path}/{name}" if parent_path else name,
        depth=depth,
        created_at=now,
        updated_at=now,
    )
    await wiki_repository.save_folder(session, folder)
    await session.commit()
    await session.refresh(folder)
    return folder_payload(folder)


async def update_folder(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    folder_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    await _require_wiki_kb(session, tenant_id, kb_id)
    folder = await wiki_repository.get_folder(session, kb_id, folder_id)
    if folder is None:
        raise not_found("文件夹不存在")

    new_name = folder.name
    if payload.get("name"):
        new_name = _validate_folder_name(str(payload["name"]))
    new_parent_id = folder.parent_id
    move_parent = bool(payload.get("move_parent"))
    if move_parent:
        new_parent_id = str(payload.get("parent_id") or "").strip()
        if new_parent_id == folder.id:
            raise bad_request("不能将文件夹移动到自身")
        if new_parent_id:
            parent = await wiki_repository.get_folder(session, kb_id, new_parent_id)
            if parent is None:
                raise not_found("目标父文件夹不存在")
            if (parent.path or "").startswith(f"{folder.path}/"):
                raise bad_request("不能将文件夹移动到其子文件夹")

    if new_name != folder.name or move_parent:
        existing = await wiki_repository.get_child_folder_by_name(
            session, kb_id, new_parent_id, new_name
        )
        if existing is not None and existing.id != folder.id:
            raise conflict("同级文件夹名称已存在")

    parent_path = ""
    depth = 1
    if new_parent_id:
        parent = await wiki_repository.get_folder(session, kb_id, new_parent_id)
        if parent is None:
            raise not_found("目标父文件夹不存在")
        parent_path = parent.path
        depth = int(parent.depth or 0) + 1

    old_path = folder.path
    new_path = f"{parent_path}/{new_name}" if parent_path else new_name
    folder.name = new_name
    folder.parent_id = new_parent_id
    folder.path = new_path
    folder.depth = depth
    folder.updated_at = datetime.now(UTC)

    folders = await wiki_repository.list_all_folders(session, kb_id)
    for child in folders:
        if child.id == folder.id:
            continue
        if (child.path or "").startswith(f"{old_path}/"):
            child.path = new_path + child.path[len(old_path) :]
            child.updated_at = datetime.now(UTC)

    pages = await wiki_repository.list_all_pages(session, kb_id)
    for page in pages:
        if not page.folder_id:
            continue
        target = next((item for item in folders if item.id == page.folder_id), None)
        if page.folder_id == folder.id:
            target = folder
        if target is None or not (target.path or "").startswith(new_path):
            continue
        page.category_path = _folder_segments(target.path)
        page.depth = len(page.category_path)
        page.wiki_path = _build_wiki_path(
            page.page_type, page.category_path, (page.title or "").strip() or page.slug
        )
        page.updated_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(folder)
    return folder_payload(folder)


async def delete_folder(
    session: AsyncSession, tenant_id: int, kb_id: str, folder_id: str
) -> None:
    await _require_wiki_kb(session, tenant_id, kb_id)
    folder = await wiki_repository.get_folder(session, kb_id, folder_id)
    if folder is None:
        raise not_found("文件夹不存在")
    if await wiki_repository.count_pages_in_folder(session, kb_id, folder.id):
        raise conflict("文件夹内仍有 Wiki 页面，无法删除")
    if await wiki_repository.count_folders_children(session, kb_id, folder.id):
        raise conflict("文件夹仍有子文件夹，无法删除")
    folder.deleted_at = datetime.now(UTC)
    await session.commit()


async def move_page(
    session: AsyncSession, tenant_id: int, kb_id: str, slug: str, folder_id: str
) -> dict[str, Any]:
    await _require_wiki_kb(session, tenant_id, kb_id)
    page = await _get_page(session, kb_id, slug)
    page.folder_id = (folder_id or "").strip()
    await _apply_folder(session, kb_id, page)
    _normalize_hierarchy(page)
    page.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(page)
    return page_payload(page)


# --------------------------------------------------------------------------
# 图谱与统计
# --------------------------------------------------------------------------


def _graph_from_pages(
    pages: list[WikiPage],
    mode: str,
    center: str,
    depth: int,
    limit: int,
) -> dict[str, Any]:
    by_slug = {page.slug: page for page in pages}
    if mode == "ego" and center not in by_slug:
        raise not_found("图谱中心页面不存在")

    def neighbors(slug: str) -> list[str]:
        page = by_slug.get(slug)
        if page is None:
            return []
        linked = [item for item in (page.out_links or []) if item in by_slug]
        linked += [item for item in (page.in_links or []) if item in by_slug]
        return list(dict.fromkeys(linked))

    if mode == "ego":
        visited = {center}
        frontier = {center}
        for _ in range(max(1, depth)):
            nxt: set[str] = set()
            for slug in frontier:
                nxt.update(item for item in neighbors(slug) if item not in visited)
            visited |= nxt
            frontier = nxt
            if not frontier:
                break
        selected = [by_slug[slug] for slug in visited if slug in by_slug]
    else:
        selected = sorted(
            pages,
            key=lambda item: (
                -(len(item.in_links or []) + len(item.out_links or [])),
                item.page_type,
                item.slug,
            ),
        )[:limit]

    selected_slugs = {page.slug for page in selected}
    nodes = [
        {
            "slug": page.slug,
            "title": page.title or page.slug,
            "page_type": page.page_type,
            "link_count": len(page.in_links or []) + len(page.out_links or []),
        }
        for page in selected
    ]
    edges = []
    for page in selected:
        for target in page.out_links or []:
            if target in selected_slugs and target != page.slug:
                edges.append({"source": page.slug, "target": target})

    meta: dict[str, Any] = {
        "mode": mode,
        "total": len(pages),
        "returned": len(nodes),
        "truncated": len(nodes) < len(pages),
    }
    if mode == "ego":
        meta["center"] = center
        meta["depth"] = depth
    return {"nodes": nodes, "edges": edges, "meta": meta}


async def get_graph(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    mode: str = "overview",
    center: str = "",
    depth: int = 1,
    page_types: list[str] | None = None,
    limit: int = GRAPH_DEFAULT_LIMIT,
) -> dict[str, Any]:
    await _require_wiki_kb(session, tenant_id, kb_id)
    if mode not in ("overview", "ego"):
        raise bad_request("mode 必须是 'overview' 或 'ego'")
    if mode == "ego" and not center.strip():
        raise bad_request("ego 模式必须提供 center")
    depth = min(max(1, depth), GRAPH_MAX_DEPTH)
    limit = min(max(1, limit), GRAPH_MAX_LIMIT)
    pages = await wiki_repository.list_all_pages(session, kb_id)
    if page_types:
        pages = [page for page in pages if page.page_type in page_types]
    return _graph_from_pages(pages, mode, normalize_slug(center), depth, limit)


async def get_stats(session: AsyncSession, tenant_id: int, kb_id: str) -> dict[str, Any]:
    await _require_wiki_kb(session, tenant_id, kb_id)
    pages = await wiki_repository.list_all_pages(session, kb_id)
    by_type = await wiki_repository.count_pages_by_type(session, kb_id)
    orphans = len([page for page in pages if not (page.in_links or [])])
    recent = sorted(
        pages,
        key=lambda item: item.updated_at.timestamp() if item.updated_at else 0.0,
        reverse=True,
    )[:5]
    return {
        "total_pages": len(pages),
        "pages_by_type": by_type,
        "total_links": sum(len(page.out_links or []) for page in pages),
        "orphan_count": orphans,
        "recent_updates": [summary_payload(page) for page in recent],
        "pending_tasks": 0,
        "pending_issues": 0,
        "is_active": False,
    }
