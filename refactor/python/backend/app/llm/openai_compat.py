"""OpenAI 兼容客户端（chat / embeddings / rerank）。

base_url 形如 `https://api.openai.com/v1`；兼容服务（DeepSeek、Qwen、Ollama 等）
只需替换 base_url 与 api_key。不做重试与降级，错误直接抛出交给上层。
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

import httpx

from app.core.config import get_settings
from app.core.errors import ERR_BAD_REQUEST, AppError
from app.domain.entities import Model
from app.llm.base import ChatMessage


class OpenAICompatibleClient:
    def __init__(self, model: Model, timeout: float = 60.0) -> None:
        self.model = model
        self.base_url = (model.base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = model.api_key
        self.timeout = timeout
        self.proxy = self._resolve_proxy()

    def _resolve_proxy(self) -> str | None:
        """代理优先级：模型参数 proxy → 环境变量 → .env 的 LLM_PROXY。"""
        candidates = [
            (self.model.parameters or {}).get("proxy"),
            os.environ.get("WEKNORA_LLM_PROXY"),
            get_settings().llm_proxy,
        ]
        for candidate in candidates:
            if candidate:
                return str(candidate)
        return None

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, proxy=self.proxy)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        extra = (self.model.parameters or {}).get("custom_headers") or {}
        headers.update({str(k): str(v) for k, v in extra.items()})
        return headers

    async def complete(self, messages: list[ChatMessage]) -> str:
        payload = {
            "model": self.model.name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
        }
        async with self._client() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=self._headers()
            )
        if response.status_code >= 400:
            raise AppError(
                ERR_BAD_REQUEST, f"chat completion failed: {response.text[:300]}", 502
            )
        data = response.json()
        return str(data["choices"][0]["message"]["content"])

    async def complete_with_tools(
        self, messages: list[ChatMessage], tools: list[dict]
    ) -> dict:
        """非流式 function calling。

        返回 `{"content": str, "tool_calls": [{"id","name","arguments":{}}], "finish_reason": str}`。
        `arguments` 已从 JSON 字符串解析为 dict，解析失败时置空。
        """
        payload = {
            "model": self.model.name,
            "messages": [
                {"role": m.role, "content": m.content} for m in messages
            ],
            "stream": False,
            "tools": tools,
            "tool_choice": "auto",
        }
        async with self._client() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=self._headers()
            )
        if response.status_code >= 400:
            raise AppError(
                ERR_BAD_REQUEST, f"chat completion failed: {response.text[:300]}", 502
            )
        data = response.json()
        message = data["choices"][0]["message"] or {}
        tool_calls: list[dict] = []
        for raw in message.get("tool_calls") or []:
            function = raw.get("function") or {}
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            tool_calls.append(
                {
                    "id": raw.get("id") or "",
                    "name": function.get("name") or "",
                    "arguments": arguments,
                }
            )
        return {
            "content": str(message.get("content") or ""),
            "tool_calls": tool_calls,
            "finish_reason": str(data["choices"][0].get("finish_reason") or ""),
        }

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        payload = {
            "model": self.model.name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }
        async with self._client() as client, client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=self._headers(),
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "ignore")
                raise AppError(
                    ERR_BAD_REQUEST, f"chat stream failed: {body[:300]}", 502
                )
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                if not chunk:
                    continue
                try:
                    delta = json.loads(chunk)["choices"][0].get("delta") or {}
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                content = delta.get("content")
                if content:
                    yield str(content)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.model.name, "input": texts}
        async with self._client() as client:
            response = await client.post(
                f"{self.base_url}/embeddings", json=payload, headers=self._headers()
            )
        if response.status_code >= 400:
            raise AppError(ERR_BAD_REQUEST, f"embedding failed: {response.text[:300]}", 502)
        data = response.json()["data"]
        data = sorted(data, key=lambda item: item.get("index", 0))
        return [list(map(float, item["embedding"])) for item in data]

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        """OpenAI 协议本身没有 rerank，这里按常见 `/rerank` 约定调用。

        未配置 rerank 服务时由上层跳过，不走到这里。
        """
        payload = {"model": self.model.name, "query": query, "documents": documents}
        async with self._client() as client:
            response = await client.post(
                f"{self.base_url}/rerank", json=payload, headers=self._headers()
            )
        if response.status_code >= 400:
            raise AppError(ERR_BAD_REQUEST, f"rerank failed: {response.text[:300]}", 502)
        results = response.json().get("results") or []
        scores = [0.0] * len(documents)
        for item in results:
            index = int(item.get("index", 0))
            if 0 <= index < len(scores):
                scores[index] = float(item.get("relevance_score", 0.0))
        return scores
