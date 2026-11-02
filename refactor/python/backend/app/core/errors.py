"""应用错误与统一错误响应，数值错误码对齐 `internal/errors/errors.go`。"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Common error codes (1000-1999)
ERR_BAD_REQUEST = 1000
ERR_UNAUTHORIZED = 1001
ERR_FORBIDDEN = 1002
ERR_NOT_FOUND = 1003
ERR_METHOD_NOT_ALLOWED = 1004
ERR_CONFLICT = 1005
ERR_TOO_MANY_REQUESTS = 1006
ERR_INTERNAL_SERVER = 1007
ERR_SERVICE_UNAVAILABLE = 1008
ERR_TIMEOUT = 1009
ERR_VALIDATION = 1010

# Tenant related error codes (2000-2099)
ERR_TENANT_NOT_FOUND = 2000
ERR_TENANT_ALREADY_EXISTS = 2001
ERR_TENANT_INACTIVE = 2002


class AppError(Exception):
    """对应 Go 端的 `errors.AppError`。"""

    def __init__(
        self,
        code: int,
        message: str,
        http_status: int = 400,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details

    def with_details(self, details: Any) -> AppError:
        self.details = details
        return self


def bad_request(message: str, details: Any = None) -> AppError:
    return AppError(ERR_BAD_REQUEST, message, 400, details)


def validation_error(message: str, details: Any = None) -> AppError:
    return AppError(ERR_VALIDATION, message, 400, details)


def unauthorized(message: str = "Unauthorized", details: Any = None) -> AppError:
    return AppError(ERR_UNAUTHORIZED, message, 401, details)


def forbidden(message: str = "Forbidden", details: Any = None) -> AppError:
    return AppError(ERR_FORBIDDEN, message, 403, details)


def not_found(message: str = "Not found", details: Any = None) -> AppError:
    return AppError(ERR_NOT_FOUND, message, 404, details)


def conflict(message: str, details: Any = None) -> AppError:
    return AppError(ERR_CONFLICT, message, 409, details)


def _error_body(code: int, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"success": False, "error": error}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=_error_body(ERR_VALIDATION, "Invalid request parameters", exc.errors()),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # 与 Go 端一致：未分类错误只返回通用信息，细节写日志。
        import logging

        logging.getLogger(__name__).exception("unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content=_error_body(ERR_INTERNAL_SERVER, "Internal server error"),
        )
