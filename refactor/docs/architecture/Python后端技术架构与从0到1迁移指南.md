# WeKnora Python 后端技术架构与从 `0` 到 `1` 迁移指南

本文把当前 Go + Python 后端整理成一条可执行的 Python 迁移路线，并与 [前端从 `0` 到 `1` 实现指南](./frontend从0到1实现指南.md) 的阶段保持对应。目标是逐步替换服务实现，保持现有前端、数据库和 `/api/v1` 契约可用。

## 1. 当前后端地图

```text
cmd/server/main.go
  └─ Gin 路由、认证中间件、DI、后台任务、数据库和外部基础设施
internal/
  ├─ handler/      HTTP 参数校验、响应和 SSE
  ├─ router/       约 395 个接口、RBAC、API Key 和租户路由
  ├─ application/  领域 Service、Repository、后台工作流
  ├─ models/       数据访问模型
  ├─ database/     migrations/versioned 与 migrations/sqlite
  ├─ agent/chat/   Agent、工具调用、对话编排
  ├─ infrastructure/ PostgreSQL、Redis、对象存储、向量库、搜索和外部服务
  └─ background/   长任务、重试、任务查询和取消
docreader/
  └─ 独立 Python gRPC 文档解析服务；Go 通过 `docreader/client` 调用
refactor/python/backend/
  └─ FastAPI、SQLAlchemy 异步会话、Pydantic、JWT、SSE、ARQ、LLM 适配和分层业务代码
```

当前主要技术点：

| 领域 | 当前实现 | Python 目标 | 迁移关注点 |
| --- | --- | --- | --- |
| HTTP | `Gin` | `FastAPI` + `Uvicorn` | 路由、状态码、错误 JSON、OpenAPI |
| 鉴权 | JWT、OIDC、API Key、RBAC | `PyJWT` + FastAPI 依赖 | Token 刷新、租户头、能力边界 |
| 数据库 | `GORM`/SQL、PostgreSQL、SQLite | `SQLAlchemy 2` async | 复用既有 SQL，禁止破坏数据 |
| 迁移 | `golang-migrate` | 当前 Python migration runner | 版本表格式和并发锁必须兼容 |
| 缓存/任务 | Redis、`Asynq`、后台 worker | Redis、`ARQ` | 重试、取消、幂等、死信 |
| 文档 | Go 调度 + Python `docreader` gRPC | 先保留 gRPC，再逐步内嵌 | 大文件、OCR、流式读取 |
| 检索 | 向量库、关键词、重排 | 当前 Python 混合检索 | 生产环境切换到真实向量库 |
| 模型 | 多厂商 LLM、Embedding、Rerank | OpenAI-compatible client | 密钥隔离、超时、流式错误 |
| 实时 | SSE、WebSocket、gRPC | SSE 优先，WebSocket 后迁移 | 事件类型、断线、取消 |
| 存储 | 本地、S3/MinIO、COS 等 | storage adapter | URL 鉴权和租户隔离 |
| 可观测性 | 日志、OpenTelemetry、指标 | `logging` + OTel | request id、trace、错误关联 |

## 2. Python 目标分层

`refactor/python/backend/app` 已经形成目标骨架：

```text
main.py
api/v1/routes/       HTTP 路由与依赖
api/v1/schemas/      请求/响应模型
core/                 配置、数据库、迁移、安全、错误、中间件
domain/entities/     领域实体和常量
repositories/        数据访问
services/             业务用例
llm/                  模型网关
integrations/         docreader、搜索等外部适配
storage/              文件和对象存储
agent/、mcp/          Agent 与 MCP
```

一条请求应保持 `route → dependency → service → repository/integration`。路由不直接写 SQL，跨请求共享的数据放在 service 或任务层；所有业务查询带 `tenant_id`。

## 3. 与前端指南的阶段映射

| 前端阶段 | 后端迁移阶段 | 交付和验收 |
| --- | --- | --- |
| 阶段 `0` 静态壳 | `P0` 可启动骨架 | `/health`、Swagger、配置、日志、数据库连接可用 |
| 阶段 `1` 登录和请求 | `P1` 认证与租户边界 | 登录、刷新、退出、`/auth/me`、`X-Tenant-ID`、RBAC 与 Go 返回一致 |
| 阶段 `2` 知识库 CRUD | `P2` 核心资源 | 知识库、标签、FAQ、Wiki CRUD；同一数据库可由 Go/Python 交替读写 |
| 阶段 `3` 上传和后台任务 | `P3` 文档流水线 | 上传、解析、分块、向量化、任务状态、重试和取消 |
| 阶段 `4` 检索和聊天 | `P4` 检索与 SSE | 检索结果、引用、`answer`/`complete`、取消和错误事件 |
| 阶段 `5` Agent 和工具 | `P5` Agent/MCP | 工具调用、审批、工具结果、Agent 会话和沙箱边界 |
| 阶段 `6` 多租户和权限 | `P1` 起即建设，`P6` 补齐 | 组织、成员、共享资源、API Key、能力矩阵和缓存失效 |
| 阶段 `7` 生产能力 | `P7` 切流与下线 Go | OTel、限流、部署、性能、安全、回滚和 Go 只读观察期 |

