"""Agent 路由，对齐 Go `internal/handler/custom_agent.go` 的 `/agents` 与 `/agent-chat`。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import AgentRunContext, stream_agent_answer
from app.api.v1.deps import AuthContext, get_auth_context, get_session, require_role
from app.core.database import SessionLocal
from app.core.errors import bad_request
from app.domain.entities import (
    MODEL_TYPE_CHAT,
    MODEL_TYPE_EMBEDDING,
    ROLE_CONTRIBUTOR,
    ROLE_VIEWER,
)
from app.repositories import model_repository
from app.services import agent_service, chat_service

router = APIRouter(tags=["Agent"])
contributor_only = require_role(ROLE_CONTRIBUTOR)
viewer_only = require_role(ROLE_VIEWER)


@router.get("/agents/placeholders")
async def get_placeholders(
    context: AuthContext = Depends(get_auth_context),
) -> dict:
    return {"success": True, "data": agent_service.placeholders()}


@router.get("/agents/type-presets")
async def get_agent_type_presets(
    context: AuthContext = Depends(get_auth_context),
) -> dict:
    return {"success": True, "data": agent_service.type_presets()}


@router.get("/agents/tools")
async def get_agent_tools(
    context: AuthContext = Depends(get_auth_context),
) -> dict:
    return {"success": True, "data": agent_service.tool_catalog()}


@router.get("/agents")
async def list_agents(
    creator: str = "",
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await agent_service.list_agents(
        session, context.tenant_id, creator=creator, caller_user_id=context.user.id
    )
    return {"success": True, "data": data}


@router.post("/agents", status_code=201)
async def create_agent(
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    agent = await agent_service.create_agent(
        session, context.tenant_id, context.user.id, payload
    )
    return {"success": True, "data": agent}


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    agent = await agent_service.get_agent(session, context.tenant_id, agent_id)
    return {"success": True, "data": agent}


@router.put("/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    agent = await agent_service.update_agent(
        session, context.tenant_id, agent_id, payload
    )
    return {"success": True, "data": agent}


@router.patch("/agents/{agent_id}")
async def patch_agent(
    agent_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    agent = await agent_service.patch_agent(
        session, context.tenant_id, agent_id, payload
    )
    return {"success": True, "data": agent}


@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await agent_service.delete_agent(session, context.tenant_id, agent_id)
    return {"success": True}


@router.post("/agents/{agent_id}/copy", status_code=201)
async def copy_agent(
    agent_id: str,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    agent = await agent_service.copy_agent(
        session, context.tenant_id, agent_id, context.user.id
    )
    return {"success": True, "data": agent}


@router.post("/agent-chat/{session_id}")
async def agent_chat(
    session_id: str,
    payload: dict,
    context: AuthContext = Depends(viewer_only),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    query = str(payload.get("query") or "")
    if not query.strip():
        raise bad_request("query is required")
    agent_id = str(payload.get("agent_id") or "")

    # 会话归属校验，保证 404/403 以普通 JSON 返回
    chat_session = await chat_service.get_session(
        session, context.tenant_id, context.user.id, session_id
    )

    # 解析 agent 配置；agent_id 为空时回退到内置 quick-answer
    if agent_id:
        agent = await agent_service.get_agent(session, context.tenant_id, agent_id)
    else:
        agent = await agent_service.get_agent(
            session, context.tenant_id, "builtin-quick-answer"
        )
    config = agent.get("config") or {}

    # 确定检索范围：优先会话知识库，其次 agent 配置
    kb_ids: list[str] = []
    if chat_session.knowledge_base_id:
        kb_ids = [chat_session.knowledge_base_id]
    elif config.get("knowledge_bases"):
        kb_ids = list(config.get("knowledge_bases") or [])

    # 解析模型
    chat_model = None
    if config.get("model_id"):
        candidate = await model_repository.get_model(
            session, context.tenant_id, str(config["model_id"])
        )
        if candidate is not None and candidate.type == MODEL_TYPE_CHAT:
            chat_model = candidate
    if chat_model is None:
        chat_model = await model_repository.first_of_type(
            session, context.tenant_id, MODEL_TYPE_CHAT
        )
    if chat_model is None:
        raise bad_request("no chat model configured")

    embedding_model_id = ""
    embedding = await model_repository.first_of_type(
        session, context.tenant_id, MODEL_TYPE_EMBEDDING
    )
    if embedding is not None:
        embedding_model_id = embedding.id

    tenant_id = context.tenant_id
    user_id = context.user.id

    async def event_stream():
        async with SessionLocal() as stream_session:
            run_ctx = AgentRunContext(
                session=stream_session,
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                agent_id=agent.get("id", ""),
                agent_name=agent.get("name", ""),
                agent_config=config,
                kb_ids=kb_ids,
                chat_model=chat_model,
                embedding_model_id=embedding_model_id,
                rerank_model_id=chat_session.rerank_model_id or "",
            )
            async for chunk in stream_agent_answer(run_ctx, query):
                yield chunk

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
