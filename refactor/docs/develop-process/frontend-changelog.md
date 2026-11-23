---
task_id: WEKNORA-PRODUCT-AUTH-20261122
stage: TASK-03
author: 开发工程师
date: 2026-11-22
run_mode: auto
---

# `Vue` 前端变更记录

## 当前正式结论（`2026-11-22`）

独立复审 `PASSED/P0=0/P1=0/P2=0`；独立 `TASK-04 PASSED/completed`：前端新增 `14`／全套 `41 passed`，真实浏览器 `29` 场景组；后端新增 `92`／全套 `220 passed`，必需失败／阻塞 `0`，静态／类型／构建通过，无生产缺陷。真实账户／空间主产品、辅助工作台、恢复／退出、`CR-001–005`、响应式／键盘及竞态／重启均独立回归。

见[复审](../../artifacts/weknora-product-auth/03-code/code-review-report.md)、[正式测试](../../artifacts/weknora-product-auth/04-e2e/test-report.md)、[新增用例](../../artifacts/weknora-product-auth/04-e2e/added-cases.md)。首轮失败、两处测试自身问题修正及上游警告保留；本文同步不重跑。五接口／`SQLite v7` 认证子集不等于知识库 `CRUD` 或全量迁移；生产／`PostgreSQL`／跨浏览器矩阵等仍范围外 `not-run`。安全后端分端命令保留 `--no-proxy-headers`，禁止统一启动器用于认证；收尾后暂停，下一需求需明确继续。

## 历史：首轮审核纠正与修复（下方未执行状态仅属当时）

首轮独立 `CODE-REVIEW FAILED`（`P0=0/P1=3/P2=2`）；下方修复前开发自检 `PASS` 历史保留，独立复审未执行，`TASK-04 not-run`。`CR-001` 修复代理剥除不可信转发头，后端安全分端命令须带 `--no-proxy-headers`；真实代理对端共享桶，不信 `X-Forwarded-For`，旧统一 `npm run dev` 不支持认证运行、不要执行。`CR-003` 修复令牌已安装后的首次 `me` 失败恢复，复用原会话重试或真实退出；`401` 清理、`403` 隐藏身份且可退出，不反复提交密码积累会话。`CR-002` 的非法原始请求封装由后端同步，实际源码／最终行号已核对，协调者恢复浏览器 `7` 项、真实换头限流／代理剥头、原始字节 `14` 项／受控递归 `3` 项与最终回归开发自检通过，来源与自然深度未复现限制见[学习指南](../../artifacts/weknora-product-auth/03-code/learning-guide.md)。

本文件记录 `refactor/python/frontend/` 的实际开发进度。后端状态请查看[后端变更记录](./backend-changelog.md)，双端总览请查看[开发变更总览](./changelog.md)。

## 1. 修复前实现与自检快照（当前审核状态以上方纠正为准）

- 当前版本 `Unreleased`，`2026-11-22` 身份产品增量已核对实际源码并同步开发自检；真实注册、登录、账户／个人空间为主，工作台仅一个辅助模块。
- 页面为 `/#/register`、`/#/login`、受保护 `/#/account` 与公开 `/#/workbench/health`、`/#/workbench/progress`；根入口按身份跳转，旧 `/#/health`、`/#/progress` 兼容跳转，未知地址可恢复。
- 五个真实接口为 `POST /api/v1/auth/register`、`POST /api/v1/auth/login`、`POST /api/v1/auth/refresh`、`GET /api/v1/auth/me`、`POST /api/v1/auth/logout`。注册后回登录；刷新 `refreshToken` 与 `access_token/refresh_token` 精确适配，账户只读 `me.data`；`Pinia` 存会话、`vue-query` 存身份，退出服务端撤销失败保留待重试而不报成功。
- 后端使用原版 `SQLite 000000–000007` 完整前缀的 `v7` 认证结构子集；不是全量迁移或整个 `S2/S3` 验收，不交付知识库／上传／问答／模型配置，不提供虚假数据或空壳操作。`Vite` 增加同源 `/api/v1` 代理，健康仍手动检测与切离取消。
- 初始化、持久秘密、自有空闲端口分端启动、浏览器步骤与统一启动器停止 `8080/5400` 监听者的警告见[前端说明](../../python/frontend/README.md)。实际函数／行号已只读核对，开发者本轮 `pnpm build` 与既有 `Node 27` 项通过，协调者真实浏览器账户旅程／移动／键盘、并发刷新与退出故障恢复通过；受控客户端 `6` 项／存储 `7` 项另列，本文未重跑，独立 `CODE-REVIEW/TASK-04` 仍为 `not-run`；历史导航／健康证据不代替本轮。见[学习指南](../../artifacts/weknora-product-auth/03-code/learning-guide.md)。

### 历史 `2026-11-21`：导航与静态进度切片

