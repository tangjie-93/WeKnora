"""模型实体，对应 models 表。字段与 Go 端 `types.Model` 一致。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.base import Base, TimestampMixin

MODEL_TYPE_CHAT = "chat"
MODEL_TYPE_EMBEDDING = "embedding"
MODEL_TYPE_RERANK = "rerank"
MODEL_TYPE_VLM = "vlm"
MODEL_TYPE_ASR = "asr"

MODEL_TYPES = {
    MODEL_TYPE_CHAT,
    MODEL_TYPE_EMBEDDING,
    MODEL_TYPE_RERANK,
    MODEL_TYPE_VLM,
    MODEL_TYPE_ASR,
}

MODEL_STATUS_ACTIVE = "active"
MODEL_STATUS_DISABLED = "disabled"

SOURCE_REMOTE = "remote"
SOURCE_LOCAL = "local"
SOURCE_BUILTIN = "builtin"


def new_id() -> str:
    return str(uuid.uuid4())


class Model(Base, TimestampMixin):
    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default=SOURCE_REMOTE)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    managed_by: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=MODEL_STATUS_ACTIVE)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def base_url(self) -> str:
        return str((self.parameters or {}).get("base_url") or "")

    @property
    def api_key(self) -> str:
        return str((self.parameters or {}).get("api_key") or "")

    @property
    def provider(self) -> str:
        return str((self.parameters or {}).get("provider") or "openai")

    @property
    def dimension(self) -> int:
        emb = (self.parameters or {}).get("embedding_parameters") or {}
        return int(emb.get("dimension") or 1024)
