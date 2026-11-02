"""MCP Streamable HTTP 服务器：公开 `/mcp/{endpoint_id}` 供外部 MCP 客户端连接。

对齐 Go `internal/mcpserver`（stateless Streamable HTTP）：
- JSON-RPC 2.0：`initialize` / `notifications/initialized` / `ping` / `tools/list` / `tools/call`
- 认证走 `mcp_endpoint_service.authenticate`（Bearer `mcp_...`）
- 工具白名单与知识库范围来自 endpoint 行，写工具（add/update/delete_document）本阶段未实现
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_session
from app.core.errors import AppError
from app.domain.entities import (
    KB_TYPE_WIKI,
    TOOL_ASK,
    TOOL_GREP_CHUNKS,
    TOOL_LIST_DOCUMENTS,
    TOOL_LIST_KNOWLEDGE_BASES,
    TOOL_READ_DOCUMENT,
    TOOL_SEARCH_KNOWLEDGE,
    TOOL_WIKI_INDEX,
    TOOL_WIKI_READ_PAGE,
    TOOL_WIKI_SEARCH,
    MCPEndpoint,
)
from app.repositories import knowledge_repository, wiki_repository
from app.services import mcp_endpoint_service, retrieval_service

router = APIRouter(prefix="/mcp", tags=["MCP"])

SERVER_NAME = "weknora"
SERVER_VERSION = "1.0.0"

SERVER_INSTRUCTIONS = (
    "WeKnora knowledge workspace. Start with list_knowledge_bases to see what is in scope, "
    "then use search_knowledge for semantic questions, grep_chunks for exact keywords, "
    "read_document to read a whole document, and ask to get a synthesized answer with citations. "
    "Wiki tools browse the generated wiki when a knowledge base has one."
)

_READ_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


def _tool_schema(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": properties, "required": required},
        "annotations": _READ_ANNOTATIONS,
    }


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    TOOL_LIST_KNOWLEDGE_BASES: _tool_schema(
        TOOL_LIST_KNOWLEDGE_BASES,
        "List the knowledge bases this endpoint can access, with their id, name, description "
        "and supported retrieval capabilities. Call this first to learn what is in scope.",
        {},
        [],
    ),
    TOOL_SEARCH_KNOWLEDGE: _tool_schema(
        TOOL_SEARCH_KNOWLEDGE,
        "Search the knowledge bases in scope and return the most relevant passages with their "
        "document ids and titles. mode hybrid (default) combines semantic and keyword retrieval.",
        {
            "query": {"type": "string", "description": "A natural-language question or the exact terms to match"},
            "mode": {
                "type": "string",
                "enum": ["hybrid", "semantic", "keyword"],
                "description": "hybrid (default), semantic, or keyword",
            },
            "limit": {"type": "number", "description": "Maximum passages to return, default 10, max 30"},
            "knowledge_base_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional knowledge base ids or names to restrict the search",
            },
        },
        ["query"],
    ),
    TOOL_GREP_CHUNKS: _tool_schema(
        TOOL_GREP_CHUNKS,
        "Case-insensitive regular-expression search over the text chunks of the knowledge bases "
        "in scope. Best for exact terms, identifiers, error codes or product names.",
        {
            "query": {"type": "string", "description": "Regular expression to match against chunk text"},
            "limit": {"type": "number", "description": "Maximum passages to return, default 10, max 30"},
            "knowledge_base_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional knowledge base ids or names to restrict the search",
            },
        },
        ["query"],
    ),
    TOOL_LIST_DOCUMENTS: _tool_schema(
        TOOL_LIST_DOCUMENTS,
        "List the documents inside one knowledge base with pagination and an optional title keyword filter.",
        {
            "knowledge_base_id": {"type": "string", "description": "Knowledge base id or exact name"},
            "keyword": {"type": "string", "description": "Optional substring to filter document titles"},
            "page": {"type": "number", "description": "1-based page number, default 1"},
            "page_size": {"type": "number", "description": "Documents per page, default 20, max 100"},
        },
        ["knowledge_base_id"],
    ),
    TOOL_READ_DOCUMENT: _tool_schema(
        TOOL_READ_DOCUMENT,
        "Read a document's metadata and its text chunks in order. Page through long documents "
        "with offset and limit, or pass query to return only the chunks containing a phrase.",
        {
            "knowledge_id": {"type": "string", "description": "Document id from search results or list_documents"},
            "offset": {"type": "number", "description": "Chunk offset to start from, default 0"},
            "limit": {"type": "number", "description": "Number of chunks to return, default 20, max 100"},
            "query": {"type": "string", "description": "Optional case-insensitive phrase to find inside the document"},
        },
        ["knowledge_id"],
    ),
    TOOL_ASK: {
        "name": TOOL_ASK,
        "description": "Answer a question using the knowledge bases in scope and return passages with citations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The question to answer"},
                "knowledge_base_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional knowledge base ids or names to restrict the answer",
                },
            },
            "required": ["query"],
        },
    },
    TOOL_WIKI_SEARCH: _tool_schema(
        TOOL_WIKI_SEARCH,
        "Search the wiki pages of a knowledge base by title or content.",
        {
            "query": {"type": "string", "description": "Keywords to search wiki pages"},
            "knowledge_base_id": {"type": "string", "description": "Knowledge base id or exact name"},
            "limit": {"type": "number", "description": "Maximum pages to return, default 10"},
        },
        ["query", "knowledge_base_id"],
    ),
    TOOL_WIKI_READ_PAGE: _tool_schema(
        TOOL_WIKI_READ_PAGE,
        "Read a single wiki page by its slug.",
        {
            "slug": {"type": "string", "description": "Wiki page slug"},
            "knowledge_base_id": {"type": "string", "description": "Knowledge base id or exact name"},
        },
        ["slug", "knowledge_base_id"],
    ),
    TOOL_WIKI_INDEX: _tool_schema(
        TOOL_WIKI_INDEX,
        "List the wiki pages of a knowledge base (an index of the generated wiki).",
        {"knowledge_base_id": {"type": "string", "description": "Knowledge base id or exact name"}},
        ["knowledge_base_id"],
    ),
}


# --------------------------------------------------------------------------
# 工具执行
# --------------------------------------------------------------------------


def _chunk_snippet(content: str, limit: int = 800) -> str:
    content = (content or "").strip()
    return content[:limit] + ("…" if len(content) > limit else "")


async def _resolve_kbs_async(session: AsyncSession, endpoint: MCPEndpoint, selectors: list[str]):
    all_kbs = await knowledge_repository.list_kbs(session, endpoint.tenant_id)
    if selectors:
        wanted = {str(item).strip() for item in selectors if str(item).strip()}
        kbs = [kb for kb in all_kbs if kb.id in wanted or kb.name in wanted]
    else:
        kbs = all_kbs
    return [kb for kb in kbs if endpoint.allows_knowledge_base(kb.id)]


def _kb_capabilities(kb) -> list[str]:
    caps = ["semantic", "keyword"]
    if kb.type == KB_TYPE_WIKI or bool((kb.indexing_strategy or {}).get("wiki_enabled")):
        caps.append("wiki")
    return caps


async def _tool_list_knowledge_bases(session: AsyncSession, endpoint: MCPEndpoint, args: dict) -> str:
    kbs = await _resolve_kbs_async(session, endpoint, [])
    rows = [
        {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description or "",
            "type": kb.type,
            "capabilities": _kb_capabilities(kb),
        }
        for kb in kbs
    ]
    return json.dumps({"knowledge_bases": rows, "total": len(rows)}, ensure_ascii=False, indent=2)


async def _tool_search_knowledge(session: AsyncSession, endpoint: MCPEndpoint, args: dict) -> str:
    query = str(args.get("query") or "").strip()
    if not query:
        return "错误：search_knowledge 需要 query 参数"
    limit = max(1, min(int(args.get("limit") or 10), 30))
    selectors = [str(item) for item in args.get("knowledge_base_ids") or []]
    kbs = await _resolve_kbs_async(session, endpoint, selectors)
    if not kbs:
        return "错误：没有可检索的知识库"
    hits: list[tuple[Any, Any]] = []
    for kb in kbs:
        results = await retrieval_service.search(
            session, endpoint.tenant_id, kb.id, query, top_k=limit
        )
        for hit in results:
            hits.append((hit, kb))
    hits.sort(key=lambda item: item[0].score, reverse=True)
    hits = hits[:limit]
    if not hits:
        return "未检索到相关内容"
    rows = [
        {
            "knowledge_base_id": hit.chunk.knowledge_base_id,
            "knowledge_id": hit.chunk.knowledge_id,
            "content": _chunk_snippet(hit.chunk.content),
            "chunk_index": hit.chunk.chunk_index,
            "score": round(hit.score, 6),
        }
        for hit, _kb in hits
    ]
    return json.dumps({"results": rows, "total": len(rows)}, ensure_ascii=False, indent=2)


async def _tool_grep_chunks(session: AsyncSession, endpoint: MCPEndpoint, args: dict) -> str:
    query = str(args.get("query") or "").strip()
    if not query:
        return "错误：grep_chunks 需要 query 参数"
    try:
        pattern = re.compile(query, re.IGNORECASE)
    except re.error:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
    limit = max(1, min(int(args.get("limit") or 10), 30))
    selectors = [str(item) for item in args.get("knowledge_base_ids") or []]
    kbs = await _resolve_kbs_async(session, endpoint, selectors)
    rows: list[dict[str, Any]] = []
    for kb in kbs:
        chunks = await knowledge_repository.list_kb_chunks(session, kb.id)
        for chunk in chunks:
            if pattern.search(chunk.content or ""):
                rows.append(
                    {
                        "knowledge_base_id": kb.id,
                        "knowledge_id": chunk.knowledge_id,
                        "content": _chunk_snippet(chunk.content),
                        "chunk_index": chunk.chunk_index,
                    }
                )
                if len(rows) >= limit:
                    break
        if len(rows) >= limit:
            break
    return json.dumps({"results": rows, "total": len(rows)}, ensure_ascii=False, indent=2)


async def _tool_list_documents(session: AsyncSession, endpoint: MCPEndpoint, args: dict) -> str:
    selector = str(args.get("knowledge_base_id") or "").strip()
    if not selector:
        return "错误：list_documents 需要 knowledge_base_id 参数"
    kbs = await _resolve_kbs_async(session, endpoint, [selector])
    if not kbs:
        return "错误：知识库不存在或不在范围内"
    kb = kbs[0]
    keyword = str(args.get("keyword") or "").strip()
    page = max(1, int(args.get("page") or 1))
    page_size = max(1, min(int(args.get("page_size") or 20), 100))
    items = await knowledge_repository.list_knowledge(session, kb.id)
    if keyword:
        items = [item for item in items if keyword.lower() in (item.title or item.file_name or "").lower()]
    total = len(items)
    start = (page - 1) * page_size
    rows = [
        {
            "id": item.id,
            "title": item.title or item.file_name,
            "file_name": item.file_name or "",
            "file_type": item.file_type or "",
            "source": item.source or "",
            "parse_status": item.parse_status,
            "description": item.description or "",
        }
        for item in items[start : start + page_size]
    ]
    return json.dumps(
        {"knowledge_base_id": kb.id, "total": total, "page": page, "page_size": page_size, "documents": rows},
        ensure_ascii=False,
        indent=2,
    )


async def _tool_read_document(session: AsyncSession, endpoint: MCPEndpoint, args: dict) -> str:
    knowledge_id = str(args.get("knowledge_id") or "").strip()
    if not knowledge_id:
        return "错误：read_document 需要 knowledge_id 参数"
    knowledge = await knowledge_repository.get_knowledge(session, endpoint.tenant_id, knowledge_id)
    if knowledge is None or not endpoint.allows_knowledge_base(knowledge.knowledge_base_id):
        return "错误：文档不存在或不在范围内"
    chunks = await knowledge_repository.list_chunks(session, knowledge_id)
    offset = max(0, int(args.get("offset") or 0))
    limit = max(1, min(int(args.get("limit") or 20), 100))
    phrase = str(args.get("query") or "").strip().lower()
    selected = chunks
    if phrase:
        selected = [c for c in chunks if phrase in (c.content or "").lower()]
    window = selected[offset : offset + limit]
    rows = [
        {"chunk_index": chunk.chunk_index, "content": _chunk_snippet(chunk.content)}
        for chunk in window
    ]
    result = {
        "document": {
            "id": knowledge.id,
            "title": knowledge.title or knowledge.file_name,
            "file_name": knowledge.file_name or "",
            "parse_status": knowledge.parse_status,
        },
        "knowledge_base_id": knowledge.knowledge_base_id,
        "total_chunks": len(selected),
        "chunks": rows,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


async def _tool_ask(session: AsyncSession, endpoint: MCPEndpoint, args: dict) -> str:
    query = str(args.get("query") or "").strip()
    if not query:
        return "错误：ask 需要 query 参数"
    selectors = [str(item) for item in args.get("knowledge_base_ids") or []]
    kbs = await _resolve_kbs_async(session, endpoint, selectors)
    if not kbs:
        return "错误：没有可检索的知识库"
    hits: list[Any] = []
    for kb in kbs:
        hits.extend(await retrieval_service.search(session, endpoint.tenant_id, kb.id, query, top_k=5))
    hits.sort(key=lambda item: item.score, reverse=True)
    hits = hits[:5]
    if not hits:
        return "未检索到相关内容"
    context = "\n\n".join(f"[{i + 1}] {_chunk_snippet(hit.chunk.content)}" for i, hit in enumerate(hits))
    return f"基于知识库检索到的证据：\n\n{context}"


async def _tool_wiki_search(session: AsyncSession, endpoint: MCPEndpoint, args: dict) -> str:
    query = str(args.get("query") or "").strip()
    kbs = await _resolve_kbs_async(session, endpoint, [str(args.get("knowledge_base_id") or "")])
    if not kbs:
        return "错误：知识库不存在或不在范围内"
    limit = max(1, min(int(args.get("limit") or 10), 50))
    pages, total = await wiki_repository.list_pages(
        session, kbs[0].id, query=query, limit=limit
    )
    rows = [{"slug": page.slug, "title": page.title or page.slug, "page_type": page.page_type} for page in pages]
    return json.dumps({"knowledge_base_id": kbs[0].id, "total": total, "pages": rows}, ensure_ascii=False, indent=2)


async def _tool_wiki_read_page(session: AsyncSession, endpoint: MCPEndpoint, args: dict) -> str:
    slug = str(args.get("slug") or "").strip()
    kbs = await _resolve_kbs_async(session, endpoint, [str(args.get("knowledge_base_id") or "")])
    if not kbs:
        return "错误：知识库不存在或不在范围内"
    page = await wiki_repository.get_page_by_slug(session, kbs[0].id, slug)
    if page is None:
        return "错误：Wiki 页面不存在"
    return json.dumps(
        {"slug": page.slug, "title": page.title or page.slug, "content": page.content or ""},
        ensure_ascii=False,
        indent=2,
    )


async def _tool_wiki_index(session: AsyncSession, endpoint: MCPEndpoint, args: dict) -> str:
    kbs = await _resolve_kbs_async(session, endpoint, [str(args.get("knowledge_base_id") or "")])
    if not kbs:
        return "错误：知识库不存在或不在范围内"
    pages = await wiki_repository.list_all_pages(session, kbs[0].id)
    rows = [{"slug": page.slug, "title": page.title or page.slug, "page_type": page.page_type} for page in pages]
    return json.dumps({"knowledge_base_id": kbs[0].id, "total": len(rows), "pages": rows}, ensure_ascii=False, indent=2)


TOOL_HANDLERS: dict[str, Any] = {
    TOOL_LIST_KNOWLEDGE_BASES: _tool_list_knowledge_bases,
    TOOL_SEARCH_KNOWLEDGE: _tool_search_knowledge,
    TOOL_GREP_CHUNKS: _tool_grep_chunks,
    TOOL_LIST_DOCUMENTS: _tool_list_documents,
    TOOL_READ_DOCUMENT: _tool_read_document,
    TOOL_ASK: _tool_ask,
    TOOL_WIKI_SEARCH: _tool_wiki_search,
    TOOL_WIKI_READ_PAGE: _tool_wiki_read_page,
    TOOL_WIKI_INDEX: _tool_wiki_index,
}


# --------------------------------------------------------------------------
# JSON-RPC 分发
# --------------------------------------------------------------------------


def _jsonrpc_result(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _jsonrpc_error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _tool_error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


async def _dispatch(session: AsyncSession, endpoint: MCPEndpoint, body: dict[str, Any]) -> dict | None:
    msg_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params") or {}

    if method == "initialize":
        protocol = str(params.get("protocolVersion") or "2024-11-05")
        return _jsonrpc_result(
            msg_id,
            {
                "protocolVersion": protocol,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": SERVER_INSTRUCTIONS,
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _jsonrpc_result(msg_id, {})
    if method == "tools/list":
        tools = [TOOL_SCHEMAS[name] for name in endpoint.tools if name in TOOL_SCHEMAS]
        return _jsonrpc_result(msg_id, {"tools": tools})
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        if not endpoint.has_tool(name):
            return _jsonrpc_result(msg_id, _tool_error(f"tool {name!r} is not enabled on this endpoint"))
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            return _jsonrpc_result(msg_id, _tool_error(f"tool {name!r} is not implemented"))
        try:
            text = await handler(session, endpoint, arguments)
            return _jsonrpc_result(msg_id, {"content": [{"type": "text", "text": text}], "isError": False})
        except Exception as exc:  # noqa: BLE001 - 工具失败反馈给客户端而非中断
            return _jsonrpc_result(msg_id, _tool_error(f"{type(exc).__name__}: {exc}"))

    return _jsonrpc_error(msg_id, -32601, "Method not found")


def _extract_bearer(request: Request) -> str:
    header = (request.headers.get("Authorization") or "").strip()
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


@router.api_route("/{endpoint_id}", methods=["POST", "GET", "DELETE"])
async def mcp_entry(
    endpoint_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    token = _extract_bearer(request)
    try:
        endpoint = await mcp_endpoint_service.authenticate(session, endpoint_id, token)
    except AppError as exc:
        headers = {"WWW-Authenticate": 'Bearer realm="weknora-mcp"'} if exc.http_status == 401 else {}
        return JSONResponse(status_code=exc.http_status, content={"error": exc.message}, headers=headers)

    if request.method != "POST":
        return JSONResponse(status_code=202, content={})

    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        return JSONResponse(status_code=400, content=_jsonrpc_error(None, -32700, "Parse error"))

    result = await _dispatch(session, endpoint, body)
    if result is None:
        return JSONResponse(status_code=202, content={})
    return JSONResponse(status_code=200, content=result)
