# WeKnora Python 全栈重构逐步实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`，按任务逐项实现。每个任务都用复选框追踪，并在独立验证通过后提交。

**Goal:** 从当前可见的 `integration-web` 和历史 `WeKnora` 契约出发，自己逐步实现一个由 `Python` 后端驱动、保持 `/api/v1` 兼容、可以完成“登录 → 建库 → 上传 → 检索 → 对话 → Agent”的可运行系统。

**Architecture:** 后端使用 `FastAPI` 接收请求，按 `route → dependency → service → repository/integration` 分层；数据库使用 `SQLAlchemy 2` 异步访问，长任务使用 `Redis + ARQ`，聊天使用 `SSE`。前端先继续使用 `integration-web`，每完成一个后端域就用真实页面和 `curl` 验证，再逐步补齐生产能力。

**Tech Stack:** `Python 3.12+`、`FastAPI`、`Pydantic Settings`、`SQLAlchemy 2 async`、`Alembic` 或兼容现有迁移表的迁移器、`PostgreSQL`、`SQLite`、`Redis`、`ARQ`、`PyJWT`、`httpx`、`pytest`、`Vue 3`、`TypeScript`、`Vite`、`Pinia`。

**Spec:** [Python 后端技术架构与迁移指南](./architecture/Python后端技术架构与从0到1迁移指南.md)、[前端技术架构与从 `0` 到 `1` 实现指南](./architecture/frontend从0到1实现指南.md)、[前端知识点与可迁移能力梳理](./analysis/frontend-knowledge-map.md)、[前后端实现清单](./progress/前后端实现清单.md)、[Python 后端重构进度管理](./progress/Python后端重构进度管理.md)。

## 全局约束

- 工作目录以 `/Users/james/Desktop/github/WeKnora/refactor` 为学习和实现目录。
- 当前工作树里 `python/` 相对 `HEAD` 处于删除状态；计划把历史 `python/backend` 和 `python/frontend` 当作参考基线，不把历史“已实现”数字当作当前源码事实。
- 所有外部请求继续使用 `/api/v1` 前缀；不要先改前端路径来掩盖后端缺口。
- 所有需要租户隔离的数据查询都必须带 `tenant_id`；不能依赖调用方自己过滤。
- 路由不得直接写 SQL；路由只做参数接收、依赖注入、调用 service 和返回响应。
- 每一个业务阶段都必须同时有 `schema`、`service`、`repository`、自动化测试和一个可执行验收命令。
- 新增密码、Token、模型密钥、对象存储凭据只能来自环境变量或密钥管理器，不能写进源码、示例页面或提交记录。
- `SSE`、文件上传、解析任务、Agent 工具调用必须单独验收，不能用普通 `CRUD` 的 `200` 响应替代。
- 每完成一个任务先运行对应测试，再运行全量测试；测试通过后提交一个小 commit。
- 暂不引入微服务、`GraphQL`、事件总线或新的前端组件库；只有出现容量或隔离证据时再拆分。

## 1. 先理解当前工作树和历史基线

### Task 0: 建立可回滚的学习分支

**Files:**

- Create: `docs/notes/baseline-2026-11-03.md`
- Read: `integration-web/src/api.ts`
- Read: `integration-web/src/types/api.ts`
- Read: `integration-web/openapi.json`
- Read: `docs/progress/前后端实现清单.md`
- Read: `docs/progress/Python后端重构进度管理.md`

**Interfaces:**

- Consumes: 当前 `integration-web` 的请求路径、请求体、响应类型和流式事件。
- Produces: 一份“当前工作树事实”和“历史文档事实”分开的基线记录。

- [ ] **Step 1: 确认 Git 根目录和未提交变更**

```bash
cd /Users/james/Desktop/github/WeKnora/refactor
git rev-parse --show-toplevel
git status --short
```

如果 `python/` 显示为删除，先创建分支并保存状态：

```bash
git switch -c learn/python-rebuild
git diff --stat > docs/notes/baseline-diff.txt
```

- [ ] **Step 2: 只读恢复历史 Python 参考代码**

把历史代码恢复到当前工作树，作为对照和测试来源；实现时逐模块重写，不直接复制业务实现：

```bash
git restore --source=HEAD -- python
```

如果你明确要从空目录开始，保留这一步产生的文件作为参考，不修改它们，另建 `python/backend-rebuild`；推荐先恢复到 `python/backend`，因为现有契约测试可以减少遗漏。

- [ ] **Step 3: 生成接口清单**

```bash
find integration-web/src -type f | sort
rg -n "fetch\(|XMLHttpRequest|/api/v1|streamChat|knowledge-chat|agent-chat" integration-web/src
python - <<'PY'
import json
from pathlib import Path
spec = json.loads(Path('integration-web/openapi.json').read_text())
print('routes:', len(spec.get('paths', {})))
for path, methods in sorted(spec.get('paths', {}).items()):
    print(','.join(methods.keys()).upper(), path)
PY
```

- [ ] **Step 4: 写入基线记录**

`docs/notes/baseline-2026-11-03.md` 至少记录：

