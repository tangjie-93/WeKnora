"""MCP Endpoint 管理路由，对齐 Go `internal/handler/mcp_endpoint.go` 的 `/mcp-endpoints`。

读取面向所有成员，写操作（创建/更新/删除/轮换 token）要求 admin。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AuthContext, get_auth_context, get_session, require_role
from app.domain.entities import ROLE_ADMIN
from app.services import mcp_endpoint_service

router = APIRouter(prefix="/mcp-endpoints", tags=["MCP Endpoint"])
admin_only = require_role(ROLE_ADMIN)


@router.get("")
async def list_endpoints(
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    items = await mcp_endpoint_service.list_endpoints(session, context.tenant_id)
    return {"success": True, "data": [mcp_endpoint_service.endpoint_payload(item) for item in items]}


@router.get("/tools")
async def list_tool_catalog(
    context: AuthContext = Depends(get_auth_context),
) -> dict:
    return {"success": True, "data": mcp_endpoint_service.tool_catalog_payload()}


@router.post("", status_code=201)
async def create_endpoint(
    payload: dict,
    context: AuthContext = Depends(admin_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    endpoint, token = await mcp_endpoint_service.create_endpoint(
        session, context.tenant_id, payload
    )
    return {"success": True, "data": mcp_endpoint_service.endpoint_payload(endpoint, token)}


@router.get("/{endpoint_id}")
async def get_endpoint(
    endpoint_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    endpoint = await mcp_endpoint_service.get_endpoint(session, context.tenant_id, endpoint_id)
    return {"success": True, "data": mcp_endpoint_service.endpoint_payload(endpoint)}


@router.put("/{endpoint_id}")
async def update_endpoint(
    endpoint_id: str,
    payload: dict,
    context: AuthContext = Depends(admin_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    endpoint = await mcp_endpoint_service.update_endpoint(
        session, context.tenant_id, endpoint_id, payload
    )
    return {"success": True, "data": mcp_endpoint_service.endpoint_payload(endpoint)}


@router.delete("/{endpoint_id}")
async def delete_endpoint(
    endpoint_id: str,
    context: AuthContext = Depends(admin_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await mcp_endpoint_service.delete_endpoint(session, context.tenant_id, endpoint_id)
    return {"success": True}


@router.post("/{endpoint_id}/rotate-token")
async def rotate_token(
    endpoint_id: str,
    context: AuthContext = Depends(admin_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    endpoint, token = await mcp_endpoint_service.rotate_token(
        session, context.tenant_id, endpoint_id
    )
    return {"success": True, "data": mcp_endpoint_service.endpoint_payload(endpoint, token)}
