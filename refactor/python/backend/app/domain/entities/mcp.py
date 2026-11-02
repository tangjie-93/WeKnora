"""MCP Endpoint 实体与工具目录，对应 `mcp_endpoints` 表与 Go `types/mcp_endpoint*.go`。

对齐 Go：
- 端点 = 工作空间发布的 MCP 服务器面（`/mcp/{endpoint_id}`），带独立 bearer token、
  知识库范围与工具白名单
- 工具目录分 retrieve / chat / wiki / ingest 四组，默认启用全部非破坏性工具
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.base import Base, TimestampMixin
from app.domain.entities.knowledge import new_id

MCP_ENDPOINT_TOKEN_PREFIX = "mcp_"
DEFAULT_MCP_ENDPOINT_RATE_LIMIT_PER_MINUTE = 60
MCP_ENDPOINT_MAX_NAME_LEN = 255
MCP_ENDPOINT_MAX_RATE_PER_MIN = 6000

GROUP_RETRIEVE = "retrieve"
GROUP_CHAT = "chat"
GROUP_WIKI = "wiki"
GROUP_INGEST = "ingest"

MCP_ENDPOINT_TOOL_GROUPS = [GROUP_RETRIEVE, GROUP_CHAT, GROUP_WIKI, GROUP_INGEST]

TOOL_LIST_KNOWLEDGE_BASES = "list_knowledge_bases"
TOOL_SEARCH_KNOWLEDGE = "search_knowledge"
TOOL_GREP_CHUNKS = "grep_chunks"
TOOL_LIST_DOCUMENTS = "list_documents"
TOOL_READ_DOCUMENT = "read_document"
TOOL_ASK = "ask"
TOOL_WIKI_SEARCH = "wiki_search"
TOOL_WIKI_READ_PAGE = "wiki_read_page"
TOOL_WIKI_INDEX = "wiki_index"
TOOL_ADD_DOCUMENT = "add_document"
TOOL_UPDATE_DOCUMENT = "update_document"
TOOL_DELETE_DOCUMENT = "delete_document"

# 有序目录，顺序即前端展示顺序（对齐 `types.MCPEndpointToolCatalog`）。
MCP_ENDPOINT_TOOL_CATALOG: list[dict[str, Any]] = [
    {"name": TOOL_LIST_KNOWLEDGE_BASES, "group": GROUP_RETRIEVE, "destructive": False},
    {"name": TOOL_SEARCH_KNOWLEDGE, "group": GROUP_RETRIEVE, "destructive": False},
    {"name": TOOL_GREP_CHUNKS, "group": GROUP_RETRIEVE, "destructive": False},
    {"name": TOOL_LIST_DOCUMENTS, "group": GROUP_RETRIEVE, "destructive": False},
    {"name": TOOL_READ_DOCUMENT, "group": GROUP_RETRIEVE, "destructive": False},
    {"name": TOOL_ASK, "group": GROUP_CHAT, "destructive": False},
    {"name": TOOL_WIKI_SEARCH, "group": GROUP_WIKI, "destructive": False},
    {"name": TOOL_WIKI_READ_PAGE, "group": GROUP_WIKI, "destructive": False},
    {"name": TOOL_WIKI_INDEX, "group": GROUP_WIKI, "destructive": False},
    {"name": TOOL_ADD_DOCUMENT, "group": GROUP_INGEST, "destructive": True},
    {"name": TOOL_UPDATE_DOCUMENT, "group": GROUP_INGEST, "destructive": True},
    {"name": TOOL_DELETE_DOCUMENT, "group": GROUP_INGEST, "destructive": True},
]


def default_mcp_endpoint_tools() -> list[str]:
    """新端点默认白名单：全部只读工具，不含写入。"""
    return [item["name"] for item in MCP_ENDPOINT_TOOL_CATALOG if not item["destructive"]]


def normalize_mcp_endpoint_tools(names: list[str]) -> list[str]:
    """丢弃未知/重复名，按目录顺序返回规范白名单。"""
    wanted = {(name or "").strip() for name in names}
    wanted.discard("")
    return [item["name"] for item in MCP_ENDPOINT_TOOL_CATALOG if item["name"] in wanted]


class MCPEndpoint(Base, TimestampMixin):
    __tablename__ = "mcp_endpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    token_hint: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    knowledge_base_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    tools: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    default_agent_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_MCP_ENDPOINT_RATE_LIMIT_PER_MINUTE
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def has_tool(self, name: str) -> bool:
        return (name or "").strip() in (self.tools or [])

    def restricts_knowledge_bases(self) -> bool:
        return bool(self.knowledge_base_ids)

    def allows_knowledge_base(self, kb_id: str) -> bool:
        ids = self.knowledge_base_ids or []
        if not ids:
            return True
        return kb_id in ids
