"""认证领域服务：注册、登录、刷新、登出。

响应字段严格对齐 Go 端 `internal/handler/auth.go` 与 `internal/handler/dto/auth.go`。
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.errors import bad_request, unauthorized
from app.domain.entities import (
    ROLE_OWNER,
    AuthToken,
    Tenant,
    TenantMember,
    User,
)
from app.repositories import tenant_repository, token_repository, user_repository

logger = logging.getLogger(__name__)

SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?"


def validate_password_policy(password: str, complex_enabled: bool = False) -> None:
    """对齐 Go 端 `ValidatePasswordPolicy`：8-32 位，至少一个字母 + 一个数字。"""
    if not 8 <= len(password) <= 32:
        raise bad_request(
            "password must be 8-32 characters and contain at least one letter and one number"
        )
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not has_letter or not has_digit:
        raise bad_request(
            "password must be 8-32 characters and contain at least one letter and one number"
        )
    if complex_enabled:
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_special = any(c in SPECIAL_CHARS for c in password)
        if not (has_upper and has_lower and has_digit and has_special):
            raise bad_request(
                "password must contain uppercase, lowercase, digit and special characters"
            )


def _ascii_only(value: str) -> bool:
    return all(unicodedata.category(ch) != "Cc" for ch in value)


@dataclass
class LoginResult:
    user: User
    tenant: Tenant | None
    memberships: list[dict] = field(default_factory=list)
    access_token: str = ""
    refresh_token: str = ""


async def _build_memberships(session: AsyncSession, user_id: str) -> list[dict]:
    members = await tenant_repository.list_memberships(session, user_id)
    tenants = await tenant_repository.list_tenants_by_ids(session, [m.tenant_id for m in members])
    by_id = {t.id: t for t in tenants}
    result: list[dict] = []
    for m in members:
        tenant = by_id.get(m.tenant_id)
        if tenant is None:
            continue
        result.append({"tenant_id": m.tenant_id, "tenant_name": tenant.name, "role": m.role})
    return result


async def _issue_tokens(session: AsyncSession, user: User, tenant_id: int) -> tuple[str, str]:
    access_token = security.create_access_token(user.id, user.email, tenant_id)
    refresh_token = security.create_refresh_token(user.id)
    now = datetime.now(UTC)
    await token_repository.save_token(
        session,
        AuthToken(
            user_id=user.id,
            token=access_token,
            token_type="access_token",
            expires_at=now + security.ACCESS_TOKEN_TTL,
        ),
    )
    await token_repository.save_token(
        session,
        AuthToken(
            user_id=user.id,
            token=refresh_token,
            token_type="refresh_token",
            expires_at=now + security.REFRESH_TOKEN_TTL,
        ),
    )
    return access_token, refresh_token


async def register(
    session: AsyncSession, username: str, email: str, password: str
) -> User:
    username = username.strip()
    email = email.strip()
    if not username or not email or not password:
        raise bad_request("Username, email and password are required")
    if not _ascii_only(username) or not _ascii_only(email):
        raise bad_request("Invalid registration parameters")

    validate_password_policy(password)

    if await user_repository.get_user_by_email(session, email):
        raise bad_request("email already exists")
    if await user_repository.get_user_by_username(session, username):
        raise bad_request("username already exists")

    user = User(
        username=username,
        email=email,
        password_hash=security.hash_password(password),
        is_active=True,
        preferences={},
    )
    await user_repository.create_user(session, user)

    tenant = Tenant(
        name=username,
        description="",
        retriever_engines=[],
        status="active",
        business="",
    )
    await tenant_repository.create_tenant(session, tenant)

    user.tenant_id = tenant.id
    await tenant_repository.add_member(
        session,
        TenantMember(user_id=user.id, tenant_id=tenant.id, role=ROLE_OWNER),
    )
    await session.commit()
    await session.refresh(user)
    logger.info("user registered: %s", email)
    return user


async def login(session: AsyncSession, login_name: str, password: str) -> LoginResult:
    login_name = login_name.strip()
    user = await user_repository.get_user_by_email(session, login_name)
    if user is None:
        user = await user_repository.get_user_by_username(session, login_name)

    if user is None or not security.verify_password(password, user.password_hash):
        raise unauthorized("Login failed", details="invalid email or password")
    if not user.is_active:
        raise unauthorized("Login failed", details="user account is disabled")

    memberships = await _build_memberships(session, user.id)

    tenant: Tenant | None = None
    if user.tenant_id:
        tenant = await tenant_repository.get_tenant(session, user.tenant_id)
    if tenant is None and memberships:
        tenant = await tenant_repository.get_tenant(session, memberships[0]["tenant_id"])
    if tenant is None:
        raise unauthorized("Login failed", details="user has no workspace")

    access_token, refresh_token = await _issue_tokens(session, user, tenant.id)
    await session.commit()

    logger.info("user logged in: %s", user.email)
    return LoginResult(
        user=user,
        tenant=tenant,
        memberships=memberships,
        access_token=access_token,
        refresh_token=refresh_token,
    )


async def refresh(session: AsyncSession, refresh_token: str) -> tuple[str, str]:
    claims = security.decode_token(refresh_token, expected_type="refresh")
    stored = await token_repository.get_active_token(session, refresh_token, "refresh_token")
    if stored is None or stored.user_id != claims.get("user_id"):
        raise unauthorized("Unauthorized: invalid or expired refresh token")

    user = await user_repository.get_user_by_id(session, stored.user_id)
    if user is None or not user.is_active:
        raise unauthorized("Unauthorized: invalid or expired refresh token")

    await token_repository.revoke_token(session, refresh_token)

    memberships = await _build_memberships(session, user.id)
    tenant_id = user.tenant_id or (memberships[0]["tenant_id"] if memberships else 0)
    access_token, new_refresh_token = await _issue_tokens(session, user, tenant_id)
    await session.commit()
    return access_token, new_refresh_token


async def logout(session: AsyncSession, user_id: str) -> None:
    await token_repository.revoke_all_for_user(session, user_id)
    await session.commit()


async def current_context(
    session: AsyncSession, user: User, active_tenant_id: int | None = None
) -> tuple[Tenant | None, list[dict], str]:
    memberships = await _build_memberships(session, user.id)
    tenant_id = active_tenant_id or user.tenant_id
    tenant = await tenant_repository.get_tenant(session, tenant_id) if tenant_id else None
    role = ""
    for item in memberships:
        if tenant is not None and item["tenant_id"] == tenant.id:
            role = item["role"]
            break
    return tenant, memberships, role


async def authenticate_token(session: AsyncSession, token: str) -> User:
    claims = security.decode_token(token, expected_type="access")
    stored = await token_repository.get_active_token(session, token, "access_token")
    if stored is None or stored.user_id != claims.get("user_id"):
        raise unauthorized("Unauthorized: invalid or expired token")
    user = await user_repository.get_user_by_id(session, stored.user_id)
    if user is None or not user.is_active:
        raise unauthorized("Unauthorized: invalid or expired token")
    return user


__all__ = [
    "LoginResult",
    "authenticate_token",
    "current_context",
    "login",
    "logout",
    "refresh",
    "register",
    "validate_password_policy",
]
