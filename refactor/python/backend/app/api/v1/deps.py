"""FastAPI 依赖：会话、当前用户、当前空间与 RBAC。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.core.errors import forbidden, unauthorized
from app.domain.entities import ROLE_WEIGHTS, TenantMember, User
from app.repositories import tenant_repository
from app.services import auth_service


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


def _extract_bearer(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        raise unauthorized("Unauthorized: missing or invalid authorization header")
    token = header[7:].strip()
    if not token:
        raise unauthorized("Unauthorized: missing token")
    return token


@dataclass
class AuthContext:
    user: User
    tenant_id: int
    role: str
    member: TenantMember | None = None

    def has_role(self, minimum: str) -> bool:
        return ROLE_WEIGHTS.get(self.role, 0) >= ROLE_WEIGHTS.get(minimum, 0)


async def get_current_user(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User:
    return await auth_service.authenticate_token(session, _extract_bearer(request))


async def get_auth_context(
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
) -> AuthContext:
    user = await auth_service.authenticate_token(session, _extract_bearer(request))

    try:
        requested_tenant = int(x_tenant_id) if x_tenant_id else 0
    except ValueError:
        raise unauthorized("Unauthorized: invalid tenant id header")

    tenant_id = requested_tenant or user.tenant_id or 0
    if not tenant_id:
        raise forbidden("No workspace available for current user")

    member = await tenant_repository.get_membership(session, user.id, tenant_id)
    if member is None:
        if user.can_access_all_tenants:
            return AuthContext(user=user, tenant_id=tenant_id, role="viewer", member=None)
        raise forbidden("Forbidden: no access to this workspace")

    return AuthContext(user=user, tenant_id=tenant_id, role=member.role, member=member)


def require_role(minimum: str):
    async def _dependency(context: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if not context.has_role(minimum):
            raise forbidden(f"Forbidden: {minimum} role required")
        return context

    return _dependency
