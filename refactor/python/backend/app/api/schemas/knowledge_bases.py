"""Strict create input and credential-free, prefix-v7 response projection."""

import json
from copy import deepcopy
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.domain.knowledge_bases import (
    GO_WHITESPACE,
    SUPPORTED_STORAGE,
    invalid,
    storage_failure,
    unsupported_configuration,
)

DEFAULT_CONFIGS = {
    "chunking_config": {"chunk_size": 0, "chunk_overlap": 0, "separators": None},
    "image_processing_config": {"model_id": ""},
    "vlm_config": {"enabled": False, "model_id": "", "model_name": "", "base_url": "",
                   "api_key": "", "interface_type": ""},
    "asr_config": {"enabled": False, "model_id": "", "language": ""},
    "cos_config": {"secret_id": "", "secret_key": "", "region": "", "bucket_name": "",
                   "app_id": "", "path_prefix": "", "provider": ""},
    "indexing_strategy": {"vector_enabled": True, "keyword_enabled": True,
                          "wiki_enabled": False, "graph_enabled": False},
}
OPTIONAL_CONFIGS = ("extract_config", "faq_config", "question_generation_config", "auto_tag_config", "wiki_config")
# Types from the original entity. Known out-of-subset fields are checked before classifying scope.
EXTRA_TYPES = {
    "cos_config": {"endpoint": str, "use_ssl": bool, "force_path_style": bool},
    "chunking_config": {"split_markers": list, "keep_separator": bool, "parser_engine_rules": list,
                        "enable_parent_child": bool, "parent_chunk_size": int, "child_chunk_size": int,
                        "strategy": str, "token_limit": int, "languages": list,
                        "table_metadata_instructions": str},
    "image_processing_config": {"enable_multimodal": bool, "image_actions": dict,
                                "image_attrs_enabled": bool, "image_pipeline": str,
                                "image_pipeline_params": dict, "image_vector_enabled": bool},
    "vlm_config": {"description_language": str, "custom_instructions": str},
    "extract_config": {"enabled": bool, "text": str, "tags": list, "nodes": list,
                       "relations": list, "custom_instructions": str},
    "faq_config": {"index_mode": str, "question_index_mode": str},
    "question_generation_config": {"model_id": str, "enabled": bool, "question_count": int,
                                   "custom_instructions": str},
    "auto_tag_config": {"enabled": bool, "model_id": str, "max_tags": int, "skip_if_tagged": bool},
    "wiki_config": {"auto_generate": bool, "synthesis_model_id": str, "max_pages_per_ingest": int,
                    "extraction_granularity": str, "content_instructions": str,
                    "extraction_instructions": str, "ingest_batch_size": int,
                    "ingest_map_parallel": int, "ingest_reduce_parallel": int, "ingest_max_inflight": int},
}


