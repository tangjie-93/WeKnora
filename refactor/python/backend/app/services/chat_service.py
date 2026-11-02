"""会话管理与流式问答（SSE）。

SSE 事件格式对齐前端 `useChatStreamHandler`：
`data: {"id": "...", "response_type": "references|answer|complete", "data": {...}}`
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, not_found
from app.domain.entities import (
    MODEL_TYPE_CHAT,
    ROLE_ASSISTANT,
    ROLE_USER,
    Message,
    Session,
)
from app.llm import OpenAICompatibleClient
from app.repositories import knowledge_repository, model_repository, session_repository
from app.services import knowledge_service, retrieval_service
from app.services.retrieval_service import SearchHit, build_messages

logger = logging.getLogger(__name__)


def _iso(value) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat().replace("+00:00", "Z")


def session_payload(item: Session) -> dict[str, Any]:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "user_id": item.user_id or "",
        "title": item.title or "",
        "description": item.description or "",
        "knowledge_base_id": item.knowledge_base_id or "",
        "max_rounds": item.max_rounds,
        "enable_rewrite": bool(item.enable_rewrite),
        "embedding_top_k": item.embedding_top_k,
        "rerank_top_k": item.rerank_top_k,
        "keyword_threshold": item.keyword_threshold,
        "vector_threshold": item.vector_threshold,
        "rerank_model_id": item.rerank_model_id or "",
        "summary_model_id": item.summary_model_id or "",
        "is_pinned": bool(item.is_pinned),
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def message_payload(item: Message) -> dict[str, Any]:
    return {
        "id": item.id,
        "session_id": item.session_id,
        "request_id": item.request_id or "",
        "role": item.role,
        "content": item.content,
        "knowledge_references": item.knowledge_references or [],
        "is_completed": bool(item.is_completed),
        "is_fallback": bool(item.is_fallback),
        "channel": item.channel,
        "model_id": item.model_id or "",
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


async def create_session(
    session: AsyncSession, tenant_id: int, user_id: str, payload: dict[str, Any]
) -> Session:
    kb_id = str(payload.get("knowledge_base_id") or "")
    if kb_id:
        await knowledge_service.get_kb(session, tenant_id, kb_id)

    item = Session(
        tenant_id=tenant_id,
        user_id=user_id,
        title=str(payload.get("title") or "新会话"),
        description=str(payload.get("description") or ""),
        knowledge_base_id=kb_id,
        max_rounds=int(payload.get("max_rounds") or 5),
        enable_rewrite=bool(payload.get("enable_rewrite")),
        embedding_top_k=int(payload.get("embedding_top_k") or 8),
        rerank_top_k=int(payload.get("rerank_top_k") or 4),
        rerank_model_id=str(payload.get("rerank_model_id") or ""),
    )
    await session_repository.save_session(session, item)
    await session.commit()
    await session.refresh(item)
    return item


async def list_sessions(session: AsyncSession, tenant_id: int, user_id: str) -> list[Session]:
    return await session_repository.list_sessions(session, tenant_id, user_id)


async def get_session(session: AsyncSession, tenant_id: int, user_id: str, session_id: str) -> Session:
    item = await session_repository.get_session(session, tenant_id, session_id)
    if item is None or item.user_id != user_id:
        raise not_found("session not found")
    return item


async def update_session(
    session: AsyncSession, tenant_id: int, user_id: str, session_id: str, payload: dict[str, Any]
) -> Session:
    item = await get_session(session, tenant_id, user_id, session_id)
    if payload.get("title"):
        item.title = str(payload["title"])
    if payload.get("knowledge_base_id"):
        await knowledge_service.get_kb(session, tenant_id, str(payload["knowledge_base_id"]))
        item.knowledge_base_id = str(payload["knowledge_base_id"])
    if "embedding_top_k" in payload:
        item.embedding_top_k = int(payload["embedding_top_k"])
    await session.commit()
    await session.refresh(item)
    return item


async def delete_session(session: AsyncSession, tenant_id: int, user_id: str, session_id: str) -> None:
    item = await get_session(session, tenant_id, user_id, session_id)
    item.deleted_at = datetime.now(UTC)
    await session.commit()


async def list_messages(session: AsyncSession, tenant_id: int, user_id: str, session_id: str):
    await get_session(session, tenant_id, user_id, session_id)
    return await session_repository.list_messages(session, session_id)


async def clear_messages(
    session: AsyncSession, tenant_id: int, user_id: str, session_id: str
) -> int:
    await get_session(session, tenant_id, user_id, session_id)
    count = await session_repository.delete_messages(session, session_id)
    await session.commit()
    return count


async def generate_title(
    session: AsyncSession, tenant_id: int, user_id: str, session_id: str
) -> Session:
    """用首条用户消息生成标题，避免额外调用模型（Phase 5 简化）。"""
    item = await get_session(session, tenant_id, user_id, session_id)
    rows = await session_repository.list_messages(session, session_id)
    first_user = next((row for row in rows if row.role == ROLE_USER), None)
    if first_user and first_user.content.strip():
        item.title = first_user.content.strip()[:30]
        await session.commit()
        await session.refresh(item)
    return item


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _reference_payload(hits: list[SearchHit]) -> list[dict[str, Any]]:
    return [
        {
            "id": hit.chunk.id,
            "knowledge_id": hit.chunk.knowledge_id,
            "knowledge_title": "",
            "chunk_index": hit.chunk.chunk_index,
            "content": hit.chunk.content,
            "score": round(hit.score, 6),
        }
        for hit in hits
    ]


async def stream_answer(
    session: AsyncSession,
    tenant_id: int,
    user_id: str,
    session_id: str,
    query: str,
) -> AsyncIterator[str]:
    """返回 SSE 事件流，并在结束时落库 user / assistant 两条消息。"""
    started = time.time()
    chat_session = await get_session(session, tenant_id, user_id, session_id)
    if not query.strip():
        raise bad_request("query is required")

    from app.domain.entities import MODEL_TYPE_EMBEDDING

    kb = None
    hits: list[SearchHit] = []
    if chat_session.knowledge_base_id:
        kb = await knowledge_service.get_kb(session, tenant_id, chat_session.knowledge_base_id)
        embedding_model_id = kb.embedding_model_id or ""
        if not embedding_model_id:
            default_embedding = await model_repository.first_of_type(
                session, tenant_id, MODEL_TYPE_EMBEDDING
            )
            embedding_model_id = default_embedding.id if default_embedding else ""
        hits = await retrieval_service.search(
            session,
            tenant_id,
            kb.id,
            query,
            top_k=chat_session.embedding_top_k,
            embedding_model_id=embedding_model_id,
            rerank_model_id=chat_session.rerank_model_id,
        )

    chat_model = await model_repository.first_of_type(session, tenant_id, MODEL_TYPE_CHAT)
    if chat_model is None:
        raise bad_request("no chat model configured")

    history_rows = await session_repository.list_messages(session, session_id)
    history = [(row.role, row.content) for row in history_rows if row.role in ("user", "assistant")]

    request_id = uuid.uuid4().hex
    assistant_id = str(uuid.uuid4())

    references = _reference_payload(hits)
    if references:
        for reference, hit in zip(references, hits):
            knowledge = await knowledge_repository.get_knowledge(
                session, tenant_id, hit.chunk.knowledge_id
            )
            if knowledge is not None:
                reference["knowledge_title"] = knowledge.title or knowledge.file_name

    user_message = Message(
        session_id=session_id,
        role=ROLE_USER,
        content=query,
        request_id=request_id,
        is_completed=True,
    )
    await session_repository.save_message(session, user_message)

    event_id = request_id
    yield _sse(
        {
            "id": event_id,
            "response_type": "agent_query",
            "assistant_message_id": assistant_id,
            "data": {"query": query},
        }
    )
    if references:
        yield _sse({"id": event_id, "response_type": "references", "data": {"references": references}})

    answer = ""
    client = OpenAICompatibleClient(chat_model)
    messages = build_messages(query, hits, history)
    try:
        async for delta in client.stream(messages):
            answer += delta
            yield _sse(
                {"id": event_id, "response_type": "answer", "data": {"content": delta}}
            )
    except Exception as exc:
        logger.exception("chat stream failed")
        yield _sse(
            {
                "id": event_id,
                "response_type": "error",
                "data": {"message": f"{type(exc).__name__}: {exc}"},
            }
        )
        answer = answer or ""

    yield _sse({"id": event_id, "response_type": "answer", "data": {"done": True}})

    assistant_message = Message(
        id=assistant_id,
        session_id=session_id,
        role=ROLE_ASSISTANT,
        content=answer,
        request_id=request_id,
        knowledge_references=references,
        is_completed=True,
        model_id=chat_model.id,
    )
    await session_repository.save_message(session, assistant_message)
    await session.commit()

    yield _sse(
        {
            "id": event_id,
            "response_type": "complete",
            "assistant_message_id": assistant_id,
            "data": {
                "total_duration_ms": int((time.time() - started) * 1000),
                "session_id": session_id,
                "message_id": assistant_id,
                "content": answer,
                "knowledge_references": references,
            },
        }
    )
