from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong123", hashed)


def test_access_token_claims() -> None:
    token = create_access_token("user-1", "a@b.com", 10001)
    claims = decode_token(token, expected_type="access")
    assert claims["user_id"] == "user-1"
    assert claims["email"] == "a@b.com"
    assert claims["tenant_id"] == 10001


def test_refresh_token_type_mismatch_rejected() -> None:
    token = create_refresh_token("user-1")
    with pytest.raises(AppError) as exc:
        decode_token(token, expected_type="access")
    assert exc.value.http_status == 401


def test_tampered_token_rejected() -> None:
    token = create_access_token("user-1", "a@b.com", 1)
    with pytest.raises(AppError):
        decode_token(token + "x", expected_type="access")
