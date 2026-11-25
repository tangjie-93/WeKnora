"""Knowledge-base contracts against a new private prefix-v7 SQLite database per test."""

import json
import sqlite3
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from threading import Barrier

import pytest
from test_auth import auth, bearer, error, register_login, sql  # noqa: F401 - existing fixture/helpers

from app.api.schemas.knowledge_bases import DEFAULT_CONFIGS
from app.core import migrations
from app.repositories import knowledge_bases as repository
from app.services import knowledge_bases as service

PATH = "/api/v1/knowledge-bases"


@pytest.fixture
def kb(auth, monkeypatch):  # noqa: F811 - imported pytest fixture
    monkeypatch.setenv("STORAGE_ALLOW_LIST", "s3,local")
    login = register_login(auth)
    client, app, path = auth
    return client, app, path, login, bearer(login["token"])


def create(kb, **body):
    return kb[0].post(PATH, headers=kb[4], json={"name": "真实空知识库", **body})


def listing(kb, query=""):
    return kb[0].get(PATH + query, headers=kb[4])


def seed(kb, count):
    """Clone a real created row, changing only generated identifiers in the owned test database."""
    first = create(kb).json()["data"]["id"]
    columns = repository.COLUMNS
    row = sql(kb[2], f"SELECT {repository.COLUMN_SQL} FROM knowledge_bases WHERE id = ?", (first,))[0]
    with sqlite3.connect(kb[2]) as connection:
        for _ in range(count - 1):
            values = list(row)
            values[columns.index("id")] = str(uuid.uuid4())
            connection.execute(
                f"INSERT INTO knowledge_bases ({repository.COLUMN_SQL}) VALUES ({','.join('?' for _ in columns)})",
                values,
            )
    return first


def test_empty_create_exact_dto_persistence_and_audit(kb):
    assert listing(kb).json() == {"success": True, "data": []}
    response = create(kb, name="\u0085　知识库 😀 内部  空白 ", description="  原样\n描述  ")
    assert response.status_code == 201 and response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"success", "data"} and response.json()["success"] is True
    item = response.json()["data"]
    assert uuid.UUID(item["id"]).version == 4
    expected_fields = {
        "id", "name", "type", "tenant_id", "creator_id", "embedding_model_id", "summary_model_id",
        "description", "is_temporary", "created_at", "updated_at", "deleted_at", "chunking_config",
        "image_processing_config", "vlm_config", "asr_config", "storage_config", "indexing_strategy",
        "extract_config", "faq_config", "question_generation_config", "auto_tag_config", "wiki_config",
        "storage_provider_config", "profile_config", "knowledge_count", "chunk_count", "is_processing",
        "processing_count", "share_count", "is_pinned", "pinned_at", "capabilities", "vector_store_source",
        "vector_store_status",
    }
    assert set(item) == expected_fields
    assert item["name"] == "知识库 😀 内部  空白" and item["description"] == "  原样\n描述  "
    assert item["creator_id"] == kb[3]["user"]["id"] and item["tenant_id"] == kb[3]["active_tenant"]["id"]
    assert item["embedding_model_id"] == item["summary_model_id"] == ""
    assert item["vector_store_source"] == item["vector_store_status"] == "unavailable"
    assert item["capabilities"] == {"vector": True, "keyword": True, "wiki": False, "graph": False, "faq": False}
    assert item["storage_provider_config"] == {"provider": "local"}
    for key, value in DEFAULT_CONFIGS.items():
        assert item["storage_config" if key == "cos_config" else key] == value
    for key in ("extract_config", "faq_config", "question_generation_config", "auto_tag_config", "wiki_config",
                "profile_config", "pinned_at", "deleted_at"):
        assert item[key] is None
    for key in ("knowledge_count", "chunk_count", "processing_count", "share_count"):
        assert item[key] == 0
    assert item["is_processing"] is item["is_temporary"] is item["is_pinned"] is False
    assert item["created_at"].endswith("Z") and item["created_at"] == item["updated_at"]
    assert sql(kb[2], "SELECT embedding_model_id, summary_model_id, creator_id FROM knowledge_bases") == [
        ("", "", kb[3]["user"]["id"])]
    result = listing(kb)
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert result.json()["data"] == [{**item, "creator_name": kb[3]["user"]["username"]}]
    assert sql(kb[2], "SELECT action, actor_user_id, actor_role, target_id, scope_id FROM audit_logs") == [
        ("kb.created", item["creator_id"], "owner", item["id"], item["id"])]
    assert "profile_config" not in {row[1] for row in sql(kb[2], "PRAGMA table_info(knowledge_bases)")}
    # Duplicate names intentionally have no invented uniqueness/idempotency contract.
    assert create(kb, name=item["name"]).status_code == 201


