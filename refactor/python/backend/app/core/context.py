"""请求级上下文变量。"""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
language_var: ContextVar[str] = ContextVar("language", default="")
