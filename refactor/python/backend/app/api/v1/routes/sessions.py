"""会话路由：/api/v1/sessions（对齐 Go 端 `internal/router/routes_chat.go` 的会话部分）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AuthContext, get_session, require_role
from app.domain.entities import ROLE_VIEWER
from app.services import chat_service

router = APIRouter(prefix="/sessions", tags=["会话"])
viewer_only = require_role(ROLE_VIEWER)


@router.get("")
async def list_sessions(
    context: AuthContext = Depends(viewer_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    items = await chat_service.list_sessions(session, context.tenant_id, context.user.id)
    return {"success": True, "data": [chat_service.session_payload(item) for item in items]}


@router.post("", status_code=201)
async def create_session(
    payload: dict,
    context: AuthContext = Depends(viewer_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    item = await chat_service.create_session(
        session, context.tenant_id, context.user.id, payload
    )
    return {"success": True, "data": chat_service.session_payload(item)}


@router.get("/{session_id}")
async def get_session_detail(
    session_id: str,
    context: AuthContext = Depends(viewer_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    item = await chat_service.get_session(session, context.tenant_id, context.user.id, session_id)
    return {"success": True, "data": chat_service.session_payload(item)}


@router.put("/{session_id}")
async def update_session(
    session_id: str,
    payload: dict,
    context: AuthContext = Depends(viewer_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    item = await chat_service.update_session(
        session, context.tenant_id, context.user.id, session_id, payload
    )
    return {"success": True, "data": chat_service.session_payload(item)}


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    context: AuthContext = Depends(viewer_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await chat_service.delete_session(
        session, context.tenant_id, context.user.id, session_id
    )
    return {"success": True, "message": "session deleted"}


@router.delete("/{session_id}/messages")
async def clear_session_messages(
    session_id: str,
    context: AuthContext = Depends(viewer_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    count = await chat_service.clear_messages(
        session, context.tenant_id, context.user.id, session_id
    )
    return {"success": True, "data": {"deleted": count}}


@router.post("/{session_id}/generate_title")
async def generate_session_title(
    session_id: str,
    context: AuthContext = Depends(viewer_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    item = await chat_service.generate_title(
        session, context.tenant_id, context.user.id, session_id
    )
    return {"success": True, "data": chat_service.session_payload(item)}