- 根入口跳转 `/#/health`，未知 hash 显示未找到、保留错误 URL 并可返回服务检测；浏览器 hash 导航与 HTTP `GET /health` 不同。
- 保留健康组件、hook 和 API 当前目录；手动检测、在途离开取消、重入待检测及迟到响应隔离由本轮独立测试验证，不以历史健康测试代替。
- `/#/progress` 仅展示版本化静态事实与报告定位，不读本机状态文件、不请求 API，不是实时服务／工作流状态、完成率或运行 `trace`。
- 本轮无后端行为变化；数据库、上传、解析、检索、问答未开始，整个 `S1` 未全量验收。每轮一个需求，完成必要审核、测试、知识与讲解后暂停等待用户明确继续。
- 本轮实际验证：独立 CODE-REVIEW `PASSED`、`P0/P1=0`，唯一 `P2` 报告定位文字已修；TASK-04 本增量重跑 Node `27` 项与浏览器 `25` 组（导航 `13`＋健康 `11`＋真实服务 `1`），全部通过，必要项 failed/blocked 为 `0`；frozen 安装、类型检查／构建通过，未发现生产缺陷。证据：[审查](../../artifacts/weknora-learning-workbench/03-code/code-review-report.md)、[测试](../../artifacts/weknora-learning-workbench/04-e2e/test-report.md)、[用例](../../artifacts/weknora-learning-workbench/04-e2e/added-cases.md)、[学习指南](../../artifacts/weknora-learning-workbench/03-code/learning-guide.md)。本次文档同步未重跑测试；失败恢复为真实浏览器离线／在线，未停后端；取消／迟到响应的受控注入边界见报告。

## 2. `2026-11-21`：统一开发启动命令

### Added

- 在 `python/` 根目录提供 `npm run dev` 统一启动入口。
- 启动器从 `python/frontend` 执行现有 `pnpm dev --host 127.0.0.1` 命令。
- 启动前自动停止占用 `5400` 的旧监听进程，并在退出时联动清理后端进程。

### 验证

- `node --check python/scripts/dev.mjs` 通过。
- `GET http://127.0.0.1:5400/health` 通过 Vite 代理返回 `200` 和 `{"status":"ok"}`。

## 3. `2026-11-20`：首个健康检查增量

### Added

- 建立 `Vue 3`、`Vite`、`TypeScript`、`pnpm`、`Tailwind CSS`、`vue-query` 和 `Pinia` 的单页面健康工作台。
- 用户点击后通过同源 `/health` 请求检测 `Python` 后端，不自动请求、不自动重试。
- 校验 `HTTP 200`、`JSON` 响应和 `Python` 身份 `header`，并将网络、超时、HTTP 和协议问题归类为固定安全文案。
- 补充本地代理目标、端口配置、失败恢复和浏览器检查说明。

### Changed — `2026-11-21` 目录整理

- 页面入口移至 `src/views/health/index.vue`。
- 页面私有组件移至 `src/views/health/components/HealthPanel.vue`。
- 页面私有 hook 移至 `src/views/health/hooks/useHealthCheck.ts`。
- 保留 `src/api/health.ts` 作为接口客户端，并同步测试、README 和浏览器动态导入路径。

### 兼容范围

请求仅为相对 `GET /health`。默认前端端口为 `5400`，开发代理目标为本机 `8080`，可用 `FRONTEND_PORT` 和 `BACKEND_PROXY_TARGET` 配置。

本轮不改变原工程，不提供登录、上传、解析、检索、问答、`SSE`、持久化或全量 `/api/v1` 兼容。

### 验证与证据

- 独立代码审查：通过，`P0/P1/P2` 均为 `0`。
- 前端 `Node` 测试：`27` 项通过。
- 浏览器检查：`11` 组通过，覆盖初始零请求、键盘操作、成功、失败、恢复、超时、重复点击和移动端无横向溢出。
- 构建：`pnpm build` 通过，包含 `vue-tsc --noEmit` 和 `Vite` 构建。
- 证据：[代码审查报告](../../artifacts/weknora-python-vue3-rebuild/03-code/code-review-report.md)、[正式测试报告](../../artifacts/weknora-python-vue3-rebuild/04-e2e/test-report.md)、[新增用例](../../artifacts/weknora-python-vue3-rebuild/04-e2e/added-cases.md)。
- 测试执行日期为 `2026-11-20`（`UTC`）；本文件于 `2026-11-21` 同步，未因本次整理重新执行前端测试。

### 已知告警与边界

- `pnpm` 安装阶段的 `ignored scripts`（`esbuild`、`vue-demi`）和 `url.parse` 弃用提示未导致构建失败。
- `favicon 404`、故障注入和停后端后的代理 `500` 属已记录的诊断事件，不代表应用业务错误。
- 本轮未提交、未推送、未发布。
