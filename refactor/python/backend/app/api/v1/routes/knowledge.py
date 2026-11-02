"""知识库与文档路由。

对齐 Go 端：
- `/knowledge-bases`、`/knowledge-bases/{id}`
- `/knowledge-bases/{id}/knowledge/file|url|manual`、`GET .../knowledge`
- `/knowledge/{id}`、`/knowledge/{id}/reparse`
- `/chunks/{knowledge_id}`
- `/knowledge-bases/{id}/hybrid-search`
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import AuthContext, get_auth_context, get_session, require_role
from app.core.errors import bad_request
from app.domain.entities import ROLE_CONTRIBUTOR
from app.repositories import tag_repository
from app.services import knowledge_service, retrieval_service, tag_service

router = APIRouter(tags=["知识库"])
contributor_only = require_role(ROLE_CONTRIBUTOR)


@router.get("/knowledge-bases")
async def list_knowledge_bases(
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    items = await knowledge_service.list_kbs(session, context.tenant_id)
    return {"success": True, "data": [knowledge_service.kb_payload(kb) for kb in items]}


@router.post("/knowledge-bases", status_code=201)
async def create_knowledge_base(
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    kb = await knowledge_service.create_kb(
        session, context.tenant_id, context.user.id, payload
    )
    return {"success": True, "data": knowledge_service.kb_payload(kb)}


@router.get("/knowledge-bases/{kb_id}")
async def get_knowledge_base(
    kb_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    kb = await knowledge_service.get_kb(session, context.tenant_id, kb_id)
    return {"success": True, "data": knowledge_service.kb_payload(kb)}


@router.put("/knowledge-bases/{kb_id}")
async def update_knowledge_base(
    kb_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    kb = await knowledge_service.update_kb(session, context.tenant_id, kb_id, payload)
    return {"success": True, "data": knowledge_service.kb_payload(kb)}


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base(
    kb_id: str,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await knowledge_service.delete_kb(session, context.tenant_id, kb_id)
    return {"success": True, "message": "knowledge base deleted"}


@router.get("/knowledge-bases/{kb_id}/knowledge")
async def list_knowledge(
    kb_id: str,
    folder_path: str = "",
    folder_scope: str = "",
    tag_id: str = "",
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await knowledge_service.get_kb(session, context.tenant_id, kb_id)
    items = await knowledge_service.list_knowledge(
        session,
        kb_id,
        folder_path,
        folder_scope,
        [tag_id] if tag_id else None,
    )
    tag_map = await tag_repository.tag_ids_for_knowledge(session, [item.id for item in items])
    data = []
    for item in items:
        payload = knowledge_service.knowledge_payload(item)
        payload["folder_path"] = item.folder_path or ""
        payload["tag_ids"] = tag_map.get(item.id, [])
        data.append(payload)
    return {"success": True, "data": data}


@router.get("/knowledge-bases/{kb_id}/knowledge/folders")
async def list_folders(
    kb_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tree = await knowledge_service.folder_tree(session, context.tenant_id, kb_id)
    return {"success": True, "data": tree}


@router.put("/knowledge-bases/{kb_id}/knowledge/folders")
async def rename_folder(
    kb_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from_path = str(payload.get("from") or "")
    to_path = str(payload.get("to") or "")
    if not from_path or not to_path:
        raise bad_request("from and to are required")
    data = await knowledge_service.rename_folder(
        session, context.tenant_id, kb_id, from_path, to_path
    )
    return {"success": True, "data": data}


@router.post("/knowledge/move")
async def move_knowledge(
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    kb_id = str(payload.get("kb_id") or "")
    if not kb_id:
        raise bad_request("kb_id is required")
    data = await knowledge_service.move_knowledge_to_folder(
        session,
        context.tenant_id,
        kb_id,
        list(payload.get("knowledge_ids") or []),
        str(payload.get("folder_path") or ""),
    )
    return {"success": True, "data": data}


@router.put("/knowledge/tags")
async def update_knowledge_tags(
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await tag_service.set_knowledge_tags_from_request(
        session, context.tenant_id, payload
    )
    return {"success": True}


@router.post("/knowledge-bases/{kb_id}/knowledge/file", status_code=201)
async def upload_file(
    kb_id: str,
    file: UploadFile = File(...),
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not file.filename:
        raise bad_request("file name is required")
    content = await file.read()
    knowledge = await knowledge_service.create_from_file(
        session, context.tenant_id, kb_id, file.filename, content
    )
    return {"success": True, "data": knowledge_service.knowledge_payload(knowledge)}


@router.post("/knowledge-bases/{kb_id}/knowledge/manual", status_code=201)
async def create_manual_knowledge(
    kb_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    knowledge = await knowledge_service.create_manual(
        session, context.tenant_id, kb_id, payload
    )
    return {"success": True, "data": knowledge_service.knowledge_payload(knowledge)}


@router.post("/knowledge-bases/{kb_id}/knowledge/url", status_code=201)
async def create_url_knowledge(
    kb_id: str,
    payload: dict,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    knowledge = await knowledge_service.create_from_url(
        session, context.tenant_id, kb_id, payload
    )
    return {"success": True, "data": knowledge_service.knowledge_payload(knowledge)}


@router.get("/knowledge/{knowledge_id}")
async def get_knowledge(
    knowledge_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    knowledge = await knowledge_service.get_knowledge(
        session, context.tenant_id, knowledge_id
    )
    return {"success": True, "data": knowledge_service.knowledge_payload(knowledge)}


@router.post("/knowledge/{knowledge_id}/reparse")
async def reparse_knowledge(
    knowledge_id: str,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    knowledge = await knowledge_service.reparse(session, context.tenant_id, knowledge_id)
    return {"success": True, "data": knowledge_service.knowledge_payload(knowledge)}


@router.delete("/knowledge/{knowledge_id}")
async def delete_knowledge(
    knowledge_id: str,
    context: AuthContext = Depends(contributor_only),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await knowledge_service.delete_knowledge(session, context.tenant_id, knowledge_id)
    return {"success": True, "message": "knowledge deleted"}


@router.get("/chunks/{knowledge_id}")
async def list_chunks(
    knowledge_id: str,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    chunks = await knowledge_service.list_chunks(session, context.tenant_id, knowledge_id)
    return {
        "success": True,
        "data": [knowledge_service.chunk_payload(chunk) for chunk in chunks],
    }


@router.post("/knowledge-bases/{kb_id}/hybrid-search")
async def hybrid_search(
    kb_id: str,
    payload: dict,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await knowledge_service.get_kb(session, context.tenant_id, kb_id)
    hits = await retrieval_service.search(
        session,
        context.tenant_id,
        kb_id,
        str(payload.get("query") or ""),
        top_k=int(payload.get("top_k") or 8),
        embedding_model_id=str(payload.get("embedding_model_id") or ""),
        rerank_model_id=str(payload.get("rerank_model_id") or ""),
    )
    return {"success": True, "data": [hit.payload() for hit in hits]}


@router.post("/knowledge-search")
async def knowledge_search(
    payload: dict,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    kb_id = str(payload.get("knowledge_base_id") or "")
    if not kb_id:
        raise bad_request("knowledge_base_id is required")
    hits = await retrieval_service.search(
        session,
        context.tenant_id,
        kb_id,
        str(payload.get("query") or ""),
        top_k=int(payload.get("top_k") or 8),
    )
    return {"success": True, "data": [hit.payload() for hit in hits]}
