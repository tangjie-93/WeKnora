---
name: python-unified-dev
summary: 在 python/ 根目录通过 npm run dev 同时启动 Vue 前端和 FastAPI 后端
status: approved
---

# `python/` 根目录统一开发启动设计

## 1. 目标与范围

在 `/Users/james/Desktop/github/WeKnora/refactor/python` 目录提供一个统一入口：

```sh
npm run dev
```

该命令同时启动现有 Vue 前端和 FastAPI 后端，不改变两端现有独立启动命令、端口、代理配置或业务代码。

本次不引入第三方并发运行依赖，不增加生产启动能力，不修改前端或后端运行逻辑。

## 2. 文件与职责

新增：

```text
python/package.json
python/scripts/dev.mjs
```

### `python/package.json`

作为工作区根目录的 Node 启动入口，仅声明：

```json
{
  "private": true,
  "scripts": {
    "dev": "node scripts/dev.mjs"
  }
}
```

不添加依赖、不添加 lockfile。`python/frontend/package.json` 继续由前端自身管理依赖和 `pnpm` 版本。

### `python/scripts/dev.mjs`

使用 Node.js 内置 `node:child_process` 的 `spawn` 启动两个子进程：

- 后端工作目录：`python/backend`
- 后端命令：`uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload`
- 前端工作目录：`python/frontend`
- 前端命令：`pnpm dev --host 127.0.0.1`

脚本通过基于自身文件位置计算绝对工作目录，避免用户从 `python/` 目录执行时依赖当前目录之外的路径假设。

## 3. 生命周期与日志

启动器应做到：

1. 一次启动前端和后端两个子进程。
2. 使用继承的标准输入、输出和错误流，让两端日志直接显示在当前终端。
3. 为日志增加简短的 `[frontend]` / `[backend]` 前缀，便于区分来源；如果实现前缀会改变流处理复杂度，则优先保证原始日志可见性和退出行为。
4. 收到 `SIGINT` 或 `SIGTERM` 时向两个子进程转发终止信号并等待清理。
5. 任一子进程异常退出时，终止另一个子进程并以非零状态退出，避免用户误以为项目仍完整运行。
6. 子进程启动失败时输出明确的命令和工具提示，不吞掉原始错误。

启动前检查默认开发端口 `8080` 和 `5400`；若存在监听进程，发送 `SIGTERM` 并等待端口释放后再启动。只处理这两个配置的默认端口，不扫描或停止其他端口上的进程；若旧进程无法停止，则输出明确错误并退出。

## 4. 数据流与配置

```text
npm run dev (python/)
    ├── spawn uv run ... (cwd=python/backend)
    │       └── FastAPI :8080
    └── spawn pnpm dev ... (cwd=python/frontend)
            └── Vite :5400
                    └── /health proxy -> http://127.0.0.1:8080
```

现有环境变量继续生效：

- `FRONTEND_PORT`：由 Vite 配置读取
- `BACKEND_PROXY_TARGET`：由 Vite 配置读取

统一启动器不硬编码这些可配置项，也不读取或复制秘密配置。

## 5. 错误处理与边界

- 未安装 `uv`：后端子进程启动失败，终端显示工具缺失信息，并停止前端。
- 未安装 `pnpm`：前端子进程启动失败，终端显示工具缺失信息，并停止后端。
- `5400` 或 `8080` 被占用：启动前停止占用默认端口的监听进程；无法停止时退出并报告端口仍被占用。
- 用户按 `Ctrl+C`：属于正常退出，不将主动终止误报为服务故障。
- 子进程退出码非零：统一启动器返回非零退出码。
- 只关闭一个子进程后，另一个不应继续孤立运行。

## 6. 验证方案

从 `python/` 目录执行：

```sh
npm run dev
```

验证：

1. 前端地址 `http://127.0.0.1:5400` 返回页面。
2. 后端地址 `http://127.0.0.1:8080/health` 返回 HTTP 200 和 `{"status":"ok"}`。
3. 前端代理地址 `http://127.0.0.1:5400/health` 返回同样的健康响应。
4. 在终端按 `Ctrl+C` 后，前后端进程均退出，端口释放。
5. 使用 `FRONTEND_PORT` 和 `BACKEND_PROXY_TARGET` 的现有配置时，统一启动器不覆盖这些配置。
6. 默认端口被旧进程占用时，启动器先停止旧监听进程；若无法停止，启动失败信息可见并退出。

## 7. 非目标

- 不将 `integration-web` 纳入本次统一启动。
- 不把后端改成 npm 脚本或 Node 服务。
- 不替换 `pnpm` 为 `npm install`。
- 不修改 Vue、FastAPI、Vite 或代理业务代码。
- 不增加 concurrently、助记进程管理器或其他 npm 依赖。
