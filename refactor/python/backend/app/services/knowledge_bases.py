"""Single-connection knowledge-base authorization, snapshots and durable creation."""

import logging
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime

from app.api.schemas.knowledge_bases import project_knowledge_base
from app.core.database import connect_auth_database
from app.core.security import decode_token, timestamp
from app.domain.auth import AuthFailure
from app.domain.knowledge_bases import (
    GO_WHITESPACE,
    MAX_KNOWLEDGE_BASES,
    SUPPORTED_STORAGE,
    KnowledgeBaseFailure,
    invalid,
)
from app.repositories import knowledge_bases as repository

logger = logging.getLogger(__name__)


def allowed_storage_providers():
    raw = os.environ.get("STORAGE_ALLOW_LIST", "").strip(GO_WHITESPACE)
    if not raw:
        return set(SUPPORTED_STORAGE)
    return {part.strip(GO_WHITESPACE).lower() for part in re.split(r"[,;|\n\t ]+", raw)} & set(SUPPORTED_STORAGE)


def resolve_storage_binding(connection, tenant_id):
    metadata = repository.load_storage_metadata(connection, tenant_id)
    allowed = allowed_storage_providers()
    default_provider = (metadata["default_provider"] or "").strip(GO_WHITESPACE).lower()
    provider = (default_provider if default_provider in allowed else
                next((item for item in SUPPORTED_STORAGE if item in allowed), ""))
    backend_id = metadata["default_storage_backend_id"]
    backend = None
    if backend_id:
        backend = repository.find_storage_backend(connection, tenant_id, backend_id=backend_id)
        if backend is None:
            raise invalid("storage backend is unavailable")
    elif provider:
        backend = repository.find_storage_backend(connection, tenant_id, provider=provider)
    if backend is not None:
        if (backend["status"] != "active" or backend["deleted_at"] is not None or
                backend["provider"] not in allowed or backend["tenant_id"] != tenant_id):
            raise invalid("storage backend is unavailable")
        provider, backend_id = backend["provider"], backend["id"]
    return provider, backend_id or None


def record_activity_best_effort(connection, identity, kb):
    """The business transaction has committed; an audit failure must never reverse success."""
    try:
        repository.insert_activity(connection, identity, kb)
    except Exception:  # noqa: BLE001 - post-commit audit must never turn a committed write into failure.
        # No exception text, SQL, body or identity data in logs. Never retry the creation.
        logger.warning("knowledge_base_audit_failure category=storage")


class KnowledgeBaseService:
    def __init__(self, auth_service):
        self.auth = auth_service

    @contextmanager
    def operation(self, raw, tenant_id, *, write=False):
        try:
            self.auth.require_available()
            decode_token(raw, self.auth.secret, "access")
            with connect_auth_database(self.auth.settings) as connection:
                connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                try:
                    identity = self.auth.current_identity_in_connection(connection, raw, tenant_id)
                    yield connection, identity
                except BaseException:
                    connection.rollback()
                    raise
                finally:
                    if connection.in_transaction:
                        connection.rollback()
        except AuthFailure as exc:
            if exc.code in (1007, 1008):
                message = ("Knowledge base storage failure" if exc.code == 1007 else
                           "Knowledge base service unavailable")
                raise KnowledgeBaseFailure(exc.status, exc.code, message) from None
            raise
        except sqlite3.Error:
            # Normally normalized by connect_auth_database, retained for injected adapters.
            raise KnowledgeBaseFailure(500, 1007, "Knowledge base storage failure") from None

    def create(self, payload, raw, tenant_id=None):
        with self.operation(raw, tenant_id, write=True) as (connection, identity):
            if identity.memberships[0]["role"] not in ("owner", "admin", "contributor"):
                raise KnowledgeBaseFailure(403, 1002, "Knowledge base creation is not permitted")
            if len(repository.probe_capacity(connection, identity.tenant["id"])) >= MAX_KNOWLEDGE_BASES:
                raise invalid("Knowledge base limit reached")
            provider, backend_id = resolve_storage_binding(connection, identity.tenant["id"])
            kb_id, now = str(uuid.uuid4()), timestamp()
            repository.insert_knowledge_base(connection, payload, identity, kb_id, now, provider, backend_id)
            row = repository.read_knowledge_base(connection, identity.tenant["id"], kb_id)
            projected = project_knowledge_base(row)
            connection.commit()
            record_activity_best_effort(connection, identity, row)
            return projected

    def list(self, raw, tenant_id=None, creator=""):
        with self.operation(raw, tenant_id) as (connection, identity):
            if len(repository.probe_capacity(connection, identity.tenant["id"])) > MAX_KNOWLEDGE_BASES:
                raise KnowledgeBaseFailure(503, 1008, "Knowledge base list exceeds supported capacity")
            rows = repository.list_knowledge_bases(connection, identity.tenant["id"], identity.user["id"], creator)
            metadata = repository.load_list_metadata(connection, identity.tenant["id"], identity.user["id"], rows)
            items = [project_knowledge_base(row, metadata[row["id"]]) for row in rows]
            items.sort(key=lambda item: (item["is_pinned"],
                                         datetime.fromisoformat(item["pinned_at"]).timestamp()
                                         if item["pinned_at"] else float("-inf"),
                                         datetime.fromisoformat(item["created_at"]).timestamp(), item["id"]),
                       reverse=True)
            return items
