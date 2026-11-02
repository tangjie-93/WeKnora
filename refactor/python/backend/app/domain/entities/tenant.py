"""空间（租户）与成员实体，对应 tenants / tenant_members 表。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.base import Base, TimestampMixin

# 四级 RBAC，与 Go 端 internal/types 中定义的常量一致
ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_CONTRIBUTOR = "contributor"
ROLE_VIEWER = "viewer"

ROLE_WEIGHTS = {
    ROLE_VIEWER: 1,
    ROLE_CONTRIBUTOR: 2,
    ROLE_ADMIN: 3,
    ROLE_OWNER: 4,
}


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    retriever_engines: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True, default="active")
    business: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    storage_quota: Mapped[int] = mapped_column(BigInteger, nullable=False, default=10 * 1024**3)
    storage_used: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    agent_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TenantMember(Base, TimestampMixin):
    __tablename__ = "tenant_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=ROLE_CONTRIBUTOR)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    invited_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
