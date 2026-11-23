"""Isolated auth contracts, storage faults, boundaries and transaction races."""

import hashlib
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from threading import Barrier

import bcrypt
import jwt
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core import migrations
from app.core.auth_limits import AuthRequestLimits
from app.core.config import AuthSettings, load_secret
from app.core.database import connect_auth_database
from app.core.security import timestamp
from app.domain.auth import AuthFailure
from app.main import create_app

PASSWORD = "Isolated-test-8"
FIELDS = {"username": "Auth Test", "email": "auth-test@example.com", "password": PASSWORD}
USER_FIELDS = {
    "id",
    "username",
    "email",
    "avatar",
    "tenant_id",
    "is_active",
    "can_access_all_tenants",
    "is_system_admin",
    "preferences",
    "created_at",
    "updated_at",
    "deleted_at",
}
TENANT_FIELDS = {
    "id",
    "name",
    "description",
    "status",
    "retriever_engines",
    "business",
    "storage_quota",
    "storage_used",
    "created_at",
    "updated_at",
    "deleted_at",
}


@pytest.fixture
def auth(tmp_path):
    path = tmp_path.resolve() / "auth.sqlite3"
    migrations.initialize_auth_database(path)
    app = create_app(auth_settings=AuthSettings(path))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, app, path


def sql(path, statement, parameters=()):
    with sqlite3.connect(path) as connection:
        return connection.execute(statement, parameters).fetchall()


def error(response, status, code):
    assert response.status_code == status
    data = response.json()
    assert set(data) == {"success", "error"} and data["success"] is False
    assert set(data["error"]) == {"code", "message", "details"}
    assert data["error"]["code"] == code and data["error"]["details"] is None
    assert response.headers["cache-control"] == "no-store"
    assert not any(value in response.text for value in (PASSWORD, "password_hash", "Traceback", "/Users/"))


def register_login(auth):
    client, _, _ = auth
    assert client.post("/api/v1/auth/register", json=FIELDS).status_code == 201
    response = client.post("/api/v1/auth/login", json={"email": FIELDS["email"], "password": PASSWORD})
    assert response.status_code == 200
    return response.json()


def bearer(raw):
    return {"Authorization": f"Bearer {raw}"}


def test_migration_prefix_original_schema_defaults_indexes_and_private_files(auth):
    _, _, path = auth
    root = Path(__file__).resolve().parents[5] / "migrations/sqlite"
    manifest = json.loads((migrations.MIGRATION_ROOT / "manifest.json").read_text())
    assert [entry["version"] for entry in manifest["migrations"]] == list(range(8))
    reference = sqlite3.connect(":memory:")
    try:
        for entry in manifest["migrations"]:
            data = (migrations.MIGRATION_ROOT / entry["file"]).read_bytes()
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]
            assert data == (root / entry["file"]).read_bytes()
            reference.executescript(data.decode())
        for table in ("users", "tenants", "tenant_members", "auth_tokens"):
            assert (
                sql(path, f"PRAGMA table_info({table})")
                == reference.execute(f"PRAGMA table_info({table})").fetchall()
            )
            assert (
                sql(path, f"PRAGMA index_list({table})")
                == reference.execute(f"PRAGMA index_list({table})").fetchall()
            )
    finally:
        reference.close()
    assert sql(path, "SELECT profile FROM _python_auth_schema") == [("auth-sqlite-prefix-v7",)]
    assert path.stat().st_mode & 0o777 == 0o600
    assert Path(f"{path}.jwt-secret").stat().st_mode & 0o777 == 0o600


def test_initializer_refuses_overwrite_and_secret_collision(auth, tmp_path):
    _, _, path = auth
    before = path.read_bytes()
    secret_path = Path(f"{path}.jwt-secret")
    secret_digest = hashlib.sha256(secret_path.read_bytes()).digest()
    with pytest.raises(ValueError):
        migrations.initialize_auth_database(path)
    assert path.read_bytes() == before
    assert hashlib.sha256(secret_path.read_bytes()).digest() == secret_digest
    fresh = tmp_path.resolve() / "collision.sqlite3"
    Path(f"{fresh}.jwt-secret").write_text("owned sentinel")
    with pytest.raises(ValueError):
        migrations.initialize_auth_database(fresh)
    assert not fresh.exists()
    assert Path(f"{fresh}.jwt-secret").read_text() == "owned sentinel"


