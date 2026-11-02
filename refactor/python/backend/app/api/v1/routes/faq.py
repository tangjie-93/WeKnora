"""FAQ 条目路由，对齐 Go `internal/handler/faq.go`（Phase 6A 范围）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AuthContext, get_auth_context, get_session, require_role
from app.domain.entities import ROLE_CONTRIBUTOR
from app.services import faq_service

router = APIRouter(tags=["FAQ"])
contributor_only = require_role(ROLE_CONTRIBUTOR)


@router.get("/knowledge-bases/{kb_id}/faq/entries")
async def list_entries(
    kb_id: str,
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    tag_id: str = "",
    tag_ids: str = "",
    is_enabled: str = "",
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tags = [item.strip() for item in tag_ids.split(",") if item.strip()]
    if tag_id:
        tags.append(tag_id)
    enabled: bool | None = None
    if is_enabled:
        if is_enabled.lower() not in ("true", "false"):
            from app.core.errors import bad_request

            raise bad_request("is_enabled must be true or false")
        enabled = is_enabled.lower() == "true"

    data = await faq_service.list_entries(
        session, context.tenant_id, kb_id, keyword, tags, enabled, page, page_size
    )
    return {"success": True, "data": data}


@router.post("/knowledge-bases/{kb_id}/faq/entry", status_code=201)
async def create_entry(
    kb_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    entry = await faq_service.create_entry(session, context.tenant_id, kb_id, payload)
    return {"success": True, "data": entry}


@router.put("/knowledge-bases/{kb_id}/faq/entries/fields")
async def update_fields_batch(
    kb_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await faq_service.update_fields_batch(
        session, context.tenant_id, kb_id, payload
    )
    return {"success": True, "data": data}


@router.put("/knowledge-bases/{kb_id}/faq/entries/tags")
async def update_tags_batch(
    kb_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await faq_service.update_tags_batch(
        session,
        context.tenant_id,
        kb_id,
        dict(payload.get("updates") or {}),
    )
    return {"success": True, "data": data}


@router.get("/knowledge-bases/{kb_id}/faq/entries/{entry_id}")
async def get_entry(
    kb_id: str,
    entry_id: int,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    entry = await faq_service.get_entry(session, context.tenant_id, kb_id, entry_id)
    return {"success": True, "data": entry}


@router.put("/knowledge-bases/{kb_id}/faq/entries/{entry_id}")
async def update_entry(
    kb_id: str,
    entry_id: int,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    entry = await faq_service.update_entry(
        session, context.tenant_id, kb_id, entry_id, payload
    )
    return {"success": True, "data": entry}


@router.delete("/knowledge-bases/{kb_id}/faq/entries")
async def delete_entries(
    kb_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await faq_service.delete_entries(
        session, context.tenant_id, kb_id, list(payload.get("ids") or [])
    )
    return {"success": True, "data": data}


@router.post("/knowledge-bases/{kb_id}/faq/search")
async def search(
    kb_id: str,
    payload: dict,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    hits = await faq_service.search(session, context.tenant_id, kb_id, payload)
    return {"success": True, "data": hits}
