---
task_id: WEKNORA-REBUILD-20261120
stage: TASK-03
author: 开发工程师
date: 2026-11-20
run_mode: auto
---

# Vue 前端：健康检查工作台

本轮只提供一个可点击的“检测后端连接”工作台：浏览器通过同源相对 `/health` 请求，经 Vite 开发代理访问 Python FastAPI。页面状态由 `@tanstack/vue-query` 管理，Pinia 只完成应用注册，不复制服务端结果。没有登录、上传、问答、SSE、持久化或模拟 trace。

**开发阶段快照（2026-11-20）：** 2026-11-20 主 developer 已真实完成 uv frozen dev 同步、锁一致性、Ruff、pnpm 10.11.0 frozen 安装与 vue-tsc/Vite 构建，均 exit 0；直连/代理 GET 返回精确 JSON 与 Python header；浏览器初始零请求、键盘触发成功、停本次后端后代理 HTTP 500 失败且隐藏旧成功、重启后恢复均通过。受控延迟转发确认请求中禁用且重复点击仅一次请求；network/http/protocol/timeout 为显式故障注入自检，不是后端真实业务错误。独立 CODE-REVIEW/TASK-04 尚未执行，测试 not-run，不算独立验收通过。

**当前验证更新（2026-11-21）：** 独立 CODE-REVIEW 已 PASSED（P0/P1/P2 均 0）；TASK-04 已 completed，38 项自动测试（pytest 11 + Node 27）与 11 个浏览器检查组全部 passed，必需行为 failed/blocked 均 0。测试执行日期按正式报告为 2026-11-20（UTC），本次文档同步日期为 2026-11-21；不是重新执行测试。 [独立审查](../../artifacts/weknora-python-vue3-rebuild/03-code/code-review-report.md) · [正式测试报告](../../artifacts/weknora-python-vue3-rebuild/04-e2e/test-report.md) · [新增用例](../../artifacts/weknora-python-vue3-rebuild/04-e2e/added-cases.md)。上述待执行/not-run 仅属开发阶段历史，当前以正式报告为准；仅健康子项，不表示全 S1 或上传问答完成。main 收尾后暂停等待用户明确继续，本轮未提交推送。

## 1. 安装与构建

需要 Node.js >= 22.12、pnpm 10.11.0 和 Python 后端（若要点击成功）。从 `refactor/` 进入前端目录：

```sh
cd python/frontend
node --version
pnpm --version
pnpm install --frozen-lockfile
pnpm build
```

`package.json` 的 `build` 应包含 `vue-tsc --noEmit && vite build`。`pnpm-lock.yaml` 是唯一前端锁文件；不要用 npm install 或补写 `package-lock.json` 替代它。Corepack 不可用时按项目环境安装指定 pnpm，工具或 registry 受限则记录 blocked，不把另一台机器的构建当作本机证据。

## 2. 启动与配置

### 从 `python/` 根目录同时启动前后端

如果需要同时启动 Python 后端和本 Vue 前端，在 `python/` 目录执行：

```sh
npm run dev
```

该命令由 `python/scripts/dev.mjs` 管理两个现有开发进程；前端单独调试时仍可在本目录执行 `pnpm dev --host 127.0.0.1`。

默认启动：

```sh
pnpm dev --host 127.0.0.1
```

打开 `http://127.0.0.1:5400`。Vite 默认只监听本机、`strictPort=true`，并且只将 `/health` 代理到 `http://127.0.0.1:8080`。浏览器代码始终请求相对 `/health`，不拼接后端绝对地址。

可在启动前用无秘密环境变量改地址：

```sh
BACKEND_PROXY_TARGET=http://127.0.0.1:8081 FRONTEND_PORT=5401 pnpm dev --host 127.0.0.1
```

此时后端应以 8081 运行，页面入口是 `http://127.0.0.1:5401`。也可写入本地 `.env`；不要把真实凭据或生产地址放入 `.env.example`。端口被占用时不要让工具自动换端口，也不要停止不明进程；选择空闲端口后同步前端入口和代理目标。

## 3. 亲自点击成功、停止后端失败与恢复

1. 先启动本次 Python 后端，再启动 Vite。打开页面和浏览器 Network，确认初始是“待检测”，没有自动发出 `/health`。
2. 点击“检测后端连接”。按钮进入请求中并防止重复点击；请求成功后核对 Network 中的相对 `/health`、200、`status: ok` 和 `X-WeKnora-Implementation: python-fastapi`，再对照页面显示。
3. 只停止本次启动的 Python 进程，保留前端。再次点击，页面应进入失败并给固定诊断，不能保留旧成功结果冒充本次成功。代理失败的响应可能被归为 HTTP 或 protocol；不要把它写成 FastAPI 业务错误。
4. 重启本次 Python 服务，再点击；页面应恢复成功。本次真实页面验证已观察到成功→停后端代理 HTTP 500→恢复成功；独立 TASK-04 仍未执行。

前端成功条件不是只有 HTTP 200：还必须是 JSON、对象 `status` 为 `ok`、身份 header 正确。`fetchHealth` 的固定错误分类为 `network`、`timeout`、`http`、`protocol`；超时阈值为 5000ms。页面不渲染代理返回的 HTML、堆栈或任意原始错误正文。请求取消不伪造成超时或成功。

## 4. 从点击到页面更新的源码阅读顺序

按实际文件阅读，而不是把静态说明当运行 trace：

1. `src/views/health/components/HealthPanel.vue` 的 `onCheckClick()` 接收按钮事件并调用 `check()`。
2. `src/views/health/hooks/useHealthCheck.ts` 的 `useHealthCheck()` 建立禁用自动请求的 query，`check()` 主动 `refetch`，以 `idle/checking/success/failure` 映射页面状态并保护并发点击。
3. `src/api/health.ts` 的 `fetchHealth(signal?)` 用相对 `/health` 发请求，校验 HTTP、内容类型、JSON 形状和 Python 身份，并清理 5000ms 超时资源。
4. `vite.config.ts` 的 `server.proxy` 只负责开发期转发，不是业务方法，也不记录 trace。
5. `python/backend/app/main.py` 的 FastAPI `health()` 返回精确 JSON 和身份 header；响应沿代理回到 fetch，再由 query 更新页面模板。

实际定位：`src/views/health/components/HealthPanel.vue:47–49` onCheckClick；`src/views/health/hooks/useHealthCheck.ts:12–67` hook、48–57 check、60–64 取消；`src/api/health.ts:33–74` fetchHealth；`vite.config.ts:10–31` 配置；`src/main.ts:8–9` 插件注册；后端 `app/main.py:15–18` health。详见本任务的 `03-code/learning-guide.md` 和 `api-docs.md`。

## 5. 本轮边界与下一步

刷新页面后回到待检测；没有数据库、localStorage、sessionStorage、JSONL 或 trace 表。健康结果只表示当前 Python HTTP 应用响应，不表示数据库、模型、队列或完整业务可用。上传、解析、检索、问答、SSE 和全量 `/api/v1` 兼容仍未实现。

完成独立审核、测试和知识记录后，主线程会暂停并持久化等待用户继续。下一项应由用户明确继续后，在新的增量任务目录中重新确认，不自动接着实现。