def test_initializer_failed_migration_cleans_only_owned_files(tmp_path, monkeypatch):
    path = tmp_path.resolve() / "failure.sqlite3"
    monkeypatch.setattr(migrations, "verify_migration_manifest", lambda: ("test", ["INVALID SQL;"]))
    with pytest.raises(sqlite3.Error):
        migrations.initialize_auth_database(path)
    assert not path.exists() and not Path(f"{path}.jwt-secret").exists()


def test_initializer_rejects_relative_and_symlink(tmp_path):
    with pytest.raises(ValueError):
        migrations.initialize_auth_database(Path("relative.sqlite3"))
    target = tmp_path.resolve() / "target"
    target.mkdir()
    link = tmp_path.resolve() / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        migrations.initialize_auth_database(link / "auth.sqlite3")
    assert not list(target.iterdir())


@pytest.mark.parametrize("mutation", ["profile", "checksum", "missing"])
def test_unknown_database_profile_is_503_not_auth_failure(auth, mutation):
    client, _, path = auth
    if mutation == "missing":
        sql(path, "DROP TABLE _python_auth_schema")
    else:
        column = {"profile": "profile", "checksum": "manifest_sha256"}[mutation]
        sql(path, f"UPDATE _python_auth_schema SET {column} = ?", ("unsupported",))
    error(client.post("/api/v1/auth/register", json=FIELDS), 503, 1008)
    assert client.get("/health").json() == {"status": "ok"}


def test_five_route_exact_dtos_persisted_identity_and_hash(auth):
    client, _, path = auth
    response = client.post("/api/v1/auth/register", json=FIELDS)
    assert response.status_code == 201
    registration = response.json()
    assert set(registration) == {"success", "message", "user"}
    assert registration["message"] == "Registration successful"
    user = registration["user"]
    assert set(user) == USER_FIELDS and user["deleted_at"] is None
    assert user["preferences"] == {} and not user["is_system_admin"] and not user["can_access_all_tenants"]
    assert user["created_at"].endswith("Z") and user["updated_at"].endswith("Z")
    for table in ("users", "tenants", "tenant_members"):
        assert sql(path, f"SELECT COUNT(*) FROM {table}") == [(1,)]
    hashed = sql(path, "SELECT password_hash FROM users")[0][0]
    assert hashed.startswith("$2b$10$") and bcrypt.checkpw(PASSWORD.encode(), hashed.encode())
    assert PASSWORD.encode() not in path.read_bytes()
    assert sql(path, "SELECT role, status FROM tenant_members") == [("owner", "active")]
    login = client.post("/api/v1/auth/login", json={"email": FIELDS["email"], "password": PASSWORD})
    assert login.status_code == 200
    data = login.json()
    assert set(data) == {
        "success",
        "message",
        "user",
        "active_tenant",
        "memberships",
        "token",
        "refresh_token",
    }
    assert data["message"] == "Login successful"
    assert set(data["active_tenant"]) == TENANT_FIELDS
    assert data["active_tenant"]["name"] == "Auth Test's Workspace"
    assert data["active_tenant"]["storage_quota"] == 10737418240
    assert data["active_tenant"]["storage_used"] == 0 and data["active_tenant"]["retriever_engines"] == []
    assert data["memberships"] == [
        {"tenant_id": user["tenant_id"], "tenant_name": "Auth Test's Workspace", "role": "owner"}
    ]
    current = client.get("/api/v1/auth/me", headers=bearer(data["token"]))
    assert current.status_code == 200 and set(current.json()) == {"success", "data"}
    identity = current.json()["data"]
    assert set(identity) == {
        "user",
        "tenant",
        "memberships",
        "preference_defaults",
        "tenant_required",
        "capabilities",
    }
    assert set(identity["user"]) == USER_FIELDS - {"deleted_at"}
    assert identity["tenant"] == data["active_tenant"] and identity["memberships"] == data["memberships"]
    assert identity["tenant_required"] is False
    assert identity["capabilities"] == {"can_create_tenant": False, "auto_accept_invitation": False}
    refresh = client.post("/api/v1/auth/refresh", json={"refreshToken": data["refresh_token"]})
    assert refresh.status_code == 200
    assert set(refresh.json()) == {"success", "message", "access_token", "refresh_token"}
    assert refresh.json()["message"] == "Token refreshed successfully"
    assert client.get("/api/v1/auth/me", headers=bearer(data["token"])).status_code == 200
    logout = client.post("/api/v1/auth/logout", headers=bearer(data["refresh_token"]))
    assert logout.json() == {"success": True, "message": "Logout successful"}
    for raw in (data["token"], refresh.json()["access_token"]):
        error(client.get("/api/v1/auth/me", headers=bearer(raw)), 401, 1001)
    assert sql(path, "SELECT COUNT(*) FROM auth_tokens WHERE is_revoked = 0") == [(0,)]


