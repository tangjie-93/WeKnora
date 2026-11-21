# Vue 前端变更记录

本文件记录 `refactor/python/frontend/` 的实际开发进度。后端状态请查看[后端变更记录](./backend-changelog.md)，双端总览请查看[开发变更总览](./changelog.md)。

## 1. 当前状态

- 当前已完成模块：`/health` 连接工作台。
- 当前阶段：仅完成健康检查子集，不代表 `S1` 全量完成。
- 当前版本：`Unreleased`。

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
