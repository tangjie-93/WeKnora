"""测试公共辅助：注册登录、建模型、建库上传。"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

PASSWORD = "Abcdef12"


async def register_and_login(
    client: AsyncClient, email: str, username: str = ""
) -> dict[str, str]:
    register = await client.post(
        "/api/v1/auth/register",
        json={"username": username or email.split("@")[0], "email": email, "password": PASSWORD},
    )
    assert register.status_code in (201, 400), register.text

    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    body = login.json()
    return {
        "Authorization": f"Bearer {body['token']}",
        "X-Tenant-ID": str(body["active_tenant"]["id"]),
    }


async def create_model(
    client: AsyncClient,
    headers: dict[str, str],
    base_url: str,
    name: str,
    model_type: str,
    dimension: int = 64,
) -> dict[str, Any]:
    parameters: dict[str, Any] = {"base_url": base_url, "api_key": "test-key"}
    if model_type == "embedding":
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
    return response.json()["data"]


async def create_models(
    client: AsyncClient, headers: dict[str, str], base_url: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    chat = await create_model(client, headers, base_url, "fake-chat", "chat")
    embedding = await create_model(client, headers, base_url, "fake-embedding", "embedding")
    return chat, embedding


async def create_kb(
    client: AsyncClient, headers: dict[str, str], name: str = "测试知识库"
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/knowledge-bases",
        headers=headers,
        json={"name": name, "description": "pytest 用例", "chunking_config": {"chunk_size": 120}},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


SAMPLE_TEXT = (
    "Nebula 模块负责知识入库：上传文档后会自动解析、分块并写入向量索引。\n\n"
    "Nebula 默认端口是 8080，管理后台通过 /swagger/index.html 访问。\n\n"
    "部署时需要 PostgreSQL 存储业务数据，Redis 用于缓存与任务队列。"
)


async def upload_sample(
    client: AsyncClient, headers: dict[str, str], kb_id: str, filename: str = "guide.txt"
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/knowledge/file",
        headers=headers,
        files={"file": (filename, SAMPLE_TEXT.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]