@pytest.mark.parametrize("body", [
    {}, {"name": ""}, {"name": " \u0085　  "}, {"name": "😀" * 256},
    {"name": 1}, {"name": None}, {"name": True}, {"name": "ok", "description": None},
    {"name": "ok", "description": "😀" * 4001}, {"name": "ok", "type": "faq"},
    {"name": "ok", "type": "wiki"}, {"name": "ok", "embedding_model_id": "model"},
    {"name": "ok", "summary_model_id": None},
    *[{"name": "ok", field: None} for field in (
        "id", "tenant_id", "creator_id", "created_at", "deleted_at", "knowledge_count", "capabilities",
        "chunking_config", "storage_backend_id", "vector_store_id", "profile_config", "is_temporary")],
])
def test_strict_request_rejected_without_write(kb, body):
    error(kb[0].post(PATH, headers=kb[4], json=body), 400, 1000)
    assert sql(kb[2], "SELECT COUNT(*) FROM knowledge_bases") == [(0,)]


@pytest.mark.parametrize("raw", [
    b'[]', b'null', b'1', b'{"name":"a","name":"b"}', b'{"name":"x"}{}',
    b'{"name":NaN}', b'{"name":"\\ud800"}', b'{"name":"\xff"}',
    b'{"name":' + b'[' * 1200 + b'0' + b']' * 1200 + b'}', b'x' * (1024 * 1024 + 1),
])
def test_strict_raw_json_and_body_bound(kb, raw):
    response = kb[0].post(PATH, headers={**kb[4], "Content-Type": "application/json"}, content=raw)
    error(response, 400, 1000)
    assert sql(kb[2], "SELECT COUNT(*) FROM knowledge_bases") == [(0,)]


def test_unicode_boundaries_empty_type_and_content_type(kb):
    response = create(kb, name="😀" * 255, description="😀" * 4000, type="", embedding_model_id="")
    assert response.status_code == 201 and response.json()["data"]["type"] == "document"
    assert create(kb, name="﻿").json()["data"]["name"] == "﻿"
    error(kb[0].post(PATH, headers={**kb[4], "Content-Type": "text/plain"}, content='{"name":"a"}'), 400, 1000)


@pytest.mark.parametrize("query", ["?page=1", "?creator=all&creator=mine", "?limit=1", "?agent_id=x", "?x=y"])
def test_query_whitelist(kb, query):
    error(listing(kb, query), 400, 1000)
    error(kb[0].post(PATH + query, headers=kb[4], json={"name": "x"}), 400, 1000)


@pytest.mark.parametrize("role", ["owner", "admin", "contributor", "viewer"])
def test_role_matrix_and_non_admin_owner(kb, role):
    sql(kb[2], "UPDATE tenant_members SET role = ?", (role,))
    assert listing(kb).status_code == 200
    response = create(kb)
    if role == "viewer":
        error(response, 403, 1002)
        assert sql(kb[2], "SELECT COUNT(*) FROM knowledge_bases") == [(0,)]
    else:
        assert response.status_code == 201
    assert kb[3]["user"]["is_system_admin"] is False