1. 当前前端真实调用的路径、方法、请求体和响应解包规则。
2. `SSE` 事件名：`answer`、`references`、`tool_call`、`tool_result`、`complete`、`error`。
3. 当前前端默认后端地址和鉴权头。
4. 历史文档中的 Python 路由数字只作为历史快照，不作为完成证明。
5. `integration-web/src/embed.ts` 中凭据参数的安全整改项。

- [ ] **Step 5: 验证并提交**

```bash
git diff --check
git add docs/notes/baseline-2026-11-03.md
git commit -m "docs: freeze rebuild baseline"
```

**完成标准:** 你能说清楚当前页面调用了哪些后端接口，并知道哪些文件来自历史基线、哪些是当前真实代码。

## 2. 搭建 Python 服务最小骨架

### Task 1: FastAPI 启动、配置、日志和错误

**Files:**

- Create/Modify: `python/backend/pyproject.toml`
- Create: `python/backend/app/main.py`
- Create: `python/backend/app/core/config.py`
- Create: `python/backend/app/core/logging.py`
- Create: `python/backend/app/core/errors.py`
- Create: `python/backend/app/core/middleware.py`
- Create: `python/backend/app/api/v1/router.py`
- Create: `python/backend/tests/unit/test_health.py`

**Interfaces:**

- Produces: `create_app() -> FastAPI`。
- Produces: `GET /health -> {"status": "ok"}`。
- Produces: 统一错误结构 `{"success": false, "error": {"code": int, "message": str}}`。
- Produces: 每个请求都有 `X-Request-ID` 响应头。

- [ ] **Step 1: 写失败测试**

```python
from fastapi.testclient import TestClient
from app.main import create_app

def test_health_returns_request_id():
    response = TestClient(create_app()).get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
    assert response.headers['X-Request-ID']
```

- [ ] **Step 2: 安装并运行测试确认失败**

```bash
cd python/backend
uv sync
uv run pytest tests/unit/test_health.py -q
```

预期：因为 `app.main` 或 `/health` 尚未存在而失败。

- [ ] **Step 3: 实现最小应用**

`config.py` 定义 `Settings`：`APP_ENV`、`DATABASE_URL`、`JWT_SECRET`、`JWT_EXPIRE_MINUTES`、`CORS_ORIGINS`、`REDIS_URL`。所有默认值只能用于本地开发，生产缺失密钥时启动失败。

`main.py` 实现：

```python
from fastapi import FastAPI

def create_app() -> FastAPI:
    app = FastAPI(title='WeKnora API', version='0.1.0')
    app.include_router(api_router, prefix='/api/v1')
    app.add_api_route('/health', health, methods=['GET'])
    return app
```

中间件顺序固定为：请求 ID → CORS → 访问日志 → 统一异常处理。

- [ ] **Step 4: 运行验证**

```bash
uv run pytest tests/unit/test_health.py -q
uv run uvicorn app.main:create_app --factory --reload --port 8080
curl -i http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/openapi.json | python -m json.tool | head -40
```

- [ ] **Step 5: 提交**

```bash
git add python/backend
git commit -m "feat: bootstrap python api"
```

**完成标准:** 服务可启动、`/health` 可访问、异常和请求 ID 可观察，且没有把业务逻辑写入 `main.py`。

## 3. 建立数据库和迁移安全边界

### Task 2: SQLAlchemy 异步会话、迁移和基础实体

**Files:**

- Create: `python/backend/app/core/database.py`
- Create: `python/backend/app/core/migrations.py`
- Create: `python/backend/app/domain/entities/base.py`
- Create: `python/backend/app/domain/entities/tenant.py`
- Create: `python/backend/app/domain/entities/user.py`
- Create: `python/backend/app/domain/entities/model.py`
- Create: `python/backend/tests/unit/test_database.py`
- Create: `python/backend/tests/contract/test_migrations.py`

**Interfaces:**

- Produces: `get_db() -> AsyncIterator[AsyncSession]`。
- Produces: `run_migrations() -> None`。
- Produces: `Tenant`、`User`、`Model` 三个最小实体。
- Produces: 迁移状态与 Go 侧 `schema_migrations(version, dirty)` 兼容。

- [ ] **Step 1: 先检查旧表和迁移格式**

```bash
rg -n "schema_migrations|CREATE TABLE|tenant|users|models" python server-deploy docs
find . -path '*migrations*' -type f | sort
```

把已有数据库字段写入 `docs/notes/database-contract.md`，每个字段记录类型、是否为空、默认值、索引和租户归属。

- [ ] **Step 2: 写数据库测试**

测试至少覆盖：内存 `SQLite` 建表、事务回滚、重复迁移不重复执行、`dirty` 状态阻止启动。

- [ ] **Step 3: 实现会话工厂**

创建 `async_sessionmaker`，请求结束后关闭 session；不要把 session 放进全局可变变量。实体继承同一个 `Base`，所有时间使用带时区的 `datetime`。

- [ ] **Step 4: 运行两个数据库验证**

