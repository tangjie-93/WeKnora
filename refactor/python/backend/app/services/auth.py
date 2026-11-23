"""Authentication business operations and atomic transaction boundaries."""

import sqlite3

from app.core.auth_limits import AuthRequestLimits
from app.core.config import AuthSettings
from app.core.database import connect_auth_database, transaction
from app.core.security import DUMMY_HASH, decode_token, hash_password, issue_token_pair, verify_password
from app.domain.auth import AuthFailure, InvalidCredentials, unauthorized, unavailable
from app.repositories import auth as repository


class AuthService:
    def __init__(self, settings: AuthSettings, secret: str | None, limits: AuthRequestLimits):
        self.settings = settings
        self.secret = secret
        self.limits = limits

    def require_available(self):
        if self.secret is None:
            raise unavailable()

    def register(self, username: str, email: str, password: str) -> dict:
        self.require_available()
        # Validate the owned database before hashing, retaining one operation-local connection.
        # Hashing still occurs outside the write transaction, without holding a write lock.
        with connect_auth_database(self.settings) as connection:
            with self.limits.password_slot():
                password_hash = hash_password(password)
            try:
                with transaction(connection):
                    return repository.create_personal_identity(connection, username, email, password_hash)
            except sqlite3.IntegrityError as exc:
                if (getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE and
                        str(exc) in ("UNIQUE constraint failed: users.email", "UNIQUE constraint failed: users.username")):
                    raise AuthFailure(400, 1000, "Email or username already registered") from None
                raise

    def login(self, email: str, password: str):
        self.require_available()
        with connect_auth_database(self.settings) as connection:
            user = repository.find_user_by_email(connection, email)
            with self.limits.password_slot():
                valid = verify_password(password, user["password_hash"] if user else DUMMY_HASH)
            if not user or not valid or not user["is_active"] or user["deleted_at"] is not None:
                raise InvalidCredentials()
            with transaction(connection):
                identity = repository.get_active_identity(connection, user["id"])
                if identity.user["password_hash"] != user["password_hash"]:
                    raise InvalidCredentials()
                records = issue_token_pair(identity.user, self.secret)
                repository.insert_token_pair(connection, records)
            return identity, records

    def current_identity(self, raw: str, tenant_id: int | None = None):
        self.require_available()
        claims = decode_token(raw, self.secret, "access")
        with connect_auth_database(self.settings) as connection:
            # Read token, user, tenant and member from one consistent snapshot.
            connection.execute("BEGIN")
            repository.require_token_record(connection, raw, claims)
            identity = repository.get_active_identity(connection, claims["user_id"])
            if (claims["tenant_id"] != identity.tenant["id"] or
                    (tenant_id is not None and tenant_id != identity.tenant["id"])):
                raise AuthFailure(403, 1002, "Current workspace does not match authentication")
            return identity

    def refresh(self, raw: str):
        self.require_available()
        claims = decode_token(raw, self.secret, "refresh")
        with connect_auth_database(self.settings) as connection:
            with transaction(connection):
                record = repository.require_token_record(connection, raw, claims)
                repository.rotate_refresh(connection, record["id"])
                identity = repository.get_active_identity(connection, claims["user_id"])
                records = issue_token_pair(identity.user, self.secret)
                repository.insert_token_pair(connection, records)
            return records

    def logout(self, raw: str) -> None:
        self.require_available()
        claims = decode_token(raw, self.secret, for_logout=True)
        with connect_auth_database(self.settings) as connection, transaction(connection):
            repository.require_token_record(connection, raw, claims, for_logout=True)
            if repository.find_user_by_id(connection, claims["user_id"]) is None:
                raise unauthorized()
            repository.revoke_user_tokens(connection, claims["user_id"])
