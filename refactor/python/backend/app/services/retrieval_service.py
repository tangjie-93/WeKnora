"""检索服务：向量检索 + 关键词检索 + 混合排序（可选重排）。

SQLite 与 PostgreSQL 共用同一实现：向量以 JSON 存于 `chunks.metadata`，
相似度在 Python 内计算。阶段 4 之后切到 pgvector 只需替换 `_vector_search`。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import bad_request
from app.domain.entities import MODEL_TYPE_CHAT, MODEL_TYPE_EMBEDDING, Chunk
from app.llm import ChatMessage, OpenAICompatibleClient
from app.repositories import knowledge_repository, model_repository

VECTOR_WEIGHT = 0.7
KEYWORD_WEIGHT = 0.3


@dataclass
class SearchHit:
    chunk: Chunk
    score: float
    vector_score: float
    keyword_score: float

    def payload(self) -> dict:
        return {
            "id": self.chunk.id,
            "knowledge_id": self.chunk.knowledge_id,
            "knowledge_base_id": self.chunk.knowledge_base_id,
            "content": self.chunk.content,
            "chunk_index": self.chunk.chunk_index,
            "score": round(self.score, 6),
            "vector_score": round(self.vector_score, 6),
            "keyword_score": round(self.keyword_score, 6),
        }


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def tokenize(text: str) -> list[str]:
    try:
        import jieba

        return [token for token in jieba.cut(text) if token.strip()]
    except ImportError:
        return re.findall(r"[\w\u4e00-\u9fff]+", text.lower())


def keyword_score(query: str, content: str) -> float:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    content_tokens = tokenize(content)
    if not content_tokens:
        return 0.0
    hits = sum(1 for token in content_tokens if token in query_tokens)
    return min(1.0, hits / max(1, len(query_tokens)))


async def _embed_query(
    session: AsyncSession, tenant_id: int, model_id: str, query: str
) -> list[float]:
    model = None
    if model_id:
        candidate = await model_repository.get_model(session, tenant_id, model_id)
        if candidate is not None and candidate.type == MODEL_TYPE_EMBEDDING:
            model = candidate
    if model is None:
        model = await model_repository.first_of_type(session, tenant_id, MODEL_TYPE_EMBEDDING)
    if model is None:
        return []
    vectors = await OpenAICompatibleClient(model).embed([query])
    return vectors[0] if vectors else []


async def search(
    session: AsyncSession,
    tenant_id: int,
    kb_id: str,
    query: str,
    top_k: int = 8,
    embedding_model_id: str = "",
    rerank_model_id: str = "",
) -> list[SearchHit]:
    query = (query or "").strip()
    if not query:
        raise bad_request("query is required")

    top_k = max(1, min(top_k, 50))
    chunks = await knowledge_repository.list_kb_chunks(session, kb_id)
    if not chunks:
        return []

    query_vector = await _embed_query(session, tenant_id, embedding_model_id, query)

    hits: list[SearchHit] = []
    for chunk in chunks:
        vector_score = cosine(query_vector, chunk.embedding) if query_vector else 0.0
        text_score = keyword_score(query, chunk.content)
        score = VECTOR_WEIGHT * vector_score + KEYWORD_WEIGHT * text_score
        hits.append(SearchHit(chunk, score, vector_score, text_score))

    hits.sort(key=lambda item: item.score, reverse=True)
    hits = hits[:top_k]

    if rerank_model_id:
        rerank_model = await model_repository.get_model(session, tenant_id, rerank_model_id)
        if rerank_model is not None:
            scores = await OpenAICompatibleClient(rerank_model).rerank(
                query, [hit.chunk.content for hit in hits]
            )
            for hit, score in zip(hits, scores):
                hit.score = float(score)
            hits.sort(key=lambda item: item.score, reverse=True)

    return hits


async def build_prompt(
    session: AsyncSession,
    tenant_id: int,
    query: str,
    hits: list[SearchHit],
    history: list[tuple[str, str]],
    chat_model_id: str,
) -> str:
    """把引用片段与历史拼成最终答案（非流式，供测试与降级使用）。"""
    model = await model_repository.get_model(session, tenant_id, chat_model_id)
    if model is None:
        model = await model_repository.first_of_type(session, tenant_id, MODEL_TYPE_CHAT)
    if model is None:
        raise bad_request("no chat model configured")

    messages = build_messages(query, hits, history)
    return await OpenAICompatibleClient(model).complete(messages)


def build_messages(
    query: str, hits: list[SearchHit], history: list[tuple[str, str]]
) -> list[ChatMessage]:
    context = "\n\n".join(
        f"[{index + 1}] {hit.chunk.content}" for index, hit in enumerate(hits)
    )
    system = (
        "你是 WeKnora 知识库助手。只根据提供的资料回答，资料没有的信息明确说明不知道，"
        "回答中可用 [序号] 标注引用来源。资料：\n" + (context or "（无相关资料）")
    )
    messages = [ChatMessage(role="system", content=system)]
    for role, content in history[-6:]:
        messages.append(ChatMessage(role=role, content=content))
    messages.append(ChatMessage(role="user", content=query))
    return messages