class CreateKnowledgeBaseRequest(BaseModel):
    """Accept only the five frozen request fields without coercion."""

    model_config = ConfigDict(extra="forbid", strict=True)
    name: str
    description: str = ""
    type: str = "document"
    embedding_model_id: str = ""
    summary_model_id: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        value = value.strip(GO_WHITESPACE)
        if not value:
            raise invalid("name cannot be empty")
        if len(value) > 255:
            raise invalid("Knowledge base name exceeds 255 characters")
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value):
        if len(value) > 4000:
            raise invalid("Knowledge base description exceeds 4000 characters")
        return value

    @field_validator("type")
    @classmethod
    def validate_type(cls, value):
        if value not in ("", "document"):
            raise invalid("Unsupported knowledge base type")
        return "document"

    @field_validator("embedding_model_id", "summary_model_id")
    @classmethod
    def validate_model(cls, value):
        if value:
            raise invalid("Models are not supported for empty knowledge bases")
        return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def strict_json(raw):
    """Reject duplicate keys, non-finite constants and surrogate code points."""
    value = json.loads(raw, object_pairs_hook=unique_object,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid constant")))
    # Round-trip validation rejects escaped lone surrogates before SQLite/JSON encoding.
    json.dumps(value, ensure_ascii=False).encode("utf-8")
    return value


def stored_config(raw, name):
    if raw is None and name in (*OPTIONAL_CONFIGS, "storage_provider_config"):
        return None
    try:
        value = strict_json(raw)
        if value is None and name in (*OPTIONAL_CONFIGS, "storage_provider_config"):
            return None
        if type(value) is not dict:
            raise ValueError("Expected object")
        defaults = DEFAULT_CONFIGS.get(name, {})
        types = {key: type(item) for key, item in defaults.items() if item is not None}
        types.update(EXTRA_TYPES.get(name, {}))
        if name == "storage_provider_config":
            types["provider"] = str
        if name == "chunking_config":
            types["separators"] = list
        for key, item in value.items():
            expected = types.get(key)
            if expected is not None and type(item) is not expected:
                if item is None and (expected is list or key in (
                        "image_actions", "image_pipeline_params", "skip_if_tagged", "auto_generate")):
                    continue
                raise ValueError("Invalid field type")
            if expected is int and not -(2 ** 63) <= item < 2 ** 63:
                raise ValueError("Integer overflow")
            if (key in ("separators", "split_markers", "languages", "tags") and item is not None and
                    any(type(part) is not str for part in item)):
                raise ValueError("Invalid string array")
            if key == "parser_engine_rules" and item is not None:
                for rule in item:
                    if (type(rule) is not dict or type(rule.get("engine", "")) is not str or
                            (rule.get("file_types") is not None and
                             type(rule["file_types"]) is not list) or
                            any(type(part) is not str for part in rule.get("file_types") or []) or
                            (rule.get("xlsx_first_row_as_header") is not None and
                             type(rule["xlsx_first_row_as_header"]) is not bool)):
                        raise ValueError("Invalid parser rule")
        validate_nested_config(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise storage_failure() from None


def validate_nested_config(value):
    """Check nested original entity field types before reporting a valid unsupported configuration."""
    for key in ("nodes", "relations"):
        for item in value.get(key) or []:
            if item is None:  # The original graph configuration contains slices of pointers.
                continue
            if type(item) is not dict:
                raise ValueError("Invalid graph object")
            fields = ({"name": str, "chunks": list, "attributes": list} if key == "nodes" else
                      {"node1": str, "node2": str, "type": str})
            for field, expected in fields.items():
                if field not in item:
                    continue
                part = item[field]
                if part is None and expected is list:
                    continue
                if type(part) is not expected or (expected is list and
                                                  any(type(entry) is not str for entry in part)):
                    raise ValueError("Invalid graph field")
    actions = value.get("image_actions")
    if actions is not None and "ocr" in actions:
        ocr = actions["ocr"]
        if type(ocr) is not dict or (ocr.get("on") is not None and type(ocr["on"]) is not list):
            raise ValueError("Invalid image action")
        for condition in ocr.get("on") or []:
            if (type(condition) is not dict or
                    any(type(condition.get(key, "")) is not str for key in ("prop", "is"))):
                raise ValueError("Invalid image condition")


def rfc3339(raw):
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise storage_failure() from None


def project_knowledge_base(row: dict, metadata: dict | None = None) -> dict:
    """Validate all persisted configs first; never expose credential-bearing supersets."""
    configs = {name: stored_config(row[name], name)
               for name in (*DEFAULT_CONFIGS, *OPTIONAL_CONFIGS, "storage_provider_config")}
    for key in ("name", "type", "embedding_model_id", "summary_model_id"):
        if type(row[key]) is not str:
            raise storage_failure()
    if row["description"] is not None and type(row["description"]) is not str:
        raise storage_failure()
    if row["creator_id"] is not None and type(row["creator_id"]) is not str:
        raise storage_failure()
    outside = (row["type"] != "document" or bool(row["embedding_model_id"]) or
               bool(row["summary_model_id"]) or bool(row["vector_store_id"]))
    for name, defaults in DEFAULT_CONFIGS.items():
        value = configs[name]
        allowed = deepcopy(defaults)
        if name == "cos_config":
            provider = value.get("provider", "")
            if provider and provider not in SUPPORTED_STORAGE:
                outside = True
            allowed["provider"] = provider
        # Missing Go struct fields have zero/default values; don't rewrite persisted records.
        outside |= any(key not in allowed or item != allowed[key] for key, item in value.items())
        configs[name] = {**allowed, **value}
    provider_config = configs["storage_provider_config"]
    if provider_config is not None:
        outside |= (set(provider_config) - {"provider"} != set() or
                    provider_config.get("provider", "") not in ("", *SUPPORTED_STORAGE))
        configs["storage_provider_config"] = {"provider": "", **provider_config}
    outside |= any(configs[name] is not None for name in OPTIONAL_CONFIGS)
    if outside:
        raise unsupported_configuration()
    result = {key: row[key] for key in ("id", "name", "type", "tenant_id", "creator_id",
                                       "embedding_model_id", "summary_model_id")}
    result.update(creator_id=row["creator_id"] if row["creator_id"] is not None else "",
                  description=row["description"] or "", is_temporary=bool(row["is_temporary"]),
                  created_at=rfc3339(row["created_at"]), updated_at=rfc3339(row["updated_at"]),
                  deleted_at=rfc3339(row["deleted_at"]) if row["deleted_at"] else None)
    result.update({("storage_config" if key == "cos_config" else key): value
                   for key, value in configs.items()})
    result.update(profile_config=None, knowledge_count=0, chunk_count=0, is_processing=False,
                  processing_count=0, share_count=0, is_pinned=False, pinned_at=None,
                  capabilities={"vector": True, "keyword": True, "wiki": False, "graph": False, "faq": False},
                  vector_store_source="unavailable", vector_store_status="unavailable")
    for key in ("vector_store_id", "storage_backend_id"):
        if row[key]:
            result[key] = row[key]
    if metadata:
        result.update(metadata)
    return result
