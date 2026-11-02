"""MCP Client 管理路由，对齐 Go `internal/handler/mcp_service.go` 的 `/mcp-services`。

读取面向 Viewer+，写操作（create/update/delete/test/credentials/tool-approvals）要求 admin。
OAuth 流程与 usage-instructions 生成本阶段未实现。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AuthContext, get_auth_context, get_session, require_role
from app.core.errors import bad_request
from app.domain.entities import ROLE_ADMIN
from app.services import mcp_service

router = APIRouter(prefix="/mcp-services", tags=["MCP Service"])
admin_only = require_role(ROLE_ADMIN)


@router.get("")
async def list_services(
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    items = await mcp_service.list_services(session, context.tenant_id)
    data = []
    for item in items:
        catalog = await mcp_service.catalog_summary(session, item)
        data.append(mcp_service.service_payload(item, catalog))
    return {"success": True, "data": data}


@router.post("")
async def create_service(
    payload: dict,
    context: AuthContext = Depends(admin_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    service = await mcp_service.create_service(session, context.tenant_id, payload)
    return {"success": True, "data": mcp_service.service_payload(service)}


@router.get("/{service_id}")
async def get_service(
    service_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    service = await mcp_service.get_service(session, context.tenant_id, service_id)
    catalog = await mcp_service.catalog_summary(session, service)
    return {"success": True, "data": mcp_service.service_payload(service, catalog)}


@router.put("/{service_id}")
async def update_service(
    service_id: str,
    payload: dict,
    context: AuthContext = Depends(admin_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    service = await mcp_service.update_service(
        session, context.tenant_id, service_id, payload
    )
    catalog = await mcp_service.catalog_summary(session, service)
    return {"success": True, "data": mcp_service.service_payload(service, catalog)}


@router.delete("/{service_id}")
async def delete_service(
    service_id: str,
    context: AuthContext = Depends(admin_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await mcp_service.delete_service(session, context.tenant_id, service_id)
    return {"success": True, "message": "MCP service deleted successfully"}


@router.post("/{service_id}/test")
async def test_service(
    service_id: str,
    context: AuthContext = Depends(admin_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await mcp_service.test_service(session, context.tenant_id, service_id)
    return {"success": True, "data": result}


@router.get("/{service_id}/tools")
async def get_tools(
    service_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tools = await mcp_service.get_tools(session, context.tenant_id, service_id)
    return {"success": True, "data": tools}


@router.get("/{service_id}/resources")
async def get_resources(
    service_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    resources = await mcp_service.get_resources(session, context.tenant_id, service_id)
    return {"success": True, "data": resources}


@router.get("/{service_id}/metadata")
async def get_metadata(
    service_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await mcp_service.get_metadata(session, context.tenant_id, service_id)
    return {"success": True, "data": data}


@router.post("/{service_id}/metadata/refresh")
async def refresh_metadata(
    service_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await mcp_service.refresh_metadata(session, context.tenant_id, service_id)
    return {"success": True, "data": data}


@router.get("/{service_id}/tool-approvals")
async def list_tool_approvals(
    service_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    rows = await mcp_service.list_tool_approvals(session, context.tenant_id, service_id)
    return {"success": True, "data": rows}


@router.put("/{service_id}/tool-approvals/{tool_name}")
async def set_tool_approval(
    service_id: str,
    tool_name: str,
    payload: dict,
    context: AuthContext = Depends(admin_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if "require_approval" not in payload and "enabled" not in payload:
        raise bad_request("require_approval or enabled is required")
    row = await mcp_service.set_tool_approval(
        session,
        context.tenant_id,
        service_id,
        tool_name,
        payload.get("require_approval"),
        payload.get("enabled"),
    )
    return {"success": True, "data": row}


@router.put("/{service_id}/credentials")
async def set_credentials(
    service_id: str,
    payload: dict,
    context: AuthContext = Depends(admin_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await mcp_service.set_credentials(session, context.tenant_id, service_id, payload)
    return {"success": True, "data": result}


@router.delete("/{service_id}/credentials/{field}")
async def clear_credential(
    service_id: str,
    field: str,
    context: AuthContext = Depends(admin_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await mcp_service.clear_credential(session, context.tenant_id, service_id, field)
    return {"success": True}
