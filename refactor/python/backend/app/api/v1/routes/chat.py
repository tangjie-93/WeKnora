"""对话路由：SSE 流式问答与消息历史。

- `POST /api/v1/knowledge-chat/{session_id}`：SSE 事件流
- `GET  /api/v1/messages/{session_id}/load`：加载历史消息
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AuthContext, get_session, require_role
from app.core.database import SessionLocal
from app.core.errors import bad_request
from app.domain.entities import ROLE_VIEWER
from app.services import chat_service

router = APIRouter(tags=["对话"])
viewer_only = require_role(ROLE_VIEWER)


@router.get("/messages/{session_id}/load")
async def load_messages(
    session_id: str,
    context: AuthContext = Depends(viewer_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    rows = await chat_service.list_messages(
        session, context.tenant_id, context.user.id, session_id
    )
    return {"success": True, "data": [chat_service.message_payload(row) for row in rows]}


@router.post("/knowledge-chat/{session_id}")
async def knowledge_chat(
    session_id: str,
    payload: dict,
    context: AuthContext = Depends(viewer_only),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    query = str(payload.get("query") or "")
    if not query.strip():
        raise bad_request("query is required")

    # 先用依赖会话做归属校验，保证 404/403 以普通 JSON 返回，而不是流中断。
    await chat_service.get_session(
        session, context.tenant_id, context.user.id, session_id
    )

    tenant_id = context.tenant_id
    user_id = context.user.id

    async def event_stream():
        # 流式响应期间使用独立会话：FastAPI 会在响应结束后关闭依赖会话。
        async with SessionLocal() as stream_session:
            async for chunk in chat_service.stream_answer(
                stream_session, tenant_id, user_id, session_id, query
            ):
                yield chunk

    # 不显式设置 Connection 头：由 uvicorn 管理分块编码与连接收尾，
    # 手动写 keep-alive 会让开发代理（Vite http-proxy）在流结束后销毁连接，
    # 浏览器侧记录 net::ERR_ABORTED。
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