```bash
uv run pytest tests/unit/test_database.py tests/contract/test_migrations.py -q
DATABASE_URL=sqlite+aiosqlite:///./var/test.db uv run python -m app.core.migrations
DATABASE_URL="$POSTGRES_TEST_URL" uv run python -m app.core.migrations
```

- [ ] **Step 5: 提交**

```bash
git add python/backend docs/notes/database-contract.md
git commit -m "feat: add async database foundation"
```

**完成标准:** 空数据库和已有数据库都能安全启动；迁移失败会停止服务，不会静默跳过或改写旧数据。

## 4. 先完成鉴权和租户隔离

### Task 3: 注册、登录、刷新、退出和当前用户

**Files:**

- Create/Modify: `python/backend/app/api/v1/deps.py`
- Create: `python/backend/app/api/v1/routes/auth.py`
- Create: `python/backend/app/api/v1/schemas/auth.py`
- Create: `python/backend/app/core/security.py`
- Create: `python/backend/app/core/context.py`
- Create: `python/backend/app/repositories/user_repository.py`
- Create: `python/backend/app/repositories/tenant_repository.py`
- Create: `python/backend/app/repositories/token_repository.py`
- Create: `python/backend/app/services/auth_service.py`
- Create: `python/backend/tests/unit/test_security.py`
- Create: `python/backend/tests/e2e/test_auth_flow.py`

**Interfaces:**

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `get_current_user()` 和 `get_auth_context()` 供所有受保护路由复用。

- [ ] **Step 1: 固定 Token claims**

至少包含 `sub`、`tenant_id`、`token_type`、`iat`、`exp`、`jti`。刷新 Token 使用轮换策略；旧 Token 不能在刷新成功后继续有效。

- [ ] **Step 2: 先写失败边界测试**

测试错误密码、弱密码、过期 Token、错误签名、重复刷新和缺少 `X-Tenant-ID`。每个失败响应都检查状态码和错误结构。

- [ ] **Step 3: 实现安全函数**

实现 `hash_password()`、`verify_password()`、`create_access_token()`、`create_refresh_token()`、`decode_token()`。密码哈希使用 `argon2` 或 `bcrypt`，禁止保存明文密码。

- [ ] **Step 4: 实现依赖和服务**

`get_auth_context()` 从 `Authorization` 解析用户，再校验 `X-Tenant-ID` 是否属于该用户；repository 查询必须把用户和租户条件一起下推到 SQL。

- [ ] **Step 5: 运行端到端验证**

```bash
uv run pytest tests/unit/test_security.py tests/e2e/test_auth_flow.py -q
curl -s -X POST http://127.0.0.1:8080/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo","email":"demo@example.com","password":"StrongPass123!"}'
curl -s -X POST http://127.0.0.1:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"StrongPass123!"}'
```

- [ ] **Step 6: 提交**

```bash
git add python/backend
git commit -m "feat: add tenant-aware authentication"
```

**完成标准:** 前端可以登录、刷新和退出；任意租户外资源访问都会返回同一种授权错误，不泄露资源是否存在。

## 5. 接入模型网关

### Task 4: 模型配置、OpenAI-compatible 客户端和连通性测试

**Files:**

- Create: `python/backend/app/domain/entities/model.py`
- Create: `python/backend/app/repositories/model_repository.py`
- Create: `python/backend/app/services/model_service.py`
- Create: `python/backend/app/llm/base.py`
- Create: `python/backend/app/llm/openai_compat.py`
- Create: `python/backend/app/api/v1/routes/models.py`
- Create: `python/backend/tests/e2e/test_models_api.py`
- Create: `python/backend/tests/fakes/fake_openai.py`

**Interfaces:**

- `GET/POST/PUT/DELETE /api/v1/models`
- `POST /api/v1/models/{id}/test`
- `ModelProvider.chat()`、`embed()`、`rerank()`。

- [ ] **Step 1: 写模型配置和密钥隔离测试**

断言 API 响应不会返回完整 `api_key`；日志中不能出现密钥；默认模型按租户和模型类型唯一。

- [ ] **Step 2: 实现模型实体和 CRUD**

参数保存为 JSON，模型状态保存为可解释的字符串；服务层负责默认模型唯一性和类型校验。

- [ ] **Step 3: 实现统一模型接口**

接口至少包含：`chat(messages, stream)`、`embed(texts)`、`rerank(query, documents)`。超时、非 `2xx`、无效 JSON 和上游流中断统一转换成内部异常。

- [ ] **Step 4: 使用 fake provider 验证**

```bash
OPENAI_BASE_URL=http://127.0.0.1:8090/v1 \
uv run pytest tests/e2e/test_models_api.py -q
```

- [ ] **Step 5: 从前端验证模型页**

```bash
cd integration-web
pnpm install --frozen-lockfile
pnpm run build
```

**完成标准:** 可以在前端创建模型、测试连接；模型密钥不会出现在响应和日志中；上游失败可被页面显示。

## 6. 实现知识库和基础资源

### Task 5: 知识库、标签、文件夹和删除边界

**Files:**

