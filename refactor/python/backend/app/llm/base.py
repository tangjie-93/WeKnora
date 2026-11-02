"""模型调用抽象：Chat / Embedding / Rerank。

与 Go 端 `internal/models` 的接口意图一致，但只实现 OpenAI 兼容协议，
其它厂商（DeepSeek / Qwen / Zhipu / Moonshot / Ollama）均可复用。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ChatMessage:
    role: str
    content: str


class ChatModel(Protocol):
    async def complete(self, messages: list[ChatMessage]) -> str: ...

    def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]: ...


class EmbeddingModel(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class RerankModel(Protocol):
    async def rerank(self, query: str, documents: list[str]) -> list[float]: ...
