"""MCP Endpoint 持久化，对应 `mcp_endpoints` 表。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import MCPEndpoint


async def get_endpoint(session: AsyncSession, endpoint_id: str) -> MCPEndpoint | None:
    stmt = select(MCPEndpoint).where(
        MCPEndpoint.id == endpoint_id,
        MCPEndpoint.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def get_endpoint_by_token_hash(
    session: AsyncSession, token_hash: str
) -> MCPEndpoint | None:
    if not token_hash:
        return None
    stmt = select(MCPEndpoint).where(
        MCPEndpoint.token_hash == token_hash,
        MCPEndpoint.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def list_endpoints(session: AsyncSession, tenant_id: int) -> list[MCPEndpoint]:
    stmt = (
        select(MCPEndpoint)
        .where(MCPEndpoint.tenant_id == tenant_id, MCPEndpoint.deleted_at.is_(None))
        .order_by(MCPEndpoint.created_at.desc())
    )
    return list((await session.scalars(stmt)).all())


async def save_endpoint(session: AsyncSession, endpoint: MCPEndpoint) -> MCPEndpoint:
    session.add(endpoint)
    await session.flush()
    return endpoint


async def delete_endpoint(session: AsyncSession, endpoint: MCPEndpoint) -> None:
    endpoint.deleted_at = datetime.now(UTC)
    await session.flush()


async def touch_last_used(session: AsyncSession, endpoint_id: str) -> None:
    endpoint = await get_endpoint(session, endpoint_id)
    if endpoint is not None:
        endpoint.last_used_at = datetime.now(UTC)
        await session.flush()
