"""`/api/v1` 路由汇总。新增模块时在此挂载。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import (
    agent,
    auth,
    chat,
    faq,
    knowledge,
    mcp_endpoint,
    mcp_service,
    models,
    sessions,
    tags,
    wiki,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(models.router)
api_router.include_router(knowledge.router)
api_router.include_router(tags.router)
api_router.include_router(faq.router)
api_router.include_router(wiki.router)
api_router.include_router(agent.router)
api_router.include_router(sessions.router)
api_router.include_router(chat.router)
api_router.include_router(mcp_endpoint.router)
api_router.include_router(mcp_service.router)
