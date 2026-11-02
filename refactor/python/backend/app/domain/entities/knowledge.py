"""知识库 / 知识 / 分块实体，对应 knowledge_bases / knowledges / chunks 表。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.base import Base, TimestampMixin

KB_TYPE_DOCUMENT = "document"
KB_TYPE_FAQ = "faq"
KB_TYPE_WIKI = "wiki"

PARSE_PENDING = "pending"
PARSE_PROCESSING = "processing"
PARSE_COMPLETED = "completed"
PARSE_FAILED = "failed"

KNOWLEDGE_TYPE_FILE = "file"
KNOWLEDGE_TYPE_URL = "url"
KNOWLEDGE_TYPE_MANUAL = "manual"
KNOWLEDGE_TYPE_FAQ = "faq"

CHUNK_TYPE_TEXT = "text"
CHUNK_TYPE_FAQ = "faq"

CHUNK_FLAG_RECOMMENDED = 1
CHUNK_STATUS_STORED = 1
CHUNK_STATUS_INDEXED = 2


def new_id() -> str:
    return str(uuid.uuid4())


class KnowledgeBase(Base, TimestampMixin):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    type: Mapped[str] = mapped_column(String(32), nullable=False, default=KB_TYPE_DOCUMENT)
    chunking_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    embedding_model_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    summary_model_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    vlm_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    faq_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    is_temporary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    creator_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    indexing_strategy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Knowledge(Base, TimestampMixin):
    __tablename__ = "knowledges"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default=KNOWLEDGE_TYPE_FILE)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default=PARSE_PENDING)
    enable_status: Mapped[str] = mapped_column(String(32), nullable=False, default="enabled")
    embedding_model_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    file_name: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    file_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    storage_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    channel: Mapped[str] = mapped_column(String(64), nullable=False, default="web")
    folder_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Chunk(Base, TimestampMixin):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    chunk_type: Mapped[str] = mapped_column(String(32), nullable=False, default=CHUNK_TYPE_TEXT)
    # chunks.status 在表里是 INTEGER NOT NULL DEFAULT 0
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # FAQ 条目对外用 seq_id 作为 entry_id；文本分块同样可能有值。
    seq_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tag_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 位标记：1 表示「可推荐」，FAQ 条目默认置位。
    flags: Mapped[int] = mapped_column(Integer, nullable=False, default=CHUNK_FLAG_RECOMMENDED)
    # 表里 start_at / end_at 为 NOT NULL 且无默认值，入库时必须显式给值
    start_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_at: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Phase 4 简化：向量以 JSON 存在此处，PostgreSQL 版本后续切 pgvector 列。
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def embedding(self) -> list[float]:
        return list((self.metadata_json or {}).get("embedding") or [])