@pytest.mark.parametrize("mutation", ["missing", "invalid", "revoked", "expired", "member", "tenant", "header"])
def test_auth_and_tenant_reject_both_methods(kb, mutation):
    headers, status, code = dict(kb[4]), 401, 1001
    if mutation == "missing":
        headers = {}
    elif mutation == "invalid":
        headers = bearer("invalid")
    elif mutation == "revoked":
        sql(kb[2], "UPDATE auth_tokens SET is_revoked = 1")
    elif mutation == "expired":
        sql(kb[2], "UPDATE auth_tokens SET expires_at = '2000-01-01 00:00:00'")
    elif mutation == "member":
        sql(kb[2], "UPDATE tenant_members SET status = 'inactive'")
        status, code = 403, 1002
    elif mutation == "tenant":
        headers["X-Tenant-ID"] = str(kb[3]["active_tenant"]["id"] + 1)
        status, code = 403, 1002
    else:
        headers["X-Tenant-ID"] = "-1"
        status, code = 400, 1010
    for method in ("GET", "POST"):
        response = kb[0].request(method, PATH, headers=headers, **({"json": {"name": "x"}} if method == "POST" else {}))
        error(response, status, code)
    assert sql(kb[2], "SELECT COUNT(*) FROM knowledge_bases") == [(0,)]


def test_overlong_bearer_preserves_400_1010(kb):
    for method in ("GET", "POST"):
        response = kb[0].request(method, PATH, headers=bearer("x" * 4097),
                                 **({"json": {"name": "x"}} if method == "POST" else {}))
        error(response, 400, 1010)
        assert response.json()["error"]["message"] == "Authentication token is too long"
        assert "x" * 100 not in response.text


def test_bearer_limit_counts_utf8_bytes_not_characters(kb):
    from starlette.requests import Request

    from app.api.routes.auth import bearer as parse_bearer
    from app.domain.auth import AuthFailure

    # ASGI header bytes are latin-1 decoded by Starlette; the parser then bounds UTF-8 bytes.
    request = Request({"type": "http", "headers": [(b"authorization", b"Bearer " + b"\xe9" * 2049)]})
    with pytest.raises(AuthFailure) as caught:
        parse_bearer(request)
    assert (caught.value.status, caught.value.code, caught.value.message) == (
        400, 1010, "Authentication token is too long")


def test_cross_user_spaces_are_isolated(kb):
    created = create(kb).json()["data"]
    fields = {"username": "Other", "email": "other@example.com", "password": "Isolated-test-8"}
    assert kb[0].post("/api/v1/auth/register", json=fields).status_code == 201
    login = kb[0].post("/api/v1/auth/login", json={key: fields[key] for key in ("email", "password")}).json()
    assert kb[0].get(PATH, headers=bearer(login["token"])).json()["data"] == []
    error(kb[0].get(PATH, headers={**bearer(login["token"]), "X-Tenant-ID": str(created["tenant_id"])}), 403, 1002)
    assert listing(kb).json()["data"][0]["id"] == created["id"]


@pytest.mark.parametrize("branch", ["local", "minio", "cos", "tos", "s3", "oss", "ks3", "obs"])
@pytest.mark.parametrize("bad", [5, [], "broken"])
def test_cr003_branch_shape_rejected_before_insert(kb, monkeypatch, branch, bad):
    raw = json.dumps({branch: bad})
    sql(kb[2], "UPDATE tenants SET storage_engine_config = ?", (raw,))
    called = []
    monkeypatch.setattr(repository, "insert_knowledge_base", lambda *args: called.append(True))
    error(create(kb), 500, 1007)
    assert called == [] and sql(kb[2], "SELECT COUNT(*) FROM knowledge_bases") == [(0,)]
    assert sql(kb[2], "SELECT storage_engine_config FROM tenants") == [(raw,)]


STORAGE_FIELDS = [
    (provider, field, "wrong" if boolean else False)
    for boolean, mapping in ((False, repository._STORAGE_STRING_FIELDS), (True, repository._STORAGE_BOOL_FIELDS))
    for provider, fields in mapping.items() for field in fields
]


@pytest.mark.parametrize("branch,field,bad", STORAGE_FIELDS)
def test_cr003_known_storage_field_types(kb, branch, field, bad):
    sql(kb[2], "UPDATE tenants SET storage_engine_config = ?", (json.dumps({branch: {field: bad}}),))
    error(create(kb), 500, 1007)
    assert sql(kb[2], "SELECT COUNT(*) FROM knowledge_bases") == [(0,)]


