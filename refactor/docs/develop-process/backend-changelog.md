# Python 后端变更记录

本文件记录 `refactor/python/backend/` 的实际开发进度。前端状态请查看[前端变更记录](./frontend-changelog.md)，双端总览请查看[开发变更总览](./changelog.md)。

## 1. 当前状态

- 当前已完成模块：免鉴权 `GET /health`。
- 当前阶段：仅完成健康检查子集，不代表 `S1` 全量完成。
- 当前版本：`Unreleased`。

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
