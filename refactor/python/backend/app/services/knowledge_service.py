"""知识库与文档入库：上传 → 解析 → 分块 → 向量化 → 落库。"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request, not_found
from app.domain.entities import (
    KB_TYPE_DOCUMENT,
    KNOWLEDGE_TYPE_FILE,
    KNOWLEDGE_TYPE_MANUAL,
    MODEL_TYPE_EMBEDDING,
    PARSE_COMPLETED,
    PARSE_FAILED,
    PARSE_PENDING,
    Chunk,
    Knowledge,
    KnowledgeBase,
)
from app.integrations.docreader import parse_and_split
from app.llm import OpenAICompatibleClient
from app.repositories import knowledge_repository, model_repository
from app.storage import local

DEFAULT_CHUNKING = {"chunk_size": 600, "chunk_overlap": 80}


def _iso(value) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat().replace("+00:00", "Z")


def kb_payload(kb: KnowledgeBase) -> dict[str, Any]:
    return {
        "id": kb.id,
        "tenant_id": kb.tenant_id,
        "name": kb.name,
        "description": kb.description or "",
        "type": kb.type,
        "chunking_config": kb.chunking_config or DEFAULT_CHUNKING,
        "embedding_model_id": kb.embedding_model_id or "",
        "summary_model_id": kb.summary_model_id or "",
        "indexing_strategy": kb.indexing_strategy or {},
        "faq_config": kb.faq_config or {},
        "is_temporary": bool(kb.is_temporary),
        "is_pinned": bool(kb.is_pinned),
        "creator_id": kb.creator_id or "",
        "created_at": _iso(kb.created_at),
        "updated_at": _iso(kb.updated_at),
    }


def knowledge_payload(knowledge: Knowledge) -> dict[str, Any]:
    return {
        "id": knowledge.id,
        "tenant_id": knowledge.tenant_id,
        "knowledge_base_id": knowledge.knowledge_base_id,
        "type": knowledge.type,
        "title": knowledge.title or knowledge.file_name,
        "description": knowledge.description or "",
        "source": knowledge.source or "",
        "parse_status": knowledge.parse_status,
        "enable_status": knowledge.enable_status,
        "file_name": knowledge.file_name or "",
        "file_type": knowledge.file_type or "",
        "file_size": knowledge.file_size,
        "file_path": knowledge.file_path or "",
        "error_message": knowledge.error_message or "",
        "created_at": _iso(knowledge.created_at),
        "updated_at": _iso(knowledge.updated_at),
        "processed_at": _iso(knowledge.processed_at),
    }


def chunk_payload(chunk: Chunk) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "knowledge_id": chunk.knowledge_id,
        "knowledge_base_id": chunk.knowledge_base_id,
        "content": chunk.content,
        "chunk_index": chunk.chunk_index,
        "is_enabled": bool(chunk.is_enabled),
        "chunk_type": chunk.chunk_type,
        "created_at": _iso(chunk.created_at),
    }


async def list_kbs(session: AsyncSession, tenant_id: int) -> list[KnowledgeBase]:
    return await knowledge_repository.list_kbs(session, tenant_id)


async def get_kb(session: AsyncSession, tenant_id: int, kb_id: str) -> KnowledgeBase:
    kb = await knowledge_repository.get_kb(session, tenant_id, kb_id)
    if kb is None:
        raise not_found("knowledge base not found")
    return kb


async def create_kb(
    session: AsyncSession, tenant_id: int, user_id: str, payload: dict[str, Any]
) -> KnowledgeBase:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise bad_request("knowledge base name is required")

    chunking = payload.get("chunking_config") or {}
    config = dict(DEFAULT_CHUNKING)
    if isinstance(chunking, dict):
        config.update({k: v for k, v in chunking.items() if v is not None})

    embedding_model_id = str(payload.get("embedding_model_id") or "")
    if not embedding_model_id:
        default_model = await model_repository.default_embedding_model(session, tenant_id)
        if default_model is not None:
            embedding_model_id = default_model.id

    kb = KnowledgeBase(
        tenant_id=tenant_id,
        name=name,
        description=str(payload.get("description") or ""),
        type=str(payload.get("type") or KB_TYPE_DOCUMENT),
        chunking_config=config,
        embedding_model_id=embedding_model_id,
        creator_id=user_id,
        indexing_strategy=payload.get("indexing_strategy") or {},
    )
    await knowledge_repository.save_kb(session, kb)
    await session.commit()
    await session.refresh(kb)
    return kb


async def update_kb(
    session: AsyncSession, tenant_id: int, kb_id: str, payload: dict[str, Any]
) -> KnowledgeBase:
    kb = await get_kb(session, tenant_id, kb_id)
    if payload.get("name"):
        kb.name = str(payload["name"])
    if "description" in payload:
        kb.description = str(payload["description"])
    if "embedding_model_id" in payload:
        kb.embedding_model_id = str(payload["embedding_model_id"])
    if isinstance(payload.get("chunking_config"), dict):
        merged = dict(kb.chunking_config or DEFAULT_CHUNKING)
        merged.update(payload["chunking_config"])
        kb.chunking_config = merged
    await session.commit()
    await session.refresh(kb)
    return kb


async def delete_kb(session: AsyncSession, tenant_id: int, kb_id: str) -> None:
    kb = await get_kb(session, tenant_id, kb_id)
    kb.deleted_at = datetime.now(UTC)
    await session.commit()


async def list_knowledge(
    session: AsyncSession,
    kb_id: str,
    folder_path: str = "",
    folder_scope: str = "",
    tag_ids: list[str] | None = None,
) -> list[Knowledge]:
    return await knowledge_repository.list_knowledge(
        session, kb_id, folder_path, folder_scope, tag_ids
    )


async def get_knowledge(session: AsyncSession, tenant_id: int, knowledge_id: str) -> Knowledge:
    knowledge = await knowledge_repository.get_knowledge(session, tenant_id, knowledge_id)
    if knowledge is None:
        raise not_found("knowledge not found")
    return knowledge


async def _index_knowledge(
    session: AsyncSession,
    knowledge: Knowledge,
    kb: KnowledgeBase,
    filename: str,
    content: bytes,
) -> None:
    """解析 → 分块 → 向量化；失败时把状态置为 failed 并记录原因。"""
    chunking = kb.chunking_config or DEFAULT_CHUNKING
    chunk_size = int(chunking.get("chunk_size") or 600)
    chunk_overlap = int(chunking.get("chunk_overlap") or 80)

    try:
        text, chunks = parse_and_split(filename, content, chunk_size, chunk_overlap)
    except Exception as exc:  # noqa: BLE001 - 解析失败必须落库为 failed
        knowledge.parse_status = PARSE_FAILED
        knowledge.error_message = f"{type(exc).__name__}: {exc}"
        await session.commit()
        return

    if not chunks:
        knowledge.parse_status = PARSE_FAILED
        knowledge.error_message = "no text extracted from document"
        await session.commit()
        return

    vectors: list[list[float]] = []
    model = await model_repository.first_of_type(
        session, knowledge.tenant_id, MODEL_TYPE_EMBEDDING
    )
    if model is not None:
        client = OpenAICompatibleClient(model)
        vectors = await client.embed(chunks)
        knowledge.embedding_model_id = model.id

    await knowledge_repository.delete_chunks_of_knowledge(session, knowledge.id)
    for index, chunk_text in enumerate(chunks):
        vector = vectors[index] if index < len(vectors) else []
        session.add(
            Chunk(
                tenant_id=knowledge.tenant_id,
                knowledge_base_id=knowledge.knowledge_base_id,
                knowledge_id=knowledge.id,
                content=chunk_text,
                source_content=chunk_text,
                chunk_index=index,
                metadata_json={"embedding": vector, "char_count": len(chunk_text)},
            )
        )

    knowledge.parse_status = PARSE_COMPLETED
    knowledge.error_message = ""
    knowledge.processed_at = datetime.now(UTC)
    knowledge.metadata_json = {"text_length": len(text), "chunk_count": len(chunks)}
    await session.commit()


async def create_from_file(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    filename: str,
    content: bytes,
) -> Knowledge:
    kb = await get_kb(session, tenant_id, kb_id)
    if not content:
        raise bad_request("uploaded file is empty")

    knowledge = Knowledge(
        tenant_id=tenant_id,
        knowledge_base_id=kb.id,
        type=KNOWLEDGE_TYPE_FILE,
        title=filename,
        source=filename,
        parse_status=PARSE_PENDING,
        file_name=filename,
        file_type=(filename.rsplit(".", 1)[-1].lower() if "." in filename else ""),
        file_size=len(content),
        file_hash=hashlib.sha256(content).hexdigest(),
        storage_size=len(content),
        embedding_model_id=kb.embedding_model_id,
    )
    await knowledge_repository.save_knowledge(session, knowledge)
    knowledge.file_path = local.save_bytes(tenant_id, knowledge.id, filename, content)
    await session.commit()

    await _index_knowledge(session, knowledge, kb, filename, content)
    await session.refresh(knowledge)
    return knowledge


async def create_manual(
    session: AsyncSession, tenant_id: int, kb_id: str, payload: dict[str, Any]
) -> Knowledge:
    kb = await get_kb(session, tenant_id, kb_id)
    title = str(payload.get("title") or "").strip()
    content_text = str(payload.get("content") or "").strip()
    if not title or not content_text:
        raise bad_request("title and content are required")

    content = content_text.encode("utf-8")
    knowledge = Knowledge(
        tenant_id=tenant_id,
        knowledge_base_id=kb.id,
        type=KNOWLEDGE_TYPE_MANUAL,
        title=title,
        source="manual",
        parse_status=PARSE_PENDING,
        file_name=f"{title}.md",
        file_type="md",
        file_size=len(content),
        file_hash=hashlib.sha256(content).hexdigest(),
        embedding_model_id=kb.embedding_model_id,
    )
    await knowledge_repository.save_knowledge(session, knowledge)
    knowledge.file_path = local.save_bytes(tenant_id, knowledge.id, f"{title}.md", content)
    await session.commit()

    await _index_knowledge(session, knowledge, kb, f"{title}.md", content)
    await session.refresh(knowledge)
    return knowledge


async def create_from_url(
    session: AsyncSession, tenant_id: int, kb_id: str, payload: dict[str, Any]
) -> Knowledge:
    url = str(payload.get("url") or "").strip()
    if not url:
        raise bad_request("url is required")

    import httpx

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise bad_request(f"failed to fetch url: {exc}") from exc

    filename = (payload.get("file_name") or url.rstrip("/").split("/")[-1] or "index.html")
    return await create_from_file(
        session, tenant_id, kb_id, str(filename), response.content
    )


async def reparse(session: AsyncSession, tenant_id: int, knowledge_id: str) -> Knowledge:
    knowledge = await get_knowledge(session, tenant_id, knowledge_id)
    kb = await get_kb(session, tenant_id, knowledge.knowledge_base_id)
    content = local.read_bytes(knowledge.file_path)
    knowledge.parse_status = PARSE_PENDING
    await session.commit()
    await _index_knowledge(session, knowledge, kb, knowledge.file_name, content)
    await session.refresh(knowledge)
    return knowledge


async def delete_knowledge(session: AsyncSession, tenant_id: int, knowledge_id: str) -> None:
    knowledge = await get_knowledge(session, tenant_id, knowledge_id)
    knowledge.deleted_at = datetime.now(UTC)
    await knowledge_repository.delete_chunks_of_knowledge(session, knowledge_id)
    local.delete(knowledge.file_path)
    await session.commit()


async def list_chunks(session: AsyncSession, tenant_id: int, knowledge_id: str) -> list[Chunk]:
    await get_knowledge(session, tenant_id, knowledge_id)
    return await knowledge_repository.list_chunks(session, knowledge_id)


# --------------------------------------------------------------------------
# 文件夹（路径由知识条目推导，不需要独立表）
# --------------------------------------------------------------------------

MAX_FOLDER_DEPTH = 16
MAX_FOLDER_PATH_LENGTH = 1024
MAX_FOLDER_SEGMENT_LENGTH = 128


def normalize_folder_path(raw: str) -> str:
    """对齐 `types.NormalizeKnowledgeFolderPath`：`/` 分隔、去空段、深度与长度受限。"""
    if not raw:
        return ""
    raw = str(raw).replace("\\", "/")
    segments: list[str] = []
    for segment in raw.split("/"):
        segment = segment.strip().rstrip(". ")
        if not segment or segment in (".", ".."):
            continue
        if len(segment.encode("utf-8")) > MAX_FOLDER_SEGMENT_LENGTH:
            segment = segment.encode("utf-8")[:MAX_FOLDER_SEGMENT_LENGTH]
            segment = segment.decode("utf-8", "ignore").strip()
        if not segment:
            continue
        segments.append(segment)
        if len(segments) >= MAX_FOLDER_DEPTH:
            break
    while len(segments) > 0 and len("/".join(segments)) > MAX_FOLDER_PATH_LENGTH:
        segments.pop()
    return "/".join(segments)


def folder_name(path: str) -> str:
    return path.rsplit("/", 1)[-1] if path else ""


def folder_parent(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


async def folder_tree(session: AsyncSession, tenant_id: int, kb_id: str) -> dict[str, Any]:
    await get_kb(session, tenant_id, kb_id)
    paths = await knowledge_repository.folder_paths(session, kb_id)

    counts: dict[str, int] = {path: 0 for path in paths}
    for path in paths:
        if path:
            counts[path] = await knowledge_repository.count_under_folder(
                session, kb_id, path, include_subtree=False
            )

    nodes: dict[str, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    children: dict[str, list[dict[str, Any]]] = {}

    def ensure(path: str) -> dict[str, Any]:
        if path in nodes:
            return nodes[path]
        node = {"path": path, "name": folder_name(path), "document_count": 0, "total_count": 0}
        nodes[path] = node
        parent = folder_parent(path)
        if parent:
            ensure(parent)
            children.setdefault(parent, []).append(node)
        else:
            roots.append(node)
        return node

    root_documents = await knowledge_repository.count_root_knowledge(session, kb_id)
    for path, count in counts.items():
        if not path:
            continue
        ensure(path)["document_count"] = count

    # 先汇总自身与后代数量（按路径深度倒序）
    for path in sorted(nodes, key=lambda item: (-item.count("/"), item)):
        node = nodes[path]
        node["total_count"] += node["document_count"]
        parent = folder_parent(path)
        if parent:
            nodes[parent]["total_count"] += node["total_count"]

    for path, items in children.items():
        nodes[path]["children"] = sorted(items, key=lambda item: item["name"].lower())
    for items in children.values():
        items.sort(key=lambda item: item["name"].lower())
    roots.sort(key=lambda item: item["name"].lower())

    total = await knowledge_repository.count_under_folder(session, kb_id, "", True)
    return {
        "root_document_count": root_documents,
        "total_document_count": total,
        "folders": roots,
    }


async def move_knowledge_to_folder(
    session: AsyncSession, tenant_id: int, kb_id: str, knowledge_ids: list[str], folder_path: str
) -> dict[str, Any]:
    await get_kb(session, tenant_id, kb_id)
    ids = list(dict.fromkeys(item.strip() for item in knowledge_ids if item.strip()))
    if not ids:
        raise bad_request("knowledge_ids cannot be empty")
    if len(ids) > 200:
        raise bad_request("too many ids (max 200 per batch)")

    items = await knowledge_repository.get_knowledge_in_kb(session, kb_id, ids)
    if len(items) != len(ids):
        raise bad_request("部分知识不存在或不属于该知识库")

    normalized = normalize_folder_path(folder_path)
    moved = await knowledge_repository.move_knowledge(session, kb_id, ids, normalized)
    await session.commit()
    return {"moved_count": moved, "folder_path": normalized}


async def rename_folder(
    session: AsyncSession, tenant_id: int, kb_id: str, from_path: str, to_path: str
) -> dict[str, Any]:
    await get_kb(session, tenant_id, kb_id)
    source = normalize_folder_path(from_path)
    target = normalize_folder_path(to_path)
    if not source:
        raise bad_request("from is required")
    if target.startswith(f"{source}/"):
        raise bad_request("不能把文件夹移动到自身的子目录")

    moved = await knowledge_repository.rename_folder(session, kb_id, source, target)
    await session.commit()
    return {"moved_count": moved, "folder_path": target}
