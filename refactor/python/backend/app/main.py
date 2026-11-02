"""应用入口，对应 `cmd/server/main.go`。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import dispose_engine
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import register_middlewares
from app.core.migrations import run_migrations
from app.mcp.server import router as mcp_router

logger = logging.getLogger(__name__)

ALLOW_HEADERS = [
    "Origin",
    "Content-Type",
    "Accept",
    "Authorization",
    "X-Request-ID",
    "X-Tenant-ID",
    "X-API-Key",
    "X-Language",
    "X-Requested-With",
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.auto_migrate:
        logger.info("running migrations (driver=%s)", settings.db_driver)
        await run_migrations(settings)
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings)

    app = FastAPI(
        title="WeKnora Python API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/swagger/index.html",
        openapi_url="/swagger/doc.json",
    )

    origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=ALLOW_HEADERS,
        expose_headers=["X-Request-ID", "Content-Length"],
    )

    register_middlewares(app)
    register_exception_handlers(app)
    app.include_router(api_router)
    app.include_router(mcp_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
