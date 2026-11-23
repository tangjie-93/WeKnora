"""The five original auth HTTP contracts; all CPU/SQLite work is synchronous."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    project_current,
    project_tenant,
    project_user,
)
from app.domain.auth import AuthFailure, AuthIdentity, InvalidCredentials, unauthorized
from app.services.auth import AuthService

router = APIRouter(prefix="/api/v1/auth")
logger = logging.getLogger(__name__)


def failure_response(exc: AuthFailure) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if exc.status == 429:
        headers["Retry-After"] = "60"
    if isinstance(exc, InvalidCredentials):
        payload = {"success": False, "message": "Invalid email or password", "memberships": []}
    else:
        payload = {"success": False, "error": {"code": exc.code, "message": exc.message, "details": None}}
    return JSONResponse(payload, status_code=exc.status, headers=headers)


async def handle_auth_failure(request: Request, exc: AuthFailure):
    logger.warning("auth_failure path=%s status=%s category=%s", request.url.path, exc.status, exc.code)
    return failure_response(exc)


async def handle_validation_failure(request: Request, exc: RequestValidationError):
    # Never serialize Pydantic's input/ctx; they can contain passwords, tokens or invalid JSON bodies.
    return failure_response(AuthFailure(400, 1010, "Invalid request parameters"))


async def handle_http_failure(request: Request, exc: HTTPException):
    """Normalize auth body-parser 400s, leaving routing and non-auth errors unchanged."""
    if exc.status_code == 400 and request.url.path.startswith("/api/v1/auth/"):
        return failure_response(AuthFailure(400, 1010, "Invalid request parameters"))
    return await http_exception_handler(request, exc)


async def handle_internal_failure(request: Request, exc: Exception):
    # No exception text, body, header, SQL, path-to-database or traceback in auth logs/responses.
    logger.error("auth_failure path=%s status=500 category=1007", request.url.path)
    return failure_response(AuthFailure(500, 1007, "Internal authentication failure"))


def get_auth_service(request: Request) -> AuthService:
    operation = request.url.path.rsplit("/", 1)[-1]
    request.app.state.auth_limits.check_rate(request.client.host if request.client else "unknown", operation)
    if (request.method == "POST" and operation != "logout" and
            request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json"):
        raise AuthFailure(400, 1010, "Content-Type must be application/json")
    return request.app.state.auth_service


def bearer(request: Request, *, logout=False) -> str:
    value = request.headers.get("authorization", "")
    parts = value.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        if logout:
            raise AuthFailure(400, 1010, "Bearer authentication token is required")
        raise unauthorized()
    raw = parts[1]
    if len(raw.encode("utf-8")) > 4096:
        raise AuthFailure(400, 1010, "Authentication token is too long")
    return raw


def require_identity(request: Request, service: Annotated[AuthService, Depends(get_auth_service)]):
    tenant_header = request.headers.get("x-tenant-id")
    tenant_id = None
    if tenant_header is not None:
        if (not tenant_header.isascii() or not tenant_header.isdecimal() or len(tenant_header) > 19 or
                int(tenant_header) <= 0):
            raise AuthFailure(400, 1010, "X-Tenant-ID must be a positive integer")
        tenant_id = int(tenant_header)
    return service.current_identity(bearer(request), tenant_id)


@router.post("/register", status_code=201)
def register(payload: RegisterRequest, service: Annotated[AuthService, Depends(get_auth_service)]):
    user = service.register(payload.username, payload.email, payload.password)
    return {"success": True, "message": "Registration successful", "user": project_user(user)}


@router.post("/login")
def login(payload: LoginRequest, service: Annotated[AuthService, Depends(get_auth_service)]):
    identity, records = service.login(payload.email, payload.password)
    return {"success": True, "message": "Login successful", "user": project_user(identity.user),
            "active_tenant": project_tenant(identity.tenant), "memberships": identity.memberships,
            "token": records[0]["token"], "refresh_token": records[1]["token"]}


@router.post("/refresh")
def refresh(payload: RefreshRequest, service: Annotated[AuthService, Depends(get_auth_service)]):
    records = service.refresh(payload.refreshToken)
    return {"success": True, "message": "Token refreshed successfully", "access_token": records[0]["token"],
            "refresh_token": records[1]["token"]}


@router.get("/me")
def me(identity: Annotated[AuthIdentity, Depends(require_identity)]):
    return {"success": True, "data": project_current(identity)}


@router.post("/logout")
def logout(request: Request, service: Annotated[AuthService, Depends(get_auth_service)]):
    service.logout(bearer(request, logout=True))
    return {"success": True, "message": "Logout successful"}