- Create: `python/backend/app/domain/entities/knowledge.py`
- Create: `python/backend/app/domain/entities/tag.py`
- Create: `python/backend/app/repositories/knowledge_repository.py`
- Create: `python/backend/app/repositories/tag_repository.py`
- Create: `python/backend/app/services/knowledge_service.py`
- Create: `python/backend/app/services/tag_service.py`
- Create: `python/backend/app/api/v1/routes/knowledge.py`
- Create: `python/backend/app/api/v1/routes/tags.py`
- Create: `python/backend/tests/e2e/test_knowledge_api.py`
- Create: `python/backend/tests/e2e/test_tags_api.py`

**Interfaces:**

- `GET/POST/PUT/DELETE /api/v1/knowledge-bases`
- `GET /api/v1/knowledge-bases/{kb_id}/knowledge`
- `GET/POST/PUT/DELETE /api/v1/knowledge-bases/{kb_id}/tags`
- `GET/POST/PUT /api/v1/knowledge-bases/{kb_id}/knowledge/folders`
- `DELETE /api/v1/knowledge/{knowledge_id}`。

- [ ] **Step 1: 建立数据模型和索引**

为 `knowledge_base_id`、`tenant_id`、`folder_path`、`tag_id`、`parse_status` 建索引；删除知识库前检查仍在运行的任务。

- [ ] **Step 2: 写两个租户隔离测试**

租户 `A` 创建的知识库不能被租户 `B` 列表、读取、修改或删除；不存在和无权限使用同一外部错误语义。

- [ ] **Step 3: 实现 CRUD 和分页**

分页参数统一为 `page`、`page_size`；响应统一决定是 `{data: ...}` 还是裸数组，并记录在契约文档中。不要在每个路由里自行解包。

- [ ] **Step 4: 实现标签和文件夹操作**

标签更新支持批量绑定；文件夹移动必须校验目标路径不形成自身子树；删除操作默认软删除或进入任务，直到数据恢复策略明确。

- [ ] **Step 5: 前端闭环**

使用 `integration-web` 完成：创建知识库 → 列表显示 → 创建标签 → 刷新页面仍存在 → 删除后不可见。

- [ ] **Step 6: 提交**

```bash
git add python/backend integration-web
 git commit -m "feat: add knowledge base resources"
```

**完成标准:** 知识库、标签、文件夹的读写和租户边界稳定，页面不需要特殊分支才能调用 Python API。

## 7. 做好上传、解析和后台任务

### Task 6: 文件上传、文档解析、分块、向量化和任务状态

**Files:**

- Create: `python/backend/app/domain/entities/knowledge.py` 中的文档和任务实体
- Create: `python/backend/app/integrations/docreader/client.py`
- Create: `python/backend/app/integrations/docreader/parser.py`
- Create: `python/backend/app/storage/local.py`
- Create: `python/backend/app/tasks/queue.py`
- Create: `python/backend/app/tasks/knowledge_tasks.py`
- Modify: `python/backend/app/api/v1/routes/knowledge.py`
- Create: `python/backend/tests/e2e/test_upload_flow.py`

**Interfaces:**

- `POST /api/v1/knowledge-bases/{kb_id}/knowledge/file`
- `POST /api/v1/knowledge/{id}/reparse`
- `GET /api/v1/knowledge-bases/{kb_id}/knowledge`
- `GET /api/v1/tasks/{task_id}`
- `DELETE /api/v1/tasks/{task_id}`。

- [ ] **Step 1: 先让上传请求安全落盘**

检查文件名、大小、内容类型和租户目录；使用临时文件写完后原子替换，避免进程中断留下半文件。

- [ ] **Step 2: 写上传失败测试**

覆盖空文件、超限、非法扩展名、重复上传、磁盘写失败、解析异常和取消任务。确保失败后状态为 `failed`，并保留可读错误。

- [ ] **Step 3: 复用 `docreader` 协议**

先保留现有独立解析服务，通过 adapter 调用；adapter 返回统一的 `ParsedDocument(text, metadata, pages)`，路由不感知 `gRPC` 细节。

- [ ] **Step 4: 实现任务状态机**

状态固定为 `queued → parsing → chunking → embedding → completed`，异常进入 `failed`，取消进入 `cancelled`。每次重试必须增加 `attempt`，并设置最大重试次数。

- [ ] **Step 5: 先使用本地 worker，再换 ARQ**

本地开发可以直接调用任务函数；生产使用 `Redis + ARQ`。任务函数必须幂等，重复执行不会生成重复 chunk 或重复向量。

- [ ] **Step 6: 真实页面验收**

在 `integration-web` 上传一个小文本文件，观察进度、状态和列表刷新；再上传坏文件，确认页面显示失败原因且服务仍可处理下一份文件。

- [ ] **Step 7: 提交**

```bash
uv run pytest tests/e2e/test_upload_flow.py -q
git add python/backend integration-web
git commit -m "feat: add document ingestion pipeline"
```

**完成标准:** 上传和解析不会阻塞 API 进程；任务可查询、失败可重试、取消不再写入后续阶段。

