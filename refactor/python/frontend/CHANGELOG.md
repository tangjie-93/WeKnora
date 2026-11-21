---
task_id: WEKNORA-REBUILD-20261120
stage: TASK-03
author: 开发工程师
date: 2026-11-20
run_mode: auto
---

# `Vue` 前端变更记录

## [Unreleased] - `2026-11-21`：学习工作台导航切片

- 本轮范围：共享外壳与服务检测 `/#/health`、开发进度 `/#/progress` 两页；根入口跳转健康页，未知 hash 显示未找到并可返回。hash 导航不是 HTTP `GET /health`。
- 健康链保留 `src/views/health/components/HealthPanel.vue`、`src/views/health/hooks/useHealthCheck.ts` 与 `src/api/health.ts`；切离取消、重入待检测与无自动检测已由本轮独立路由回归验证。
- 进度仅为版本化静态事实，不是实时服务／工作流状态、完成率或运行 `trace`。数据库、上传、解析、检索、问答未开始，整个 `S1` 未全量验收。
- 本轮无后端行为变化，不修改 HTTP API、代理或部署；交付完成审核、测试、知识记录与讲解后暂停，等待用户明确继续。
- 本轮实际结论：独立 CODE-REVIEW `PASSED`、`P0/P1=0`，唯一 `P2` 报告定位文字已修正；TASK-04 实跑 Node `27` 项、浏览器 `25` 组（导航 `13`／健康 `11`／真实服务 `1`）均通过，必要项 failed/blocked 为 `0`，frozen 安装与类型检查／构建通过，未发现生产缺陷。证据：[独立审查](../../artifacts/weknora-learning-workbench/03-code/code-review-report.md)、[测试报告](../../artifacts/weknora-learning-workbench/04-e2e/test-report.md)、[测试用例](../../artifacts/weknora-learning-workbench/04-e2e/added-cases.md)、[学习指南](../../artifacts/weknora-learning-workbench/03-code/learning-guide.md)。本次只同步正式记录，不重跑测试；真实失败采用浏览器离线恢复，未停服务，受控注入不当作真实后端故障。

以下保留上一健康子项的历史开发快照与验收记录，数量与结论不适用于本轮导航增量。

## [Unreleased] - 2026-11-20

### Added — `/health` 连接工作台

- 已实现指定栈 Vue 3 / Vite / TypeScript / pnpm / Tailwind CSS / vue-query / Pinia 的单页面健康工作台，点击后真实检测 Python 后端。
- 文档列出待检测、请求中、成功、失败及停后端恢复的观察步骤，说明相对请求、可配置代理、端口冲突和固定错误分类。
- Pinia 仅注册，服务端结果由 vue-query 管理；方法解释是静态源码说明，不是后端逐方法运行追踪。

### 兼容性与范围

请求仅为相对 `GET /health`，校验 200、JSON 和 Python 身份 header，防止误连原 Go。默认本机 5400 代理本机 8080，可配置 `FRONTEND_PORT` 与 `BACKEND_PROXY_TARGET`；不改变原工程。没有登录、上传、解析、检索、问答、SSE 或持久化，不声明全量界面或 `/api/v1` 兼容已完成。

### 上一健康子项独立验证状态（`2026-11-21` 同步，历史证据）

独立 CODE-REVIEW 已 PASSED（P0/P1/P2 均 0）；TASK-04 已 completed，38 项自动测试（pytest 11 + Node 27）与 11 个浏览器检查组全部 passed，必需行为 failed/blocked 均 0。测试执行日期按正式报告为 2026-11-20（UTC），本次文档同步日期为 2026-11-21；不是重新执行测试。

[独立审查](../../artifacts/weknora-python-vue3-rebuild/03-code/code-review-report.md) · [正式测试报告](../../artifacts/weknora-python-vue3-rebuild/04-e2e/test-report.md) · [新增用例](../../artifacts/weknora-python-vue3-rebuild/04-e2e/added-cases.md)。下方 not-run 只记录开发阶段时点，不是当前独立测试状态。

保留告警/失败审计：pytest 有 1 条上游 StarletteDeprecationWarning（httpx/TestClient），未为消警增加依赖；pnpm ignored scripts（esbuild/vue-demi）及 url.parse 弃用提示未导致构建失败。TASK-04 首次从错误 cwd 调用 corepack pnpm --dir build，Corepack 先选到 pnpm 12.21.0 而失败；进入 python/frontend 后按固定 pnpm 10.11.0 重跑构建通过，未修改生产配置/锁。favicon 404、故障注入和停后端代理 500 属已说明的资源/诊断事件；最终浏览器应用异常与 warnings 均为空。

仅 S1 健康子项通过上述独立审查与行为测试，整个 S1、上传/解析/检索/问答及数据库/模型均未完成；内部 Python 500 注入、全浏览器/无障碍认证等报告列明 not-run 的项仍未执行。当前由 main 协调质量门禁与知识记录，收尾后暂停供用户查看；只有用户明确继续才新建独立增量目录，不自动实施下一需求。本轮未提交、未推送或发布；本文不改变 workflow-state、当前路由或暂停字段。

### 开发阶段快照（2026-11-20）

源码已编码，pnpm 10.11.0 frozen 安装与 build（vue-tsc + Vite）exit 0；浏览器初始零请求、键盘成功、停后端代理 HTTP 500 失败/隐藏旧成功、恢复、延迟转发中禁用/一次请求均自检通过；四类故障注入诊断通过。独立测试 TASK-04 not-run，最终以其正式报告为准。未提交、未推送或发布。

本轮审核、测试、知识记录后由 main 持久化等待继续并暂停；未经用户明确继续，不实施下一项。
