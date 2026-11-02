"""MCP Client 服务：外部 MCP 服务 CRUD + 凭证 + 测试连接 + 工具审批 + 持久化目录。

对齐 Go `internal/application/service/mcp_service.go` + `mcp_tool_approval_service.go`：
- 凭证（api_key/token/client_secret）走 /credentials 子资源，主响应永不回显明文
- stdio 传输因安全原因禁用；本阶段仅支持 http-streamable 传输建连
- 测试连接与工具/资源列表为即时连接；metadata 为持久化目录
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, not_found
from app.domain.entities import (
    DEFAULT_MCP_ADVANCED_CONFIG,
    MCP_CREDENTIAL_FIELDS,
    MCP_TRANSPORT_HTTP_STREAMABLE,
    MCP_TRANSPORT_SSE,
    MCP_TRANSPORT_STDIO,
    MCPMetadata,
    MCPService,
    MCPToolApproval,
)
from app.integrations.mcp_client import MCPClient
from app.repositories import mcp_service_repository, mcp_tool_approval_repository


def _iso(value) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat().replace("+00:00", "Z")


def config_fingerprint(service: MCPService) -> str:
    auth = service.auth_config or {}
    data = {
        "url": service.url,
        "transport_type": service.transport_type,
        "headers": service.headers or {},
        "auth_type": auth.get("auth_type", ""),
        "api_key_header": auth.get("api_key_header", ""),
        "client_id": auth.get("client_id", ""),
        "custom_headers": auth.get("custom_headers") or {},
    }
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def service_payload(service: MCPService, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    auth = service.auth_config or {}
    row: dict[str, Any] = {
        "id": service.id,
        "tenant_id": service.tenant_id,
        "name": service.name,
        "description": service.description or "",
        "usage_instructions": service.usage_instructions or "",
        "enabled": bool(service.enabled),
        "transport_type": service.transport_type,
        "is_builtin": bool(service.is_builtin),
        "created_at": _iso(service.created_at),
        "updated_at": _iso(service.updated_at),
    }
    if service.is_builtin:
        row["url"] = None
        row["headers"] = None
        row["env_vars"] = None
        row["stdio_config"] = None
        row["auth_config"] = None
    else:
        row["url"] = service.url
        row["headers"] = dict(service.headers or {})
        row["env_vars"] = dict(service.env_vars or {})
        row["stdio_config"] = dict(service.stdio_config or {})
        row["advanced_config"] = dict(service.advanced_config or DEFAULT_MCP_ADVANCED_CONFIG)
        row["auth_config"] = {
            "auth_type": auth.get("auth_type", ""),
            "api_key_header": auth.get("api_key_header", ""),
            "custom_headers": dict(auth.get("custom_headers") or {}),
            "scopes": list(auth.get("scopes") or []),
            "auth_server_metadata_url": auth.get("auth_server_metadata_url", ""),
            "client_id": auth.get("client_id", ""),
        }
        row["credentials"] = {
            "api_key": {"configured": bool(auth.get("api_key"))},
            "token": {"configured": bool(auth.get("token"))},
            "client_secret": {"configured": bool(auth.get("client_secret"))},
        }
    if catalog is not None:
        row["catalog"] = catalog
    return row


def metadata_payload(meta: MCPMetadata, service: MCPService) -> dict[str, Any]:
    return {
        "service_id": meta.service_id,
        "tools": list(meta.tools or []),
        "instructions": meta.instructions or "",
        "server_name": meta.server_name or "",
        "server_version": meta.server_version or "",
        "server_description": meta.server_description or "",
        "synced_at": _iso(meta.synced_at),
        "stale": meta.config_fingerprint != config_fingerprint(service),
    }


async def catalog_summary(session: AsyncSession, service: MCPService) -> dict[str, Any] | None:
    meta = await mcp_service_repository.get_metadata(session, service.tenant_id, service.id, "")
    if meta is None:
        return None
    return {
        "tool_count": len(meta.tools or []),
        "stale": meta.config_fingerprint != config_fingerprint(service),
        "synced_at": _iso(meta.synced_at),
    }


def _validate_transport(transport_type: str, url: str | None) -> str:
    transport_type = (transport_type or "").strip()
    if transport_type == MCP_TRANSPORT_STDIO:
        raise bad_request("stdio transport is disabled for security reasons")
    if transport_type not in (MCP_TRANSPORT_HTTP_STREAMABLE, MCP_TRANSPORT_SSE):
        raise bad_request(f"invalid transport_type: {transport_type}")
    url = (url or "").strip()
    if not url:
        raise bad_request("url is required for this transport")
    if not url.startswith(("http://", "https://")):
        raise bad_request("url must use http or https")
    return transport_type


def _normalize_headers(raw: Any) -> dict[str, str] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise bad_request("headers must be an object")
    return {str(k): str(v) for k, v in raw.items()}


def _normalize_auth_config(raw: Any, include_secrets: bool) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise bad_request("auth_config must be an object")
    out: dict[str, Any] = {}
    if "auth_type" in raw:
        out["auth_type"] = str(raw.get("auth_type") or "")
    if "api_key_header" in raw:
        out["api_key_header"] = str(raw.get("api_key_header") or "")
    if "custom_headers" in raw:
        out["custom_headers"] = {str(k): str(v) for k, v in (raw.get("custom_headers") or {}).items()}
    if "scopes" in raw:
        out["scopes"] = [str(item) for item in raw.get("scopes") or []]
    if "auth_server_metadata_url" in raw:
        out["auth_server_metadata_url"] = str(raw.get("auth_server_metadata_url") or "")
    if "client_id" in raw:
        out["client_id"] = str(raw.get("client_id") or "")
    # 创建时允许在 body 里带初始凭证；更新时则强制走 /credentials。
    if include_secrets:
        for field in MCP_CREDENTIAL_FIELDS:
            if raw.get(field):
                out[field] = str(raw[field])
    return out


async def _owned(session: AsyncSession, tenant_id: int, service_id: str) -> MCPService:
    service = await mcp_service_repository.get_service(session, tenant_id, service_id)
    if service is None:
        raise not_found("MCP service not found")
    return service


async def create_service(
    session: AsyncSession, tenant_id: int, payload: dict[str, Any]
) -> MCPService:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise bad_request("name is required")

    transport_type = _validate_transport(
        str(payload.get("transport_type") or ""), payload.get("url")
    )
    auth_config = _normalize_auth_config(payload.get("auth_config"), include_secrets=True)
    advanced = dict(payload.get("advanced_config") or {})
    advanced = {**DEFAULT_MCP_ADVANCED_CONFIG, **advanced} if advanced else dict(DEFAULT_MCP_ADVANCED_CONFIG)

    service = MCPService(
        tenant_id=tenant_id,
        name=name,
        description=str(payload.get("description") or ""),
        enabled=bool(payload.get("enabled", True)),
        transport_type=transport_type,
        url=str(payload.get("url") or "").strip(),
        headers=_normalize_headers(payload.get("headers")),
        auth_config=auth_config,
        advanced_config=advanced,
        stdio_config=dict(payload.get("stdio_config") or {}) if payload.get("stdio_config") else None,
        env_vars=_normalize_headers(payload.get("env_vars")),
        is_builtin=False,
    )
    await mcp_service_repository.save_service(session, service)
    await session.commit()
    await session.refresh(service)
    return service


async def get_service(session: AsyncSession, tenant_id: int, service_id: str) -> MCPService:
    return await _owned(session, tenant_id, service_id)


async def list_services(session: AsyncSession, tenant_id: int) -> list[MCPService]:
    return await mcp_service_repository.list_services(session, tenant_id)


async def update_service(
    session: AsyncSession, tenant_id: int, service_id: str, payload: dict[str, Any]
) -> MCPService:
    service = await _owned(session, tenant_id, service_id)
    if service.is_builtin:
        raise bad_request("builtin MCP services cannot be updated")

    if "name" in payload:
        name = str(payload["name"] or "").strip()
        if not name:
            raise bad_request("name is required")
        service.name = name
    if "description" in payload:
        service.description = str(payload["description"] or "")
    if "enabled" in payload:
        service.enabled = bool(payload["enabled"])
    if "usage_instructions" in payload:
        service.usage_instructions = str(payload["usage_instructions"] or "")
    if "transport_type" in payload or "url" in payload:
        transport_type = str(payload.get("transport_type") or service.transport_type)
        url = payload.get("url") if "url" in payload else service.url
        service.transport_type = _validate_transport(transport_type, url)
        service.url = str(url or "").strip()
    if "headers" in payload:
        service.headers = _normalize_headers(payload.get("headers"))
    if "env_vars" in payload:
        service.env_vars = _normalize_headers(payload.get("env_vars"))
    if "stdio_config" in payload:
        service.stdio_config = dict(payload.get("stdio_config") or {}) if payload.get("stdio_config") else None
    if "advanced_config" in payload:
        advanced = dict(payload.get("advanced_config") or {})
        service.advanced_config = {**DEFAULT_MCP_ADVANCED_CONFIG, **advanced}
    if "auth_config" in payload:
        # 更新走主 PUT 只接受非机密 auth 字段；凭证经 /credentials。
        existing = service.auth_config or {}
        merged = _normalize_auth_config(payload.get("auth_config"), include_secrets=False) or {}
        if "custom_headers" in merged:
            existing["custom_headers"] = merged["custom_headers"]
        for key in ("auth_type", "api_key_header", "scopes", "auth_server_metadata_url", "client_id"):
            if key in merged:
                existing[key] = merged[key]
        service.auth_config = existing

    await session.commit()
    await session.refresh(service)
    return service


async def delete_service(session: AsyncSession, tenant_id: int, service_id: str) -> None:
    service = await _owned(session, tenant_id, service_id)
    if service.is_builtin:
        raise bad_request("builtin MCP services cannot be deleted")
    await mcp_service_repository.delete_service(session, service)
    await session.commit()


async def test_service(session: AsyncSession, tenant_id: int, service_id: str) -> dict[str, Any]:
    service = await mcp_service_repository.get_service(session, tenant_id, service_id)
    if service is None:
        return {"success": False, "message": "MCP service not found"}
    try:
        client = MCPClient(service)
        init = await client.initialize()
        server_info = init.get("serverInfo") or {}
        capabilities = init.get("capabilities") or {}
        tools = await client.list_tools() if "tools" in capabilities else []
        resources = await client.list_resources() if "resources" in capabilities else []
        return {
            "success": True,
            "message": (
                f"Connected successfully to {server_info.get('name', '')} "
                f"v{server_info.get('version', '')}"
            ),
            "description": server_info.get("description", ""),
            "tools": tools,
            "resources": resources,
        }
    except Exception as exc:  # noqa: BLE001 - 测试失败返回结果而非中断
        return {"success": False, "message": f"Test failed: {type(exc).__name__}: {exc}"}


async def _connect_and_list(service: MCPService, kind: str) -> list[Any]:
    client = MCPClient(service)
    await client.initialize()
    return await (client.list_tools() if kind == "tools" else client.list_resources())


async def get_tools(session: AsyncSession, tenant_id: int, service_id: str) -> list[Any]:
    service = await _owned(session, tenant_id, service_id)
    try:
        return await _connect_and_list(service, "tools")
    except Exception as exc:
        raise bad_request(f"failed to list tools: {type(exc).__name__}: {exc}") from exc


async def get_resources(session: AsyncSession, tenant_id: int, service_id: str) -> list[Any]:
    service = await _owned(session, tenant_id, service_id)
    try:
        return await _connect_and_list(service, "resources")
    except Exception as exc:
        raise bad_request(f"failed to list resources: {type(exc).__name__}: {exc}") from exc


# --------------------------------------------------------------------------
# 凭证子资源
# --------------------------------------------------------------------------


async def set_credentials(
    session: AsyncSession, tenant_id: int, service_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    service = await _owned(session, tenant_id, service_id)
    if service.is_builtin:
        raise bad_request("builtin MCP services cannot have credentials modified")
    auth = dict(service.auth_config or {})
    for field in MCP_CREDENTIAL_FIELDS:
        if payload.get(field):
            auth[field] = str(payload[field])
    service.auth_config = auth
    service.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(service)
    auth = service.auth_config or {}
    return {"fields": {field: {"configured": bool(auth.get(field))} for field in MCP_CREDENTIAL_FIELDS}}


async def clear_credential(
    session: AsyncSession, tenant_id: int, service_id: str, field: str
) -> None:
    if field not in MCP_CREDENTIAL_FIELDS:
        raise bad_request(f"unknown credential field: {field}")
    service = await _owned(session, tenant_id, service_id)
    if service.is_builtin:
        raise bad_request("builtin MCP services cannot have credentials modified")
    auth = dict(service.auth_config or {})
    auth[field] = ""
    service.auth_config = auth
    service.updated_at = datetime.now(UTC)
    await session.commit()


# --------------------------------------------------------------------------
# 持久化目录 metadata
# --------------------------------------------------------------------------


async def get_metadata(
    session: AsyncSession, tenant_id: int, service_id: str
) -> dict[str, Any] | None:
    service = await _owned(session, tenant_id, service_id)
    meta = await mcp_service_repository.get_metadata(session, tenant_id, service_id, "")
    return metadata_payload(meta, service) if meta is not None else None


async def refresh_metadata(
    session: AsyncSession, tenant_id: int, service_id: str
) -> dict[str, Any]:
    service = await _owned(session, tenant_id, service_id)
    client = MCPClient(service)
    init = await client.initialize()
    server_info = init.get("serverInfo") or {}
    tools = await client.list_tools()

    meta = await mcp_service_repository.get_metadata(session, tenant_id, service_id, "")
    now = datetime.now(UTC)
    if meta is None:
        meta = MCPMetadata(
            tenant_id=tenant_id,
            service_id=service_id,
            principal="",
            config_fingerprint=config_fingerprint(service),
            tools=tools,
            instructions=init.get("instructions") or "",
            server_name=server_info.get("name", ""),
            server_version=server_info.get("version", ""),
            server_description=server_info.get("description", ""),
            synced_at=now,
        )
    else:
        meta.config_fingerprint = config_fingerprint(service)
        meta.tools = tools
        meta.instructions = init.get("instructions") or ""
        meta.server_name = server_info.get("name", "")
        meta.server_version = server_info.get("version", "")
        meta.server_description = server_info.get("description", "")
        meta.synced_at = now
    await mcp_service_repository.save_metadata(session, meta)
    await session.commit()
    await session.refresh(meta)
    return metadata_payload(meta, service)


# --------------------------------------------------------------------------
# 工具审批
# --------------------------------------------------------------------------


def _approval_payload(row: MCPToolApproval) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "service_id": row.service_id,
        "tool_name": row.tool_name,
        "require_approval": bool(row.require_approval),
        "enabled": bool(row.enabled),
    }


async def list_tool_approvals(
    session: AsyncSession, tenant_id: int, service_id: str
) -> list[dict[str, Any]]:
    await _owned(session, tenant_id, service_id)
    rows = await mcp_tool_approval_repository.list_by_service(session, tenant_id, service_id)
    return [_approval_payload(row) for row in rows]


async def set_tool_approval(
    session: AsyncSession,
    tenant_id: int,
    service_id: str,
    tool_name: str,
    require_approval: bool | None,
    enabled: bool | None,
) -> dict[str, Any]:
    await _owned(session, tenant_id, service_id)
    row = await mcp_tool_approval_repository.get_approval(
        session, tenant_id, service_id, tool_name
    )
    if row is None:
        row = MCPToolApproval(
            tenant_id=tenant_id,
            service_id=service_id,
            tool_name=tool_name,
            require_approval=bool(require_approval) if require_approval is not None else False,
            enabled=bool(enabled) if enabled is not None else True,
        )
    else:
        if require_approval is not None:
            row.require_approval = bool(require_approval)
        if enabled is not None:
            row.enabled = bool(enabled)
    await mcp_tool_approval_repository.save_approval(session, row)
    await session.commit()
    await session.refresh(row)
    return _approval_payload(row)