## 8. 实现混合检索

### Task 7: 关键词、向量和引用结果

**Files:**

- Create: `python/backend/app/services/retrieval_service.py`
- Create: `python/backend/app/integrations/vector_store.py`
- Create: `python/backend/app/integrations/search.py`
- Modify: `python/backend/app/api/v1/routes/knowledge.py`
- Create: `python/backend/tests/e2e/test_retrieval_api.py`

**Interfaces:**

- `POST /api/v1/knowledge-bases/{kb_id}/hybrid-search`
- 内部函数 `hybrid_search(kb_id, query, top_k) -> list[SearchHit]`。

- [ ] **Step 1: 固定请求字段**

兼容当前集成页使用的 `query_text`、`match_count`，同时在内部统一命名为 `query`、`top_k`；在适配层完成字段转换，服务层不混用两套名字。

- [ ] **Step 2: 写检索排序测试**

使用固定向量和固定关键词分数，验证融合公式、去重、`top_k` 上限、空结果和 FAQ 知识库限制。

- [ ] **Step 3: 实现 Lite 模式**

SQLite 下先使用可测试的内存/文件索引；向量库通过 adapter 隔离。不要把生产向量库 SDK 直接放进 route。

- [ ] **Step 4: 预留生产向量库**

定义 `VectorStore.upsert/delete/search`，并为维度不匹配抛出明确错误；模型切换不能静默重用旧维度数据。

- [ ] **Step 5: 页面验收**

```bash
curl -s -X POST http://127.0.0.1:8080/api/v1/knowledge-bases/$KB_ID/hybrid-search \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H 'Content-Type: application/json' \
  -d '{"query_text":"默认端口是多少","match_count":8}'
```

检查每个结果都有 `id`、`content`、`score`、`knowledge_id` 和 `chunk_index`。

- [ ] **Step 6: 提交**

```bash
uv run pytest tests/e2e/test_retrieval_api.py -q
git add python/backend
git commit -m "feat: add hybrid retrieval"
```

**完成标准:** Lite 模式能稳定返回排序结果；生产向量库只需替换 adapter，不需重写路由和页面。

## 9. 实现会话、消息和 SSE 对话

### Task 8: 会话 CRUD 和消息历史

**Files:**

- Create: `python/backend/app/domain/entities/session.py`
- Create: `python/backend/app/repositories/session_repository.py`
- Create: `python/backend/app/services/chat_service.py`
- Create: `python/backend/app/api/v1/routes/sessions.py`
- Create: `python/backend/app/api/v1/routes/chat.py`
- Create: `python/backend/tests/e2e/test_chat_api.py`

**Interfaces:**

- `GET/POST/PUT/DELETE /api/v1/sessions`
- `GET /api/v1/messages/{session_id}/load`
- `POST /api/v1/knowledge-chat/{session_id}`。

- [ ] **Step 1: 先写会话和权限测试**

测试会话标题创建、重命名、删除、跨租户读取、空会话和消息分页。

- [ ] **Step 2: 实现消息持久化**

用户消息先落库；助手消息流结束后保存完整内容、引用和耗时；流中断时保存已生成内容和失败状态，不能丢失用户问题。

- [ ] **Step 3: 定义 SSE 事件编码器**

统一输出：

```text
data: {"response_type":"answer","data":{"content":"部分答案"}}

data: {"response_type":"references","data":{"references":[]}}

data: {"response_type":"complete","data":{"total_duration_ms":123}}

data: {"response_type":"error","data":{"message":"模型调用失败"}}
```

每个事件以两个换行结束，设置 `Content-Type: text/event-stream`、`Cache-Control: no-cache` 和连接取消处理。

- [ ] **Step 4: 实现最小流式链路**

顺序固定为：读取会话 → 保存用户消息 → 检索 → 调用模型流 → 发送 `references` → 发送 `answer` 增量 → 保存助手消息 → 发送 `complete`。异常发送 `error` 后结束，不再发送 `complete`。

- [ ] **Step 5: 测试分片和取消**

模拟客户端把一个事件拆成多个网络块；测试新请求取消旧请求、上游超时、客户端断开和模型返回空内容。

- [ ] **Step 6: 前端验收**

在 `integration-web` 创建会话，发送问题，确认增量内容、引用、完成耗时和刷新后的历史消息都正确。

- [ ] **Step 7: 提交**

```bash
uv run pytest tests/e2e/test_chat_api.py -q
git add python/backend integration-web
git commit -m "feat: add session and streaming chat"
```

**完成标准:** 页面可以稳定完成一次问答；流断开不会破坏数据库；客户端取消可以释放模型和检索资源。

## 10. 补齐 FAQ、Wiki 和图谱

### Task 9: FAQ、Wiki 页面、版本和图谱

**Files:**