@pytest.mark.parametrize("table", ["tenants", "users", "tenant_members"])
def test_register_each_write_failure_rolls_back_every_entity(auth, table):
    client, _, path = auth
    sql(
        path,
        f"CREATE TRIGGER inject_failure BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT, 'test fault'); END",
    )
    error(client.post("/api/v1/auth/register", json=FIELDS), 500, 1007)
    for item in ("tenants", "users", "tenant_members"):
        assert sql(path, f"SELECT COUNT(*) FROM {item}") == [(0,)]


@pytest.mark.parametrize("field", ["email", "username"])
def test_duplicate_conflict_is_safe_and_atomic(auth, field):
    client, _, path = auth
    assert client.post("/api/v1/auth/register", json=FIELDS).status_code == 201
    fields = {**FIELDS, "username": "Another Test", "email": "another-test@example.com"}
    fields[field] = FIELDS[field]
    error(client.post("/api/v1/auth/register", json=fields), 400, 1000)
    assert sql(path, "SELECT COUNT(*) FROM tenants") == [(1,)]


def test_concurrent_duplicate_register_exactly_one_identity(auth):
    _, app, path = auth
    gate = Barrier(2)

    def register():
        gate.wait()
        try:
            app.state.auth_service.register(**FIELDS)
            return 201
        except AuthFailure as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: register(), range(2)))
    assert sorted(results) == [201, 400]
    for table in ("tenants", "users", "tenant_members"):
        assert sql(path, f"SELECT COUNT(*) FROM {table}") == [(1,)]


@pytest.mark.parametrize(
    "password,valid",
    [
        ("Aa123456", True),
        ("a1" + "界" * 22 + "éé", True),
        ("a1" + "界" * 23 + "é", False),
        ("a1" + "x" * 31, False),
        ("a123456", False),
        ("abcdefgh", False),
        ("12345678", False),
        ("éééééé12", False),
    ],
)
def test_password_unicode_character_and_bcrypt_byte_boundaries(auth, password, valid):
    client, _, path = auth
    response = client.post("/api/v1/auth/register", json={**FIELDS, "password": password})
    if valid:
        assert response.status_code == 201
        hashed = sql(path, "SELECT password_hash FROM users")[0][0]
        assert bcrypt.checkpw(password.encode(), hashed.encode())
    else:
        error(response, 400, 1010)
        assert sql(path, "SELECT COUNT(*) FROM users") == [(0,)]


@pytest.mark.parametrize(
    "fields",
    [
        {"username": " x"},
        {"username": "a"},
        {"username": "x" * 51},
        {"username": "x\u0000y"},
        {"email": " auth-test@example.com"},
        {"email": "not-an-email"},
        {"email": 12},
        {"extra": "rejected"},
    ],
)
def test_invalid_identifiers_and_strict_request_shape(auth, fields):
    error(auth[0].post("/api/v1/auth/register", json={**FIELDS, **fields}), 400, 1010)


