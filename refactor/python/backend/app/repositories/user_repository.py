"""用户持久化。"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import AuthToken, User


async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    return await session.get(User, user_id)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email, User.deleted_at.is_(None))
    return await session.scalar(stmt)


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    stmt = select(User).where(User.username == username, User.deleted_at.is_(None))
    return await session.scalar(stmt)


async def get_user_by_login(session: AsyncSession, login: str) -> User | None:
    stmt = select(User).where(
        or_(User.email == login, User.username == login), User.deleted_at.is_(None)
    )
    return await session.scalar(stmt)


async def create_user(session: AsyncSession, user: User) -> User:
    session.add(user)
    await session.flush()
    return user


async def save_user(session: AsyncSession, user: User) -> User:
    session.add(user)
    await session.flush()
    return user


async def count_users(session: AsyncSession) -> int:
    from sqlalchemy import func

    stmt = select(func.count()).select_from(User).where(User.deleted_at.is_(None))
    return int(await session.scalar(stmt) or 0)


async def get_auth_token(session: AsyncSession, token: str, token_type: str) -> AuthToken | None:
    stmt = select(AuthToken).where(
        AuthToken.token == token,
        AuthToken.token_type == token_type,
        AuthToken.is_revoked.is_(False),
    )
    return await session.scalar(stmt)
