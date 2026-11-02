"""自定义 Agent 实体，对应 custom_agents 表。

对齐 Go `internal/types/custom_agent.go`：id + tenant_id 为复合主键，
内置 agent 使用固定 id（`builtin-quick-answer` / `builtin-smart-reasoning`），
自定义 agent 使用 UUID。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.base import Base, TimestampMixin
from app.domain.entities.knowledge import new_id

AGENT_MODE_QUICK_ANSWER = "quick-answer"
AGENT_MODE_SMART_REASONING = "smart-reasoning"
AGENT_MODES = {AGENT_MODE_QUICK_ANSWER, AGENT_MODE_SMART_REASONING}

AGENT_TYPE_RAG_QA = "rag-qa"
AGENT_TYPE_WIKI_QA = "wiki-qa"
AGENT_TYPE_HYBRID_RAG_WIKI = "hybrid-rag-wiki"
AGENT_TYPE_DATA_ANALYSIS = "data-analysis"
AGENT_TYPE_CUSTOM = "custom"
AGENT_TYPES = {
    AGENT_TYPE_RAG_QA,
    AGENT_TYPE_WIKI_QA,
    AGENT_TYPE_HYBRID_RAG_WIKI,
    AGENT_TYPE_DATA_ANALYSIS,
    AGENT_TYPE_CUSTOM,
}

KB_SELECTION_ALL = "all"
KB_SELECTION_SELECTED = "selected"
KB_SELECTION_NONE = "none"
KB_SELECTION_MODES = {KB_SELECTION_ALL, KB_SELECTION_SELECTED, KB_SELECTION_NONE}

BUILTIN_QUICK_ANSWER_ID = "builtin-quick-answer"
BUILTIN_SMART_REASONING_ID = "builtin-smart-reasoning"

MAX_AGENT_AVATAR_CHARS = 64


class CustomAgent(Base, TimestampMixin):
    __tablename__ = "custom_agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    avatar: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    runnable_by_viewer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
