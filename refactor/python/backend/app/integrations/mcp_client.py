"""MCP 客户端（HTTP-streamable），连接外部 MCP 服务并列出工具/资源。

仅支持 http-streamable 传输（对应 Go 禁用 stdio；SSE 本阶段未实现）。JSON-RPC 2.0
无状态请求，每次调用独立连接。
"""

from __future__ import annotations

from typing import Any

import httpx

from app.domain.entities import MCP_AUTH_API_KEY, MCP_AUTH_BEARER, MCP_TRANSPORT_HTTP_STREAMABLE

DEFAULT_TIMEOUT = 30.0
CLIENT_INFO = {"name": "weknora", "version": "1.0.0"}


class MCPClientError(Exception):
    """MCP 客户端配置错误（传输不支持 / 缺少 URL 等）。"""


def build_headers(service: Any) -> dict[str, str]:
    headers: dict[str, str] = dict(service.headers or {})
    auth = service.auth_config or {}
    auth_type = auth.get("auth_type") or ""
    if auth_type == MCP_AUTH_API_KEY and auth.get("api_key"):
        header_name = auth.get("api_key_header") or "X-API-Key"
        headers[header_name] = str(auth["api_key"])
    elif auth_type == MCP_AUTH_BEARER and auth.get("token"):
        headers["Authorization"] = f"Bearer {auth['token']}"
    headers.setdefault("Content-Type", "application/json")
    headers.setdefault("Accept", "application/json, text/event-stream")
    return headers


class MCPClient:
    def __init__(self, service: Any, timeout: float | None = None) -> None:
        if service.transport_type != MCP_TRANSPORT_HTTP_STREAMABLE:
            raise MCPClientError(
                f"transport {service.transport_type!r} not supported (only http-streamable)"
            )
        if not service.url:
            raise MCPClientError("url is required for http-streamable transport")
        self.url = str(service.url).rstrip("/")
        self.headers = build_headers(service)
        advanced = service.advanced_config or {}
        self.timeout = timeout or float(advanced.get("timeout") or DEFAULT_TIMEOUT)

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.url,
                headers=self.headers,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            )
            response.raise_for_status()
            data = response.json()
        if "error" in data:
            raise MCPClientError(f"RPC {method} failed: {data['error']}")
        return data

    async def initialize(self) -> dict[str, Any]:
        data = await self._rpc(
            "initialize",
            {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": CLIENT_INFO},
        )
        return data.get("result") or {}

    async def list_tools(self) -> list[Any]:
        data = await self._rpc("tools/list", {})
        return list((data.get("result") or {}).get("tools") or [])

    async def list_resources(self) -> list[Any]:
        data = await self._rpc("resources/list", {})
        return list((data.get("result") or {}).get("resources") or [])
