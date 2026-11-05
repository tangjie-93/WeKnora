# 仓库指南

仓库：[`tangjie-93/WeKnora`](https://github.com/tangjie-93/WeKnora)。使用 `git clone https://github.com/tangjie-93/WeKnora.git` 克隆。

## 项目结构与模块组织

此工作区包含分阶段替换 `WeKnora` 的 `Python` 实现。必须保留现有数据库结构和 `/api/v1` 接口契约。

- `python/backend/app/`：包含 `FastAPI` 路由与数据模式、服务、仓储、领域实体、集成和核心配置。业务逻辑放在服务层，持久化逻辑放在仓储层。
- `python/backend/tests/`：包含单元测试、`API` 端到端测试、共享测试夹具和契约报告。
- `python/backend/scripts/`：包含阶段验收、模型配置和本地模拟模型工具。
- `python/frontend/src/`：独立的 `Vue 3` 应用，包含页面、`API` 客户端和样式。
- `integration-web/src/`：独立的集成界面；其资源和组件应保留在该应用内。
- `docs/`：包含架构、进度和相关文档。`server-deploy/` 存放部署资源。

## 构建、测试与开发命令

使用 `Python` 的 `3.12+` 版本和虚拟环境。后端命令在 `python/backend/` 目录下执行：

- `python -m pip install -e ".[dev]"`：安装后端及开发依赖。
- `python -m uvicorn app.main:app --port 8080 --reload`：启动 `API` 服务；通过 `/health` 检查健康状态。
- `python -m pytest -q`：运行后端测试套件。
- `python -m ruff check .`：运行已配置的代码静态检查。
- `python scripts/stage_check.py --stage phase1`：运行阶段验收；选择适用的阶段。各阶段共享数据库和日志文件，因此必须串行执行。

在任一前端目录中，先运行 `npm install`，再运行 `npm run dev`。`python/frontend` 使用端口 `5400`，并将 `API` 请求代理至端口 `8080`；`integration-web` 使用端口 `8300`。运行 `npm run build` 进行 `TypeScript` 类型检查并生成生产构建产物。

## 代码风格与命名规范

`Python` 使用四个空格缩进，函数和模块采用 `snake_case` 命名，类采用 `PascalCase` 命名。`Ruff` 的目标版本为 `Python` 的 `3.12` 版本，每行最多 `110` 个字符。遵循周围 `TypeScript` 代码的缩进和引号风格；组件使用 `PascalCase.vue` 命名。复用现有的身份认证、`API` 和服务辅助工具。

## 测试指南

使用 `pytest` 和 `pytest-asyncio`，测试文件命名为 `test_*.py`。纯逻辑测试放在 `tests/unit/`，`API` 工作流测试放在 `tests/e2e/`。复用 `tests/conftest.py` 中的测试夹具和模拟模型服务。当前未配置数值化的覆盖率阈值；测试应覆盖变更行为、权限校验失败和持久化。真实模型测试需要显式设置 `RUN_REAL_LLM=1` 并配置凭据。

## 提交与拉取请求指南

历史提交使用带作用域的约定式提交信息：`feat(scope): ...`、`fix(scope): ...`、`docs(refactor): ...` 和 `chore(refactor): ...`。每次提交应聚焦单一主题。描述行为变更，关联相关问题，列出验证命令及结果；界面变更需附上截图。

## 安全与配置

按需将后端的 `.env.example` 复制为 `.env`。凭据、本地数据库和真实模型密钥不得包含在提交或测试报告中。
