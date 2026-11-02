# WeKnora Python

WeKnora 的 Python 分阶段实现，前后端分目录管理：

```
python/
├── backend/     # FastAPI 服务（app/ scripts/ tests/ data/）
└── frontend/    # Vue 3 + Vite + TypeScript 前端
```

目标是**不改变现有 Vue 前端、数据库表结构与 `/api/v1` 契约**的前提下，逐步替换 Go 服务。

实施规划见 [Python重写WeKnora从0到1实施规划.md](../.trae/documents/Python重写WeKnora从0到1实施规划.md)。

## 当前进度

- **Phase 0**：工程骨架、配置、数据库、迁移 runner、`/health`、接口契约清单。
- **Phase 1**：JWT 认证、注册/登录/刷新/登出、空间与成员实体、基础 RBAC 依赖。
- **Phase 2**：模型网关（`/models` CRUD、连通性测试、OpenAI 兼容 chat/embedding/rerank）。
- **Phase 3**：知识库与入库（KB/知识/分块、本地存储、文档解析分块、向量化落库）。
- **Phase 4**：混合检索（向量 + 关键词 + 加权排序）。
- **Phase 5**：对话（会话 CRUD、SSE 流式问答、引用返回与落库）。
- **前端**：`python/frontend` 自包含 Vue 3 + Vite + TS，四个页面（登录与空间、知识库与文档、对话与引用、模型管理）。

## 后端启动

```bash
cd python/backend
py -3.13 -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"

# 复制并编辑环境变量（也可直接复用仓库根目录 .env）
copy .env.example .env

# 启动（默认 8080，与 Go 后端端口一致，便于前端切换）
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

健康检查：`GET http://localhost:8080/health`。

本地无 PostgreSQL 时，可用 SQLite 快速验证：

```bash
set DB_DRIVER=sqlite
set DB_PATH=./data/weknora.db
set AUTO_MIGRATE=true
```

## 接入真实大模型（DeepSeek + ChatGPT）

自动化测试和阶段验收默认使用本地假 OpenAI（`scripts/fake_openai.py`），保证离线可复现；**真实模型**配置只写在 `python/backend/.env`（已被 `.gitignore` 忽略）。

当前 `.env` 已按「DeepSeek 对话 + ChatGPT 对话 + OpenAI Embedding」预留好位置，只需填写三个 `API_KEY`：

```ini
# 1) DeepSeek：默认对话模型
LLM_CHAT_BASE_URL=https://api.deepseek.com/v1
LLM_CHAT_MODEL=deepseek-chat
LLM_CHAT_API_KEY=sk-xxxx

# 2) ChatGPT：第二对话模型（非默认，可在模型管理页切换默认）
LLM_CHAT2_BASE_URL=https://api.openai.com/v1
LLM_CHAT2_MODEL=gpt-4o-mini
LLM_CHAT2_API_KEY=sk-xxxx

# 3) OpenAI Embedding
LLM_EMBEDDING_BASE_URL=https://api.openai.com/v1
LLM_EMBEDDING_MODEL=text-embedding-3-small
LLM_EMBEDDING_API_KEY=sk-xxxx
LLM_EMBEDDING_DIMENSION=1536

# 国内直连 api.openai.com 失败时填代理（DeepSeek 一般直连）
LLM_PROXY=http://127.0.0.1:7890
```

写入模型表并做真实连通性测试：

```bash
cd python/backend
.\.venv\Scripts\python.exe scripts\seed_models.py            # 写库 + 三个模型各调一次真实上游
.\.venv\Scripts\python.exe scripts\seed_models.py --no-check # 只写库
```

三个模型会各写一条记录（chat 默认给 DeepSeek，ChatGPT 为非默认，embedding 为默认）；输出里密钥自动打码。退出码 1 表示上游调用失败（如维度不匹配、代理不通）。

真实模型全链路验收（真实启动服务 → 建模型 → 建库 → 上传 → 真实向量化 → 检索 → DeepSeek/ChatGPT SSE 问答 → 查库）：

```bash
cd python/backend
.\.venv\Scripts\python.exe scripts\real_e2e.py
.\.venv\Scripts\python.exe scripts\real_e2e.py --chat-only   # 只验收对话模型
```

报告写入 `tests/contract/real_model_report.md`，退出码 0 表示全部通过。真实模型单测默认跳过，需显式开启：

```bash
$env:RUN_REAL_LLM="1"; .\.venv\Scripts\python.exe -m pytest tests\e2e\test_real_models.py -q
```

