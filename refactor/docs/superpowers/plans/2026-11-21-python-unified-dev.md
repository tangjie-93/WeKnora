# Python 根目录一键启动 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `python/` 根目录提供 `npm run dev`，一次启动现有 FastAPI 后端和 Vue/Vite 前端，并在退出或任一子进程失败时正确清理另一端。

**Architecture:** 新增根目录 `package.json` 作为 Node 启动入口，并新增 `scripts/dev.mjs` 使用 Node.js 内置 `child_process.spawn()` 管理两个子进程。后端和前端继续使用现有命令、工作目录和环境变量；启动器不引入第三方依赖，启动默认端口前会停止其旧监听进程，不修改业务代码。

**Tech Stack:** Node.js 22+、ES modules、Node.js `child_process`/`path`/`url` 内置模块、`npm`、`pnpm`、`uv`、Vite、Uvicorn。

---

## 文件结构与职责

本次只新增以下两个运行文件：

- `python/package.json`：声明根目录为私有 Node 工作区，并将 `npm run dev` 映射到启动脚本；不声明依赖、不生成根目录 lockfile。
- `python/scripts/dev.mjs`：解析 `python/` 根目录，启动和管理 backend/frontend 两个子进程，处理日志、信号、退出码和清理。

不修改以下现有文件：

- `python/frontend/package.json`：继续提供前端自己的 `pnpm dev`。
- `python/frontend/vite.config.ts`：继续读取 `FRONTEND_PORT` 和 `BACKEND_PROXY_TARGET`。
- `python/backend/pyproject.toml`：继续由 `uv run --frozen` 管理后端环境。

验证只使用已有工具和 HTTP smoke check，不新增测试框架或生产依赖。

---

### Task 1: Add the root npm entrypoint

**Files:**
- Create: `python/package.json`

- [ ] **Step 1: Create the root package manifest**

写入以下完整内容：

```json
{
  "name": "weknora-python",
  "private": true,
  "scripts": {
    "dev": "node scripts/dev.mjs"
  }
}
```

`private` 防止根目录被误发布；不添加 `dependencies`、`devDependencies`、`packageManager` 或 lockfile，因为前端依赖仍由 `python/frontend/package.json` 管理。

- [ ] **Step 2: Verify npm resolves the new script without starting services**

Run from the repository root:

```sh
npm --prefix python run
```

Expected output contains:

```text
dev
```

Expected failure before Task 2 is only that `scripts/dev.mjs` does not yet exist; do not treat that as a runtime failure of the completed feature.

- [ ] **Step 3: Review the manifest scope**

确认 `python/package.json` 没有覆盖前端 package manifest，也没有写入后端依赖或任何秘密配置。由于当前工作区有其他未提交修改，不执行 `git add -A`。

---

### Task 2: Implement the process supervisor

**Files:**
- Create: `python/scripts/dev.mjs`

- [ ] **Step 1: Add path resolution and child-process definitions**

写入以下启动器基础代码。路径通过脚本自身位置计算，不依赖调用者当前工作目录；子进程分别从 backend/frontend 目录启动：

```js
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const workspaceDirectory = path.resolve(scriptDirectory, '..');

const commands = [
  {
    name: 'backend',
    command: 'uv',
    args: [
      'run',
      '--frozen',
      'uvicorn',
      'app.main:app',
      '--host',
      '127.0.0.1',
      '--port',
      '8080',
      '--reload',
    ],
    cwd: path.join(workspaceDirectory, 'backend'),
  },
  {
    name: 'frontend',
    command: 'pnpm',
    args: ['dev', '--host', '127.0.0.1'],
    cwd: path.join(workspaceDirectory, 'frontend'),
  },
];
```

- [ ] **Step 2: Add readable command formatting and process startup**

在同一文件追加以下函数。`stdio: 'inherit'` 保证 Vite、Uvicorn 和 `uv` 的原始日志直接显示在当前终端；启动器只输出统一的启动提示，不重写日志流，因此不会吞掉诊断信息。

