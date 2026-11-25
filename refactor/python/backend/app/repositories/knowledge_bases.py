"""Fixed-column, bounded knowledge-base SQL; callers own connections and commits."""

import json

from app.api.schemas.knowledge_bases import DEFAULT_CONFIGS, OPTIONAL_CONFIGS, rfc3339
from app.domain.knowledge_bases import MAX_KNOWLEDGE_BASES, storage_failure

COLUMNS = (
    "id", "name", "description", "tenant_id", "type", "chunking_config", "image_processing_config",
    "embedding_model_id", "summary_model_id", "cos_config", "storage_provider_config", "vlm_config",
    "extract_config", "faq_config", "question_generation_config", "is_temporary", "asr_config",
    "vector_store_id", "storage_backend_id", "creator_id", "wiki_config", "indexing_strategy",
    "created_at", "updated_at", "deleted_at", "auto_tag_config",
)
COLUMN_SQL = ", ".join(COLUMNS)
VISIBLE = "tenant_id = ? AND deleted_at IS NULL AND is_temporary = 0"

# Fixed original StorageEngineConfig fields. Only JSON type flags leave SQLite, never field values.
_STORAGE_STRING_FIELDS = {
    "local": ("path_prefix",),
    "minio": ("mode", "endpoint", "access_key_id", "secret_access_key", "bucket_name", "path_prefix"),
    "cos": ("secret_id", "secret_key", "region", "bucket_name", "app_id", "path_prefix",
            "temp_bucket_name", "temp_region"),
    "tos": ("endpoint", "region", "access_key", "secret_key", "bucket_name", "path_prefix",
            "temp_bucket_name", "temp_region"),
    "s3": ("endpoint", "region", "access_key", "secret_key", "bucket_name", "path_prefix"),
    "oss": ("endpoint", "region", "access_key", "secret_key", "bucket_name", "path_prefix",
            "temp_bucket_name", "temp_region"),
    "ks3": ("endpoint", "region", "access_key", "secret_key", "bucket_name", "path_prefix"),
    "obs": ("endpoint", "region", "access_key", "secret_key", "bucket_name", "path_prefix"),
}
_STORAGE_BOOL_FIELDS = {
    "minio": ("use_ssl",), "s3": ("use_ssl", "force_path_style"),
    "oss": ("use_temp_bucket",), "obs": ("use_ssl",),
}
# SQL fragments are exclusively generated from the fixed field whitelist above, never request data.
_STORAGE_TYPE_CHECKS = " AND ".join(
    [f"COALESCE(json_type(storage_engine_config, '$.{provider}'), 'missing') "
     "IN ('missing', 'null', 'object')" for provider in _STORAGE_STRING_FIELDS] +
    [f"COALESCE(json_type(storage_engine_config, '$.{provider}.{field}'), 'missing') "
     "IN ('missing', 'text')" for provider, fields in _STORAGE_STRING_FIELDS.items() for field in fields] +
    [f"COALESCE(json_type(storage_engine_config, '$.{provider}.{field}'), 'missing') "
     "IN ('missing', 'true', 'false')" for provider, fields in _STORAGE_BOOL_FIELDS.items() for field in fields]
)


def probe_capacity(connection, tenant_id):
    return connection.execute(
        f"SELECT id FROM knowledge_bases WHERE {VISIBLE} LIMIT ?",
        (tenant_id, MAX_KNOWLEDGE_BASES + 1)).fetchall()


def insert_knowledge_base(connection, payload, identity, kb_id, now, provider, backend_id):
    values = {"id": kb_id, "name": payload.name, "description": payload.description,
              "tenant_id": identity.tenant["id"], "creator_id": identity.user["id"], "type": "document",
              "embedding_model_id": "", "summary_model_id": "", "is_temporary": 0,
              "vector_store_id": None, "storage_backend_id": backend_id,
              "created_at": now, "updated_at": now, "deleted_at": None,
              "storage_provider_config": json.dumps({"provider": provider}) if provider else None}
    values.update({key: None for key in OPTIONAL_CONFIGS})
    values.update({key: json.dumps(value) for key, value in DEFAULT_CONFIGS.items()})
    # SetStorageProvider in the original entity leaves the legacy credential configuration zero-valued.
    connection.execute(
        f"INSERT INTO knowledge_bases ({COLUMN_SQL}) VALUES ({','.join('?' for _ in COLUMNS)})",
        tuple(values[key] for key in COLUMNS))


def read_knowledge_base(connection, tenant_id, kb_id):
    row = connection.execute(
        f"SELECT {COLUMN_SQL} FROM knowledge_bases WHERE {VISIBLE} AND id = ?",
        (tenant_id, kb_id)).fetchone()
    if row is None:
        raise storage_failure()
    return dict(row)


def list_knowledge_bases(connection, tenant_id, user_id, creator):
    condition = ""
    parameters = [tenant_id]
    if creator == "mine":
        condition = " AND creator_id IS NOT NULL AND creator_id != '' AND creator_id = ?"
        parameters.append(user_id)
    elif creator == "others":
        condition = " AND creator_id IS NOT NULL AND creator_id != '' AND creator_id != ?"
        parameters.append(user_id)
    parameters.append(MAX_KNOWLEDGE_BASES)
    rows = connection.execute(
        f"SELECT {COLUMN_SQL} FROM knowledge_bases WHERE {VISIBLE}{condition} "
        "ORDER BY created_at DESC, id DESC LIMIT ?", parameters).fetchall()
    return [dict(row) for row in rows]


