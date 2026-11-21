---
task_id: WEKNORA-REBUILD-20261120
stage: TASK-03
author: 开发工程师
date: 2026-11-20
run_mode: auto
---

# Python 后端：第一个健康检查增量

本轮只提供 `GET /health`，用于确认 Python HTTP 应用可响应。不接数据库、模型、队列，不实现登录、上传、解析、检索、问答、SSE 或持久化 trace。原版 Go 与 `integration-web/` 保留。

**开发阶段快照（2026-11-20）：** 2026-11-20 主 developer 已真实完成 uv frozen dev 同步、锁一致性、Ruff、pnpm 10.11.0 frozen 安装与 vue-tsc/Vite 构建，均 exit 0；直连/代理 GET 返回精确 JSON 与 Python header；浏览器初始零请求、键盘触发成功、停本次后端后代理 HTTP 500 失败且隐藏旧成功、重启后恢复均通过。受控延迟转发确认请求中禁用且重复点击仅一次请求；network/http/protocol/timeout 为显式故障注入自检，不是后端真实业务错误。独立 CODE-REVIEW/TASK-04 尚未执行，测试 not-run，不算独立验收通过。

**当前验证更新（2026-11-21）：** 独立 CODE-REVIEW 已 PASSED（P0/P1/P2 均 0）；TASK-04 已 completed，38 项自动测试（pytest 11 + Node 27）与 11 个浏览器检查组全部 passed，必需行为 failed/blocked 均 0。测试执行日期按正式报告为 2026-11-20（UTC），本次文档同步日期为 2026-11-21；不是重新执行测试。 [独立审查](../../artifacts/weknora-python-vue3-rebuild/03-code/code-review-report.md) · [正式测试报告](../../artifacts/weknora-python-vue3-rebuild/04-e2e/test-report.md) · [新增用例](../../artifacts/weknora-python-vue3-rebuild/04-e2e/added-cases.md)。上述待执行/not-run 仅属开发阶段历史，当前以正式报告为准；仅健康子项，不表示全 S1 或上传问答完成。main 收尾后暂停等待用户明确继续，本轮未提交推送。

## 1. 准备与安装

需要 Python 3.12+ 和可调用的 `uv`。每个终端确认工作目录，以下从 `refactor/` 开始：

```sh
cd python/backend
uv --version
uv sync --frozen --extra dev
```

`pyproject.toml` 声明允许的依赖和 Python 版本，`uv.lock` 固定实际解析版本，`uv sync` 创建或同步本项目 `.venv`。工具不存在或下载受限时记录 blocked，不改用未锁定的系统环境来冒充可复现安装。本轮无需后端 `.env`，不读取父工程 `.env`，也不需要任何凭据。

## 2. 启动与检查

### 从 `python/` 根目录同时启动前后端

如果需要同时启动 Python 后端和 Vue 前端，在 `python/` 目录执行：

```sh
npm run dev
```

该命令会在 `python/backend` 中运行本 README 后续所示的 Uvicorn 命令，并在 `python/frontend` 中启动 Vite。后端单独调试时仍可按本节命令执行。

保持后端终端运行：

```sh
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload
```

在另一个验证终端执行：

```sh
curl -i http://127.0.0.1:8080/health
```

预期是 HTTP 200、`Content-Type: application/json`（可带 charset）、`X-WeKnora-Implementation: python-fastapi`，JSON 严格为：

```json
{"status":"ok"}
```

该 header 只用于识别本地误连原 Go 的情况，不是身份认证。HTTP 健康不代表数据库、模型或业务已可用。健康入口免鉴权、无请求体或参数，路径不是 `/api/v1/health`；仅声明此健康子集与原版 JSON 合同兼容，不声明全量 `/api/v1` 或数据库兼容已完成。

框架边界按本轮合同单列：`GET /health/` 与未知路径返回 404，不重定向；`POST /health` 返回 405。未捕获内部异常属于框架 500，不给健康添加虚构的业务错误码或依赖检查。

## 3. 检查与独立测试

开发自检命令：

```sh
uv run --frozen python -m ruff check app
```

独立测试工程师在 TASK-04 新增健康合同测试后，才能执行以下测试命令；当前不把测试文件或测试结果当作已经存在：

```sh
uv run --frozen python -m pytest -q tests/unit/test_health.py
uv run --frozen python -m ruff check .
```

分别记录 passed、failed、blocked、not-run。Ruff 不是 API 测试，curl 不是浏览器点击测试；不存在可直接运行的 `scripts/stage_check.py` 阶段验收工具。

## 4. 打开页面，亲自观察成功、失败与恢复

前端安装、构建及启动见[前端 README](../frontend/README.md)。默认页面为 `http://127.0.0.1:5400`，开发服务器只代理相对路径 `/health` 到 `http://127.0.0.1:8080`。

1. 启动两端，打开页面及开发者工具 Network。初始应显示“待检测”，不自动请求健康接口。
2. 点击“检测后端连接”。应先显示请求中并禁用重复点击，再显示本次成功结果；核对 `/health`、200、JSON 和 Python header。
3. 只在自己本次启动后端的终端按 `Ctrl+C`，保留前端运行。再次点击应失败，不应显示上次成功 JSON。代理不可达可能表现为 HTTP 错误，不一定是浏览器 network 错误。
4. 用相同命令重启本次 Python 服务，再点击，应恢复成功，无需刷新整个应用。记录实际端口、响应和页面现象；本次实际验证为成功→代理 HTTP 500 失败→恢复成功。

如果 8080 被占用，不杀不明进程，也不要把旧 Go `/health` 当成本轮成功。选择已确认空闲的端口，例如：

```sh
uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8081 --reload
```

同时在前端目录以 `BACKEND_PROXY_TARGET=http://127.0.0.1:8081 pnpm dev --host 127.0.0.1` 启动或重启开发服务器。前端端口冲突时使用 `FRONTEND_PORT=5401`，页面入口同步改为 `http://127.0.0.1:5401`；Vite 的 `strictPort` 不会悄悄换端口。

## 5. 从入口理解处理方法

冻结的方法映射是 `app/main.py` 的 `create_app()` 创建应用并注册路由、模块级 `app` 供 uvicorn 导入、`health()` 返回 JSON 并设置身份 header。`app.main:app` 左边是 Python 模块，右边是模块中的应用对象。常量健康响应无需额外 service/repository 分层。

实际源码已核对：`app/main.py:8–12` 为 create_app，10 行关闭重定向、11 行注册路由；15–18 行为 health（17 行 header）；21 行导出 app。逐步讲解见[本轮学习指南](../../artifacts/weknora-python-vue3-rebuild/03-code/learning-guide.md)，接口细节见[API 文档](../../artifacts/weknora-python-vue3-rebuild/03-code/api-docs.md)。

完成本轮独立审核、测试与知识记录后，由 main 持久化 `awaiting_user_continue=true` 并暂停。下一小需求仅在用户明确“继续”后确认，并使用独立增量任务目录，不覆盖本轮历史。
