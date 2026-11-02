"""结构化日志，对齐 Go 端 LOG_LEVEL / LOG_FORMAT 的基本行为。"""

from __future__ import annotations

import logging
import sys

from app.core.config import Settings
from app.core.context import request_id_var

_FORMAT = (
    "%(asctime)s | %(levelname)-5s | %(name)s | rid=%(request_id)s | %(message)s"
)


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


def setup_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.addFilter(_RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn 自带 handler 会重复输出，交给 root 处理
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
