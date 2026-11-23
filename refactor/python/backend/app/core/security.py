"""bcrypt password compatibility and fixed-algorithm, typed JWTs."""

import time
import uuid
from datetime import UTC, datetime

import bcrypt
import jwt

from app.domain.auth import unauthorized

ACCESS_SECONDS = 24 * 60 * 60
REFRESH_SECONDS = 7 * 24 * 60 * 60
# One fixed-cost dummy per process, never recomputed on unknown-user requests.
DUMMY_HASH = bcrypt.hashpw(b"not-a-real-account-0", bcrypt.gensalt(rounds=10)).decode("ascii")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, UnicodeError):
        return False


def timestamp(epoch: int | None = None) -> str:
    return datetime.fromtimestamp(time.time() if epoch is None else epoch, UTC).isoformat().replace("+00:00", "Z")


def issue_token_pair(user: dict, secret: str) -> list[dict]:
    now = int(time.time())
    records = []
    for kind, seconds in (("access", ACCESS_SECONDS), ("refresh", REFRESH_SECONDS)):
        claims = {"user_id": user["id"], "exp": now + seconds, "iat": now,
                  "type": kind, "jti": str(uuid.uuid4())}
        if kind == "access":
            claims.update(email=user["email"], tenant_id=user["tenant_id"])
        records.append({"id": str(uuid.uuid4()), "user_id": user["id"],
                        "token": jwt.encode(claims, secret, algorithm="HS256"),
                        "token_type": f"{kind}_token", "expires_at": timestamp(now + seconds),
                        "created_at": timestamp(now)})
    return records


def decode_token(raw: str, secret: str, expected: str | None = None, *, for_logout: bool = False) -> dict:
    if not isinstance(raw, str) or not raw or len(raw.encode("utf-8")) > 4096:
        raise unauthorized()
    try:
        claims = jwt.decode(raw, secret, algorithms=["HS256"], options={
            "require": ["exp", "iat", "user_id", "type", "jti"], "verify_exp": not for_logout})
        if (claims["type"] not in ("access", "refresh") or
                (expected is not None and claims["type"] != expected) or
                not isinstance(claims["user_id"], str) or not claims["user_id"] or
                not isinstance(claims["jti"], str) or not claims["jti"] or
                type(claims["exp"]) is not int or type(claims["iat"]) is not int or
                claims["exp"] <= claims["iat"]):
            raise unauthorized()
        if claims["type"] == "access" and (
                type(claims.get("tenant_id")) is not int or claims["tenant_id"] <= 0 or
                not isinstance(claims.get("email"), str)):
            raise unauthorized()
        return claims
    except (jwt.PyJWTError, TypeError, ValueError, OverflowError):
        raise unauthorized() from None
