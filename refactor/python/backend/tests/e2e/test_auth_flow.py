from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.parametrize("identity", [" alice@example.com ", " alice "])
async def test_login_normalizes_identity_like_registration(identity: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/auth/register", json={
            "username": " alice ", "email": " alice@example.com ", "password": " Abcdef12 ",
        })
        assert response.status_code == 201, response.text
        response = await client.post("/api/v1/auth/login", json={
            "email": identity, "password": " Abcdef12 ",
        })
        assert response.status_code == 200, response.text
        token = response.json()["token"]
        me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        wrong_password = await client.post("/api/v1/auth/login", json={
            "email": identity, "password": "Abcdef12",
        })
        assert wrong_password.status_code == 401


async def test_health() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_register_login_me_refresh_logout() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        register = await client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "email": "alice@example.com", "password": "Abcdef12"},
        )
        assert register.status_code == 201, register.text
        assert register.json()["success"] is True

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "alice@example.com", "password": "Abcdef12"},
        )
        assert login.status_code == 200, login.text
        body = login.json()
        assert body["user"]["email"] == "alice@example.com"
        assert body["active_tenant"]["name"] == "alice"
        assert body["memberships"][0]["role"] == "owner"
        assert body["token"]
        assert body["refresh_token"]

        headers = {"Authorization": f"Bearer {body['token']}"}
        me = await client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200, me.text
        assert me.json()["data"]["user"]["username"] == "alice"

        refreshed = await client.post(
            "/api/v1/auth/refresh", json={"refreshToken": body["refresh_token"]}
        )
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()["access_token"]

        logout = await client.post("/api/v1/auth/logout", headers=headers)
        assert logout.status_code == 200

        after_logout = await client.get("/api/v1/auth/me", headers=headers)
        assert after_logout.status_code == 401
