"""ReAct Agent 引擎：循环「思考 → 工具 → 观察」，对齐 Go `internal/agent/engine.go`。

7B 精简版：单轮内非流式调用 LLM 解析 tool_calls，执行内置工具后把观察反馈回模型，
直到模型给出最终答案或达到迭代上限。SSE 事件复用 chat_service 的格式。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import TOOL_DEFINITIONS, ToolContext, execute_tool
from app.core.errors import bad_request
from app.domain.entities import ROLE_ASSISTANT, ROLE_USER, Message, Model
from app.llm import ChatMessage, OpenAICompatibleClient
from app.repositories import session_repository

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "你是 WeKnora 智能助手。可以调用工具检索知识库、阅读文档来回答问题。"
    "优先使用工具获取准确信息，再基于工具结果给出答案，并在回答中引用来源。"
)


@dataclass
class AgentRunContext:
    session: AsyncSession
    tenant_id: int
    user_id: str
    session_id: str
    agent_id: str
    agent_name: str
    agent_config: dict[str, Any]
    kb_ids: list[str] = field(default_factory=list)
    chat_model: Model | None = None
    embedding_model_id: str = ""
    rerank_model_id: str = ""


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _allowed_tool_definitions(config: dict[str, Any]) -> list[dict[str, Any]]:
    allowed = set(config.get("allowed_tools") or [])
    # 未显式配置工具时，使用检索三件套
    if not allowed:
        allowed = {"search_knowledge", "read_document", "list_documents"}
    return [
        tool
        for tool in TOOL_DEFINITIONS
        if tool["function"]["name"] in allowed
    ]


def _build_messages(
    ctx: AgentRunContext, query: str, history: list[tuple[str, str]]
) -> list[ChatMessage]:
    system_prompt = str(ctx.agent_config.get("system_prompt") or "") or DEFAULT_SYSTEM_PROMPT
    messages: list[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]
    for role, content in history[-6:]:
        messages.append(ChatMessage(role=role, content=content))
    messages.append(ChatMessage(role="user", content=query))
    return messages


async def stream_agent_answer(
    ctx: AgentRunContext,
    query: str,
) -> AsyncIterator[str]:
    """执行一轮 agent 问答，yield SSE 事件，并在结束时落库 user / assistant 消息。"""
    started = time.time()
    if not query.strip():
        raise bad_request("query is required")
    if ctx.chat_model is None:
        raise bad_request("no chat model configured")

    history_rows = await session_repository.list_messages(ctx.session, ctx.session_id)
    history = [(row.role, row.content) for row in history_rows if row.role in ("user", "assistant")]

    request_id = uuid.uuid4().hex
    assistant_id = str(uuid.uuid4())
    event_id = request_id

    user_message = Message(
        session_id=ctx.session_id,
        role=ROLE_USER,
        content=query,
        request_id=request_id,
        is_completed=True,
    )
    await session_repository.save_message(ctx.session, user_message)

    yield _sse(
        {
            "id": event_id,
            "response_type": "agent_query",
            "assistant_message_id": assistant_id,
            "data": {"query": query, "agent_id": ctx.agent_id},
        }
    )

    messages = _build_messages(ctx, query, history)
    tools = _allowed_tool_definitions(ctx.agent_config)
    max_iterations = max(1, min(int(ctx.agent_config.get("max_iterations") or 10), 20))
    client = OpenAICompatibleClient(ctx.chat_model)

    tool_calls_history: list[dict[str, Any]] = []
    final_answer = ""
    references: list[dict[str, Any]] = []

    try:
        for _ in range(max_iterations):
            result = await client.complete_with_tools(messages, tools)
            calls = result.get("tool_calls") or []
            finish_reason = result.get("finish_reason") or ""

            if calls:
                # 把 assistant 的 tool_calls 消息写入历史，供后续轮次回放
                messages.append(
                    ChatMessage(
                        role="assistant",
                        content=json.dumps(
                            {
                                "tool_calls": [
                                    {
                                        "id": c["id"],
                                        "name": c["name"],
                                        "arguments": c["arguments"],
                                    }
                                    for c in calls
                                ]
                            },
                            ensure_ascii=False,
                        ),
                    )
                )
                for call in calls:
                    name = call["name"]
                    arguments = call.get("arguments") or {}
                    yield _sse(
                        {
                            "id": event_id,
                            "response_type": "tool_call",
                            "data": {"name": name, "arguments": arguments},
                        }
                    )
                    tool_ctx = ToolContext(
                        session=ctx.session,
                        tenant_id=ctx.tenant_id,
                        kb_ids=ctx.kb_ids,
                        embedding_model_id=ctx.embedding_model_id,
                        rerank_model_id=ctx.rerank_model_id,
                    )
                    observation = await execute_tool(tool_ctx, name, arguments)
                    yield _sse(
                        {
                            "id": event_id,
                            "response_type": "tool_result",
                            "data": {"name": name, "content": observation[:2000]},
                        }
                    )
                    tool_calls_history.append(
                        {"name": name, "arguments": arguments, "output": observation[:2000]}
                    )
                    messages.append(ChatMessage(role="tool", content=observation[:4000]))
                continue

            final_answer = str(result.get("content") or "").strip()
            if final_answer or finish_reason == "stop":
                break
            # 空内容且无工具调用：给模型一个继续的提示
            messages.append(
                ChatMessage(role="user", content="请继续，直接给出最终答案。")
            )

        if not final_answer:
            final_answer = "抱歉，我未能完成这次回答。"

        yield _sse(
            {
                "id": event_id,
                "response_type": "answer",
                "data": {"content": final_answer},
            }
        )
    except Exception as exc:
        logger.exception("agent run failed")
        yield _sse(
            {
                "id": event_id,
                "response_type": "error",
                "data": {"message": f"{type(exc).__name__}: {exc}"},
            }
        )
        final_answer = final_answer or ""

    assistant_message = Message(
        id=assistant_id,
        session_id=ctx.session_id,
        role=ROLE_ASSISTANT,
        content=final_answer,
        request_id=request_id,
        knowledge_references=references,
        is_completed=True,
        model_id=ctx.chat_model.id,
    )
    await session_repository.save_message(ctx.session, assistant_message)
    await ctx.session.commit()

    yield _sse(
        {
            "id": event_id,
            "response_type": "complete",
            "assistant_message_id": assistant_id,
            "data": {
                "total_duration_ms": int((time.time() - started) * 1000),
                "session_id": ctx.session_id,
                "message_id": assistant_id,
                "content": final_answer,
                "tool_calls": tool_calls_history,
            },
        }
    )
