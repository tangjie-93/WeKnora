"""真实大模型连通性用例（默认跳过，需显式开启）。

离线跑 `pytest -q` 时不会发起真实外网调用；要跑真实模型：
    $env:RUN_REAL_LLM="1"; .\\.venv\\Scripts\\python.exe -m pytest tests\\e2e\\test_real_models.py -q
前置：`python/backend/.env` 已填写 `.env.example` 中的真实 key。
完整链路（入库/检索/SSE）请跑 `scripts/real_e2e.py`。
"""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from tests.helpers import PASSWORD

settings = get_settings()
RUN = os.environ.get("RUN_REAL_LLM", "").strip() in {"1", "true", "yes", "on"}
CHAT_READY = bool(settings.llm_chat_base_url and settings.llm_chat_model and settings.llm_chat_api_key)
EMBEDDING_READY = bool(
    settings.llm_embedding_base_url and settings.llm_embedding_model and settings.llm_embedding_api_key
)

pytestmark = pytest.mark.skipif(
    not (RUN and CHAT_READY), reason="未开启 RUN_REAL_LLM 或未配置真实模型 key"
)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _login(client: AsyncClient) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register",
        json={"username": "realuser", "email": "real-llm@example.com", "password": PASSWORD},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": "real-llm@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    body = login.json()
    return {
        "Authorization": f"Bearer {body['token']}",
        "X-Tenant-ID": str(body["active_tenant"]["id"]),
    }


async def _create_model(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str,
    model_type: str,
    base_url: str,
    api_key: str,
    dimension: int | None = None,
) -> str:
    parameters: dict[str, object] = {"base_url": base_url, "api_key": api_key}
    if dimension:
        parameters["embedding_parameters"] = {"dimension": dimension}
    response = await client.post(
        "/api/v1/models",
        headers=headers,
        json={
            "name": name,
            "display_name": name,
            "type": model_type,
            "is_default": True,
            "parameters": parameters,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


async def test_deepseek_chat_real(client: AsyncClient) -> None:
    headers = await _login(client)
    model_id = await _create_model(
        client,
        headers,
        name=settings.llm_chat_model,
        model_type="chat",
        base_url=settings.llm_chat_base_url,
        api_key=settings.llm_chat_api_key,
    )
    result = await client.post(f"/api/v1/models/{model_id}/test", headers=headers)
    assert result.status_code == 200, result.text
    data = result.json()["data"]
    assert data["ok"] is True
    assert data["reply"], "DeepSeek 无回复"


@pytest.mark.skipif(not EMBEDDING_READY, reason="未配置真实 embedding key")
async def test_openai_embedding_real(client: AsyncClient) -> None:
    headers = await _login(client)
    model_id = await _create_model(
        client,
        headers,
        name=settings.llm_embedding_model,
        model_type="embedding",
        base_url=settings.llm_embedding_base_url,
        api_key=settings.llm_embedding_api_key,
        dimension=settings.llm_embedding_dimension,
    )
    result = await client.post(f"/api/v1/models/{model_id}/test", headers=headers)
    assert result.status_code == 200, result.text
    data = result.json()["data"]
    assert data["ok"] is True
    assert data["dimension"] == settings.llm_embedding_dimension
