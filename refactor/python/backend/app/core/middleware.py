"""HTTP 中间件：Request-ID、语言、访问日志。"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request

from app.core.context import language_var, request_id_var

logger = logging.getLogger("app.access")


def _parse_language(value: str | None) -> str:
    if not value:
        return ""
    # 取第一个语言标签，如 "zh-CN,zh;q=0.9" -> "zh-CN"
    return value.split(",")[0].strip()


def register_middlewares(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request_id_var.set(request_id)
        language_var.set(_parse_language(request.headers.get("Accept-Language")))

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info("%s %s -> %s", request.method, request.url.path, response.status_code)
        return response
