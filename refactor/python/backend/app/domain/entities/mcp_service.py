"""MCP Client 实体：外部 MCP 服务注册 + 工具审批策略 + 持久化目录。

对应 Go `internal/types/mcp.go` 的 `MCPService` / `MCPToolApproval` / `MCPMetadata`，
映射 `mcp_services` / `mcp_tool_approvals` / `mcp_metadata` 三张表。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.base import Base, TimestampMixin
from app.domain.entities.knowledge import new_id

# transport types
MCP_TRANSPORT_SSE = "sse"
MCP_TRANSPORT_HTTP_STREAMABLE = "http-streamable"
MCP_TRANSPORT_STDIO = "stdio"

# auth strategies
MCP_AUTH_NONE = ""
MCP_AUTH_API_KEY = "api_key"
MCP_AUTH_BEARER = "bearer"
MCP_AUTH_OAUTH = "oauth"

# credential fields handled by the /credentials subresource (never returned)
MCP_CREDENTIAL_FIELDS = ("api_key", "token", "client_secret")

DEFAULT_MCP_ADVANCED_CONFIG = {"timeout": 30, "retry_count": 3, "retry_delay": 1}


class MCPService(Base, TimestampMixin):
    __tablename__ = "mcp_services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    transport_type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    headers: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    auth_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    advanced_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    stdio_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    env_vars: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    usage_instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MCPToolApproval(Base, TimestampMixin):
    __tablename__ = "mcp_tool_approvals"
    __table_args__ = (
        UniqueConstraint("tenant_id", "service_id", "tool_name", name="idx_mcp_tool_approvals_tenant_svc_tool"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    service_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(512), nullable=False)
    require_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class MCPMetadata(Base):
    __tablename__ = "mcp_metadata"

    tenant_id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    service_id: Mapped[str] = mapped_column(String(36), primary_key=True, nullable=False)
    principal: Mapped[str] = mapped_column(String(255), primary_key=True, default="")
    config_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    tools: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    server_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    server_version: Mapped[str] = mapped_column(Text, nullable=False, default="")
    server_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