def test_identifier_case_is_not_normalized_and_login_legacy_password(auth):
    client, _, path = auth
    upper = {**FIELDS, "username": "CaseName", "email": "CaseName@example.com"}
    assert client.post("/api/v1/auth/register", json=upper).json()["user"]["email"] == upper["email"]
    lower = {**upper, "username": "casename", "email": "casename@example.com"}
    assert client.post("/api/v1/auth/register", json=lower).status_code == 201
    old_password = "old123"
    sql(
        path,
        "UPDATE users SET password_hash = ? WHERE email = ?",
        (bcrypt.hashpw(old_password.encode(), bcrypt.gensalt(rounds=10)).decode(), upper["email"]),
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": upper["email"], "password": old_password}
        ).status_code
        == 200
    )


@pytest.mark.parametrize("mode", ["unknown", "password", "inactive", "deleted"])
def test_login_failure_exact_non_enumerating_dto(auth, mode):
    client, _, path = auth
    register_login(auth)
    email, password = FIELDS["email"], PASSWORD
    if mode == "unknown":
        email = "unknown-test@example.com"
    elif mode == "password":
        password = "wrong-test-8"
    elif mode == "inactive":
        sql(path, "UPDATE users SET is_active = 0")
    else:
        sql(path, "UPDATE users SET deleted_at = ?", (timestamp(),))
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401
    assert response.json() == {"success": False, "message": "Invalid email or password", "memberships": []}


@pytest.mark.parametrize(
    "table,change,status",
    [
        ("users", "is_active = 0", 401),
        ("users", "deleted_at = CURRENT_TIMESTAMP", 401),
        ("tenants", "status = 'inactive'", 403),
        ("tenants", "deleted_at = CURRENT_TIMESTAMP", 403),
        ("tenant_members", "status = 'inactive'", 403),
        ("tenant_members", "deleted_at = CURRENT_TIMESTAMP", 403),
        ("tenant_members", "role = 'untrusted'", 403),
        ("tenant_members", None, 403),
    ],
)
def test_me_and_refresh_revalidate_true_identity(auth, table, change, status):
    client, _, _ = auth
    data = register_login(auth)
    sql(auth[2], f"UPDATE {table} SET {change}" if change else f"DELETE FROM {table}")
    error(
        client.get("/api/v1/auth/me", headers=bearer(data["token"])), status, 1001 if status == 401 else 1002
    )
    error(
        client.post("/api/v1/auth/refresh", json={"refreshToken": data["refresh_token"]}),
        status,
        1001 if status == 401 else 1002,
    )
    assert sql(auth[2], "SELECT is_revoked FROM auth_tokens WHERE token = ?", (data["refresh_token"],)) == [
        (0,)
    ]


@pytest.mark.parametrize("header,status", [("999", 403), ("0", 400), ("-1", 400), ("abc", 400), ("1.0", 400)])
def test_tenant_header_cannot_switch_or_spoof_identity(auth, header, status):
    data = register_login(auth)
    error(
        auth[0].get("/api/v1/auth/me", headers={**bearer(data["token"]), "X-Tenant-ID": header}),
        status,
        1002 if status == 403 else 1010,
    )


@pytest.mark.parametrize("mode", ["missing", "forged", "expired", "type", "unknown", "revoked", "algorithm"])
def test_me_token_signature_expiry_type_and_database_record(auth, mode):
    client, app, path = auth
    data = register_login(auth)
    raw = data["token"]
    claims = jwt.decode(raw, app.state.auth_service.secret, algorithms=["HS256"])
    if mode == "missing":
        raw = ""
    elif mode == "forged":
        raw = jwt.encode(claims, "untrusted-test-secret" * 3, algorithm="HS256")
    elif mode == "expired":
        claims.update(iat=int(time.time()) - 20, exp=int(time.time()) - 10)
        raw = jwt.encode(claims, app.state.auth_service.secret, algorithm="HS256")
    elif mode == "type":
        raw = data["refresh_token"]
    elif mode == "unknown":
        claims["jti"] = "unknown-test-record"
        raw = jwt.encode(claims, app.state.auth_service.secret, algorithm="HS256")
    elif mode == "revoked":
        sql(path, "UPDATE auth_tokens SET is_revoked = 1")
    else:
        raw = jwt.encode(claims, app.state.auth_service.secret, algorithm="HS384")
    error(client.get("/api/v1/auth/me", headers=bearer(raw) if raw else {}), 401, 1001)