@pytest.mark.parametrize("raw", ["{", "[]", '"scalar"', '{"default_provider":null}', '{"default_provider":5}'])
def test_storage_top_level_corruption(kb, raw):
    sql(kb[2], "UPDATE tenants SET storage_engine_config = ?", (raw,))
    error(create(kb), 500, 1007)


@pytest.mark.parametrize("default", [None, {}, {"default_provider": "s3"}, {"local": None},
                                    {"s3": {"secret_key": "generated-test-only", "use_ssl": True}}])
def test_storage_valid_metadata_no_secret_projection(kb, default):
    sql(kb[2], "UPDATE tenants SET storage_engine_config = ?", (json.dumps(default) if default is not None else None,))
    with sqlite3.connect(kb[2]) as connection:
        connection.row_factory = sqlite3.Row
        metadata = repository.load_storage_metadata(connection, kb[3]["active_tenant"]["id"])
    assert set(metadata) == {"default_storage_backend_id", "valid", "nested_types_valid", "shape", "provider_type", "default_provider"}
    assert "generated-test-only" not in json.dumps(metadata)
    response = create(kb)
    assert response.status_code == 201 and "generated-test-only" not in response.text
    assert response.json()["data"]["storage_provider_config"] == {"provider": "s3" if default == {"default_provider": "s3"} else "local"}


@pytest.mark.parametrize("alias,status,foreign,deleted,allowed", [
    (False, "active", False, False, True), (True, "active", False, False, True),
    (False, "disabled", False, False, True), (True, "disabled", False, False, True),
    (False, "active", True, False, True), (False, "active", False, True, True),
    (False, "active", False, False, False),
])
def test_storage_default_alias_metadata_and_rejections(kb, monkeypatch, alias, status, foreign, deleted, allowed):
    tenant = kb[3]["active_tenant"]["id"]
    sql(kb[2], "INSERT INTO storage_backends (id, tenant_id, name, provider, config, status, legacy_alias, deleted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("owned-backend", tenant + 1 if foreign else tenant, "test", "local", '{"secret":"not-projected"}',
         status, int(alias), "2020-01-01" if deleted else None))
    if not alias:
        sql(kb[2], "UPDATE tenants SET default_storage_backend_id = ?", ("owned-backend",))
    if not allowed:
        monkeypatch.setenv("STORAGE_ALLOW_LIST", "s3")
    response = create(kb)
    if status != "active" or foreign or deleted or not allowed:
        error(response, 400, 1000)
        assert sql(kb[2], "SELECT COUNT(*) FROM knowledge_bases") == [(0,)]
    else:
        assert response.status_code == 201 and response.json()["data"]["storage_backend_id"] == "owned-backend"
    assert "not-projected" not in response.text


NULLABLE_EXTENSIONS = [
    ("image_processing_config", {"image_pipeline_params": None}, {"image_pipeline_params": 7}),
    ("image_processing_config", {"image_actions": None}, {"image_actions": 7}),
    ("chunking_config", {"parser_engine_rules": [{"file_types": None}]}, {"parser_engine_rules": [{"file_types": 7}]}),
    ("chunking_config", {"parser_engine_rules": [{"xlsx_first_row_as_header": None}]},
     {"parser_engine_rules": [{"xlsx_first_row_as_header": 7}]}),
    ("extract_config", {"nodes": [None]}, {"nodes": [7]}),
    ("extract_config", {"nodes": [{"chunks": None, "attributes": None}]}, {"nodes": [{"chunks": 7}]}),
    ("extract_config", {"relations": [None]}, {"relations": [7]}),
    ("auto_tag_config", {"skip_if_tagged": None}, {"skip_if_tagged": 7}),
    ("wiki_config", {"auto_generate": None}, {"auto_generate": 7}),
]