注意事项：

- DeepSeek 只有对话接口，没有 embedding；向量服务需另配（OpenAI `text-embedding-3-small`(1536)、百炼、Ollama `bge-m3`(1024)）。
- 更换 embedding 模型后，已有文档的分块向量维度不再匹配（余弦相似度按 0 处理，退化为纯关键词检索），需要重新上传或重解析这些文档。
- 也可以不用 `.env`，直接在前端「模型管理」页面填写 base_url / model / api_key，效果一致（但密钥会明文存在本地 SQLite 的模型参数里）。


## 前端启动

```bash
cd python/frontend
npm install
npm run dev      # http://localhost:5173，/api 反向代理到 http://127.0.0.1:8000
```

后端端口不是 8000 时，改 [vite.config.ts](./frontend/vite.config.ts) 里的 `API_TARGET`。

## 目录说明

| 目录 | 对应 Go 代码 |
|---|---|
| `backend/app/core` | `internal/{config,database,middleware,logger,errors}` |
| `backend/app/domain/entities` | `internal/types` |
| `backend/app/repositories` | `internal/application/repository` |
| `backend/app/services` | `internal/application/service` |
| `backend/app/api/v1` | `internal/handler` + `internal/router` |
| `backend/app/llm` | `internal/models`（OpenAI 兼容客户端） |
| `backend/app/integrations/docreader` | `docreader/` 本地解析回退 |
| `frontend` | `frontend/`（自包含精简版） |

## 阶段验收（每个阶段必跑）

每个阶段有三条准入条件，缺一不可：**测试用例已编写 → `pytest` 全绿 → `stage_check` 全绿**。

```bash
cd python/backend
.\.venv\Scripts\python.exe -m pytest -q                                # 全量自测
.\.venv\Scripts\python.exe scripts\stage_check.py --stage phase1      # 全链路验收
```

`stage_check.py` 会：校验本阶段测试文件存在（`PHASE_TESTS`）→ ruff 检查 → pytest 全量 → 用独立 SQLite 库**真实启动 uvicorn**（走 SQL 迁移）→ 通过 HTTP 覆盖本阶段全部接口（含异常与权限分支）→ 直接查库校验落盘 → 输出 `tests/contract/stage_report_phase1.md`。任一失败退出码非 0，必须修复后重跑，不能带病进入下一阶段。

## 测试布局

| 路径 | 内容 |
|---|---|
| `tests/unit/` | 纯逻辑：JWT、密码策略 |
| `tests/e2e/test_auth_flow.py` | Phase 0/1：health、注册登录刷新登出 |
| `tests/e2e/test_models_api.py` | Phase 2：模型 CRUD、连通性、掩码 |
| `tests/e2e/test_knowledge_api.py` | Phase 3：建库、上传解析、分块、向量落库 |
| `tests/e2e/test_retrieval_api.py` | Phase 4：混合检索、排序、参数校验 |
| `tests/e2e/test_chat_api.py` | Phase 5：会话 CRUD、SSE 事件序列、引用落库 |
| `tests/helpers.py` | 公共辅助（注册登录、建模型、建库、上传） |
| `tests/conftest.py` | 建表 fixture + `fake_llm_base_url`（进程内假 OpenAI） |

当前 `pytest -q`：**43 passed**。

流程规范见 [阶段执行与验收流程.md](../.trae/documents/阶段执行与验收流程.md)。

当前状态（每个阶段均已先写测试、`pytest -q` 全绿、再跑真实服务全链路）：
- Phase 0：6/6 通过
- Phase 1：22/22 通过
- Phase 2：16/16 通过（含本地 fake OpenAI 测试双）
- Phase 3：14/14 通过
- Phase 4：9/9 通过
- Phase 5：14/14 通过
- 前端全链路（浏览器）：登录 → 建模型 → 建库 → 传文档 → 检索 → 流式问答 + 引用，全部通过

> `stage_check.py` 共用 `data/stage_server.log` 与 `data/schema_template.db`，多个阶段必须**串行**复跑，禁止并发执行。

> `backend/scripts/fake_openai.py` 是本地 OpenAI 兼容假服务，仅用于离线验收（chat 流式 + 确定性向量 + rerank），不参与生产。

## 接口契约清单

```bash
cd python/backend
python scripts/generate_route_matrix.py
```

生成 `tests/contract/route_matrix.md`，列出 swagger 接口、前端调用情况和 Python 实现状态，作为进度看板。