- Create: `python/backend/app/domain/entities/faq.py`
- Create: `python/backend/app/domain/entities/wiki.py`
- Create: `python/backend/app/repositories/wiki_repository.py`
- Create: `python/backend/app/services/faq_service.py`
- Create: `python/backend/app/services/wiki_service.py`
- Create: `python/backend/app/api/v1/routes/faq.py`
- Create: `python/backend/app/api/v1/routes/wiki.py`
- Create: `python/backend/tests/e2e/test_faq_api.py`
- Create: `python/backend/tests/e2e/test_wiki_api.py`

**Interfaces:**

- FAQ 列表、批量启用/禁用、批量删除和搜索。
- Wiki 页面列表、详情、创建、更新、删除、移动、修订、回滚、文件夹、图谱和统计。

- [ ] **Step 1: 先冻结 DTO 字段**

以 `integration-web/src/types/api.ts` 和 `integration-web/api.ts` 实际使用字段为准，给每个响应写 JSON fixture；不要直接把 ORM 对象序列化给前端。

- [ ] **Step 2: 实现 FAQ**

FAQ 搜索和普通混合检索分开；批量操作检查所有 ID 都属于当前租户和知识库；删除前记录审计信息。

- [ ] **Step 3: 实现 Wiki 版本**

每次更新生成递增版本；回滚生成新版本而不是覆盖旧版本；并发更新使用版本号检查，冲突返回 `409`。

- [ ] **Step 4: 实现图谱和统计**

图谱响应只返回当前知识库可见页面；节点和边去重；孤立节点、按类型计数和近期更新使用同一查询快照。

- [ ] **Step 5: 页面验收**

在集成页打开 Wiki、搜索页面、查看图谱，创建并修改页面后回滚，再验证旧版本仍可预览。

- [ ] **Step 6: 提交**

```bash
uv run pytest tests/e2e/test_faq_api.py tests/e2e/test_wiki_api.py -q
git add python/backend integration-web
git commit -m "feat: add faq and wiki resources"
```

**完成标准:** FAQ 和 Wiki 的数据、版本、权限、图谱响应与前端类型一致，冲突和删除边界有测试。

## 11. 实现 Agent、MCP 和工具审批

### Task 10: Agent CRUD、ReAct 循环和 MCP 工具

**Files:**

- Create: `python/backend/app/domain/entities/agent.py`
- Create: `python/backend/app/domain/entities/mcp.py`
- Create: `python/backend/app/agent/context.py`
- Create: `python/backend/app/agent/engine.py`
- Create: `python/backend/app/agent/tools.py`
- Create: `python/backend/app/mcp/client.py`
- Create: `python/backend/app/mcp/server.py`
- Create: `python/backend/app/services/agent_service.py`
- Create: `python/backend/app/services/mcp_service.py`
- Create: `python/backend/app/api/v1/routes/agent.py`
- Create: `python/backend/app/api/v1/routes/mcp_endpoint.py`
- Create: `python/backend/app/api/v1/routes/mcp_service.py`
- Create: `python/backend/tests/e2e/test_agent_api.py`
- Create: `python/backend/tests/e2e/test_mcp_api.py`

**Interfaces:**

- Agent CRUD、工具目录、类型预设、提示词占位符。
- Agent SSE：`tool_call`、`tool_result`、`answer`、`complete`、`error`。
- MCP 服务/端点、连接测试、凭证、审批和工具调用。

- [ ] **Step 1: 先实现 Agent 配置 CRUD**

配置中的模型、知识库、工具和最大迭代次数都做 schema 校验；内置 Agent 不能被普通用户删除或修改系统字段。

- [ ] **Step 2: 抽象工具协议**

每个工具必须声明名称、输入 schema、超时、所需能力和是否需要审批。工具执行上下文至少包含 `user_id`、`tenant_id`、`request_id` 和取消信号。

- [ ] **Step 3: 实现 ReAct 循环**

循环上限由 Agent 配置限制；每轮记录模型请求、工具名、参数摘要、结果摘要和耗时；完整密钥和原始敏感结果不得写日志。

- [ ] **Step 4: 接入 MCP**

MCP client 负责连接、超时、协议错误和断开；service 负责凭据解密、租户隔离和工具目录缓存；route 只返回安全字段。

- [ ] **Step 5: 实现审批状态机**

`pending → approved/rejected → executed`；拒绝和过期都不能执行工具；重复审批请求必须幂等。

- [ ] **Step 6: 测试恶意和超时工具**

至少测试越权知识库、超时、工具返回过大、重复执行、审批过期和客户端断开。

- [ ] **Step 7: 提交**

```bash
uv run pytest tests/e2e/test_agent_api.py tests/e2e/test_mcp_api.py -q
git add python/backend
git commit -m "feat: add agent and mcp execution"
```

**完成标准:** Agent 能完成一次受限工具调用；所有高权限工具都有授权、超时、审计和取消边界。

## 12. 补齐组织、附件、预览和嵌入接口

### Task 11: 先补前端已经存在但后端未完整覆盖的接口

**Files:**