@pytest.mark.parametrize("column,valid,bad", NULLABLE_EXTENSIONS)
@pytest.mark.parametrize("corrupt", [False, True])
def test_cr002_valid_nullable_extension_503_vs_wrong_scalar_500(kb, column, valid, bad, corrupt):
    identifier = create(kb).json()["data"]["id"]
    config = {**deepcopy(DEFAULT_CONFIGS.get(column, {})), **(bad if corrupt else valid)}
    raw = json.dumps(config)
    sql(kb[2], f"UPDATE knowledge_bases SET {column} = ? WHERE id = ?", (raw, identifier))
    error(listing(kb), 500 if corrupt else 503, 1007 if corrupt else 1008)
    assert sql(kb[2], f"SELECT {column} FROM knowledge_bases WHERE id = ?", (identifier,)) == [(raw,)]


@pytest.mark.parametrize("column,value,status,code", [
    ("chunking_config", "{", 500, 1007), ("vlm_config", "[]", 500, 1007),
    ("asr_config", '{"enabled":1}', 500, 1007), ("embedding_model_id", "real-model", 503, 1008),
    ("type", "faq", 503, 1008), ("chunking_config", '{"chunk_size":100}', 503, 1008),
])
def test_stored_config_failure_classification(kb, column, value, status, code):
    create(kb)
    sql(kb[2], f"UPDATE knowledge_bases SET {column} = ?", (value,))
    error(listing(kb), status, code)


def test_cr001_nullable_creator_filters_and_stable_order(kb):
    seed(kb, 4)
    ids = [row[0] for row in sql(kb[2], "SELECT id FROM knowledge_bases ORDER BY id DESC")]
    creators = [None, "", kb[3]["user"]["id"], "other-user"]
    for identifier, creator in zip(ids, creators, strict=True):
        sql(kb[2], "UPDATE knowledge_bases SET creator_id = ? WHERE id = ?", (creator, identifier))
    all_items = listing(kb, "?creator=all").json()["data"]
    assert [row["id"] for row in all_items] == ids
    assert [row["creator_id"] for row in all_items] == ["", "", creators[2], "other-user"]
    assert [row["id"] for row in listing(kb, "?creator=%20MINE%20").json()["data"]] == [ids[2]]
    assert [row["id"] for row in listing(kb, "?creator=others").json()["data"]] == [ids[3]]
    assert listing(kb, "?creator=unknown").json()["data"] == all_items
    assert sql(kb[2], "SELECT creator_id FROM knowledge_bases WHERE id = ?", (ids[0],)) == [(None,)]