```js
const childProcesses = new Map();
let shuttingDown = false;
let exitCode = 0;

function formatCommand(processDefinition) {
  return [processDefinition.command, ...processDefinition.args].join(' ');
}

function startProcess(processDefinition) {
  console.log(`[${processDefinition.name}] starting: ${formatCommand(processDefinition)}`);
  const child = spawn(processDefinition.command, processDefinition.args, {
    cwd: processDefinition.cwd,
    env: process.env,
    stdio: 'inherit',
  });

  childProcesses.set(processDefinition.name, child);

  child.on('error', (error) => {
    if (shuttingDown) {
      return;
    }

    console.error(`[${processDefinition.name}] failed to start: ${error.message}`);
    exitCode = 1;
    void shutdown(1);
  });

  child.on('exit', (code, signal) => {
    childProcesses.delete(processDefinition.name);

    if (shuttingDown) {
      return;
    }

    if (code !== 0) {
      exitCode = code ?? 1;
      console.error(
        `[${processDefinition.name}] exited unexpectedly with ${
          signal ? `signal ${signal}` : `code ${code}`
        }`,
      );
      void shutdown(exitCode);
      return;
    }

    console.log(`[${processDefinition.name}] exited normally; stopping the other service.`);
    void shutdown(0);
  });

  return child;
}
```

- [ ] **Step 3: Add coordinated shutdown and signal handling**

追加以下清理逻辑。第一次调用 `shutdown()` 设置 `shuttingDown`，避免子进程互相退出时重复触发清理；向当前启动器管理的子进程发送 `SIGTERM`，不重复处理已经退出的子进程。启动前的默认端口进程由端口清理步骤单独处理。

```js
async function shutdown(code) {
  if (shuttingDown) {
    return;
  }

  shuttingDown = true;
  exitCode = code;

  for (const child of childProcesses.values()) {
    if (child.exitCode === null && !child.killed) {
      child.kill('SIGTERM');
    }
  }

  if (childProcesses.size === 0) {
    process.exit(exitCode);
  }
}

process.on('SIGINT', () => {
  console.log('Stopping frontend and backend...');
  void shutdown(0);
});

process.on('SIGTERM', () => {
  void shutdown(0);
});
```

- [ ] **Step 4: Add the main startup flow**

文件末尾追加以下启动逻辑。启动阶段只要一个 `spawn()` 触发同步异常（例如工作目录不存在），就输出对应服务和命令，并清理已经启动的服务。

```js
try {
  for (const processDefinition of commands) {
    startProcess(processDefinition);
  }
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`Failed to start development services: ${message}`);
  void shutdown(1);
}
```

- [ ] **Step 5: Check the completed script for accidental scope expansion**

确认脚本满足以下约束：

- 仅导入 Node.js 内置模块。
- 后端命令仍为 `uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload`。
- 前端命令仍为 `pnpm dev --host 127.0.0.1`。
- `env: process.env` 保留 `FRONTEND_PORT`、`BACKEND_PROXY_TARGET` 等现有环境变量。
- 只检查默认开发端口 `8080`、`5400` 并停止其监听进程；不扫描其他端口、不自动换端口、不处理业务逻辑或秘密。

- [ ] **Step 6: Run a syntax check**

Run:

```sh
node --check python/scripts/dev.mjs
```

Expected output: no output and exit code `0`。

---

### Task 3: Run the unified command and verify the application

**Files:**
- Verify only: `python/package.json`, `python/scripts/dev.mjs`

- [ ] **Step 1: Check the target ports before starting**

Run:

```sh
for port in 5400 8080; do
  if lsof -nP -iTCP:$port -sTCP:LISTEN >/dev/null 2>&1; then
    printf 'port %s is already in use\\n' "$port"
    lsof -nP -iTCP:$port -sTCP:LISTEN
  else
    printf 'port %s is free\\n' "$port"
  fi
done
```

If a port is already occupied, do not kill an unknown process. Stop only a process known to belong to this task, or verify the unified command against alternate configured ports in Step 4.

- [ ] **Step 2: Start both services from `python/`**

Run in a dedicated terminal:

```sh
cd /Users/james/Desktop/github/WeKnora/refactor/python
npm run dev
```

Expected terminal behavior:

- one `[backend] starting:` line;
- one `[frontend] starting:` line;
- Uvicorn listens on `127.0.0.1:8080`;
- Vite listens on `127.0.0.1:5400`;
- both services remain attached to the same terminal.

- [ ] **Step 3: Verify backend, frontend, and proxy HTTP responses**

In a second terminal, run:

```sh
curl -i --max-time 5 http://127.0.0.1:8080/health
curl -i --max-time 5 http://127.0.0.1:5400/
curl -i --max-time 5 http://127.0.0.1:5400/health
```

Expected results:

- backend `/health`: HTTP `200`, JSON body `{"status":"ok"}`, header `x-weknora-implementation: python-fastapi`;
- frontend `/`: HTTP `200` and the Vite-served HTML page;
- frontend `/health`: HTTP `200`, JSON body `{"status":"ok"}`, and the same backend identity header.

