"""认证基础能力：JWT（HS256）与 bcrypt 密码哈希。

JWT claims 与 Go 端 `internal/application/service/user.go` 完全一致，
因此 Go 签发的 AccessToken 在 Python 端同样可解，反之亦然。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.errors import unauthorized

ACCESS_TOKEN_TTL = timedelta(hours=24)
REFRESH_TOKEN_TTL = timedelta(days=7)
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    # bcrypt.DefaultCost = 10，与 Go 端保持一致
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str, email: str, tenant_id: int) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "user_id": user_id,
        "email": email,
        "tenant_id": tenant_id,
        "exp": int((now + ACCESS_TOKEN_TTL).timestamp()),
        "iat": int(now.timestamp()),
        "type": "access",
    }
    return jwt.encode(claims, get_settings().effective_jwt_secret, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "user_id": user_id,
        "exp": int((now + REFRESH_TOKEN_TTL).timestamp()),
        "iat": int(now.timestamp()),
        "type": "refresh",
    }
    return jwt.encode(claims, get_settings().effective_jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            get_settings().effective_jwt_secret,
            algorithms=[ALGORITHM],
            options={"require": ["exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise unauthorized("Unauthorized: invalid or expired token") from exc
    except jwt.InvalidTokenError as exc:
        raise unauthorized("Unauthorized: invalid or expired token") from exc

    if expected_type and claims.get("type") != expected_type:
        raise unauthorized("Unauthorized: invalid token type")
    return claims
