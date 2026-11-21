"""In-process API contract checks; no database, credentials or external services."""

import pytest
from fastapi.testclient import TestClient

from app.main import app, create_app


@pytest.fixture
def client():
    with TestClient(create_app(), follow_redirects=False) as test_client:
        yield test_client


def test_health_exact_public_contract(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"].split(";")[0] == "application/json"
    assert response.headers["x-weknora-implementation"] == "python-fastapi"
    assert response.history == []


@pytest.mark.parametrize("path", ["/health/", "/unknown", "/api/v1/health"])
def test_unregistered_paths_are_404_without_redirect(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    assert "location" not in response.headers
    assert "x-weknora-implementation" not in response.headers


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
def test_other_methods_are_405(client, method):
    response = client.request(method, "/health")
    assert response.status_code == 405
    assert response.headers["allow"] == "GET"
    assert "x-weknora-implementation" not in response.headers
    if method != "HEAD":
        assert response.json() == {"detail": "Method Not Allowed"}
        assert "Traceback" not in response.text
        assert "/Users/" not in response.text


def test_module_application_and_fresh_application_are_independent():
    fresh = create_app()
    assert fresh is not app
    assert fresh.router.redirect_slashes is False
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
