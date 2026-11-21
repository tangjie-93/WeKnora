---
task_id: WEKNORA-REBUILD-20261120
stage: TASK-03
author: 开发工程师
date: 2026-11-20
run_mode: auto
---

# Vue 前端变更记录

## [Unreleased] - 2026-11-20

### Added — `/health` 连接工作台

- 已实现指定栈 Vue 3 / Vite / TypeScript / pnpm / Tailwind CSS / vue-query / Pinia 的单页面健康工作台，点击后真实检测 Python 后端。
- 文档列出待检测、请求中、成功、失败及停后端恢复的观察步骤，说明相对请求、可配置代理、端口冲突和固定错误分类。
- Pinia 仅注册，服务端结果由 vue-query 管理；方法解释是静态源码说明，不是后端逐方法运行追踪。

### 兼容性与范围

请求仅为相对 `GET /health`，校验 200、JSON 和 Python 身份 header，防止误连原 Go。默认本机 5400 代理本机 8080，可配置 `FRONTEND_PORT` 与 `BACKEND_PROXY_TARGET`；不改变原工程。没有登录、上传、解析、检索、问答、SSE 或持久化，不声明全量界面或 `/api/v1` 兼容已完成。

### 当前独立验证状态（2026-11-21 同步）

独立 CODE-REVIEW 已 PASSED（P0/P1/P2 均 0）；TASK-04 已 completed，38 项自动测试（pytest 11 + Node 27）与 11 个浏览器检查组全部 passed，必需行为 failed/blocked 均 0。测试执行日期按正式报告为 2026-11-20（UTC），本次文档同步日期为 2026-11-21；不是重新执行测试。

[独立审查](../../artifacts/weknora-python-vue3-rebuild/03-code/code-review-report.md) · [正式测试报告](../../artifacts/weknora-python-vue3-rebuild/04-e2e/test-report.md) · [新增用例](../../artifacts/weknora-python-vue3-rebuild/04-e2e/added-cases.md)。下方 not-run 只记录开发阶段时点，不是当前独立测试状态。

保留告警/失败审计：pytest 有 1 条上游 StarletteDeprecationWarning（httpx/TestClient），未为消警增加依赖；pnpm ignored scripts（esbuild/vue-demi）及 url.parse 弃用提示未导致构建失败。TASK-04 首次从错误 cwd 调用 corepack pnpm --dir build，Corepack 先选到 pnpm 12.21.0 而失败；进入 python/frontend 后按固定 pnpm 10.11.0 重跑构建通过，未修改生产配置/锁。favicon 404、故障注入和停后端代理 500 属已说明的资源/诊断事件；最终浏览器应用异常与 warnings 均为空。

仅 S1 健康子项通过上述独立审查与行为测试，整个 S1、上传/解析/检索/问答及数据库/模型均未完成；内部 Python 500 注入、全浏览器/无障碍认证等报告列明 not-run 的项仍未执行。当前由 main 协调质量门禁与知识记录，收尾后暂停供用户查看；只有用户明确继续才新建独立增量目录，不自动实施下一需求。本轮未提交、未推送或发布；本文不改变 workflow-state、当前路由或暂停字段。

### 开发阶段快照（2026-11-20）

源码已编码，pnpm 10.11.0 frozen 安装与 build（vue-tsc + Vite）exit 0；浏览器初始零请求、键盘成功、停后端代理 HTTP 500 失败/隐藏旧成功、恢复、延迟转发中禁用/一次请求均自检通过；四类故障注入诊断通过。独立测试 TASK-04 not-run，最终以其正式报告为准。未提交、未推送或发布。

本轮审核、测试、知识记录后由 main 持久化等待继续并暂停；未经用户明确继续，不实施下一项。
