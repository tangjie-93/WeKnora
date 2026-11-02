"""模型网关服务：CRUD + 连通性测试。"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, not_found
from app.domain.entities import (
    MODEL_STATUS_ACTIVE,
    MODEL_STATUS_DISABLED,
    MODEL_TYPE_CHAT,
    MODEL_TYPE_EMBEDDING,
    MODEL_TYPES,
    SOURCE_REMOTE,
    Model,
)
from app.llm import ChatMessage, OpenAICompatibleClient
from app.repositories import model_repository


def _iso(value) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat().replace("+00:00", "Z")


def model_payload(model: Model) -> dict[str, Any]:
    parameters = dict(model.parameters or {})
    if parameters.get("api_key"):
        # 与 Go 端一致：不回传明文密钥
        parameters["api_key"] = "******"
    return {
        "id": model.id,
        "tenant_id": model.tenant_id,
        "name": model.name,
        "display_name": model.display_name or model.name,
        "type": model.type,
        "source": model.source,
        "description": model.description or "",
        "parameters": parameters,
        "is_default": bool(model.is_default),
        "is_builtin": bool(model.is_builtin),
        "managed_by": model.managed_by or "",
        "status": model.status,
        "created_at": _iso(model.created_at),
        "updated_at": _iso(model.updated_at),
    }


def _validate_type(model_type: str) -> None:
    if model_type not in MODEL_TYPES:
        raise bad_request(f"invalid model type: {model_type}")


async def list_models(session: AsyncSession, tenant_id: int) -> list[Model]:
    return await model_repository.list_models(session, tenant_id)


async def get_model(session: AsyncSession, tenant_id: int, model_id: str) -> Model:
    model = await model_repository.get_model(session, tenant_id, model_id)
    if model is None:
        raise not_found("model not found")
    return model


async def create_model(
    session: AsyncSession, tenant_id: int, payload: dict[str, Any]
) -> Model:
    name = str(payload.get("name") or "").strip()
    model_type = str(payload.get("type") or "").strip()
    if not name:
        raise bad_request("model name is required")
    _validate_type(model_type)

    parameters = payload.get("parameters") or {}
    if not isinstance(parameters, dict):
        raise bad_request("parameters must be an object")
    if not parameters.get("base_url"):
        raise bad_request("parameters.base_url is required")
    if model_type == MODEL_TYPE_EMBEDDING:
        embedding_parameters = parameters.setdefault("embedding_parameters", {})
        embedding_parameters.setdefault("dimension", 1024)

    model = Model(
        tenant_id=tenant_id,
        name=name,
        display_name=str(payload.get("display_name") or name),
        type=model_type,
        source=str(payload.get("source") or SOURCE_REMOTE),
        description=str(payload.get("description") or ""),
        parameters=parameters,
        is_default=bool(payload.get("is_default")),
        status=str(payload.get("status") or MODEL_STATUS_ACTIVE),
    )
    if model.is_default:
        await model_repository.clear_default(session, tenant_id, model_type)

    await model_repository.save_model(session, model)
    await session.commit()
    await session.refresh(model)
    return model


async def update_model(
    session: AsyncSession, tenant_id: int, model_id: str, payload: dict[str, Any]
) -> Model:
    model = await get_model(session, tenant_id, model_id)

    if payload.get("name"):
        model.name = str(payload["name"])
    if "display_name" in payload:
        model.display_name = str(payload["display_name"] or model.name)
    if "description" in payload:
        model.description = str(payload["description"])
    if "status" in payload:
        model.status = str(payload["status"])
    if "type" in payload:
        _validate_type(str(payload["type"]))
        model.type = str(payload["type"])
    if "parameters" in payload and isinstance(payload["parameters"], dict):
        merged = dict(model.parameters or {})
        for key, value in payload["parameters"].items():
            # 掩码值表示"不修改"
            if key == "api_key" and value == "******":
                continue
            merged[key] = value
        model.parameters = merged
    if "is_default" in payload:
        model.is_default = bool(payload["is_default"])
        if model.is_default:
            await model_repository.clear_default(
                session, tenant_id, model.type, exclude_id=model.id
            )

    await session.commit()
    await session.refresh(model)
    return model


async def delete_model(session: AsyncSession, tenant_id: int, model_id: str) -> None:
    model = await get_model(session, tenant_id, model_id)
    from datetime import datetime

    model.deleted_at = datetime.now(UTC)
    model.status = MODEL_STATUS_DISABLED
    await session.commit()


async def test_model(session: AsyncSession, tenant_id: int, model_id: str) -> dict[str, Any]:
    """真实发起一次上游调用，返回耗时与样例输出。"""
    model = await get_model(session, tenant_id, model_id)
    client = OpenAICompatibleClient(model, timeout=30.0)

    if model.type == MODEL_TYPE_EMBEDDING:
        vectors = await client.embed(["WeKnora connectivity check"])
        return {"ok": True, "dimension": len(vectors[0]) if vectors else 0}

    if model.type == MODEL_TYPE_CHAT:
        answer = await client.complete(
            [ChatMessage(role="user", content="reply with the single word: pong")]
        )
        return {"ok": True, "reply": answer[:200]}

    return {"ok": True, "skipped": f"type {model.type} has no test routine"}
