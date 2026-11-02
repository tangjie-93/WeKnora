"""把 `.env` 里配置的真实大模型写入 `models` 表（可重复执行）。

用法：
    .\\.venv\\Scripts\\python.exe scripts\\seed_models.py
    .\\.venv\\Scripts\\python.exe scripts\\seed_models.py --tenant 1 --no-check

读取的环境变量（写在 `python/backend/.env`，该文件已被 `.gitignore` 忽略）：
    LLM_CHAT_BASE_URL / LLM_CHAT_MODEL / LLM_CHAT_API_KEY          # 对话模型（默认）
    LLM_CHAT2_BASE_URL / LLM_CHAT2_MODEL / LLM_CHAT2_API_KEY        # 第二对话模型（非默认）
    LLM_EMBEDDING_BASE_URL / LLM_EMBEDDING_MODEL / LLM_EMBEDDING_API_KEY / LLM_EMBEDDING_DIMENSION
    LLM_SEED_TENANT_ID（默认 1）

行为：
    1. 跑一次迁移（幂等），保证 `models` 表存在；
    2. 按「租户 + 模型名 + 类型」upsert，chat 默认模型 + chat 第二模型 + embedding 默认模型；
    3. 默认对上游各发起一次真实调用（chat 回 pong、embedding 返回维度），`--no-check` 可跳过。

退出码：0 成功；1 连通性测试失败（模型仍会写库，便于排查）；2 未配置任何模型。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 直接用 `python scripts/seed_models.py` 运行时，脚本目录在 sys.path[0]，
# 需要把 backend 根目录加进来才能 import app.*
PYTHON_DIR = Path(__file__).resolve().parents[1]
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal, dispose_engine
from app.core.migrations import run_migrations
from app.domain.entities import (
    MODEL_STATUS_ACTIVE,
    MODEL_TYPE_CHAT,
    MODEL_TYPE_EMBEDDING,
    SOURCE_REMOTE,
    Model,
)
from app.llm import ChatMessage, OpenAICompatibleClient
from app.repositories import model_repository

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def mask(api_key: str) -> str:
    if not api_key:
        return "<empty>"
    if len(api_key) <= 8:
        return "******"
    return f"{api_key[:4]}******{api_key[-4:]}"


async def upsert_model(
    session,
    tenant_id: int,
    *,
    name: str,
    model_type: str,
    base_url: str,
    api_key: str,
    dimension: int | None = None,
    is_default: bool = True,
) -> tuple[Model, str]:
    stmt = select(Model).where(
        Model.tenant_id == tenant_id,
        Model.name == name,
        Model.type == model_type,
        Model.deleted_at.is_(None),
    )
    model = await session.scalar(stmt)

    parameters: dict[str, object] = {"base_url": base_url}
    if api_key:
        parameters["api_key"] = api_key
    if dimension is not None:
        parameters["embedding_parameters"] = {"dimension": dimension}

    if is_default:
        # 先把同类型其他模型的默认标记清掉，再写入本模型的默认标记
        await model_repository.clear_default(session, tenant_id, model_type)

    if model is None:
        model = Model(
            tenant_id=tenant_id,
            name=name,
            display_name=name,
            type=model_type,
            source=SOURCE_REMOTE,
            description="由 scripts/seed_models.py 写入",
            parameters=parameters,
            is_default=is_default,
            status=MODEL_STATUS_ACTIVE,
        )
        await model_repository.save_model(session, model)
        action = "created"
    else:
        model.parameters = parameters
        model.is_default = is_default
        model.status = MODEL_STATUS_ACTIVE
        action = "updated"

    await session.commit()
    await session.refresh(model)
    return model, action


async def check_chat(model: Model) -> str:
    client = OpenAICompatibleClient(model, timeout=60.0)
    reply = await client.complete(
        [ChatMessage(role="user", content="reply with the single word: pong")]
    )
    return reply.strip()[:120]


async def check_embedding(model: Model) -> int:
    client = OpenAICompatibleClient(model, timeout=60.0)
    vectors = await client.embed(["WeKnora embedding check"])
    return len(vectors[0]) if vectors else 0


def collect_specs(settings) -> list[dict]:
    """按 .env 组装待写入的模型清单；未配置项直接跳过。"""
    specs: list[dict] = []
    if settings.llm_chat_base_url and settings.llm_chat_model:
        specs.append(
            {
                "label": "chat",
                "name": settings.llm_chat_model,
                "model_type": MODEL_TYPE_CHAT,
                "base_url": settings.llm_chat_base_url,
                "api_key": settings.llm_chat_api_key,
                "is_default": True,
            }
        )
    if settings.llm_chat2_base_url and settings.llm_chat2_model:
        specs.append(
            {
                "label": "chat2",
                "name": settings.llm_chat2_model,
                "model_type": MODEL_TYPE_CHAT,
                "base_url": settings.llm_chat2_base_url,
                "api_key": settings.llm_chat2_api_key,
                "is_default": False,
            }
        )
    if settings.llm_embedding_base_url and settings.llm_embedding_model:
        specs.append(
            {
                "label": "embedding",
                "name": settings.llm_embedding_model,
                "model_type": MODEL_TYPE_EMBEDDING,
                "base_url": settings.llm_embedding_base_url,
                "api_key": settings.llm_embedding_api_key,
                "dimension": settings.llm_embedding_dimension,
                "is_default": True,
            }
        )
    return specs


async def main() -> int:
    parser = argparse.ArgumentParser(description="写入真实大模型配置并做连通性测试")
    parser.add_argument("--tenant", type=int, default=None, help="租户 ID，默认取 LLM_SEED_TENANT_ID")
    parser.add_argument("--no-check", action="store_true", help="只写库，不调用上游")
    args = parser.parse_args()

    settings = get_settings()
    tenant_id = args.tenant if args.tenant is not None else settings.llm_seed_tenant_id

    specs = collect_specs(settings)
    if not specs:
        print("未配置 LLM_CHAT_* / LLM_CHAT2_* / LLM_EMBEDDING_*，请先在 python/backend/.env 填写后重试")
        return 2

    await run_migrations(settings)
    failed = False

    async with SessionLocal() as session:
        for spec in specs:
            label = str(spec.pop("label"))
            model, action = await upsert_model(session, tenant_id, **spec)
            if model.type == MODEL_TYPE_EMBEDDING:
                detail = (
                    f"base_url={model.base_url} api_key={mask(model.api_key)} "
                    f"dimension={model.dimension} is_default={model.is_default}"
                )
            else:
                detail = (
                    f"base_url={model.base_url} api_key={mask(model.api_key)} "
                    f"is_default={model.is_default}"
                )
            print(f"[{action}] {label} id={model.id} name={model.name} {detail}")

            if args.no_check:
                continue
            try:
                if model.type == MODEL_TYPE_EMBEDDING:
                    actual = await check_embedding(model)
                    expected = settings.llm_embedding_dimension
                    print(f"  embedding check: dimension={actual}")
                    if actual != expected:
                        failed = True
                        print(
                            f"  embedding check FAILED: 实际维度 {actual} != 配置维度 {expected}，"
                            "请把 LLM_EMBEDDING_DIMENSION 改成实际值后重跑"
                        )
                else:
                    print(f"  {label} check: {await check_chat(model)}")
            except Exception as exc:  # noqa: BLE001 - 需要把上游错误原样展示给使用者
                failed = True
                print(f"  {label} check FAILED: {type(exc).__name__}: {exc}")

    await dispose_engine()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