def test_refresh_request_case_type_and_logout_bearer_contract(auth):
    client, _, _ = auth
    data = register_login(auth)
    error(client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]}), 400, 1010)
    error(client.post("/api/v1/auth/refresh", json={"refreshToken": data["token"]}), 401, 1001)
    error(client.post("/api/v1/auth/refresh", json={"refreshToken": "x" * 4097}), 400, 1010)
    error(client.get("/api/v1/auth/me", headers=bearer("x" * 4097)), 400, 1010)
    error(client.post("/api/v1/auth/logout"), 400, 1010)
    error(client.post("/api/v1/auth/logout", headers=bearer("untrusted")), 401, 1001)


def test_refresh_cas_concurrent_unique_winner(auth):
    data = register_login(auth)
    service = auth[1].state.auth_service
    gate = Barrier(4)

    def refresh():
        gate.wait()
        try:
            return service.refresh(data["refresh_token"])
        except AuthFailure as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: refresh(), range(4)))
    winners = [result for result in results if isinstance(result, list)]
    assert len(winners) == 1 and results.count(401) == 3
    assert len({record["token"] for record in winners[0]}) == 2
    assert sql(auth[2], "SELECT COUNT(*) FROM auth_tokens") == [(4,)]


@pytest.mark.parametrize("kind", ["access_token", "refresh_token"])
def test_refresh_insert_failure_rolls_back_cas_and_partial_pair(auth, kind):
    data = register_login(auth)
    client, _, path = auth
    sql(
        path,
        "CREATE TRIGGER token_fault BEFORE INSERT ON auth_tokens WHEN NEW.token_type = '"
        + kind
        + "' BEGIN SELECT RAISE(ABORT, 'test fault'); END",
    )
    error(client.post("/api/v1/auth/refresh", json={"refreshToken": data["refresh_token"]}), 500, 1007)
    assert sql(path, "SELECT COUNT(*) FROM auth_tokens") == [(2,)]
    assert sql(path, "SELECT is_revoked FROM auth_tokens WHERE token = ?", (data["refresh_token"],)) == [(0,)]
    sql(path, "DROP TRIGGER token_fault")
    assert (
        client.post("/api/v1/auth/refresh", json={"refreshToken": data["refresh_token"]}).status_code == 200
    )


@pytest.mark.parametrize("iteration", range(3))
def test_logout_vs_refresh_never_leaves_new_usable_pair(auth, iteration):
    data = register_login(auth)
    service = auth[1].state.auth_service
    gate = Barrier(2)

    def operation(refresh):
        gate.wait()
        try:
            return (
                service.refresh(data["refresh_token"]) if refresh else service.logout(data["refresh_token"])
            )
        except AuthFailure as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(operation, (True, False)))
    assert results[1] is None
    assert sql(auth[2], "SELECT COUNT(*) FROM auth_tokens WHERE is_revoked = 0") == [(0,)]
    if isinstance(results[0], list):
        error(auth[0].get("/api/v1/auth/me", headers=bearer(results[0][0]["token"])), 401, 1001)


def test_known_expired_token_logout_is_idempotent_and_all_sessions(auth):
    data = register_login(auth)
    client, app, path = auth
    assert (
        client.post("/api/v1/auth/login", json={"email": FIELDS["email"], "password": PASSWORD}).status_code
        == 200
    )
    claims = jwt.decode(data["refresh_token"], app.state.auth_service.secret, algorithms=["HS256"])
    claims.update(iat=int(time.time()) - 20, exp=int(time.time()) - 10)
    expired = jwt.encode(claims, app.state.auth_service.secret, algorithm="HS256")
    sql(
        path,
        "UPDATE auth_tokens SET token = ?, expires_at = ? WHERE token = ?",
        (expired, timestamp(claims["exp"]), data["refresh_token"]),
    )
    for _ in range(2):
        assert client.post("/api/v1/auth/logout", headers=bearer(expired)).status_code == 200
    assert sql(path, "SELECT COUNT(*) FROM auth_tokens WHERE is_revoked = 0") == [(0,)]