- Create: `python/backend/app/domain/entities/organization.py`
- Create: `python/backend/app/domain/entities/attachment.py`
- Create: `python/backend/app/services/organization_service.py`
- Create: `python/backend/app/services/attachment_service.py`
- Create: `python/backend/app/api/v1/routes/organization.py`
- Create: `python/backend/app/api/v1/routes/embed.py`
- Modify: `integration-web/src/api.ts`
- Modify: `integration-web/src/embed.ts`
- Create: `python/backend/tests/e2e/test_organization_api.py`
- Create: `python/backend/tests/e2e/test_embed_api.py`

**Interfaces:**

- 组织成员、邀请、角色变更、租户切换和共享资源。
- 文件预览、受保护图片、附件上传、临时文档和嵌入访客会话。

- [ ] **Step 1: 清理前端默认凭据风险**

`integration-web/src/embed.ts` 不得内置真实账号密码；改成显式环境变量、一次性 Token 或宿主消息传递。没有凭据时页面显示连接失败，不自动猜测账号。

- [ ] **Step 2: 先实现组织边界**

邀请 Token 一次性使用并过期；角色变更检查操作者权限；成员移除后立即失效其租户 Token 或权限缓存。

- [ ] **Step 3: 实现受保护资源**

预览和下载返回短期 URL 或流式响应；服务端再次检查租户和资源权限；禁止把本地绝对路径或永久对象存储 URL 发送给浏览器。

- [ ] **Step 4: 实现嵌入会话**

嵌入访客只能访问明确授权的知识库；会话和查询不能读取主应用用户的 Token；宿主通信消息校验来源和消息类型。

- [ ] **Step 5: 验收和提交**

```bash
uv run pytest tests/e2e/test_organization_api.py tests/e2e/test_embed_api.py -q
cd integration-web && pnpm run build
git add python/backend integration-web
git commit -m "feat: add organization and embed boundaries"
```

**完成标准:** 组织和嵌入场景有独立凭据、权限和资源范围；默认配置不再泄露账号或长期 Token。

## 13. 把开发实现提升到生产可用

### Task 12: Redis/ARQ、对象存储、真实向量库和可观测性

**Files:**

- Modify: `python/backend/app/tasks/queue.py`
- Create: `python/backend/app/storage/s3.py`
- Create: `python/backend/app/integrations/vector_store_production.py`
- Create: `python/backend/app/core/observability.py`
- Create: `python/backend/app/core/rate_limit.py`
- Create: `python/backend/docker-compose.yml`
- Create: `python/backend/.env.example`
- Create: `python/backend/tests/contract/test_production_dependencies.py`

**Interfaces:**

- 任务重试、取消、死信和重启恢复。
- 对象存储 `put/get/delete/presign`。
- 向量库 `upsert/search/delete`。
- 日志字段：`request_id`、`tenant_id`、`user_id`、`route`、`duration_ms`、`status_code`。

- [ ] **Step 1: 为外部依赖写健康检查**

`/health` 只说明服务进程存活；新增 `/ready` 检查数据库、Redis、对象存储和向量库，返回每项状态和整体结果。

- [ ] **Step 2: 替换本地存储**

保留 `LocalStorage` 作为开发 adapter；生产配置显式选择 `S3Storage`。上传成功前不能写入数据库“已完成”。

- [ ] **Step 3: 接入 ARQ**

任务使用幂等键、最大重试、指数退避和取消标记；worker 重启后从数据库恢复 `queued/running` 任务。

- [ ] **Step 4: 加入限流和审计**

登录、刷新、上传、聊天和工具调用分别限流；敏感操作写审计事件，审计记录也按租户隔离。

- [ ] **Step 5: 跑真实依赖验收**

```bash
docker compose up -d postgres redis
uv run pytest tests/contract/test_production_dependencies.py -q
curl -s http://127.0.0.1:8080/ready | python -m json.tool
```

- [ ] **Step 6: 提交**

```bash
git add python/backend
git commit -m "feat: add production adapters and observability"
```

**完成标准:** 进程、依赖、任务、对象和向量库状态可观察；任务重启和外部服务短暂失败不会造成数据静默丢失。

## 14. 契约对照、灰度切流和 Go 下线

### Task 13: 用证据完成替换

**Files:**

- Create: `python/backend/tests/contract/route_matrix.md`
- Create: `python/backend/tests/contract/response_catalog.md`
- Create: `python/backend/tests/contract/stage_report_phase*.md`
- Create: `python/backend/scripts/generate_route_matrix.py`
- Create: `python/backend/scripts/compare_backends.py`
- Modify: `integration-web/vite.config.ts`
- Modify: `docs/progress/前后端实现清单.md`
- Modify: `docs/progress/Python后端重构进度管理.md`

**Interfaces:**

- `compare_backends.py` 对同一请求调用 Go 和 Python，比较状态码、错误结构、字段集合、分页和 `SSE` 事件序列。
- 路由矩阵区分：Go 已有、Python 已有、前端调用、三者交集。

- [ ] **Step 1: 先做只读路由灰度**

先切健康检查、模型列表、知识库列表和 Wiki 读取；写接口仍走 Go。记录错误率、P95 延迟、数据库读差异和前端异常。

- [ ] **Step 2: 再切知识库写和上传**

