"""Strict original request fields and explicit, secret-free response projections."""

import json
import re
import unicodedata
from datetime import UTC, datetime

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, field_validator

from app.domain.auth import AuthFailure, AuthIdentity

DEFAULT_BROWSER_SEARCH_INSTRUCTIONS = (
    "Default search engine: Bing.\nSearch URL: https://www.bing.com/search?q={query}"
)


def validate_identifier(value: str) -> str:
    if value != value.strip() or any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("Leading/trailing whitespace and control characters are not allowed")
    return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def email_valid(cls, value: str) -> str:
        validate_identifier(value)
        if len(value) > 255:
            raise ValueError("Email is too long")
        try:
            validate_email(value, check_deliverability=False)
        except EmailNotValidError:
            raise ValueError("Invalid email syntax") from None
        return value

    @field_validator("password")
    @classmethod
    def password_valid(cls, value: str) -> str:
        if len(value) < 6 or len(value.encode("utf-8")) > 72:
            raise ValueError("Password must contain at least 6 characters and at most 72 UTF-8 bytes")
        return value


class RegisterRequest(LoginRequest):
    username: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, value: str) -> str:
        validate_identifier(value)
        if not 2 <= len(value) <= 50:
            raise ValueError("Username must contain 2 to 50 characters")
        return value

    @field_validator("password")
    @classmethod
    def registration_password_valid(cls, value: str) -> str:
        if not 8 <= len(value) <= 32 or not re.search("[A-Za-z]", value) or not re.search("[0-9]", value):
            raise ValueError("Password must contain 8 to 32 characters, an ASCII letter and a digit")
        return value


class RefreshRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    refreshToken: str

    @field_validator("refreshToken")
    @classmethod
    def token_valid(cls, value: str) -> str:
        if not value or len(value.encode("utf-8")) > 4096:
            raise ValueError("Invalid token length")
        return value


def public_time(value) -> str | None:
    if value is None:
        return None
    date = datetime.fromisoformat(str(value))
    if date.tzinfo is None:
        date = date.replace(tzinfo=UTC)
    return date.astimezone(UTC).isoformat().replace("+00:00", "Z")


def safe_json(value, kind):
    try:
        result = json.loads(value)
        if not isinstance(result, kind):
            raise TypeError("Invalid persisted JSON")
        return result
    except (ValueError, TypeError):
        raise AuthFailure(500, 1007, "Authentication storage failure") from None


def project_user(user: dict, *, info=False) -> dict:
    result = {key: user[key] for key in ("id", "username", "email", "avatar", "tenant_id")}
    for key in ("is_active", "can_access_all_tenants", "is_system_admin"):
        result[key] = bool(user[key])
    result["preferences"] = safe_json(user["preferences"], dict)
    result.update(created_at=public_time(user["created_at"]), updated_at=public_time(user["updated_at"]))
    if not info:
        result["deleted_at"] = public_time(user["deleted_at"])
    return result


def project_tenant(tenant: dict) -> dict:
    result = {key: tenant[key] for key in ("id", "name", "description", "status", "business",
                                         "storage_quota", "storage_used")}
    result["retriever_engines"] = safe_json(tenant["retriever_engines"], list)
    for key in ("created_at", "updated_at", "deleted_at"):
        result[key] = public_time(tenant[key])
    return result


def project_current(identity: AuthIdentity) -> dict:
    return {"user": project_user(identity.user, info=True), "tenant": project_tenant(identity.tenant),
            "memberships": identity.memberships, "tenant_required": False,
            "preference_defaults": {"browser_search_instructions": DEFAULT_BROWSER_SEARCH_INSTRUCTIONS},
            "capabilities": {"can_create_tenant": False, "auto_accept_invitation": False}}
