"""模型持久化。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import MODEL_TYPE_EMBEDDING, Model


async def list_models(session: AsyncSession, tenant_id: int) -> list[Model]:
    stmt = (
        select(Model)
        .where(Model.tenant_id == tenant_id, Model.deleted_at.is_(None))
        .order_by(Model.created_at.desc())
    )
    return list((await session.scalars(stmt)).all())


async def get_model(session: AsyncSession, tenant_id: int, model_id: str) -> Model | None:
    stmt = select(Model).where(
        Model.id == model_id, Model.tenant_id == tenant_id, Model.deleted_at.is_(None)
    )
    return await session.scalar(stmt)


async def first_of_type(session: AsyncSession, tenant_id: int, model_type: str) -> Model | None:
    stmt = (
        select(Model)
        .where(
            Model.tenant_id == tenant_id,
            Model.type == model_type,
            Model.deleted_at.is_(None),
            Model.status == "active",
        )
        .order_by(Model.is_default.desc(), Model.created_at.asc())
    )
    return await session.scalar(stmt)


async def default_embedding_model(session: AsyncSession, tenant_id: int) -> Model | None:
    return await first_of_type(session, tenant_id, MODEL_TYPE_EMBEDDING)


async def save_model(session: AsyncSession, model: Model) -> Model:
    session.add(model)
    await session.flush()
    return model


async def clear_default(
    session: AsyncSession, tenant_id: int, model_type: str, exclude_id: str | None = None
) -> None:
    """清掉同类型模型的默认标记；`exclude_id` 用于切换默认时保留目标模型自身。"""
    models = await list_models(session, tenant_id)
    for model in models:
        if model.type == model_type and model.is_default and model.id != exclude_id:
            model.is_default = False