def test_capacity_race_99_then_full_and_overfull_list(kb):
    first = seed(kb, 99)
    barrier = Barrier(2)

    def concurrent_create(number):
        barrier.wait()
        return create(kb, name=f"race-{number}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(concurrent_create, [1, 2]))
    assert sorted(response.status_code for response in responses) == [201, 400]
    assert sql(kb[2], "SELECT COUNT(*) FROM knowledge_bases") == [(100,)]
    assert len(listing(kb).json()["data"]) == 100
    error(create(kb), 400, 1000)
    row = sql(kb[2], f"SELECT {repository.COLUMN_SQL} FROM knowledge_bases WHERE id = ?", (first,))[0]
    values = list(row)
    values[0] = str(uuid.uuid4())
    sql(kb[2], f"INSERT INTO knowledge_bases ({repository.COLUMN_SQL}) VALUES ({','.join('?' for _ in values)})", values)
    error(listing(kb), 503, 1008)
    error(listing(kb, "?creator=others"), 503, 1008)


def test_single_connection_snapshot_no_nplusone_and_index_plan(kb, monkeypatch):
    original = service.connect_auth_database
    traces, connections = [], []

    @contextmanager
    def spy(settings):
        with original(settings) as connection:
            connections.append(connection)
            connection.set_trace_callback(traces.append)
            yield connection

    monkeypatch.setattr(service, "connect_auth_database", spy)
    assert create(kb).status_code == 201
    assert len(connections) == 1
    assert "BEGIN IMMEDIATE" in traces and "COMMIT" in traces
    assert next(i for i, query in enumerate(traces) if "auth_tokens" in query) > traces.index("BEGIN IMMEDIATE")
    connections.clear()
    traces.clear()
    listing(kb)
    one_count = sum(query.startswith("SELECT") for query in traces)
    assert len(connections) == 1 and "BEGIN" in traces
    seed(kb, 4)
    connections.clear()
    traces.clear()
    listing(kb)
    assert len(connections) == 1 and sum(query.startswith("SELECT") for query in traces) == one_count
    assert all("SELECT *" not in query and "generated_profile" not in query for query in traces)
    assert any("LIMIT 101" in query for query in traces) and any("LIMIT 100" in query for query in traces)
    with sqlite3.connect(kb[2]) as connection:
        plan = connection.execute("EXPLAIN QUERY PLAN SELECT id FROM knowledge_bases WHERE "
                                  "tenant_id = ? AND deleted_at IS NULL AND is_temporary = 0 LIMIT 101",
                                  (kb[3]["active_tenant"]["id"],)).fetchall()
        assert any("INDEX" in row[3] and "tenant_id" in row[3] for row in plan)


@pytest.mark.parametrize("fault", ["insert", "read", "commit", "audit"])
def test_transaction_rollback_and_postcommit_audit_fault(kb, monkeypatch, fault):
    def fail(*args):
        raise sqlite3.IntegrityError("private-test-sentinel")

    if fault in ("insert", "read", "audit"):
        monkeypatch.setattr(repository, {"insert": "insert_knowledge_base", "read": "read_knowledge_base",
                                        "audit": "insert_activity"}[fault], fail)
    else:
        original = service.connect_auth_database

        class CommitFault:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, key):
                return getattr(self.connection, key)

            def commit(self):
                fail()

        @contextmanager
        def broken(settings):
            with original(settings) as connection:
                yield CommitFault(connection)

        monkeypatch.setattr(service, "connect_auth_database", broken)
    response = create(kb)
    if fault == "audit":
        assert response.status_code == 201
        assert sql(kb[2], "SELECT COUNT(*) FROM knowledge_bases") == [(1,)]
    else:
        error(response, 500, 1007)
        assert sql(kb[2], "SELECT COUNT(*) FROM knowledge_bases") == [(0,)]
    assert "private-test-sentinel" not in response.text
    assert sql(kb[2], "SELECT COUNT(*) FROM audit_logs") == [(0,)]


def test_batch_counts_personal_pins_deleted_temporary_and_parameter_binding(kb):
    seed(kb, 3)
    tenant, user = kb[3]["active_tenant"]["id"], kb[3]["user"]["id"]
    ids = [row[0] for row in sql(kb[2], "SELECT id FROM knowledge_bases ORDER BY id DESC")]
    for number, (status, deleted, foreign) in enumerate([
        ("pending", False, False), ("processing", False, False), ("processed", False, False),
        ("pending", True, False), ("pending", False, True),
    ]):
        sql(kb[2], "INSERT INTO knowledges (id,tenant_id,knowledge_base_id,type,title,source,parse_status,deleted_at) "
            "VALUES (?,?,?,?,?,?,?,?)", (f"doc-{number}", tenant + int(foreign), ids[0], "file", "owned", "test",
                                       status, "2020-01-01" if deleted else None))
        sql(kb[2], "INSERT INTO chunks (id,tenant_id,knowledge_base_id,knowledge_id,content,chunk_index,start_at,end_at,"
            "deleted_at) VALUES (?,?,?,?,?,?,?,?,?)", (f"chunk-{number}", tenant + int(foreign), ids[0],
                                                      f"doc-{number}", "test", 0, 0, 4,
                                                      "2020-01-01" if deleted else None))
        sql(kb[2], "INSERT INTO kb_shares (id,knowledge_base_id,organization_id,shared_by_user_id,source_tenant_id,"
            "deleted_at) VALUES (?,?,?,?,?,?)", (f"share-{number}", ids[0], "owned-org", user,
                                                tenant + int(foreign), "2020-01-01" if deleted else None))
    sql(kb[2], "INSERT INTO user_kb_pins (tenant_id,user_id,kb_id,pinned_at) VALUES (?,?,?,?)",
        (tenant, user, ids[1], "2020-01-01T00:00:00Z"))
    # A different user's pin never changes our order or DTO.
    sql(kb[2], "INSERT INTO user_kb_pins (tenant_id,user_id,kb_id,pinned_at) VALUES (?,?,?,?)",
        (tenant, "other-user", ids[0], "2030-01-01T00:00:00Z"))
    response = listing(kb)
    assert response.status_code == 200
    rows = response.json()["data"]
    assert [row["id"] for row in rows] == [ids[1], ids[0], ids[2]]
    assert rows[0]["is_pinned"] is True and rows[0]["pinned_at"] == "2020-01-01T00:00:00Z"
    assert rows[1]["is_pinned"] is False
    assert {key: rows[1][key] for key in ("knowledge_count", "chunk_count", "processing_count", "share_count")} == {
        "knowledge_count": 3, "chunk_count": 3, "processing_count": 2, "share_count": 3}
    assert rows[1]["is_processing"] is True
    sql(kb[2], "UPDATE knowledge_bases SET is_temporary = 1 WHERE id = ?", (ids[1],))
    sql(kb[2], "UPDATE knowledge_bases SET deleted_at = ? WHERE id = ?", ("2020-01-01", ids[2]))
    assert [row["id"] for row in listing(kb).json()["data"]] == [ids[0]]
    injection = "x'); DROP TABLE knowledge_bases;--"
    assert create(kb, name=injection).json()["data"]["name"] == injection
    assert sql(kb[2], "SELECT COUNT(*) FROM knowledge_bases") == [(4,)]


