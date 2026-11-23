"""Bounded local-worker abuse safeguards, using the actual peer address."""

import threading
import time
from collections import OrderedDict
from contextlib import contextmanager

from starlette.responses import JSONResponse

from app.domain.auth import AuthFailure

BODY_LIMIT = 8192
RATE_LIMITS = {"register": 5, "login": 10, "refresh": 60}


class AuthRequestLimits:
    def __init__(self):
        self._lock = threading.Lock()
        self.buckets: OrderedDict[str, dict[str, tuple[float, int]]] = OrderedDict()
        self.hash_slots = threading.BoundedSemaphore(4)

    def check_rate(self, peer: str, operation: str) -> None:
        if operation not in RATE_LIMITS:
            return
        now = time.monotonic()
        with self._lock:
            while self.buckets and all(now - start >= 60 for start, _ in next(iter(self.buckets.values())).values()):
                self.buckets.popitem(last=False)
            bucket = self.buckets.pop(peer, {})
            self.buckets[peer] = bucket
            while len(self.buckets) > 1024:
                self.buckets.popitem(last=False)
            start, count = bucket.get(operation, (now, 0))
            if now - start >= 60:
                start, count = now, 0
            if count >= RATE_LIMITS[operation]:
                raise AuthFailure(429, 1006, "Authentication rate limit exceeded; retry later")
            bucket[operation] = start, count + 1

    @contextmanager
    def password_slot(self):
        if not self.hash_slots.acquire(blocking=False):
            raise AuthFailure(429, 1006, "Password computation capacity exceeded; retry later")
        try:
            yield
        finally:
            self.hash_slots.release()


class AuthBodyLimitMiddleware:
    """Bound streamed bodies before JSON parsing, independent of Content-Length."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/auth/"):
            return await self.app(scope, receive, send)
        chunks = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(chunks) + len(chunk) > BODY_LIMIT:
                response = JSONResponse({"success": False, "error": {
                    "code": 1010, "message": "Request body exceeds 8 KiB", "details": None}},
                    status_code=413, headers={"Cache-Control": "no-store"})
                return await response(scope, receive, send)
            chunks.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(chunks), "more_body": False}
            return await receive()

        async def no_store_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [(k, v) for k, v in message["headers"] if k.lower() != b"cache-control"]
                message["headers"].append((b"cache-control", b"no-store"))
            await send(message)

        await self.app(scope, bounded_receive, no_store_send)
