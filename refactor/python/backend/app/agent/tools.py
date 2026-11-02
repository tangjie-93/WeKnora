"""内置 Agent 工具：search_knowledge / read_document / list_documents。

对齐 Go `internal/agent/tools` 的检索工具语义，工具执行复用已有 retrieval / knowledge 仓储。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import knowledge_repository
from app.services import retrieval_service


@dataclass
class ToolContext:
    session: AsyncSession
    tenant_id: int
    kb_ids: list[str] = field(default_factory=list)
    embedding_model_id: str = ""
    rerank_model_id: str = ""


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "语义、关键词或混合检索知识库分块，返回与 query 最相关的内容片段",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索查询"},
                    "top_k": {"type": "integer", "description": "返回结果数量，默认 5"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document",
            "description": "读取指定文档的元数据与分块内容，返回文档标题与正文片段",
            "parameters": {
                "type": "object",
                "properties": {
                    "knowledge_id": {"type": "string", "description": "文档 ID"},
                    "limit": {"type": "integer", "description": "返回分块数量，默认 10"},
                },
                "required": ["knowledge_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": "分页列出知识库中的文档（标题与 ID）",
            "parameters": {
                "type": "object",
                "properties": {
                    "kb_id": {"type": "string", "description": "知识库 ID"},
                    "limit": {"type": "integer", "description": "返回文档数量，默认 20"},
                },
                "required": ["kb_id"],
            },
        },
    },
]


def _chunk_snippet(content: str, limit: int = 800) -> str:
    content = (content or "").strip()
    return content[:limit] + ("…" if len(content) > limit else "")


async def _search_knowledge(ctx: ToolContext, arguments: dict[str, Any]) -> str:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return "错误：search_knowledge 需要 query 参数"
    top_k = max(1, min(int(arguments.get("top_k") or 5), 20))
    kb_ids = ctx.kb_ids or []
    if not kb_ids:
        return "错误：没有可检索的知识库"
    lines: list[str] = []
    for kb_id in kb_ids:
        hits = await retrieval_service.search(
            ctx.session,
            ctx.tenant_id,
            kb_id,
            query,
            top_k=top_k,
            embedding_model_id=ctx.embedding_model_id,
            rerank_model_id=ctx.rerank_model_id,
        )
        if not hits:
            continue
        lines.append(f"知识库 {kb_id} 检索到 {len(hits)} 条结果：")
        for index, hit in enumerate(hits, start=1):
            lines.append(f"[{index}] {_chunk_snippet(hit.chunk.content)}")
    return "\n".join(lines) if lines else "未检索到相关内容"


async def _read_document(ctx: ToolContext, arguments: dict[str, Any]) -> str:
    knowledge_id = str(arguments.get("knowledge_id") or "").strip()
    if not knowledge_id:
        return "错误：read_document 需要 knowledge_id 参数"
    knowledge = await knowledge_repository.get_knowledge(ctx.session, ctx.tenant_id, knowledge_id)
    if knowledge is None:
        return f"错误：文档 {knowledge_id} 不存在"
    chunks = await knowledge_repository.list_chunks(ctx.session, knowledge_id)
    limit = max(1, min(int(arguments.get("limit") or 10), 50))
    lines = [f"文档：{knowledge.title or knowledge.file_name}（{len(chunks)} 个分块）"]
    for chunk in chunks[:limit]:
        lines.append(f"[分块 {chunk.chunk_index}] {_chunk_snippet(chunk.content)}")
    return "\n".join(lines)


async def _list_documents(ctx: ToolContext, arguments: dict[str, Any]) -> str:
    kb_id = str(arguments.get("kb_id") or "").strip()
    if not kb_id:
        return "错误：list_documents 需要 kb_id 参数"
    items = await knowledge_repository.list_knowledge(ctx.session, kb_id)
    limit = max(1, min(int(arguments.get("limit") or 20), 100))
    if not items:
        return f"知识库 {kb_id} 暂无文档"
    lines = [f"知识库 {kb_id} 共 {len(items)} 个文档："]
    for item in items[:limit]:
        lines.append(f"- {item.title or item.file_name}（id={item.id}）")
    return "\n".join(lines)


_TOOL_EXECUTORS = {
    "search_knowledge": _search_knowledge,
    "read_document": _read_document,
    "list_documents": _list_documents,
}


async def execute_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> str:
    executor = _TOOL_EXECUTORS.get(name)
    if executor is None:
        return f"错误：未知工具 {name}"
    try:
        return await executor(ctx, arguments)
    except Exception as exc:  # noqa: BLE001 - 工具失败反馈给模型而非中断
        return f"工具 {name} 执行失败：{type(exc).__name__}: {exc}"


def tool_call_payload(name: str, arguments: dict[str, Any]) -> str:
    return json.dumps({"name": name, "arguments": arguments}, ensure_ascii=False)
