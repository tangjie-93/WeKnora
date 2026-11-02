"""知识库标签路由，对齐 Go `internal/handler/tag.go`。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AuthContext, get_auth_context, get_session, require_role
from app.domain.entities import ROLE_CONTRIBUTOR
from app.services import tag_service

router = APIRouter(tags=["标签"])
contributor_only = require_role(ROLE_CONTRIBUTOR)


@router.get("/knowledge-bases/{kb_id}/tags")
async def list_tags(
    kb_id: str,
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await tag_service.list_tags(
        session, context.tenant_id, kb_id, keyword, page, page_size
    )
    return {"success": True, "data": data}


@router.post("/knowledge-bases/{kb_id}/tags", status_code=201)
async def create_tag(
    kb_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tag = await tag_service.create_tag(
        session,
        context.tenant_id,
        kb_id,
        str(payload.get("name") or ""),
        str(payload.get("color") or ""),
        int(payload.get("sort_order") or 0),
    )
    return {"success": True, "data": tag}


@router.put("/knowledge-bases/{kb_id}/tags/{tag_ref}")
async def update_tag(
    kb_id: str,
    tag_ref: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tag = await tag_service.update_tag(
        session, context.tenant_id, kb_id, tag_ref, payload
    )
    return {"success": True, "data": tag}


@router.delete("/knowledge-bases/{kb_id}/tags/{tag_ref}")
async def delete_tag(
    kb_id: str,
    tag_ref: str,
    force: bool = False,
    content_only: bool = False,
    exclude_ids: str = "",
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    exclude = [int(item) for item in exclude_ids.split(",") if item.strip().isdigit()]
    await tag_service.delete_tag(
        session,
        context.tenant_id,
        kb_id,
        tag_ref,
        force=force,
        content_only=content_only,
        exclude_ids=exclude,
    )
    return {"success": True}
