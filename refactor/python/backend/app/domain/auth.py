"""Internal authentication identity and safe, typed failures."""

from dataclasses import dataclass
from typing import Any


class AuthFailure(Exception):
    """Expose only a fixed, safe error message at the HTTP boundary."""

    def __init__(self, status: int, code: int, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class InvalidCredentials(AuthFailure):
    """Preserve the original login failure DTO."""

    def __init__(self):
        super().__init__(401, 1001, "Invalid email or password")


@dataclass(frozen=True)
class AuthIdentity:
    user: dict[str, Any]
    tenant: dict[str, Any]
    memberships: list[dict[str, Any]]


def unauthorized() -> AuthFailure:
    return AuthFailure(401, 1001, "Invalid or expired authentication token")


def unavailable() -> AuthFailure:
    return AuthFailure(503, 1008, "Authentication unavailable; initialize an owned authentication database")
