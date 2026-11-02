"""会话与消息实体，对应 sessions / messages 表。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.base import Base, TimestampMixin
from app.domain.entities.knowledge import new_id

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"


class Session(Base, TimestampMixin):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    knowledge_base_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    max_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    enable_rewrite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    embedding_top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    rerank_top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    keyword_threshold: Mapped[float] = mapped_column(nullable=False, default=0.3)
    vector_threshold: Mapped[float] = mapped_column(nullable=False, default=0.5)
    rerank_model_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    summary_model_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    knowledge_references: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    channel: Mapped[str] = mapped_column(String(64), nullable=False, default="web")
    model_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
