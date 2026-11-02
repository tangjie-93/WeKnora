"""本地 OpenAI 兼容假服务，仅用于阶段验收（不参与生产）。

- `POST /v1/chat/completions`：支持 stream / 非 stream，按固定模板回复
- `POST /v1/embeddings`：字符 uni/bi-gram 哈希向量，语义相近文本余弦更高
- `POST /v1/rerank`：按位置递减返回分数

启动方式：
    .\\.venv\\Scripts\\python.exe scripts\\fake_openai.py --port 9100
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

DIM = 64


def embed_text(text: str) -> list[float]:
    """确定性向量：相同/相近文本得到相近向量，便于离线验证检索链路。"""
    vector = [0.0] * DIM
    cleaned = "".join(ch for ch in text if not ch.isspace())
    tokens = list(cleaned) + [cleaned[i : i + 2] for i in range(len(cleaned) - 1)]
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % DIM
        vector[index] += 1.0 + digest[4] / 255.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 8) for value in vector]


def build_reply(messages: list[dict[str, Any]]) -> str:
    user = ""
    for message in reversed(messages):
        if message.get("role") == "user":
            user = str(message.get("content") or "")
            break
    if "pong" in user.lower():
        return "pong"
    return f"根据知识库资料，答案如下：{user[:40]}（引用资料[1]）"


def _last_user_query(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def _has_tool_result(messages: list[dict[str, Any]]) -> bool:
    return any(message.get("role") == "tool" for message in messages)


def build_tool_calls(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict | None:
    """离线模拟 ReAct：首轮返回一个 search_knowledge 工具调用，次轮返回最终答案。

    只要请求带了 tools 且历史里还没有 tool 结果，就返回一个工具调用；
    否则返回 None 表示由 build_reply 给出最终答案。
    """
    if not tools or _has_tool_result(messages):
        return None
    tool_name = "search_knowledge"
    names = {
        (t.get("function") or {}).get("name")
        for t in tools
        if t.get("type") == "function"
    }
    if "search_knowledge" in names:
        tool_name = "search_knowledge"
    elif names:
        tool_name = next(iter(names))
    query = _last_user_query(messages)
    return {
        "id": "call_fake_1",
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps({"query": query, "top_k": 3}, ensure_ascii=False),
        },
    }



app = FastAPI(title="fake-openai")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/v1/embeddings")
async def embeddings(request: Request) -> JSONResponse:
    body = await request.json()
    texts = body.get("input") or []
    if isinstance(texts, str):
        texts = [texts]
    data = [
        {"object": "embedding", "index": index, "embedding": embed_text(str(text))}
        for index, text in enumerate(texts)
    ]
    return JSONResponse({"object": "list", "data": data, "model": body.get("model") or "fake"})


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages") or []
    tools = body.get("tools") or []
    tool_call = build_tool_calls(messages, tools)
    reply = build_reply(messages)

    if not body.get("stream"):
        message: dict[str, Any] = {"role": "assistant", "content": reply}
        finish_reason = "stop"
        if tool_call is not None:
            message = {"role": "assistant", "content": "", "tool_calls": [tool_call]}
            finish_reason = "tool_calls"
        return JSONResponse(
            {
                "id": "chatcmpl-fake",
                "object": "chat.completion",
                "model": body.get("model") or "fake",
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": finish_reason,
                    }
                ],
            }
        )

    async def event_stream():
        for start in range(0, len(reply), 2):
            yield _sse(
                {
                    "id": "chatcmpl-fake",
                    "object": "chat.completion.chunk",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": reply[start : start + 2]},
                            "finish_reason": None,
                        }
                    ],
                }
            )
            await asyncio.sleep(0.005)
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/v1/rerank")
async def rerank(request: Request) -> JSONResponse:
    body = await request.json()
    documents = body.get("documents") or []
    results = [
        {"index": index, "relevance_score": round(1.0 - index * 0.1, 4)}
        for index in range(len(documents))
    ]
    return JSONResponse({"results": results})


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenAI 兼容假服务（仅验收用）")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    import uvicorn

    # 显式 Server + 关闭默认日志配置：Windows 下 `uvicorn.run` 在 stdout 被
    # 重定向（stage_check 子进程）时默认 logging 会卡住，导致端口迟迟不监听。
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
        access_log=False,
        log_config=None,
    )
    uvicorn.Server(config).run()


if __name__ == "__main__":
    main()