def test_nine_migration_assets_unchanged_from_head():
    root = Path(__file__).resolve().parents[4]
    manifest = json.loads((migrations.MIGRATION_ROOT / "manifest.json").read_text())
    assets = [migrations.MIGRATION_ROOT / "manifest.json", *[
        migrations.MIGRATION_ROOT / entry["file"] for entry in manifest["migrations"]]]
    assert len(assets) == 9
    for asset in assets:
        relative = asset.relative_to(root)
        original = subprocess.check_output(["git", "show", f"HEAD:refactor/{relative}"], cwd=root)
        assert asset.read_bytes() == original


def test_cr001_real_api_to_frontend_adapter(kb):
    create(kb)
    sql(kb[2], "UPDATE knowledge_bases SET creator_id = NULL")
    data = listing(kb).json()
    frontend = Path(__file__).resolve().parents[3] / "frontend"
    script = r"""
import fs from 'node:fs';
import ts from 'typescript';
let input = ''; for await (const chunk of process.stdin) input += chunk;
const body = JSON.parse(input);
class ApiError extends Error { constructor(message,status=0,code=0,kind='http') {
    super(message); Object.assign(this,{status,code,kind}); } }
const source = fs.readFileSync('src/api/knowledge-bases.ts','utf8');
const compiled = ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,
    module:ts.ModuleKind.ES2022}}).outputText.replace(/^import .*from '\.\/client';\n/m,'');
const module = await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'));
"""
    # A tiny generated dependency exports actual client symbols while keeping transport isolated.
    script = script.replace("class ApiError extends Error", "globalThis.ApiError = class ApiError extends Error")
    script = script.replace("const source =", "globalThis.isRecord = v => !!v && typeof v === 'object' && !Array.isArray(v); "
                            "globalThis.requestJson = async () => body; const source =")
    script += "\nif ((await module.fetchKnowledgeBases('all'))[0].creator_id !== '') throw Error('creator'); "
    script += "body.data[0].creator_id=null; let rejected=false; "
    script += "try { await module.fetchKnowledgeBases('all'); } catch(e) { rejected=e.kind==='contract'; } "
    script += "if (!rejected) throw Error('null accepted'); console.log('real DTO accepted; wire null rejected');"
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=frontend,
                            input=json.dumps(data), capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert sql(kb[2], "SELECT creator_id FROM knowledge_bases") == [(None,)]


def test_health_framework_contracts_unchanged(kb):
    assert kb[0].get("/health").json() == {"status": "ok"}
    assert kb[0].get("/api/v1/knowledge-bases/not-delivered").status_code == 404
    response = kb[0].delete(PATH)
    assert response.status_code == 405 and "allow" in response.headers
