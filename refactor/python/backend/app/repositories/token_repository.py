"""认证令牌持久化。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import AuthToken


async def save_token(session: AsyncSession, token: AuthToken) -> AuthToken:
    session.add(token)
    await session.flush()
    return token


async def revoke_all_for_user(session: AsyncSession, user_id: str) -> None:
    stmt = (
        update(AuthToken)
        .where(AuthToken.user_id == user_id, AuthToken.is_revoked.is_(False))
        .values(is_revoked=True)
    )
    await session.execute(stmt)


async def revoke_token(session: AsyncSession, token: str) -> None:
    stmt = update(AuthToken).where(AuthToken.token == token).values(is_revoked=True)
    await session.execute(stmt)


async def get_active_token(
    session: AsyncSession, token: str, token_type: str
) -> AuthToken | None:
    stmt = select(AuthToken).where(
        AuthToken.token == token,
        AuthToken.token_type == token_type,
        AuthToken.is_revoked.is_(False),
        AuthToken.expires_at > datetime.now().astimezone(),
    )
    return await session.scalar(stmt)
