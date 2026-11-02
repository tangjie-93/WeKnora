"""模型路由：/api/v1/models"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AuthContext, get_auth_context, get_session, require_role
from app.domain.entities import ROLE_ADMIN
from app.services import model_service

router = APIRouter(prefix="/models", tags=["模型"])
admin_only = require_role(ROLE_ADMIN)


@router.get("")
async def list_models(
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    models = await model_service.list_models(session, context.tenant_id)
    return {"success": True, "data": [model_service.model_payload(m) for m in models]}


@router.post("", status_code=201)
async def create_model(
    payload: dict,
    context: AuthContext = Depends(admin_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    model = await model_service.create_model(session, context.tenant_id, payload)
    return {"success": True, "data": model_service.model_payload(model)}


@router.get("/{model_id}")
async def get_model(
    model_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    model = await model_service.get_model(session, context.tenant_id, model_id)
    return {"success": True, "data": model_service.model_payload(model)}


@router.put("/{model_id}")
async def update_model(
    model_id: str,
    payload: dict,
    context: AuthContext = Depends(admin_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    model = await model_service.update_model(session, context.tenant_id, model_id, payload)
    return {"success": True, "data": model_service.model_payload(model)}


@router.delete("/{model_id}")
async def delete_model(
    model_id: str,
    context: AuthContext = Depends(admin_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await model_service.delete_model(session, context.tenant_id, model_id)
    return {"success": True, "message": "model deleted"}


@router.post("/{model_id}/test")
async def test_model(
    model_id: str,
    context: AuthContext = Depends(admin_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await model_service.test_model(session, context.tenant_id, model_id)
    return {"success": True, "data": result}
