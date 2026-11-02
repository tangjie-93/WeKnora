"""Wiki 路由，对齐 Go `internal/handler/wiki_page.go` 的 `/knowledgebase/:kb_id/wiki/*`。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AuthContext, get_auth_context, get_session, require_role
from app.domain.entities import ROLE_CONTRIBUTOR
from app.services import wiki_service

router = APIRouter(tags=["Wiki"])
contributor_only = require_role(ROLE_CONTRIBUTOR)


def _kb_read(kb_id: str) -> None:
    _ = kb_id


@router.get("/knowledge-bases/{kb_id}/wiki/pages")
async def list_pages(
    kb_id: str,
    page_type: str = "",
    status: str = "",
    query: str = "",
    folder_id: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await wiki_service.list_pages(
        session,
        context.tenant_id,
        kb_id,
        page_type=page_type,
        status=status,
        query=query,
        folder_id=folder_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return {"success": True, "data": data}


@router.post("/knowledge-bases/{kb_id}/wiki/pages", status_code=201)
async def create_page(
    kb_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    page = await wiki_service.create_page(
        session, context.tenant_id, kb_id, payload, editor_id=context.user.id
    )
    return {"success": True, "data": page}


@router.put("/knowledge-bases/{kb_id}/wiki/move-page")
async def move_page(
    kb_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    page = await wiki_service.move_page(
        session,
        context.tenant_id,
        kb_id,
        str(payload.get("slug") or ""),
        str(payload.get("folder_id") or ""),
    )
    return {"success": True, "data": page}


@router.get("/knowledge-bases/{kb_id}/wiki/pages/{slug:path}")
async def get_page(
    kb_id: str,
    slug: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    page = await wiki_service.get_page(session, context.tenant_id, kb_id, slug)
    return {"success": True, "data": page}


@router.put("/knowledge-bases/{kb_id}/wiki/pages/{slug:path}")
async def update_page(
    kb_id: str,
    slug: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    page = await wiki_service.update_page(
        session,
        context.tenant_id,
        kb_id,
        slug,
        payload,
        editor_id=context.user.id,
    )
    return {"success": True, "data": page}


@router.delete("/knowledge-bases/{kb_id}/wiki/pages/{slug:path}")
async def delete_page(
    kb_id: str,
    slug: str,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await wiki_service.delete_page(session, context.tenant_id, kb_id, slug)
    return {"success": True}


@router.get("/knowledge-bases/{kb_id}/wiki/revisions/{slug:path}")
async def list_revisions(
    kb_id: str,
    slug: str,
    limit: int = 50,
    offset: int = 0,
    content_version: int = 0,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await wiki_service.list_revisions(
        session,
        context.tenant_id,
        kb_id,
        slug,
        limit=limit,
        offset=offset,
        content_version=content_version,
    )
    return {"success": True, "data": data}


@router.post("/knowledge-bases/{kb_id}/wiki/revert")
async def revert_page(
    kb_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    page = await wiki_service.revert_page(
        session,
        context.tenant_id,
        kb_id,
        str(payload.get("slug") or ""),
        int(payload.get("version") or 0),
        editor_id=context.user.id,
    )
    return {"success": True, "data": page}


@router.get("/knowledge-bases/{kb_id}/wiki/folders")
async def list_folders(
    kb_id: str,
    parent_id: str = "",
    page_types: str = "",
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    page_types_list = [item for item in page_types.split(",") if item.strip()]
    data = await wiki_service.list_child_folders(
        session, context.tenant_id, kb_id, parent_id, page_types_list or None
    )
    return {"success": True, "data": data}


@router.post("/knowledge-bases/{kb_id}/wiki/folders", status_code=201)
async def create_folder(
    kb_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    folder = await wiki_service.create_folder(
        session,
        context.tenant_id,
        kb_id,
        str(payload.get("parent_id") or ""),
        str(payload.get("name") or ""),
    )
    return {"success": True, "data": folder}


@router.put("/knowledge-bases/{kb_id}/wiki/folders/{folder_id}")
async def update_folder(
    kb_id: str,
    folder_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    folder = await wiki_service.update_folder(
        session, context.tenant_id, kb_id, folder_id, payload
    )
    return {"success": True, "data": folder}


@router.delete("/knowledge-bases/{kb_id}/wiki/folders/{folder_id}")
async def delete_folder(
    kb_id: str,
    folder_id: str,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await wiki_service.delete_folder(session, context.tenant_id, kb_id, folder_id)
    return {"success": True}


@router.get("/knowledge-bases/{kb_id}/wiki/index")
async def get_index(
    kb_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await wiki_service.list_pages(
        session,
        context.tenant_id,
        kb_id,
        page=1,
        page_size=200,
        sort_by="title",
        sort_order="asc",
    )
    return {"success": True, "data": data}


@router.get("/knowledge-bases/{kb_id}/wiki/graph")
async def get_graph(
    kb_id: str,
    mode: str = "overview",
    center: str = "",
    depth: int = 1,
    page_types: str = "",
    limit: int = 500,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    page_types_list = [item for item in page_types.split(",") if item.strip()]
    data = await wiki_service.get_graph(
        session,
        context.tenant_id,
        kb_id,
        mode=mode,
        center=center,
        depth=depth,
        page_types=page_types_list or None,
        limit=limit,
    )
    return {"success": True, "data": data}


@router.get("/knowledge-bases/{kb_id}/wiki/stats")
async def get_stats(
    kb_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await wiki_service.get_stats(session, context.tenant_id, kb_id)
    return {"success": True, "data": data}
