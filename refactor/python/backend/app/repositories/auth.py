"""Parameterized authentication persistence; callers own all transactions."""

import sqlite3
import uuid
from datetime import datetime

from app.core.security import timestamp
from app.domain.auth import AuthFailure, AuthIdentity, unauthorized

USER_COLUMNS = ("id, username, email, password_hash, avatar, tenant_id, is_active, "
                "can_access_all_tenants, is_system_admin, preferences, created_at, updated_at, deleted_at")


def find_user_by_email(connection: sqlite3.Connection, email: str) -> dict | None:
    row = connection.execute(f"SELECT {USER_COLUMNS} FROM users WHERE email = ?", (email,)).fetchone()
    return dict(row) if row else None


def find_user_by_id(connection: sqlite3.Connection, user_id: str) -> dict | None:
    row = connection.execute(f"SELECT {USER_COLUMNS} FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def create_personal_identity(connection: sqlite3.Connection, username: str, email: str,
                             password_hash: str) -> dict:
    now = timestamp()
    tenant_id = connection.execute(
        "INSERT INTO tenants (name, description, business, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)", (f"{username}'s Workspace", "Default workspace", "", "active", now, now)
    ).lastrowid
    user_id = str(uuid.uuid4())
    connection.execute(
        "INSERT INTO users (id, username, email, password_hash, avatar, tenant_id, is_active, "
        "can_access_all_tenants, is_system_admin, preferences, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, username, email, password_hash, "", tenant_id, 1, 0, 0, "{}", now, now))
    connection.execute(
        "INSERT INTO tenant_members (user_id, tenant_id, role, status, joined_at, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)", (user_id, tenant_id, "owner", "active", now, now, now))
    return find_user_by_id(connection, user_id)


def get_active_identity(connection: sqlite3.Connection, user_id: str) -> AuthIdentity:
    user = find_user_by_id(connection, user_id)
    if not user or not user["is_active"] or user["deleted_at"] is not None:
        raise unauthorized()
    tenant = connection.execute(
        "SELECT id, name, description, status, retriever_engines, business, storage_quota, storage_used, "
        "created_at, updated_at, deleted_at FROM tenants WHERE id = ?", (user["tenant_id"],)).fetchone()
    member = connection.execute(
        "SELECT tenant_id, role, status, deleted_at FROM tenant_members WHERE user_id = ? AND tenant_id = ?",
        (user_id, user["tenant_id"])).fetchone()
    if (not tenant or tenant["status"] != "active" or tenant["deleted_at"] is not None or
            not member or member["status"] != "active" or member["deleted_at"] is not None or
            member["role"] not in ("owner", "admin", "contributor", "viewer")):
        raise AuthFailure(403, 1002, "Current workspace or membership is unavailable")
    return AuthIdentity(user, dict(tenant), [{"tenant_id": tenant["id"], "tenant_name": tenant["name"],
                                           "role": member["role"]}])


def insert_token_pair(connection: sqlite3.Connection, records: list[dict]) -> None:
    connection.executemany(
        "INSERT INTO auth_tokens (id, user_id, token, token_type, expires_at, is_revoked, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(r["id"], r["user_id"], r["token"], r["token_type"], r["expires_at"], 0,
          r["created_at"], r["created_at"]) for r in records])


def require_token_record(connection: sqlite3.Connection, raw: str, claims: dict, *, for_logout=False) -> dict:
    rows = connection.execute(
        "SELECT id, user_id, token, token_type, expires_at, is_revoked FROM auth_tokens WHERE token = ?",
        (raw,)).fetchall()
    if len(rows) != 1:
        raise unauthorized()
    row = dict(rows[0])
    try:
        expiry = datetime.fromisoformat(row["expires_at"]).timestamp()
    except (ValueError, TypeError, AttributeError):
        raise AuthFailure(500, 1007, "Authentication storage failure") from None
    if (row["user_id"] != claims["user_id"] or row["token_type"] != f"{claims['type']}_token" or
            expiry != claims["exp"] or (row["is_revoked"] and not for_logout)):
        raise unauthorized()
    return row


def rotate_refresh(connection: sqlite3.Connection, token_id: str) -> None:
    result = connection.execute(
        "UPDATE auth_tokens SET is_revoked = ?, updated_at = ? "
        "WHERE id = ? AND is_revoked = ? AND expires_at > ?",
        (1, timestamp(), token_id, 0, timestamp()))
    if result.rowcount != 1:
        raise unauthorized()


def revoke_user_tokens(connection: sqlite3.Connection, user_id: str) -> None:
    connection.execute("UPDATE auth_tokens SET is_revoked = ?, updated_at = ? WHERE user_id = ?",
                       (1, timestamp(), user_id))
