"""认证路由：/api/v1/auth/*，字段与 Go 端完全对齐。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AuthContext, get_auth_context, get_current_user, get_session
from app.api.v1.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    tenant_payload,
    user_payload,
)
from app.core.config import get_settings
from app.core.errors import forbidden, unauthorized
from app.domain.entities import User
from app.services import auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["认证"])


def _complex_password_enabled() -> bool:
    return False


@router.get("/config")
async def get_auth_config() -> dict:
    settings = get_settings()
    return {
        "success": True,
        "registration_mode": settings.weknora_auth_registration_mode,
        "complex_password_enabled": _complex_password_enabled(),
    }


@router.post("/register", status_code=201)
async def register(
    payload: RegisterRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    settings = get_settings()
    if settings.weknora_auth_registration_mode != "self_serve":
        raise forbidden("Public registration is disabled")

    user = await auth_service.register(session, payload.username, payload.email, payload.password)
    return {
        "success": True,
        "message": "Registration successful",
        "user": user_payload(user),
    }


@router.post("/login")
async def login(
    payload: LoginRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    if not payload.email or not payload.password:
        raise unauthorized("Login failed", details="Email and password are required")

    result = await auth_service.login(session, payload.email, payload.password)
    return {
        "success": True,
        "message": "Login successful",
        "user": user_payload(result.user),
        "active_tenant": tenant_payload(result.tenant),
        "memberships": result.memberships,
        "token": result.access_token,
        "refresh_token": result.refresh_token,
    }


@router.post("/refresh")
async def refresh(
    payload: RefreshRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    token = payload.refresh_token or payload.token
    if not token:
        raise unauthorized("Unauthorized: refresh token is required")

    access_token, refresh_token = await auth_service.refresh(session, token)
    return {
        "success": True,
        "message": "Token refreshed successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


@router.post("/logout")
async def logout(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> dict:
    await auth_service.logout(session, user.id)
    return {"success": True, "message": "Logout successful"}


@router.get("/validate")
async def validate(user: User = Depends(get_current_user)) -> dict:
    return {"success": True, "valid": True, "user_id": user.id}


@router.get("/me")
async def get_current_user_info(
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant, memberships, _ = await auth_service.current_context(
        session, context.user, context.tenant_id
    )
    return {
        "success": True,
        "data": {
            "user": user_payload(context.user),
            "preference_defaults": {"browser_search_instructions": ""},
            "tenant": tenant_payload(tenant),
            "memberships": memberships,
            "tenant_required": tenant is None,
            "capabilities": {
                "can_create_tenant": bool(context.user.can_access_all_tenants),
                "auto_accept_invitation": False,
            },
        },
    }


@router.get("/tenant")
async def get_current_tenant(
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tenant, _, _ = await auth_service.current_context(
        session, context.user, context.tenant_id
    )
    return {"success": True, "data": tenant_payload(tenant)}