切换前执行数据库备份；灰度期间比较新建、更新、删除、上传任务状态和向量数量；任何字段差异先回滚路由，不直接修生产数据。

- [ ] **Step 3: 切聊天 SSE 和 Agent**

观察首字节延迟、完整响应时间、断开率、取消成功率、引用差异、工具错误和任务积压。

- [ ] **Step 4: 设置回滚开关**

在代理层按路由配置后端目标；保留 Go 只读观察期。回滚只切流量，不回滚数据库迁移，除非已有明确的向后兼容回滚脚本。

- [ ] **Step 5: 生成最终证据**

```bash
uv run python scripts/generate_route_matrix.py
uv run python scripts/compare_backends.py --base-url-go "$GO_BASE_URL" --base-url-python "$PYTHON_BASE_URL"
uv run pytest -q
cd ../../integration-web && pnpm run build
```

- [ ] **Step 6: 更新进度和提交**

只有同时满足“自动化测试通过、前端真实闭环通过、数据库落盘核验通过、生产依赖检查通过”时，才把阶段标成 `已验收`。

```bash
git add python/backend integration-web docs/progress
git commit -m "chore: complete python backend cutover evidence"
```

**完成标准:** 每个切流路由都有对照结果、回滚方式和阶段报告；Go 可以进入只读观察期，再决定是否下线。

## 15. 每天实际执行的固定循环

每次只做一个小目标，按下面顺序执行：

1. 在 `docs/progress/Python后端重构进度管理.md` 记录当前阶段、目标接口和失败风险。
2. 写一个会失败的最小测试。
3. 运行该测试确认失败原因符合预期。
4. 只实现让测试通过的代码。
5. 运行该域全部测试，再运行 `ruff`、`mypy` 或项目选定的静态检查。
6. 用 `curl` 或 `integration-web` 做一次真实请求。
7. 更新接口矩阵、阶段报告和进度台账。
8. 提交一个只包含当前任务的 commit。
9. 才开始下一个任务。

推荐命令：

```bash
cd /Users/james/Desktop/github/WeKnora/refactor/python/backend
uv run pytest -q
uv run ruff check app tests
uv run ruff format --check app tests
uv run python scripts/generate_route_matrix.py

cd /Users/james/Desktop/github/WeKnora/refactor/integration-web
pnpm install --frozen-lockfile
pnpm run build
```

## 16. 你可以照着执行的第一周安排

### 第 1 天：基线和服务启动

- [ ] 完成 `Task 0`。
- [ ] 完成 `Task 1` 的 `/health`、配置、日志和错误。
- [ ] 确认 `curl`、`pytest`、`OpenAPI` 都能工作。

### 第 2 天：数据库和迁移

- [ ] 完成 `Task 2` 的三张基础表。
- [ ] 在 `SQLite` 和 `PostgreSQL` 各跑一次迁移。
- [ ] 写出第一版 `database-contract.md`。

### 第 3 天：鉴权和租户

- [ ] 完成 `Task 3`。
- [ ] 验证登录、刷新、退出和跨租户拒绝。
- [ ] 清理 `integration-web/src/embed.ts` 的默认凭据风险。

### 第 4 天：模型和知识库

- [ ] 完成 `Task 4` 的 fake provider。
- [ ] 完成 `Task 5` 的知识库 CRUD、标签和文件夹。
- [ ] 前端完成“登录 → 建库”。

### 第 5 天：上传和检索

- [ ] 完成 `Task 6` 的小文件上传、解析和状态查询。
- [ ] 完成 `Task 7` 的 Lite 混合检索。
- [ ] 前端完成“上传 → 检索”。

### 第 6 天：会话和 SSE

- [ ] 完成 `Task 8`。
- [ ] 测试断流、取消、空回答和历史加载。
- [ ] 前端完成“检索 → 对话”。

### 第 7 天：复盘和下一周拆分

- [ ] 运行全量测试和前端构建。
- [ ] 更新 route matrix 和阶段报告。
- [ ] 只在前六天闭环稳定后开始 FAQ、Wiki、Agent。

## 17. 每个阶段报告必须回答的问题

1. 实现了哪些具体路由和内部接口？
2. 请求体、响应体、错误码和 `SSE` 事件是否与基线一致？
3. 哪些测试证明了成功、失败、权限和并发边界？
4. 数据库是否有迁移、回滚和旧数据验证？
5. 前端真实页面是否完成闭环？
6. 生产依赖是否已接入，还是仍使用 Lite adapter？
7. 已知风险、回滚开关和下一阶段唯一入口是什么？

## 18. 不要在前期实现的内容

- 不要先做全部 `395+` 个历史接口；先做前端真实调用的主链路。
- 不要先重写 `docreader`；先通过 adapter 复用已有解析协议。
- 不要一开始接入所有向量库、模型厂商和 `Wails` 桌面能力。
- 不要把所有页面请求塞进 `App.vue` 或一个全局 store。
- 不要用“服务能启动”代替上传、`SSE`、租户隔离和 Agent 工具验收。
- 不要为了让旧测试通过而放宽权限、错误处理或数据校验。
