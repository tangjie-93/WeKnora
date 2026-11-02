"""空间与成员的持久化。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Tenant, TenantMember


async def get_tenant(session: AsyncSession, tenant_id: int) -> Tenant | None:
    stmt = select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
    return await session.scalar(stmt)


async def get_tenant_by_name(session: AsyncSession, name: str) -> Tenant | None:
    stmt = select(Tenant).where(Tenant.name == name, Tenant.deleted_at.is_(None))
    return await session.scalar(stmt)


async def create_tenant(session: AsyncSession, tenant: Tenant) -> Tenant:
    session.add(tenant)
    await session.flush()
    return tenant


async def get_membership(
    session: AsyncSession, user_id: str, tenant_id: int
) -> TenantMember | None:
    stmt = select(TenantMember).where(
        TenantMember.user_id == user_id,
        TenantMember.tenant_id == tenant_id,
        TenantMember.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def list_memberships(session: AsyncSession, user_id: str) -> list[TenantMember]:
    stmt = (
        select(TenantMember)
        .where(TenantMember.user_id == user_id, TenantMember.deleted_at.is_(None))
        .order_by(TenantMember.id)
    )
    return list((await session.scalars(stmt)).all())


async def list_tenants_by_ids(session: AsyncSession, tenant_ids: list[int]) -> list[Tenant]:
    if not tenant_ids:
        return []
    stmt = select(Tenant).where(Tenant.id.in_(tenant_ids), Tenant.deleted_at.is_(None))
    return list((await session.scalars(stmt)).all())


async def add_member(session: AsyncSession, member: TenantMember) -> TenantMember:
    session.add(member)
    await session.flush()
    return member
