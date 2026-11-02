"""MCP 工具审批策略仓储，对应 `mcp_tool_approvals` 表。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import MCPToolApproval


async def list_by_service(
    session: AsyncSession, tenant_id: int, service_id: str
) -> list[MCPToolApproval]:
    stmt = (
        select(MCPToolApproval)
        .where(
            MCPToolApproval.tenant_id == tenant_id,
            MCPToolApproval.service_id == service_id,
        )
        .order_by(MCPToolApproval.tool_name.asc())
    )
    return list((await session.scalars(stmt)).all())


async def get_approval(
    session: AsyncSession, tenant_id: int, service_id: str, tool_name: str
) -> MCPToolApproval | None:
    stmt = select(MCPToolApproval).where(
        MCPToolApproval.tenant_id == tenant_id,
        MCPToolApproval.service_id == service_id,
        MCPToolApproval.tool_name == tool_name,
    )
    return await session.scalar(stmt)


async def save_approval(session: AsyncSession, approval: MCPToolApproval) -> MCPToolApproval:
    session.add(approval)
    await session.flush()
    return approval
