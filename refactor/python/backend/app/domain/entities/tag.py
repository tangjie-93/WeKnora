"""知识库标签实体，对应 knowledge_tags / knowledge_tag_relations 表。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.base import Base, TimestampMixin
from app.domain.entities.knowledge import new_id

UNTAGGED_TAG_NAME = "未分类"


class KnowledgeTag(Base, TimestampMixin):
    __tablename__ = "knowledge_tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    color: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # SQLite 不支持非主键自增，seq_id 由仓储层按 MAX(seq_id)+1 预分配。
    seq_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeTagRelation(Base):
    """知识与标签的多对多关系；表里只有 created_at。"""

    __tablename__ = "knowledge_tag_relations"

    knowledge_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tag_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True, default=lambda: datetime.now(UTC)
    )
