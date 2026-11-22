# Python 后端变更记录

本文件记录 `refactor/python/backend/` 的实际开发进度。前端状态请查看[前端变更记录](./frontend-changelog.md)，双端总览请查看[开发变更总览](./changelog.md)。

## 1. 当前状态

- 已有独立验收模块：免鉴权 `GET /health`；证据保留在历史章节。
- 当前仅实现 `S2.2` 显式本地 `SQLite` 连接检查子项，修复后独立复审和必要独立测试通过；整个 `S1`、`S2` 未全量验收。
- 业务数据、`schema`/迁移、`ORM` 未实现，整个 `S2` 未验收；当前版本为 `Unreleased`。

### 当前增量：`2026-11-21` 连接检查模块

- 从 `python/backend/` 运行 `uv run --frozen python -m app.cli.check_database --path PATH [--create] [--json]`，显式目标、默认只读；创建只占有新文件，不建父目录、不覆盖、不初始化业务表。
- 首轮 `P1-01` 审查失败后窄修：连接前只读最多 `100` 字节并关闭，仅允许 `rollback`/零字节；持久化 `WAL` 即使无副文件也返回 `invalid_target/3`，不是损坏判定。不改日志模式、不删副文件，修复后独立复审 `PASSED/P0/P1/P2=0`，首轮失败历史保留。
- 方法边界：`resolve_database_target` 校验目标，`check_database` 固定查询与释放，`build_parser`/`main` 负责独立命令；不修改 `GET /health` 或新增 `HTTP API`。
- 参数、输出和失败练习见[后端说明](../../python/backend/README.md#6-当前增量显式本地-sqlite-连接检查)。本轮 `TASK-04` 独立新增 `117` 项（资源/函数 `88`、真实 `CLI 29`），全套 `128 passed`（含健康 `11`）；真实关闭无副文件 `WAL 2/2` 回归、Ruff/格式/前端构建/最窄进度导航通过。见[正式测试](../../artifacts/weknora-sqlite-connection/04-e2e/test-report.md)；只同步已执行证据，不重跑或新增前端行为，业务 `schema`/迁移/`ORM` 未验证。
- 完成本需求审核、测试、知识与讲解后由主线程暂停，等待用户明确继续；未提交或推送。

## 2. `2026-11-21`：统一开发启动命令

### Added

- 在 `python/` 根目录提供 `npm run dev` 统一启动入口。
- 启动器从 `python/backend` 执行现有 `uv run --frozen uvicorn ...` 命令。
- 启动前自动停止占用 `8080` 的旧监听进程，并在退出时联动清理前端进程。

### 验证

- `node --check python/scripts/dev.mjs` 通过。
- `GET http://127.0.0.1:8080/health` 返回 `200` 和 `{"status":"ok"}`。

## 3. `2026-11-20`：首个健康检查增量

### Added

- 建立最小 `FastAPI` 应用和 `GET /health` 路由。
- 成功响应固定为 `200` 和 `{"status":"ok"}`。
- 增加 `X-WeKnora-Implementation: python-fastapi` 诊断 `header`，用于本地识别误连服务，不承担鉴权职责。
- 补充 `uv` 锁定安装、启动、代理检查和 `Ruff` 检查说明。

### 兼容范围

本轮只对齐健康接口的路径、方法和成功响应子集。尾斜杠、未知路径和错误方法按本轮 `FastAPI` 合同返回 `404` 或 `405`，不声称全量 `Go` 框架行为兼容。

未连接数据库或模型，未创建业务表；登录、上传、解析、检索、问答、`SSE` 和 `trace` 均未实现。

### 验证与证据

- 独立代码审查：通过，`P0/P1/P2` 均为 `0`。
- 正式测试：后端 `pytest 11` 项通过；双端合计 `38` 项自动测试和浏览器 `11` 组检查通过。
- 证据：[代码审查报告](../../artifacts/weknora-python-vue3-rebuild/03-code/code-review-report.md)、[正式测试报告](../../artifacts/weknora-python-vue3-rebuild/04-e2e/test-report.md)、[新增用例](../../artifacts/weknora-python-vue3-rebuild/04-e2e/added-cases.md)。
- 测试执行日期为 `2026-11-20`（`UTC`）；本文件于 `2026-11-21` 同步，未因本次整理重新执行后端测试。

### 已知告警与边界

- `pytest` 有 `1` 条上游 `StarletteDeprecationWarning`（`httpx/TestClient`），未为消警增加依赖。
- 数据库、真实模型、内部 `Python 500` 注入和全量业务路由不在本轮验收范围。
- 本轮未提交、未推送、未发布。
