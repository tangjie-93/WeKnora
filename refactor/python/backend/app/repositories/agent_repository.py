"""自定义 Agent 持久化（内置 agent 由 service 层内存提供，不落库）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import CustomAgent


async def get_agent(
    session: AsyncSession, tenant_id: int, agent_id: str
) -> CustomAgent | None:
    stmt = select(CustomAgent).where(
        CustomAgent.id == agent_id,
        CustomAgent.tenant_id == tenant_id,
        CustomAgent.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def list_agents(session: AsyncSession, tenant_id: int) -> list[CustomAgent]:
    stmt = (
        select(CustomAgent)
        .where(CustomAgent.tenant_id == tenant_id, CustomAgent.deleted_at.is_(None))
        .order_by(CustomAgent.created_at.asc())
    )
    return list((await session.scalars(stmt)).all())


async def save_agent(session: AsyncSession, agent: CustomAgent) -> CustomAgent:
    session.add(agent)
    await session.flush()
    return agent


async def delete_agent(session: AsyncSession, agent: CustomAgent) -> None:
    from datetime import UTC, datetime

    agent.deleted_at = datetime.now(UTC)
    await session.flush()