def load_list_metadata(connection, tenant_id, user_id, rows):
    """Five constant query batches, each restricted to at most 100 selected identifiers."""
    ids = [row["id"] for row in rows]
    if not ids:
        return {}
    if len(ids) > MAX_KNOWLEDGE_BASES:
        raise storage_failure()
    slots = ",".join("?" for _ in ids)
    result = {kb_id: {"knowledge_count": 0, "chunk_count": 0, "processing_count": 0,
                      "is_processing": False, "share_count": 0, "is_pinned": False, "pinned_at": None}
              for kb_id in ids}
    counts = connection.execute(
        "SELECT knowledge_base_id, COUNT(*) AS total, "
        "SUM(CASE WHEN parse_status IN (?, ?) THEN 1 ELSE 0 END) AS processing "
        f"FROM knowledges WHERE tenant_id = ? AND knowledge_base_id IN ({slots}) "
        "AND deleted_at IS NULL GROUP BY knowledge_base_id",
        ("pending", "processing", tenant_id, *ids)).fetchall()
    for row in counts:
        result[row["knowledge_base_id"]].update(knowledge_count=row["total"],
                                                processing_count=row["processing"],
                                                is_processing=row["processing"] > 0)
    counts = connection.execute(
        f"SELECT knowledge_base_id, COUNT(*) AS total FROM chunks WHERE tenant_id = ? "
        f"AND knowledge_base_id IN ({slots}) AND deleted_at IS NULL GROUP BY knowledge_base_id",
        (tenant_id, *ids)).fetchall()
    for row in counts:
        result[row["knowledge_base_id"]]["chunk_count"] = row["total"]
    counts = connection.execute(
        f"SELECT knowledge_base_id, COUNT(*) AS total FROM kb_shares WHERE source_tenant_id = ? "
        f"AND knowledge_base_id IN ({slots}) AND deleted_at IS NULL GROUP BY knowledge_base_id",
        (tenant_id, *ids)).fetchall()
    for row in counts:
        result[row["knowledge_base_id"]]["share_count"] = row["total"]
    pins = connection.execute(
        f"SELECT kb_id, pinned_at FROM user_kb_pins WHERE tenant_id = ? AND user_id = ? AND kb_id IN ({slots})",
        (tenant_id, user_id, *ids)).fetchall()
    for row in pins:
        result[row["kb_id"]].update(is_pinned=True, pinned_at=rfc3339(row["pinned_at"]))
    creators = list({row["creator_id"] for row in rows if row["creator_id"]})
    if creators:
        names = connection.execute(
            f"SELECT id, username FROM users WHERE tenant_id = ? AND id IN ({','.join('?' for _ in creators)}) "
            "AND deleted_at IS NULL", (tenant_id, *creators)).fetchall()
        names = {row["id"]: row["username"] for row in names}
        for row in rows:
            if names.get(row["creator_id"]):
                result[row["id"]]["creator_name"] = names[row["creator_id"]]
    return result


def load_storage_metadata(connection, tenant_id):
    """Project only the default provider, never retrieve a tenant credential object."""
    row = connection.execute(
        "SELECT default_storage_backend_id, "
        "CASE WHEN storage_engine_config IS NULL THEN 1 ELSE json_valid(storage_engine_config) END AS valid, "
        f"CASE WHEN json_valid(storage_engine_config) THEN ({_STORAGE_TYPE_CHECKS}) "
        "ELSE storage_engine_config IS NULL END AS nested_types_valid, "
        "CASE WHEN json_valid(storage_engine_config) THEN json_type(storage_engine_config) END AS shape, "
        "CASE WHEN json_valid(storage_engine_config) THEN "
        "json_type(storage_engine_config, '$.default_provider') END AS provider_type, "
        "CASE WHEN json_valid(storage_engine_config) THEN "
        "CASE WHEN json_type(storage_engine_config, '$.default_provider') = 'text' THEN "
        "json_extract(storage_engine_config, '$.default_provider') END END AS default_provider "
        "FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    if (row is None or not row["valid"] or not row["nested_types_valid"] or
            row["shape"] not in (None, "object") or
            row["provider_type"] not in (None, "text")):
        raise storage_failure()
    return dict(row)


def find_storage_backend(connection, tenant_id, *, backend_id=None, provider=None):
    columns = "id, tenant_id, provider, status, deleted_at, legacy_alias"
    if backend_id is not None:
        return connection.execute(
            f"SELECT {columns} FROM storage_backends WHERE id = ? AND tenant_id = ?",
            (backend_id, tenant_id)).fetchone()
    return connection.execute(
        f"SELECT {columns} FROM storage_backends WHERE tenant_id = ? AND provider = ? "
        "AND legacy_alias = 1 AND deleted_at IS NULL", (tenant_id, provider)).fetchone()


def insert_activity(connection, identity, kb):
    connection.execute(
        "INSERT INTO audit_logs (tenant_id, actor_user_id, actor_role, action, target_type, target_id, "
        "request_path, request_method, outcome, details, scope_type, scope_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identity.tenant["id"], identity.user["id"], identity.memberships[0]["role"], "kb.created",
         "knowledge_base", kb["id"], "/api/v1/knowledge-bases", "POST", "success",
         json.dumps({"name": kb["name"][:255], "type": "document"}), "knowledge_base", kb["id"],
         kb["created_at"]))