def test_database_failure_is_500_not_401_and_logs_safe(auth, caplog):
    data = register_login(auth)
    sql(auth[2], "DROP TABLE auth_tokens")
    error(auth[0].get("/api/v1/auth/me", headers=bearer(data["token"])), 500, 1007)
    assert not any(value in caplog.text for value in (PASSWORD, data["token"], str(auth[2]), "password_hash"))


def test_fresh_app_uses_same_persistent_secret_and_credentials(auth):
    data = register_login(auth)
    _, app, path = auth
    fresh = create_app(auth_settings=AuthSettings(path))
    assert fresh.state.auth_service.secret == app.state.auth_service.secret
    with TestClient(fresh) as client:
        assert client.get("/api/v1/auth/me", headers=bearer(data["token"])).status_code == 200
        assert (
            client.post(
                "/api/v1/auth/login", json={"email": FIELDS["email"], "password": PASSWORD}
            ).status_code
            == 200
        )


@pytest.mark.parametrize("mode", ["missing", "short-secret", "public-secret"])
def test_unavailable_config_does_not_break_health(tmp_path, mode):
    path = tmp_path.resolve() / "isolated.sqlite3"
    if mode != "missing":
        migrations.initialize_auth_database(path)
    if mode == "public-secret":
        Path(f"{path}.jwt-secret").chmod(0o644)
    settings = AuthSettings(path, "short" if mode == "short-secret" else None)
    with TestClient(create_app(auth_settings=settings)) as client:
        error(
            client.post("/api/v1/auth/login", json={"email": FIELDS["email"], "password": PASSWORD}),
            503,
            1008,
        )
        assert client.get("/health").json() == {"status": "ok"}
    if mode == "missing":
        assert not path.exists()


@pytest.mark.parametrize("size,status", [(8192, 400), (8193, 413)])
def test_body_limit_is_streamed_independent_of_content_length(auth, size, status):
    def body():
        yield b" " * 4000
        yield b" " * (size - 4000)

    response = auth[0].post(
        "/api/v1/auth/login", content=body(), headers={"Content-Type": "application/json"}
    )
    error(response, status, 1010)


@pytest.mark.parametrize("body", [b'{"email":"\xff"}', b"[" * 4000 + b"]" * 4000, b"{"])
def test_invalid_utf8_natural_depth_and_invalid_json_are_safe(auth, body):
    error(
        auth[0].post("/api/v1/auth/login", content=body, headers={"Content-Type": "application/json"}),
        400,
        1010,
    )