## 4. 分阶段实施顺序

### `P0` 基线和契约冻结

1. 以 `route_matrix.md` 为清单，生成 Go/Python/前端三方路由矩阵；统一 `/api/v1` 前缀。
2. 固定成功响应、错误结构、分页、时间格式、SSE 事件名和鉴权头。
3. 为每个阶段保存 Go 对照测试结果，先测读接口，再测写接口。
4. 验收：Python 服务可独立启动，现有前端只改代理目标即可访问。

### `P1` 认证、租户和数据库兼容

1. 校准 JWT claims、刷新 Token 轮换、密码策略、OIDC 和 API Key。
2. 所有 repository 查询强制接收 `tenant_id`；租户切换时清理缓存。
3. Python migration runner 改为兼容 Go 的 `schema_migrations(version, dirty)` 语义，并使用数据库锁。
4. 验收：Go/Python 交替启动不产生新迁移；同一用户在两个服务取得相同 `/auth/me`。

### `P2` 知识库和基础资源

按 `knowledge-base → tags → FAQ → wiki → model` 迁移。每个领域先完成 repository、service、route、契约测试，再切流量。删除和权限错误必须与 Go 保持一致。

### `P3` 上传与后台任务

先复用现有 Python `docreader` gRPC，不复制解析器。实现任务表、ARQ worker、幂等键、重试上限、取消和死信查询；验证大文件、重复上传、解析失败和租户隔离。

### `P4` 检索与聊天

先完成最小 SSE：`answer`、`references`、`complete`、`error`、取消。然后迁移混合检索、重排、消息历史和上下文压缩。当前 Python 的内存向量计算只作为 SQLite/Lite 模式兜底，生产必须接入现有向量库。

### `P5` Agent、MCP 和工具

迁移顺序为 Agent CRUD → 工具目录 → MCP 服务/端点 → 工具调用事件 → 审批与暂停 → 沙箱。每一步保留工具超时、权限校验、审计日志和资源配额。

### `P6` 生产切流

采用按路由切流：只读接口 → 知识库写接口 → 上传任务 → 聊天 SSE → Agent。每次切流保留 Go 回滚开关，比较错误率、延迟、任务积压、SSE 中断和数据库写入差异；全部稳定后再下线 Go handler。

## 5. 每个阶段的最小工程闭环

每个业务域都必须同时提交：

1. `route`、schema、service、repository 和配置改动。
2. Go/Python 契约对照测试，以及一个失败边界测试。
3. 前端真实调用或 `curl` 验收脚本。
4. 数据库迁移和回滚说明（若涉及 schema）。
5. 阶段报告：已实现路由、未实现路由、性能和已知限制。

## 6. 首批必须处理的风险

- 迁移记录格式可能导致两个服务互相误判迁移状态。
- `route_matrix.md` 显示 Python 已实现 `87` 条，而前端实际调用约 `361` 条；不能以“服务能启动”作为迁移完成。
- SSE、文件上传和后台任务都是长连接/长任务，不能用普通 CRUD 的验收标准替代。
- 向量维度、模型密钥和对象存储 URL 一旦变更，可能影响已有数据或暴露资源。
- Agent、MCP、沙箱和 API Key 属于高权限边界，必须在 Go 下线前完成审计和权限对照。

## 7. 第一周建议任务

1. 完成 `P0` 路由矩阵和响应样例冻结。
2. 对 `auth`、`knowledge`、`chat` 各选一个 Go/Python 对照接口，补齐契约测试。
3. 修正 migration runner 的兼容语义并在 PostgreSQL、SQLite 各跑一次。
4. 在前端把 API 目标切到 Python，完成登录 → 建库 → 上传 → 聊天的最小闭环。
5. 记录未覆盖的路由，不提前迁移嵌入、桌面专用和低频管理接口。

今天先阅读并运行：`refactor/python/backend/app/main.py`、`app/api/v1/router.py`、`app/api/v1/routes/auth.py`、`app/api/v1/routes/knowledge.py`、`app/api/v1/routes/chat.py`，然后执行后端测试和 `/health` 检查。

## 8. 暂不实现的内容

暂不新增微服务、事件总线、GraphQL、全量重写 `docreader` 或一次性迁移全部 `395` 条接口；这些会增加切流风险，只有契约或容量证据要求时再引入。
