---
task_id: WEKNORA-PRODUCT-AUTH-20261122
stage: TASK-03
author: 开发工程师
date: 2026-11-22
run_mode: auto
---

# `Python` 后端变更记录

## 当前正式结论（`2026-11-22`）

独立复审 `PASSED/P0=0/P1=0/P2=0`；独立 `TASK-04 PASSED/completed`：后端新增 `92`／全套 `220 passed`，前端新增 `14`／全套 `41 passed`，浏览器 `29` 场景组，必需失败／阻塞 `0`，静态／类型／构建通过，无生产缺陷。五接口、原版 `SQLite 0–7/v7` 认证结构、事务／身份／轮换退出／重启及 `CR-001–005` 均有独立验证，非全量迁移或知识库 `CRUD`。

[复审](../../artifacts/weknora-product-auth/03-code/code-review-report.md)、[正式测试](../../artifacts/weknora-product-auth/04-e2e/test-report.md)、[新增用例](../../artifacts/weknora-product-auth/04-e2e/added-cases.md)保留首轮失败、两处测试自身问题修正与既有上游警告；本文未重跑。生产／`PostgreSQL`／跨浏览器矩阵等范围外仍 `not-run`；受支持分端启动必须 `--no-proxy-headers`，旧统一启动器禁止用于认证。主线程收尾暂停，等待用户明确继续。

## 历史：首轮审核纠正与修复（下方未执行状态仅属当时）

首轮独立 `CODE-REVIEW FAILED`（`P0=0/P1=3/P2=2`），下方开发 `PASS` 保留为修复前历史；独立复审未执行，`TASK-04 not-run`。`CR-001` 要求受支持后端命令带 `--no-proxy-headers`，开发代理剥除不可信转发头，限流按真实连接对端而非转发身份；现有统一 `npm run dev` 无安全参数且会停止监听者，不支持认证运行、不要执行。`CR-002` 要求认证非法编码／过深 `JSON` 统一 `400/1010`，不影响健康与非认证 `404/405`；`CR-003` 联动前端已有令牌后的 `me` 恢复／真实退出。修复实际源码／最终行号已核对，真实换头限流／剥头、原始字节 `14` 项、受控递归 `3` 项、协调者恢复浏览器 `7` 项与最终回归均开发自检通过；自然深度基线已安全，不冒称复现，来源见[学习指南](../../artifacts/weknora-product-auth/03-code/learning-guide.md)，不预写复审通过。

本文件记录 `refactor/python/backend/` 的实际开发进度。前端状态请查看[前端变更记录](./frontend-changelog.md)，双端总览请查看[开发变更总览](./changelog.md)。

## 1. 修复前实现与自检快照（当前审核状态以上方纠正为准）

- 当前为 `Unreleased` 身份业务增量：真实账户与个人空间是主产品，工作台仅辅助；本节已核对实际源码／行号并同步本轮开发自检快照。
- 五条路由：`POST /api/v1/auth/register`（`201/user`，不自动登录）、`POST /api/v1/auth/login`（`token/refresh_token`）、`POST /api/v1/auth/refresh`（请求 `refreshToken`，响应 `access_token/refresh_token`）、`GET /api/v1/auth/me`（`success/data`）、`POST /api/v1/auth/logout`（撤销用户全部会话）。用户／个人空间／`owner` 成员注册事务、`bcrypt` 与入库 `JWT` 为本轮真实业务边界。
- 原版 `SQLite 000000–000007` 八份完整 `up.sql` 与 `auth-sqlite-prefix-v7` 只覆盖 `v7` 认证结构基线，不是全量迁移、生产升级或整个 `S2/S3` 验收。知识库、上传、模型配置、问答、协作与 `PostgreSQL` 不在本轮。
- 自有新库显式初始化并生成持久 `0600` 侧车秘密，不读取现有 `.env`／原版库，不覆盖旧文件；安全分端启动和统一启动器会停止默认 `8080/5400` 监听者的警告见[后端说明](../../python/backend/README.md)。
- 实际函数／行号已只读核对；开发者报告本轮既有 `pytest 128`、`Ruff` 与认证自检 `108` 项通过，协调者真实网络 `13` 项、浏览器及重启自检通过；本文未重跑，受控与真实服务证据分列，本轮独立 `CODE-REVIEW/TASK-04` 仍为 `not-run`。实际链路见[学习指南](../../artifacts/weknora-product-auth/03-code/learning-guide.md)，合同见[认证接口文档](../../artifacts/weknora-product-auth/03-code/api-docs.md)。历史健康与连接检查通过不证明本轮认证通过。

### 历史增量：`2026-11-21` 连接检查模块

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
