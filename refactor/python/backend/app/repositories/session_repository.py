"""会话与消息持久化。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import Message, Session


async def list_sessions(session: AsyncSession, tenant_id: int, user_id: str) -> list[Session]:
    stmt = (
        select(Session)
        .where(
            Session.tenant_id == tenant_id,
            Session.user_id == user_id,
            Session.deleted_at.is_(None),
        )
        .order_by(Session.updated_at.desc())
    )
    return list((await session.scalars(stmt)).all())


async def get_session(session: AsyncSession, tenant_id: int, session_id: str) -> Session | None:
    stmt = select(Session).where(
        Session.id == session_id,
        Session.tenant_id == tenant_id,
        Session.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def save_session(session: AsyncSession, item: Session) -> Session:
    session.add(item)
    await session.flush()
    return item


async def list_messages(session: AsyncSession, session_id: str) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.session_id == session_id, Message.deleted_at.is_(None))
        .order_by(Message.created_at)
    )
    return list((await session.scalars(stmt)).all())


async def delete_messages(session: AsyncSession, session_id: str) -> int:
    rows = await list_messages(session, session_id)
    now = datetime.now(UTC)
    for row in rows:
        row.deleted_at = now
    await session.flush()
    return len(rows)


async def save_message(session: AsyncSession, message: Message) -> Message:
    session.add(message)
    await session.flush()
    return message
