"""Exact-path streaming bounds and no-store responses for knowledge-base APIs."""

from starlette.responses import JSONResponse

from app.domain.knowledge_bases import BODY_LIMIT, KNOWLEDGE_BASE_PATH


class KnowledgeBaseBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != KNOWLEDGE_BASE_PATH:
            return await self.app(scope, receive, send)

        async def no_store_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [(key, value) for key, value in message["headers"]
                                      if key.lower() != b"cache-control"]
                message["headers"].append((b"cache-control", b"no-store"))
            await send(message)

        if scope["method"] != "POST":
            return await self.app(scope, receive, no_store_send)
        chunks = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(chunks) + len(chunk) > BODY_LIMIT:
                response = JSONResponse({"success": False, "error": {
                    "code": 1000, "message": "Knowledge base request body exceeds 1 MiB", "details": None}},
                    status_code=400)
                return await response(scope, receive, no_store_send)
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

        await self.app(scope, bounded_receive, no_store_send)
