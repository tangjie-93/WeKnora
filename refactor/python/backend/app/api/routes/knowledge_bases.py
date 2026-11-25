"""The two frozen knowledge-base routes and safe exact-path error dispatch."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.routes import auth
from app.api.schemas.knowledge_bases import CreateKnowledgeBaseRequest, strict_json
from app.domain.knowledge_bases import GO_WHITESPACE, KNOWLEDGE_BASE_PATH, KnowledgeBaseFailure, invalid

router = APIRouter()
logger = logging.getLogger(__name__)


def failure_response(exc):
    return JSONResponse({"success": False, "error": {
        "code": exc.code, "message": exc.message, "details": None}},
        status_code=exc.status, headers={"Cache-Control": "no-store"})


async def handle_knowledge_failure(request, exc):
    logger.warning("knowledge_base_failure status=%s category=%s", exc.status, exc.code)
    return failure_response(exc)


async def handle_auth_failure(request, exc):
    if request.url.path == KNOWLEDGE_BASE_PATH:
        if exc.code in (1007, 1008):
            exc = KnowledgeBaseFailure(exc.status, exc.code, "Knowledge base storage failure" if exc.code == 1007
                                       else "Knowledge base service unavailable")
        return await handle_knowledge_failure(request, exc)
    return await auth.handle_auth_failure(request, exc)


async def handle_validation_failure(request, exc):
    if request.url.path == KNOWLEDGE_BASE_PATH:
        return failure_response(invalid())
    return await auth.handle_validation_failure(request, exc)


async def handle_http_failure(request, exc):
    if request.url.path == KNOWLEDGE_BASE_PATH and exc.status_code == 400:
        return failure_response(invalid())
    return await auth.handle_http_failure(request, exc)


async def handle_internal_failure(request, exc):
    if request.url.path == KNOWLEDGE_BASE_PATH:
        return await handle_knowledge_failure(
            request, KnowledgeBaseFailure(500, 1007, "Internal knowledge base failure"))
    return await auth.handle_internal_failure(request, exc)


def query_creator(request, *, create=False):
    pairs = request.query_params.multi_items()
    if create:
        if pairs:
            raise invalid("Unsupported knowledge base query parameters")
        return ""
    if len(pairs) > 1 or any(key != "creator" for key, _ in pairs):
        raise invalid("Unsupported knowledge base query parameters")
    return pairs[0][1].strip(GO_WHITESPACE).lower() if pairs else ""


@router.post(KNOWLEDGE_BASE_PATH, status_code=201)
async def create_knowledge_base(request: Request):
    raw, tenant_id = auth.bearer(request), auth.requested_tenant_id(request)
    query_creator(request, create=True)
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise invalid("Content-Type must be application/json")
    try:
        body = strict_json((await request.body()).decode("utf-8"))
        if type(body) is not dict:
            raise invalid()
        if set(body) - set(CreateKnowledgeBaseRequest.model_fields):
            raise invalid("Unsupported knowledge base fields")
        payload = CreateKnowledgeBaseRequest.model_validate(body)
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError, ValidationError):
        raise invalid() from None
    data = await run_in_threadpool(request.app.state.knowledge_base_service.create, payload, raw, tenant_id)
    return JSONResponse({"success": True, "data": data}, status_code=201, headers={"Cache-Control": "no-store"})


@router.get(KNOWLEDGE_BASE_PATH)
def list_knowledge_bases(request: Request):
    raw, tenant_id = auth.bearer(request), auth.requested_tenant_id(request)
    creator = query_creator(request)
    data = request.app.state.knowledge_base_service.list(raw, tenant_id, creator)
    return JSONResponse({"success": True, "data": data}, headers={"Cache-Control": "no-store"})
