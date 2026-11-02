"""Wiki 实体，对应 wiki_pages / wiki_page_revisions / wiki_folders 表。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.base import Base, TimestampMixin
from app.domain.entities.knowledge import new_id

WIKI_PAGE_TYPE_SUMMARY = "summary"
WIKI_PAGE_TYPE_ENTITY = "entity"
WIKI_PAGE_TYPE_CONCEPT = "concept"
WIKI_PAGE_TYPE_INDEX = "index"
WIKI_PAGE_TYPE_SYNTHESIS = "synthesis"
WIKI_PAGE_TYPE_COMPARISON = "comparison"
WIKI_PAGE_TYPES = {
    WIKI_PAGE_TYPE_SUMMARY,
    WIKI_PAGE_TYPE_ENTITY,
    WIKI_PAGE_TYPE_CONCEPT,
    WIKI_PAGE_TYPE_INDEX,
    WIKI_PAGE_TYPE_SYNTHESIS,
    WIKI_PAGE_TYPE_COMPARISON,
}

WIKI_STATUS_DRAFT = "draft"
WIKI_STATUS_PUBLISHED = "published"
WIKI_STATUS_ARCHIVED = "archived"
WIKI_STATUSES = {WIKI_STATUS_DRAFT, WIKI_STATUS_PUBLISHED, WIKI_STATUS_ARCHIVED}

WIKI_EDIT_SOURCE_PIPELINE = "pipeline"
WIKI_EDIT_SOURCE_AGENT = "agent"
WIKI_EDIT_SOURCE_USER = "user"
WIKI_EDIT_SOURCE_REVERT = "revert"

WIKI_FOLDER_ROOT_ID = ""


class WikiPage(Base, TimestampMixin):
    __tablename__ = "wiki_pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(36), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    page_type: Mapped[str] = mapped_column(String(32), nullable=False, default=WIKI_PAGE_TYPE_SUMMARY)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=WIKI_STATUS_PUBLISHED)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parent_slug: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    folder_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    category_path: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    wiki_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    chunk_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    in_links: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    out_links: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    page_metadata: Mapped[dict[str, Any]] = mapped_column(
        "page_metadata", JSON, nullable=False, default=dict
    )
    aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_edit_source: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    last_editor_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WikiPageRevision(Base):
    __tablename__ = "wiki_page_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(36), nullable=False)
    page_id: Mapped[str] = mapped_column(String(36), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    page_type: Mapped[str] = mapped_column(String(32), nullable=False, default=WIKI_PAGE_TYPE_SUMMARY)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=WIKI_STATUS_PUBLISHED)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    edit_source: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    editor_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WikiFolder(Base, TimestampMixin):
    __tablename__ = "wiki_folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    knowledge_base_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parent_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
