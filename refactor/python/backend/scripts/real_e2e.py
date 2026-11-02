"""真实大模型全链路验收（DeepSeek + ChatGPT + OpenAI Embedding）。

与 `stage_check.py` 的区别：这里**不依赖本地假 OpenAI**，模型通过 `/api/v1/models`
接口写入真实 base_url / api_key，所有调用都打到真实上游。

用法：
    .\\.venv\\Scripts\\python.exe scripts\\real_e2e.py
    .\\.venv\\Scripts\\python.exe scripts\\real_e2e.py --chat-only

前置条件：`python/backend/.env` 中至少填写 LLM_CHAT_API_KEY（DeepSeek），
以及 LLM_EMBEDDING_API_KEY + LLM_CHAT2_API_KEY（OpenAI）才能跑完整链路。

流程（每步失败即记录并终止，退出码 1）：
    1. 健康检查 → 注册登录
    2. 通过 API 创建 DeepSeek chat / ChatGPT chat / OpenAI embedding 三个模型
    3. 逐个调用 `/models/{id}/test`，校验真实回复与向量维度
    4. 建知识库 → 上传样例文档 → 解析分块 → 真实 embedding 落库
    5. 直连 SQLite 校验 chunks.metadata.embedding 维度
    6. 混合检索校验向量分不为 0
    7. DeepSeek 默认模型 SSE 问答，校验事件序列 / 回答 / 引用
    8. 切换默认为 ChatGPT，再答一次，校验 message.model_id 落库
    9. 输出 tests/contract/real_model_report.md
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from stage_check import DATA_DIR, REPORT_DIR, Server

from app.core.config import get_settings

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = DATA_DIR / "real_e2e.db"
REPORT_PATH = REPORT_DIR / "real_model_report.md"
PASSWORD = "Abcdef12"

SAMPLE_TEXT = (
    "WeKnora 验收样例文档\n\n"
    "Nebula 模块负责知识入库：上传文档后会自动解析、分块并写入向量索引。\n\n"
    "Nebula 的默认端口是 8080，管理后台通过 /swagger/index.html 访问。\n\n"
    "部署时需要 PostgreSQL 存储业务数据，Redis 用于缓存与任务队列。\n"
)


class Steps:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self.started = time.time()

    def run(self, key: str, name: str, fn) -> None:
        print(f"[RUN ] {name}")
        begin = time.time()
        try:
            detail = fn()
            self.items.append(
                {"key": key, "name": name, "ok": True, "detail": str(detail), "cost": time.time() - begin}
            )
            print(f"[PASS] {name} -> {detail} ({time.time() - begin:.1f}s)")
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            self.items.append(
                {"key": key, "name": name, "ok": False, "detail": detail, "cost": time.time() - begin}
            )
            print(f"[FAIL] {name} -> {detail}")
            traceback.print_exc()
            raise

    @property
    def passed(self) -> int:
        return sum(1 for item in self.items if item["ok"])


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_ok(response: httpx.Response, code: int = 200) -> dict:
    if response.status_code != code:
        raise AssertionError(f"expected {code}, got {response.status_code}: {response.text[:300]}")
    return response.json()


def parse_sse(response: httpx.Response) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in response.iter_lines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        events.append(json.loads(payload))
    return events


def chat_stream(
    client: httpx.Client, headers: dict[str, str], session_id: str, query: str
) -> list[dict[str, Any]]:
    with client.stream(
        "POST",
        f"/api/v1/knowledge-chat/{session_id}",
        headers=headers,
        json={"query": query},
        timeout=180.0,
    ) as response:
        if response.status_code != 200:
            response.read()
            raise AssertionError(f"chat failed {response.status_code}: {response.text[:300]}")
        return parse_sse(response)


def read_db_rows(query: str) -> list[tuple]:
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(query).fetchall()
    finally:
        conn.close()


def write_report(steps: Steps, model_info: dict[str, str], failed: bool) -> None:
    total = len(steps.items)
    lines = [
        "# 真实大模型全链路验收报告",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 验收库：`data/{DB_PATH.name}`",
        f"- 结果：**{steps.passed}/{total} 通过**",
        f"- 总耗时：{time.time() - steps.started:.1f}s",
        "",
        "## 模型清单",
        "",
        "| 类型 | 模型 | base_url |",
        "|---|---|---|",
    ]
    for name, url in model_info.items():
        lines.append(f"| {name} | {url} |")
    lines += ["", "## 步骤明细", "", "| # | 步骤 | 结果 | 耗时 | 详情 |", "|---|---|---|---|---|"]
    for index, item in enumerate(steps.items, start=1):
        status = "通过" if item["ok"] else "失败"
        detail = item["detail"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {index} | {item['name']} | {status} | {item['cost']:.1f}s | {detail[:200]} |")
    if failed:
        lines += ["", "> 失败后流程已终止；修复后重跑 `scripts/real_e2e.py`。"]
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report written: {REPORT_PATH}")


def main() -> int:
    parser = argparse.ArgumentParser(description="真实模型全链路验收")
    parser.add_argument("--chat-only", action="store_true", help="只验收对话模型，不做入库/检索")
    args = parser.parse_args()

    settings = get_settings()
    deepseek_ready = bool(settings.llm_chat_base_url and settings.llm_chat_model and settings.llm_chat_api_key)
    embedding_ready = bool(
        settings.llm_embedding_base_url and settings.llm_embedding_model and settings.llm_embedding_api_key
    )
    if not deepseek_ready:
        print("请先在 python/backend/.env 填写 LLM_CHAT_*（DeepSeek）后重试")
        return 2
    if not args.chat_only and not embedding_ready:
        print("完整链路需要 LLM_EMBEDDING_*（OpenAI embedding）的 key；只测对话可加 --chat-only")
        return 2

    steps = Steps()
    model_info: dict[str, str] = {}
    failed = True

    with Server(DB_PATH) as server:
        client = httpx.Client(base_url=server.base_url, timeout=120.0)
        state: dict[str, Any] = {}

        def health() -> str:
            expect_ok(client.get("/health"))
            return server.base_url

        def auth() -> str:
            expect_ok(
                client.post(
                    "/api/v1/auth/register",
                    json={"username": "realowner", "email": "real@example.com", "password": PASSWORD},
                ),
                201,
            )
            login = expect_ok(
                client.post("/api/v1/auth/login", json={"email": "real@example.com", "password": PASSWORD})
            )
            state["headers"] = {
                "Authorization": f"Bearer {login['token']}",
                "X-Tenant-ID": str(login["active_tenant"]["id"]),
            }
            return f"tenant={login['active_tenant']['id']}"

        def create_models() -> str:
            headers = state["headers"]
            specs = [
                (
                    "deepseek-chat",
                    settings.llm_chat_model,
                    settings.llm_chat_base_url,
                    settings.llm_chat_api_key,
                    True,
                    None,
                ),
                (
                    "chatgpt",
                    settings.llm_chat2_model,
                    settings.llm_chat2_base_url,
                    settings.llm_chat2_api_key,
                    False,
                    None,
                ),
            ]
            if not args.chat_only:
                specs.append(
                    (
                        "embedding",
                        settings.llm_embedding_model,
                        settings.llm_embedding_base_url,
                        settings.llm_embedding_api_key,
                        True,
                        settings.llm_embedding_dimension,
                    )
                )
            created: dict[str, dict[str, Any]] = {}
            for label, name, base_url, api_key, is_default, dimension in specs:
                if not (base_url and name):
                    continue
                model_type = "embedding" if label == "embedding" else "chat"
                parameters: dict[str, Any] = {"base_url": base_url, "api_key": api_key}
                if dimension:
                    parameters["embedding_parameters"] = {"dimension": dimension}
                data = expect_ok(
                    client.post(
                        "/api/v1/models",
                        headers=headers,
                        json={
                            "name": name,
                            "display_name": label,
                            "type": model_type,
                            "is_default": is_default,
                            "parameters": parameters,
                        },
                    ),
                    201,
                )["data"]
                created[label] = data
                model_info[label] = f"{name} @ {base_url}"
            state["models"] = created
            return "、".join(f"{label}={item['id'][:8]}" for label, item in created.items())

        def test_models() -> str:
            headers = state["headers"]
            details = []
            for label, model in state["models"].items():
                result = expect_ok(client.post(f"/api/v1/models/{model['id']}/test", headers=headers))["data"]
                expect(result.get("ok") is True, f"{label} 连通性返回异常: {result}")
                if model["type"] == "embedding":
                    expect(
                        result.get("dimension") == settings.llm_embedding_dimension,
                        f"embedding 维度 {result.get('dimension')} != {settings.llm_embedding_dimension}",
                    )
                    details.append(f"{label}:dim={result['dimension']}")
                else:
                    expect(bool(result.get("reply")), f"{label} 无回复: {result}")
                    details.append(f"{label}:{str(result['reply'])[:24]}")
            return "，".join(details)

        def create_kb() -> str:
            payload: dict[str, Any] = {"name": "真实模型验收库", "description": "real_e2e"}
            if "embedding" in state["models"]:
                payload["embedding_model_id"] = state["models"]["embedding"]["id"]
            data = expect_ok(
                client.post("/api/v1/knowledge-bases", headers=state["headers"], json=payload), 201
            )["data"]
            state["kb_id"] = data["id"]
            return f"kb={data['id']} embedding_model={data['embedding_model_id'][:8]}"

        def upload_doc() -> str:
            data = expect_ok(
                client.post(
                    f"/api/v1/knowledge-bases/{state['kb_id']}/knowledge/file",
                    headers=state["headers"],
                    files={"file": ("e2e_sample.txt", SAMPLE_TEXT.encode("utf-8"), "text/plain")},
                    timeout=180.0,
                ),
                201,
            )["data"]
            expect(data["parse_status"] == "completed", f"解析状态 {data['parse_status']}: {data['error_message']}")
            state["knowledge_id"] = data["id"]
            chunks = expect_ok(
                client.get(f"/api/v1/chunks/{data['id']}", headers=state["headers"])
            )["data"]
            expect(len(chunks) > 0, "分块数为 0")
            state["chunk_count"] = len(chunks)
            return f"chunks={len(chunks)}"

        def verify_vectors() -> str:
            rows = read_db_rows(
                f"select metadata from chunks where knowledge_id = '{state['knowledge_id']}'"
            )
            expect(len(rows) > 0, "chunks 表无记录")
            dims = set()
            for (raw,) in rows:
                meta = json.loads(raw)
                dims.add(len(meta.get("embedding") or []))
            expected = settings.llm_embedding_dimension
            expect(dims == {expected}, f"向量维度 {dims} != {expected}")
            return f"{len(rows)} 行，维度={expected}"

        def hybrid_search() -> str:
            hits = expect_ok(
                client.post(
                    f"/api/v1/knowledge-bases/{state['kb_id']}/hybrid-search",
                    headers=state["headers"],
                    json={"query": "Nebula 默认端口是多少", "top_k": 3},
                )
            )["data"]
            expect(len(hits) > 0, "混合检索无结果")
            expect(hits[0]["vector_score"] > 0, f"向量分为 0：{hits[0]}")
            return f"top={hits[0]['content'][:30]!r} score={hits[0]['score']}"

        def ask(question: str, label: str) -> dict[str, Any]:
            session_payload: dict[str, Any] = {"title": f"真实问答-{label}"}
            if state.get("kb_id"):
                session_payload["knowledge_base_id"] = state["kb_id"]
            session = expect_ok(
                client.post(
                    "/api/v1/sessions",
                    headers=state["headers"],
                    json=session_payload,
                ),
                201,
            )["data"]
            state[f"session_{label}"] = session["id"]
            events = chat_stream(client, state["headers"], session["id"], question)
            state[f"events_{label}"] = events
            types = [event["response_type"] for event in events]
            expected = ["agent_query", "references", "answer", "complete"]
            expect(types[0] == "agent_query", f"首个事件 {types[0]} != agent_query")
            expect("complete" in types, f"缺少 complete 事件: {types}")
            expect("error" not in types, f"SSE 报错: {[e['data'] for e in events if e['response_type'] == 'error']}")
            complete = next(event for event in events if event["response_type"] == "complete")
            answer = str(complete["data"].get("content") or "")
            expect(len(answer.strip()) > 0, "回答为空")
            if state.get("kb_id"):
                expect("references" in types, f"缺少 references 事件: {types}")
                expect(
                    len(complete["data"].get("knowledge_references") or []) > 0, "引用为空"
                )
            state[f"answer_{label}"] = answer
            state[f"message_{label}"] = complete["data"].get("message_id")
            return {
                "answer": answer,
                "types": types,
                "duration_ms": complete["data"].get("total_duration_ms"),
                "events": len(events),
                "expected": expected,
            }

        def ask_deepseek() -> str:
            result = ask("Nebula 的默认端口是多少？请用一句话回答并标注引用。", "deepseek")
            if state.get("kb_id"):
                expect("8080" in result["answer"], f"DeepSeek 回答未包含 8080: {result['answer'][:120]}")
            return f"{result['duration_ms']}ms，{result['events']} 事件，答：{result['answer'][:40]}"

        def ask_chatgpt() -> str:
            chatgpt = state["models"].get("chatgpt")
            if not chatgpt:
                return "未配置 LLM_CHAT2_*，跳过"
            expect_ok(
                client.put(
                    f"/api/v1/models/{chatgpt['id']}",
                    headers=state["headers"],
                    json={"is_default": True},
                )
            )
            if state.get("kb_id"):
                result = ask("文档部署需要哪两个基础设施？请用一句话回答并标注引用。", "chatgpt")
                expect(
                    "PostgreSQL" in result["answer"] and "Redis" in result["answer"],
                    f"ChatGPT 回答未提到 PostgreSQL/Redis: {result['answer'][:120]}",
                )
            else:
                result = ask("请用一句话介绍你自己。", "chatgpt")
            default_models = expect_ok(client.get("/api/v1/models", headers=state["headers"]))["data"]
            default_chat = next(
                item for item in default_models if item["type"] == "chat" and item["is_default"]
            )
            expect(default_chat["id"] == chatgpt["id"], "默认对话模型切换失败")
            return f"{result['duration_ms']}ms，答：{result['answer'][:40]}"

        def verify_messages() -> str:
            rows = read_db_rows("select role, length(content), model_id from messages")
            expect(len(rows) == 4, f"messages 行数 {len(rows)} != 4")
            model_ids = {row[2] for row in rows if row[0] == "assistant"}
            expect(len(model_ids) >= 1 and all(model_ids), f"assistant 消息未记录 model_id: {model_ids}")
            references = read_db_rows("select knowledge_references from messages where role='assistant'")
            expect(any(json.loads(raw or "[]") for (raw,) in references), "引用未落库")
            return f"{len(rows)} 条消息，assistant models={len(model_ids)}"

        plan: list[tuple[str, str, Any]] = [
            ("health", "健康检查", health),
            ("auth", "注册登录", auth),
            ("models", "创建真实模型", create_models),
            ("models_test", "模型连通性", test_models),
        ]
        if not args.chat_only:
            plan += [
                ("kb", "创建知识库", create_kb),
                ("upload", "上传解析+真实向量化", upload_doc),
                ("vectors", "落库校验向量维度", verify_vectors),
                ("search", "混合检索", hybrid_search),
                ("chat_deepseek", "DeepSeek SSE 问答", ask_deepseek),
                ("chat_chatgpt", "ChatGPT SSE 问答", ask_chatgpt),
                ("messages", "消息与引用落库", verify_messages),
            ]
        else:
            plan += [
                ("chat_deepseek", "DeepSeek SSE 问答", ask_deepseek),
                ("chat_chatgpt", "ChatGPT SSE 问答", ask_chatgpt),
            ]

        try:
            for key, name, fn in plan:
                steps.run(key, name, fn)
            failed = False
        except Exception:  # noqa: BLE001 - 失败已记录，写报告后退出
            failed = True
        finally:
            write_report(steps, model_info, failed)
            client.close()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
