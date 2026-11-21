# 仓库指南

仓库：[`tangjie-93/WeKnora`](https://github.com/tangjie-93/WeKnora)。使用 `git clone https://github.com/tangjie-93/WeKnora.git` 克隆。

每次提交 `push` 内容到 `GitHub` 仓库时，都需要同步更新 `docs/develop-process/changelog.md` 总览及对应的 `backend-changelog.md` 或 `frontend-changelog.md`，按路由模块总结提交内容和当前项目进度。

## 项目结构与模块组织

此工作区包含分阶段替换 `WeKnora` 的 `Python` 实现。必须保留现有数据库结构和 `/api/v1` 接口契约。

- `python/backend/app/`：本轮最小 `FastAPI` 健康入口；后续按需要增加服务、仓储等业务分层。
- `python/backend/tests/`：由独立测试阶段按需添加健康合同测试，后续扩展测试支持。
- `python/backend/scripts/`：后续按需建立，当前不提供 `stage_check.py` 或模型工具。
- `python/frontend/src/`：独立的 `Vue 3` 应用，包含页面、`API` 客户端和样式。
- `integration-web/src/`：独立的集成界面；其资源和组件应保留在该应用内。
- `docs/`：包含架构、进度和相关文档。`server-deploy/` 存放部署资源。

## 构建、测试与开发命令

使用 `Python` 的 `3.12+` 版本和虚拟环境。后端命令在 `python/backend/` 目录下执行：

- `uv sync --frozen --extra dev`：根据 `uv.lock` 同步后端及开发依赖。
- `uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload`：启动本机服务；`/health` 仅检查 HTTP 应用存活。
- `uv run --frozen python -m pytest -q`：独立测试阶段添加测试后运行后端测试套件。
- `uv run --frozen python -m ruff check app`：检查应用源码；测试到位后可检查 `.`。
- 当前没有可执行的 `scripts/stage_check.py`；本轮不接数据库或模型。

在 `python/frontend/` 使用 `pnpm install --frozen-lockfile`、`pnpm build`（`vue-tsc --noEmit && vite build`）和 `pnpm dev --host 127.0.0.1`。默认页面端口 `5400`，仅 `/health` 代理到本机 `8080`；可配置 `FRONTEND_PORT` 和 `BACKEND_PROXY_TARGET`，端口冲突时同步配置，不停止不明进程。`integration-web/` 仍使用 `npm install`、`npm run dev` 和 `npm run build`，端口 `8300`，不迁移其资源或依赖。

## 代码风格与命名规范

`Python` 使用四个空格缩进，函数和模块采用 `snake_case` 命名，类采用 `PascalCase` 命名。`Ruff` 的目标版本为 `Python` 的 `3.12` 版本，每行最多 `110` 个字符。遵循周围 `TypeScript` 代码的缩进和引号风格；组件使用 `PascalCase.vue` 命名。复用现有的身份认证、`API` 和服务辅助工具。

## 测试指南

使用 `pytest` 和 `pytest-asyncio`，测试文件命名为 `test_*.py`。纯逻辑测试放在 `tests/unit/`，`API` 工作流测试放在 `tests/e2e/`。复用 `tests/conftest.py` 中的测试夹具和模拟模型服务。当前未配置数值化的覆盖率阈值；测试应覆盖变更行为、权限校验失败和持久化。真实模型测试需要显式设置 `RUN_REAL_LLM=1` 并配置凭据。

## 提交与拉取请求指南

历史提交使用带作用域的约定式提交信息：`feat(scope): ...`、`fix(scope): ...`、`docs(refactor): ...` 和 `chore(refactor): ...`。每次提交应聚焦单一主题。描述行为变更，关联相关问题，列出验证命令及结果；界面变更需附上截图。

## 安全与配置

按需将后端的 `.env.example` 复制为 `.env`。凭据、本地数据库和真实模型密钥不得包含在提交或测试报告中。
