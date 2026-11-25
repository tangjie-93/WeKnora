"""FastAPI application entry point for the minimal Python backend."""

from fastapi import FastAPI, Response
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.api.openapi import install_openapi
from app.api.routes.auth import router
from app.api.routes.knowledge_bases import (
    handle_auth_failure,
    handle_http_failure,
    handle_internal_failure,
    handle_knowledge_failure,
    handle_validation_failure,
)
from app.api.routes.knowledge_bases import (
    router as knowledge_router,
)
from app.core.auth_limits import AuthBodyLimitMiddleware, AuthRequestLimits
from app.core.config import AuthSettings, load_auth_settings, load_secret
from app.core.knowledge_limits import KnowledgeBaseBodyLimitMiddleware
from app.domain.auth import AuthFailure
from app.domain.knowledge_bases import KnowledgeBaseFailure
from app.services.auth import AuthService
from app.services.knowledge_bases import KnowledgeBaseService

IMPLEMENTATION_HEADER = "python-fastapi"


def create_app(auth_settings: AuthSettings | None = None) -> FastAPI:
    """Keep public health independent of explicit auth database initialization."""
    application = FastAPI(redirect_slashes=False)
    settings = load_auth_settings() if auth_settings is None else auth_settings
    try:
        secret = load_secret(settings)
    except AuthFailure:
        secret = None
    limits = AuthRequestLimits()
    application.state.auth_limits = limits
    application.state.auth_service = AuthService(settings, secret, limits)
    application.state.knowledge_base_service = KnowledgeBaseService(application.state.auth_service)
    application.add_middleware(AuthBodyLimitMiddleware)
    application.add_middleware(KnowledgeBaseBodyLimitMiddleware)
    application.add_exception_handler(KnowledgeBaseFailure, handle_knowledge_failure)
    application.add_exception_handler(AuthFailure, handle_auth_failure)
    application.add_exception_handler(RequestValidationError, handle_validation_failure)
    application.add_exception_handler(HTTPException, handle_http_failure)
    application.add_exception_handler(Exception, handle_internal_failure)
    application.include_router(router)
    application.include_router(knowledge_router)
    application.add_api_route("/health", health, methods=["GET"])
    install_openapi(application)
    return application


def health(response: Response) -> dict[str, str]:
    """Return the minimal HTTP liveness response."""
    response.headers["X-WeKnora-Implementation"] = IMPLEMENTATION_HEADER
    return {"status": "ok"}


app = create_app()
