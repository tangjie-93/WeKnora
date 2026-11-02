"""Phase 8B 自测：MCP Client 管理 API + 凭证子资源 + 测试连接 + 工具审批 + 持久化目录。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.helpers import register_and_login


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _create_service(client: AsyncClient, headers: dict[str, str], **overrides) -> dict:
    payload: dict = {
        "name": "external-mcp",
        "transport_type": "http-streamable",
        "url": "http://127.0.0.1:1/mcp",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/mcp-services", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def test_create_get_list(client: AsyncClient, fake_mcp_base_url: str) -> None:
    headers = await register_and_login(client, "mcps-crud@example.com")
    created = await _create_service(client, headers, url=fake_mcp_base_url)
    assert created["id"]
    assert created["transport_type"] == "http-streamable"
    assert created["enabled"] is True

    detail = await client.get(f"/api/v1/mcp-services/{created['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["name"] == "external-mcp"

    listing = await client.get("/api/v1/mcp-services", headers=headers)
    assert listing.status_code == 200
    assert any(item["id"] == created["id"] for item in listing.json()["data"])


async def test_create_requires_url(client: AsyncClient, fake_mcp_base_url: str) -> None:
    headers = await register_and_login(client, "mcps-url@example.com")
    response = await client.post(
        "/api/v1/mcp-services",
        headers=headers,
        json={"name": "no-url", "transport_type": "http-streamable"},
    )
    assert response.status_code == 400


async def test_stdio_disabled(client: AsyncClient, fake_mcp_base_url: str) -> None:
    headers = await register_and_login(client, "mcps-stdio@example.com")
    response = await client.post(
        "/api/v1/mcp-services",
        headers=headers,
        json={"name": "stdio-svc", "transport_type": "stdio", "url": "http://x"},
    )
    assert response.status_code == 400


async def test_credentials_subresource(client: AsyncClient, fake_mcp_base_url: str) -> None:
    headers = await register_and_login(client, "mcps-cred@example.com")
    created = await _create_service(
        client,
        headers,
        url=fake_mcp_base_url,
        auth_config={"auth_type": "api_key", "api_key": "sk-secret-value"},
    )
    # 主响应不得回显明文凭证
    assert "sk-secret-value" not in str(created)
    assert created["auth_config"]["auth_type"] == "api_key"
    assert created["credentials"]["api_key"]["configured"] is True
    assert created["credentials"]["token"]["configured"] is False

    put = await client.put(
        f"/api/v1/mcp-services/{created['id']}/credentials",
        headers=headers,
        json={"token": "tok-abc", "client_secret": "cs-xyz"},
    )
    assert put.status_code == 200, put.text
    fields = put.json()["data"]["fields"]
    assert fields["api_key"]["configured"] is True
    assert fields["token"]["configured"] is True
    assert fields["client_secret"]["configured"] is True

    cleared = await client.delete(
        f"/api/v1/mcp-services/{created['id']}/credentials/api_key", headers=headers
    )
    assert cleared.status_code == 200
    detail = await client.get(f"/api/v1/mcp-services/{created['id']}", headers=headers)
    assert detail.json()["data"]["credentials"]["api_key"]["configured"] is False


async def test_test_connection(client: AsyncClient, fake_mcp_base_url: str) -> None:
    headers = await register_and_login(client, "mcps-test@example.com")
    created = await _create_service(client, headers, url=fake_mcp_base_url)
    response = await client.post(
        f"/api/v1/mcp-services/{created['id']}/test", headers=headers
    )
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["success"] is True
    assert "fake-mcp" in result["message"]
    tool_names = {tool["name"] for tool in result["tools"]}
    assert tool_names == {"echo", "add"}
    assert result["resources"][0]["uri"] == "resource://hello"


async def test_get_tools_resources(client: AsyncClient, fake_mcp_base_url: str) -> None:
    headers = await register_and_login(client, "mcps-tools@example.com")
    created = await _create_service(client, headers, url=fake_mcp_base_url)

    tools = await client.get(f"/api/v1/mcp-services/{created['id']}/tools", headers=headers)
    assert tools.status_code == 200
    assert {tool["name"] for tool in tools.json()["data"]} == {"echo", "add"}

    resources = await client.get(
        f"/api/v1/mcp-services/{created['id']}/resources", headers=headers
    )
    assert resources.status_code == 200
    assert resources.json()["data"][0]["name"] == "hello"


async def test_metadata_refresh_and_get(client: AsyncClient, fake_mcp_base_url: str) -> None:
    headers = await register_and_login(client, "mcps-meta@example.com")
    created = await _create_service(client, headers, url=fake_mcp_base_url)

    empty = await client.get(f"/api/v1/mcp-services/{created['id']}/metadata", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["data"] is None

    refreshed = await client.post(
        f"/api/v1/mcp-services/{created['id']}/metadata/refresh", headers=headers
    )
    assert refreshed.status_code == 200, refreshed.text
    data = refreshed.json()["data"]
    assert data["server_name"] == "fake-mcp"
    assert len(data["tools"]) == 2

    got = await client.get(f"/api/v1/mcp-services/{created['id']}/metadata", headers=headers)
    assert got.json()["data"]["service_id"] == created["id"]


async def test_tool_approvals(client: AsyncClient, fake_mcp_base_url: str) -> None:
    headers = await register_and_login(client, "mcps-approval@example.com")
    created = await _create_service(client, headers, url=fake_mcp_base_url)

    empty = await client.get(
        f"/api/v1/mcp-services/{created['id']}/tool-approvals", headers=headers
    )
    assert empty.status_code == 200
    assert empty.json()["data"] == []

    put = await client.put(
        f"/api/v1/mcp-services/{created['id']}/tool-approvals/echo",
        headers=headers,
        json={"require_approval": True, "enabled": False},
    )
    assert put.status_code == 200, put.text

    rows = await client.get(
        f"/api/v1/mcp-services/{created['id']}/tool-approvals", headers=headers
    )
    row = rows.json()["data"][0]
    assert row["tool_name"] == "echo"
    assert row["require_approval"] is True
    assert row["enabled"] is False


async def test_update_and_delete(client: AsyncClient, fake_mcp_base_url: str) -> None:
    headers = await register_and_login(client, "mcps-delete@example.com")
    created = await _create_service(client, headers, url=fake_mcp_base_url)

    updated = await client.put(
        f"/api/v1/mcp-services/{created['id']}",
        headers=headers,
        json={"name": "改名服务", "enabled": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["name"] == "改名服务"
    assert updated.json()["data"]["enabled"] is False

    deleted = await client.delete(f"/api/v1/mcp-services/{created['id']}", headers=headers)
    assert deleted.status_code == 200
    gone = await client.get(f"/api/v1/mcp-services/{created['id']}", headers=headers)
    assert gone.status_code == 404


async def test_create_requires_auth(client: AsyncClient, fake_mcp_base_url: str) -> None:
    response = await client.post(
        "/api/v1/mcp-services", json={"name": "x", "transport_type": "http-streamable", "url": "http://x"}
    )
    assert response.status_code == 401