- [ ] **Step 4: Verify configured non-default ports without changing files**

Use a confirmed free frontend port and a matching backend proxy target. For example:

```sh
cd /Users/james/Desktop/github/WeKnora/refactor/python
FRONTEND_PORT=5401 BACKEND_PROXY_TARGET=http://127.0.0.1:8080 npm run dev
```

Expected result: Vite listens on `127.0.0.1:5401`, the backend remains on `127.0.0.1:8080`, and `curl http://127.0.0.1:5401/health` still returns the backend health JSON. Stop this run before continuing.

- [ ] **Step 5: Verify Ctrl+C cleanup**

With the unified command running, press `Ctrl+C` once in its terminal. Then run:

```sh
for port in 5400 8080; do
  if lsof -nP -iTCP:$port -sTCP:LISTEN >/dev/null 2>&1; then
    printf 'port %s is still in use\\n' "$port"
    lsof -nP -iTCP:$port -sTCP:LISTEN
  else
    printf 'port %s is free\\n' "$port"
  fi
done
```

Expected result: both ports are free, and no frontend/backend child process from this run remains.

- [ ] **Step 6: Verify failure propagation with a controlled occupied port**

Start a known temporary listener on a confirmed free test port only, or use a configured frontend test port that is already occupied by a process created for this verification. Run the unified command with that frontend port:

```sh
FRONTEND_PORT=5401 npm run dev
```

Expected result: Vite reports the strict-port conflict, the launcher stops the backend child, and the command exits non-zero. Do not terminate unrelated processes, and release the controlled listener after the check.

- [ ] **Step 7: Verify missing-tool diagnostics without changing the host installation**

Do not uninstall tools. Instead, run the launcher with a temporary `PATH` containing Node but excluding the directory that provides `uv` or `pnpm`, only if the local shell can construct such a path safely. Expected result: the relevant child emits a clear `failed to start` or command-not-found diagnostic, the other child is stopped, and the launcher exits non-zero. If the environment cannot safely isolate the tool path, record this case as not-run rather than modifying the machine.

---

### Task 4: Update the local usage documentation

**Files:**
- Modify: `python/frontend/README.md` (add a short cross-reference in the startup section)
- Modify: `python/backend/README.md` (add a short cross-reference in the startup section)

- [ ] **Step 1: Add the unified command to the frontend startup instructions**

在前端 README 的启动命令前增加：

```markdown
### 从 `python/` 根目录同时启动前后端

如果需要同时启动 Python 后端和本 Vue 前端，在 `python/` 目录执行：

```sh
npm run dev
```

该命令由 `python/scripts/dev.mjs` 管理两个现有开发进程；前端单独调试时仍可在本目录执行 `pnpm dev --host 127.0.0.1`。
```
```

保留现有前端独立启动、端口配置和代理说明。

- [ ] **Step 2: Add the unified command to the backend startup instructions**

在后端 README 的启动命令前增加：

```markdown
### 从 `python/` 根目录同时启动前后端

如果需要同时启动 Python 后端和 Vue 前端，在 `python/` 目录执行：

```sh
npm run dev
```

该命令会在 `python/backend` 中运行本 README 后续所示的 Uvicorn 命令，并在 `python/frontend` 中启动 Vite。后端单独调试时仍可按本节命令执行。
```
```

不要删除后端独立启动和 `/health` 验证步骤。

- [ ] **Step 3: Review documentation consistency**

确认文档中的以下信息一致：

- 统一入口目录为 `python/`；
- 统一命令为 `npm run dev`；
- 前端默认 `5400`、后端默认 `8080`；
- 独立启动命令仍分别使用 `pnpm` 和 `uv run --frozen`。

---

## Final verification checklist

完成所有任务后，从仓库根目录执行：

```sh
node --check python/scripts/dev.mjs
npm --prefix python run
```

然后从 `python/` 执行一次完整启动和 HTTP 验证：

```sh
cd python
npm run dev
```

必须确认：

- `npm run dev` 是唯一新增的一键入口；
- 前端页面可访问；
- 后端 `/health` 可访问；
- 前端 `/health` 代理可访问；
- `Ctrl+C` 能清理两端；
- 任一端启动失败会让另一端停止并返回非零状态；
- 未修改现有业务代码、Vite 配置或后端依赖；
- 未新增第三方 npm 依赖和根目录 lockfile。

实施者可按仓库提交规范将本次变更作为一个聚焦提交提交；当前计划生成阶段不执行 commit，也不覆盖工作区已有修改。