def test_controlled_parser_recursion_normalized_auth_only(auth, monkeypatch):
    async def recursive_json(self):
        raise RecursionError("unsafe input sentinel")

    monkeypatch.setattr(Request, "json", recursive_json)
    client = auth[0]
    for operation in ("register", "login", "refresh"):
        error(client.post(f"/api/v1/auth/{operation}", json={}), 400, 1010)
    assert client.get("/missing").json() == {"detail": "Not Found"}
    response = client.post("/health", json={})
    assert response.status_code == 405 and response.headers["allow"] == "GET"
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("operation,limit", [("register", 5), ("login", 10), ("refresh", 60)])
def test_rate_threshold_retry_and_expiry(operation, limit, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.core.auth_limits.time.monotonic", lambda: clock[0])
    limits = AuthRequestLimits()
    for _ in range(limit):
        limits.check_rate("test-peer", operation)
    with pytest.raises(AuthFailure) as caught:
        limits.check_rate("test-peer", operation)
    assert caught.value.status == 429 and caught.value.code == 1006
    clock[0] += 61
    limits.check_rate("test-peer", operation)
    for index in range(1100):
        limits.check_rate(f"test-{index}", operation)
    assert len(limits.buckets) == 1024


def test_hash_capacity_nonblocking_four_slots_and_release():
    limits = AuthRequestLimits()
    with ExitStack() as stack:
        for _ in range(4):
            stack.enter_context(limits.password_slot())
        with pytest.raises(AuthFailure) as caught, limits.password_slot():
            pytest.fail("Fifth password computation was admitted")
        assert caught.value.status == 429
    with limits.password_slot():
        pass


def test_real_hash_slot_saturation_returns_api_429_and_retry_after(auth):
    with ExitStack() as stack:
        for _ in range(4):
            stack.enter_context(auth[1].state.auth_limits.password_slot())
        response = auth[0].post("/api/v1/auth/register", json=FIELDS)
        error(response, 429, 1006)
        assert response.headers["retry-after"] == "60"


@pytest.mark.parametrize("mismatch", ["user", "type", "expiry", "duplicate"])
def test_token_record_must_match_signed_claims(auth, mismatch):
    data = register_login(auth)
    client, _, path = auth
    if mismatch == "user":
        sql(path, "UPDATE auth_tokens SET user_id = ? WHERE token = ?", ("other-test-user", data["token"]))
    elif mismatch == "type":
        sql(path, "UPDATE auth_tokens SET token_type = ? WHERE token = ?", ("refresh_token", data["token"]))
    elif mismatch == "expiry":
        sql(path, "UPDATE auth_tokens SET expires_at = ? WHERE token = ?", (timestamp(), data["token"]))
    else:
        sql(
            path,
            "INSERT INTO auth_tokens (id, user_id, token, token_type, expires_at, is_revoked, created_at, updated_at) "
            "SELECT ?, user_id, token, token_type, expires_at, is_revoked, created_at, updated_at "
            "FROM auth_tokens WHERE token = ?",
            ("duplicate-test-row", data["token"]),
        )
    error(client.get("/api/v1/auth/me", headers=bearer(data["token"])), 401, 1001)


def test_me_ignores_arbitrary_user_query_and_cannot_cross_other_real_tenant(auth):
    data = register_login(auth)
    client, _, _ = auth
    second = client.post(
        "/api/v1/auth/register",
        json={**FIELDS, "username": "Second Test", "email": "second-test@example.com"},
    ).json()["user"]
    response = client.get("/api/v1/auth/me", params={"user_id": second["id"]}, headers=bearer(data["token"]))
    assert response.json()["data"]["user"]["id"] == data["user"]["id"]
    assert second["id"] not in response.text
    error(
        client.get(
            "/api/v1/auth/me", headers={**bearer(data["token"]), "X-Tenant-ID": str(second["tenant_id"])}
        ),
        403,
        1002,
    )


def test_database_busy_is_503_not_invalid_credentials(auth):
    register_login(auth)
    client, _, path = auth
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.execute("BEGIN EXCLUSIVE")
        response = client.post("/api/v1/auth/login", json={"email": FIELDS["email"], "password": PASSWORD})
        error(response, 503, 1008)
    finally:
        connection.rollback()
        connection.close()


def test_unexpected_internal_failure_response_and_log_do_not_echo_exception(auth, monkeypatch, caplog):
    def fail(*args):
        raise RuntimeError("unsafe-password-and-private-path-sentinel")

    monkeypatch.setattr(auth[1].state.auth_service, "register", fail)
    response = auth[0].post("/api/v1/auth/register", json=FIELDS)
    error(response, 500, 1007)
    assert "sentinel" not in response.text and "sentinel" not in caplog.text


def test_connection_missing_file_never_creates_and_explicit_secret_validation(tmp_path):
    path = tmp_path.resolve() / "missing.sqlite3"
    with pytest.raises(AuthFailure), connect_auth_database(AuthSettings(path)):
        pass
    assert not path.exists()
    with pytest.raises(AuthFailure):
        load_secret(AuthSettings(path, "short"))
