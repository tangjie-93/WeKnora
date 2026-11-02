"""MCP 服务与持久化目录（metadata）仓储，对应 `mcp_services` / `mcp_metadata`。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import MCPMetadata, MCPService


async def get_service(session: AsyncSession, tenant_id: int, service_id: str) -> MCPService | None:
    stmt = select(MCPService).where(
        MCPService.id == service_id,
        MCPService.tenant_id == tenant_id,
        MCPService.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def list_services(session: AsyncSession, tenant_id: int) -> list[MCPService]:
    stmt = (
        select(MCPService)
        .where(MCPService.tenant_id == tenant_id, MCPService.deleted_at.is_(None))
        .order_by(MCPService.created_at.asc())
    )
    return list((await session.scalars(stmt)).all())


async def list_services_by_ids(
    session: AsyncSession, tenant_id: int, ids: list[str]
) -> list[MCPService]:
    if not ids:
        return []
    stmt = select(MCPService).where(
        MCPService.tenant_id == tenant_id,
        MCPService.id.in_(ids),
        MCPService.deleted_at.is_(None),
    )
    return list((await session.scalars(stmt)).all())


async def save_service(session: AsyncSession, service: MCPService) -> MCPService:
    session.add(service)
    await session.flush()
    return service


async def delete_service(session: AsyncSession, service: MCPService) -> None:
    service.deleted_at = datetime.now(UTC)
    await session.flush()


async def get_metadata(
    session: AsyncSession, tenant_id: int, service_id: str, principal: str = ""
) -> MCPMetadata | None:
    stmt = select(MCPMetadata).where(
        MCPMetadata.tenant_id == tenant_id,
        MCPMetadata.service_id == service_id,
        MCPMetadata.principal == principal,
    )
    return await session.scalar(stmt)


async def save_metadata(session: AsyncSession, metadata: MCPMetadata) -> MCPMetadata:
    session.add(metadata)
    await session.flush()
    return metadata
