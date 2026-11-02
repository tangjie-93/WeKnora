"""MCP Endpoint 服务：工作空间发布的 MCP 服务器端点 CRUD + 鉴权。

对齐 Go `internal/application/service/mcp_endpoint.go`：
- token = `mcp_` + base64url(32 字节随机)，只存 SHA-256 hex，明文仅在 create/rotate 返回一次
- 工具白名单按目录规范化；知识库/agent 引用在建点前校验
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, forbidden, not_found, unauthorized
from app.domain.entities import (
    DEFAULT_MCP_ENDPOINT_RATE_LIMIT_PER_MINUTE,
    MCP_ENDPOINT_MAX_NAME_LEN,
    MCP_ENDPOINT_MAX_RATE_PER_MIN,
    MCP_ENDPOINT_TOKEN_PREFIX,
    MCP_ENDPOINT_TOOL_CATALOG,
    MCP_ENDPOINT_TOOL_GROUPS,
    MCPEndpoint,
    default_mcp_endpoint_tools,
    normalize_mcp_endpoint_tools,
)
from app.repositories import knowledge_repository, mcp_endpoint_repository

TOKEN_HINT_LEN = 12


def _iso(value) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat().replace("+00:00", "Z")


def generate_token() -> str:
    return MCP_ENDPOINT_TOKEN_PREFIX + base64.urlsafe_b64encode(
        secrets.token_bytes(32)
    ).decode().rstrip("=")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_hint(token: str) -> str:
    return token[:TOKEN_HINT_LEN]


def endpoint_payload(endpoint: MCPEndpoint, token: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": endpoint.id,
        "tenant_id": endpoint.tenant_id,
        "name": endpoint.name,
        "description": endpoint.description or "",
        "enabled": bool(endpoint.enabled),
        "token_hint": endpoint.token_hint or "",
        "knowledge_base_ids": list(endpoint.knowledge_base_ids or []),
        "tools": list(endpoint.tools or []),
        "default_agent_id": endpoint.default_agent_id or "",
        "rate_limit_per_minute": int(endpoint.rate_limit_per_minute),
        "path": f"/mcp/{endpoint.id}",
        "last_used_at": _iso(endpoint.last_used_at),
        "created_at": _iso(endpoint.created_at),
        "updated_at": _iso(endpoint.updated_at),
    }
    if token:
        row["token"] = token
    return row


def tool_catalog_payload() -> dict[str, Any]:
    tools = [
        {"name": item["name"], "group": item["group"], "destructive": item["destructive"]}
        for item in MCP_ENDPOINT_TOOL_CATALOG
    ]
    return {
        "groups": list(MCP_ENDPOINT_TOOL_GROUPS),
        "tools": tools,
        "default_tools": default_mcp_endpoint_tools(),
    }


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------


def _normalize_rate(rate: int) -> int:
    if rate == 0:
        return DEFAULT_MCP_ENDPOINT_RATE_LIMIT_PER_MINUTE
    if rate < 0 or rate > MCP_ENDPOINT_MAX_RATE_PER_MIN:
        raise bad_request("rate_limit_per_minute is out of range")
    return rate


async def _validate_kbs(session: AsyncSession, tenant_id: int, ids: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in ids:
        kb_id = (raw or "").strip()
        if not kb_id or kb_id in seen:
            continue
        kb = await knowledge_repository.get_kb(session, tenant_id, kb_id)
        if kb is None:
            raise not_found(f"knowledge base not found: {kb_id}")
        seen.add(kb_id)
        out.append(kb_id)
    return out


async def _validate_agent(session: AsyncSession, tenant_id: int, agent_id: str) -> str:
    agent_id = (agent_id or "").strip()
    if not agent_id:
        return ""
    from app.services import agent_service

    await agent_service.get_agent(session, tenant_id, agent_id)
    return agent_id


async def _owned(session: AsyncSession, tenant_id: int, endpoint_id: str) -> MCPEndpoint:
    endpoint = await mcp_endpoint_repository.get_endpoint(session, endpoint_id)
    if endpoint is None or endpoint.tenant_id != tenant_id:
        raise not_found("mcp endpoint not found")
    return endpoint


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------


async def create_endpoint(
    session: AsyncSession, tenant_id: int, payload: dict[str, Any]
) -> tuple[MCPEndpoint, str]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise bad_request("name is required")
    if len(name) > MCP_ENDPOINT_MAX_NAME_LEN:
        raise bad_request("name is too long")

    tools = default_mcp_endpoint_tools()
    if payload.get("tools") is not None:
        tools = normalize_mcp_endpoint_tools([str(item) for item in payload["tools"]])
    if not tools:
        raise bad_request("at least one tool must be enabled")

    kb_ids = await _validate_kbs(
        session, tenant_id, [str(item) for item in payload.get("knowledge_base_ids") or []]
    )
    agent_id = await _validate_agent(session, tenant_id, str(payload.get("default_agent_id") or ""))
    rate = _normalize_rate(int(payload.get("rate_limit_per_minute") or 0))

    token = generate_token()
    endpoint = MCPEndpoint(
        tenant_id=tenant_id,
        name=name,
        description=str(payload.get("description") or ""),
        enabled=bool(payload.get("enabled", True)),
        token_hash=hash_token(token),
        token_hint=token_hint(token),
        knowledge_base_ids=kb_ids,
        tools=tools,
        default_agent_id=agent_id,
        rate_limit_per_minute=rate,
    )
    await mcp_endpoint_repository.save_endpoint(session, endpoint)
    await session.commit()
    await session.refresh(endpoint)
    return endpoint, token


async def get_endpoint(session: AsyncSession, tenant_id: int, endpoint_id: str) -> MCPEndpoint:
    return await _owned(session, tenant_id, endpoint_id)


async def list_endpoints(session: AsyncSession, tenant_id: int) -> list[MCPEndpoint]:
    return await mcp_endpoint_repository.list_endpoints(session, tenant_id)


async def update_endpoint(
    session: AsyncSession, tenant_id: int, endpoint_id: str, payload: dict[str, Any]
) -> MCPEndpoint:
    endpoint = await _owned(session, tenant_id, endpoint_id)

    if payload.get("name") is not None:
        name = str(payload["name"]).strip()
        if not name:
            raise bad_request("name is required")
        if len(name) > MCP_ENDPOINT_MAX_NAME_LEN:
            raise bad_request("name is too long")
        endpoint.name = name
    if payload.get("description") is not None:
        endpoint.description = str(payload["description"])
    if payload.get("enabled") is not None:
        endpoint.enabled = bool(payload["enabled"])
    if payload.get("tools") is not None:
        tools = normalize_mcp_endpoint_tools([str(item) for item in payload["tools"]])
        if not tools:
            raise bad_request("at least one tool must be enabled")
        endpoint.tools = tools
    if payload.get("knowledge_base_ids") is not None:
        endpoint.knowledge_base_ids = await _validate_kbs(
            session, tenant_id, [str(item) for item in payload["knowledge_base_ids"]]
        )
    if payload.get("default_agent_id") is not None:
        endpoint.default_agent_id = await _validate_agent(
            session, tenant_id, str(payload["default_agent_id"])
        )
    if payload.get("rate_limit_per_minute") is not None:
        endpoint.rate_limit_per_minute = _normalize_rate(
            int(payload.get("rate_limit_per_minute") or 0)
        )

    await session.commit()
    await session.refresh(endpoint)
    return endpoint


async def delete_endpoint(session: AsyncSession, tenant_id: int, endpoint_id: str) -> None:
    endpoint = await _owned(session, tenant_id, endpoint_id)
    await mcp_endpoint_repository.delete_endpoint(session, endpoint)
    await session.commit()


async def rotate_token(
    session: AsyncSession, tenant_id: int, endpoint_id: str
) -> tuple[MCPEndpoint, str]:
    endpoint = await _owned(session, tenant_id, endpoint_id)
    token = generate_token()
    endpoint.token_hash = hash_token(token)
    endpoint.token_hint = token_hint(token)
    await session.commit()
    await session.refresh(endpoint)
    return endpoint, token


# --------------------------------------------------------------------------
# 鉴权（公开 /mcp/{endpoint_id} 面）
# --------------------------------------------------------------------------


async def authenticate(
    session: AsyncSession, endpoint_id: str, token: str
) -> MCPEndpoint:
    endpoint_id = (endpoint_id or "").strip()
    token = (token or "").strip()
    if not endpoint_id or not token or not token.startswith(MCP_ENDPOINT_TOKEN_PREFIX):
        raise unauthorized("unauthorized: invalid token")

    endpoint = await mcp_endpoint_repository.get_endpoint_by_token_hash(
        session, hash_token(token)
    )
    if endpoint is None or endpoint.id != endpoint_id:
        raise unauthorized("unauthorized: invalid token")
    if not endpoint.enabled:
        raise forbidden("mcp endpoint disabled")
    return endpoint
