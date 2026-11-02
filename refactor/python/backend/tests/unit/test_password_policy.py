from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.services.auth_service import validate_password_policy


@pytest.mark.parametrize("password", ["Abcdef12", "password1", "12345678a"])
def test_valid_simple_password(password: str) -> None:
    validate_password_policy(password)


@pytest.mark.parametrize("password", ["short1", "password", "12345678", "a" * 33])
def test_invalid_simple_password(password: str) -> None:
    with pytest.raises(AppError):
        validate_password_policy(password)


def test_complex_password_requires_all_classes() -> None:
    validate_password_policy("Abcdef1!", complex_enabled=True)
    with pytest.raises(AppError):
        validate_password_policy("Abcdef12", complex_enabled=True)
