"""HTTP 请求/响应结构，字段名与 Go 端 JSON tag 一一对应。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Tenant, User


def iso_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat().replace("+00:00", "Z")


class RegisterRequest(BaseModel):
    username: str = ""
    email: str = ""
    password: str = ""


class LoginRequest(BaseModel):
    email: str = ""
    password: str = ""


class RefreshRequest(BaseModel):
    # 前端发送 camelCase 的 refreshToken，兼容两种写法
    model_config = ConfigDict(populate_by_name=True)

    refresh_token: str = Field(default="", alias="refreshToken")
    token: str = Field(default="", alias="token")


def user_payload(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "avatar": user.avatar or "",
        "tenant_id": user.tenant_id or 0,
        "is_active": bool(user.is_active),
        "can_access_all_tenants": bool(user.can_access_all_tenants),
        "is_system_admin": bool(user.is_system_admin),
        "preferences": user.preferences or {},
        "created_at": iso_time(user.created_at),
        "updated_at": iso_time(user.updated_at),
    }


def tenant_payload(tenant: Tenant | None) -> dict[str, Any] | None:
    if tenant is None:
        return None
    return {
        "id": tenant.id,
        "name": tenant.name,
        "description": tenant.description or "",
        "status": tenant.status or "active",
        "retriever_engines": tenant.retriever_engines or [],
        "business": tenant.business or "",
        "storage_quota": tenant.storage_quota,
        "storage_used": tenant.storage_used,
        "created_at": iso_time(tenant.created_at),
        "updated_at": iso_time(tenant.updated_at),
        "deleted_at": None,
    }
