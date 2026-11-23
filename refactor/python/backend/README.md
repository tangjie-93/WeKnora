---
task_id: WEKNORA-PRODUCT-AUTH-20261122
stage: TASK-03
author: 开发工程师
date: 2026-11-22
run_mode: auto
---

# `Python` 后端：账户、个人空间与辅助诊断

## 当前正式验证结论（`2026-11-22`）

独立复审 **`PASSED`**，未解决 `P0/P1/P2` 均为 `0`；独立 `TASK-04 PASSED/completed`，后端新增 `92` 项、全套 `220 passed`，前端新增 `14` 项、全套 `41 passed`，真实浏览器 `29` 场景组通过，必需 `failed/blocked=0`。`CR-001–005`、注册事务、真实身份、轮换／退出竞态和重启恢复均有独立证据；`Ruff`、类型检查与构建通过，未发现生产缺陷。本文只同步正式报告，没有重跑测试。

证据：[独立复审（含首轮失败全文）](../../artifacts/weknora-product-auth/03-code/code-review-report.md)、[正式测试](../../artifacts/weknora-product-auth/04-e2e/test-report.md)、[新增用例](../../artifacts/weknora-product-auth/04-e2e/added-cases.md)。初轮 `FAILED`、原开发 `PASS` 和下方“复审未执行／not-run”均保留为当时历史，**不代表当前状态**。两处浏览器脚本自身问题及仅测试修正留在正式报告，未掩盖生产缺陷；既有上游弃用警告保留。生产、多实例、`PostgreSQL`、真实模型、未交付知识业务、跨浏览器矩阵与压力基准仍为范围外 `not-run`。

主产品仍是账户／个人空间，工作台辅助；仅五个认证接口和原版 `SQLite 0–7/v7` 结构子集通过，不是知识库 `CRUD`、全量迁移或整个 `S2/S3` 验收。受支持后端启动必须保留 `--no-proxy-headers`，禁止旧统一启动器用于认证。下方初始化／分端命令仍可用于自有新库体验；临时演示地址／进程仅为记录时点，以本次 `owned-services.json` 为准，不承诺持续在线。主线程完成本需求收尾后暂停，下一需求必须由用户明确继续。

## 历史审核与修复过程（以下状态仅属对应时点）

> **当前审核纠正（`2026-11-22`）：** 首轮独立 `CODE-REVIEW` 为 `FAILED`（`P0=0/P1=3/P2=2`），不是下文历史开发自检 `PASS` 可覆盖的结论。`CR-001` 为默认代理头改写对端导致限流绕过，`CR-002` 为非法编码／过深 `JSON` 未统一错误封装，`CR-003` 为首次 `me` 失败缺少现有会话恢复／真实退出入口。修复后已核对实际源码并读取真实换转发头限流、代理剥头、原始字节 `14` 项／受控解析递归 `3` 项证据，协调者浏览器恢复 `7` 项通过，最终回归通过；这些只是修复开发自检，独立复审尚未执行，`TASK-04` 仍为 `not-run`。详见[首轮审查](../../artifacts/weknora-product-auth/03-code/code-review-report.md)。
>
> 受支持认证启动命令必须带 `--no-proxy-headers`：限流按真实连接对端而非客户端可伪造的转发身份；经 `Vite` 时对端是本地代理，共享其桶，不是终端用户地址。开发代理同时剥除不可信转发头。现有统一 `npm run dev` 启动器既会停止端口监听者，也未带此安全参数，**不是受支持的认证运行入口，不要运行**；下方所有旧统一启动描述仅为历史。文档中可复制的后端命令已纠正，旧自检证据不因此自动升级为修复后通过。

## 本增量实现与修复前开发自检快照（`2026-11-22`）

`WeKnora` 主产品是注册、登录和真实账户／个人空间；工作台只是辅助模块。已只读核对实际文件、函数行号，并同步开发者／协调者真实自检：后端既有 `pytest 128`、`Ruff` 与认证自检 `108` 项通过；协调者真实网络 `13` 项、浏览器注册登录／`me`／重载／退出、并发刷新与退出故障恢复、后端重启恢复通过。具体证据与受控故障边界见学习指南第 `6` 节；本文作者未重跑。本轮独立 `CODE-REVIEW/TASK-04` 仍为 `not-run`，不把开发自检当独立验收。下方健康、导航和连接检查结论均为历史记录。

### 账户接口与兼容范围

| 接口 | 用途与关键合同 |
| --- | --- |
| `POST /api/v1/auth/register` | `{username,email,password}`，成功 `201` 返回 `user`，不发令牌、不自动登录；在同一事务创建用户、个人空间、`owner` 成员 |
| `POST /api/v1/auth/login` | `{email,password}`，成功返回 `user/active_tenant/memberships/token/refresh_token` |
| `POST /api/v1/auth/refresh` | 请求字段为 `refreshToken`，响应字段为 `access_token/refresh_token`；旧刷新令牌原子撤销，新令牌对落库才响应 |
| `GET /api/v1/auth/me` | `Authorization: Bearer <access>`，成功为 `success/data`；核对用户、个人空间与有效成员，不信任客户端自报角色 |
| `POST /api/v1/auth/logout` | `Bearer` 携带已知访问或刷新令牌；撤销该用户全部会话，不能仅删除浏览器存储 |

数据库采用原版 `SQLite 000000–000007` 的八份完整 `up.sql`，以 `auth-sqlite-prefix-v7` 和独立 `_python_auth_schema` 记录此认证结构基线；**不是全量迁移、生产升级或整个 `S2/S3` 验收**。不删改原迁移，不把原版已有库接入初始化。知识库、上传、问答、模型配置、空间切换／邀请、系统管理、`PostgreSQL` 与生产部署均不在本轮范围。`GET /health` 仍免鉴权，仅证明应用可响应；旧 `check_database` 仍是独立只读诊断，不代替认证初始化。

详细合同见[认证接口文档](../../artifacts/weknora-product-auth/03-code/api-docs.md)，调用链与验证边界见[学习指南](../../artifacts/weknora-product-auth/03-code/learning-guide.md)，阶段事实以[唯一进度入口](../../docs/从0到1重构WeKnora/13-进度与验收记录.md)为准。

### 自有新库与持久签名秘密

以下是供用户执行的步骤，不是本工作者已执行记录。需要 `Python 3.12+` 与 `uv`，从 `refactor/` 开始；只使用自己拥有且非符号链接的目录，不读取或修改现有 `.env`、原版库或用户数据库。

```sh
cd python/backend
uv sync --frozen --extra dev
mkdir -p .local/auth
uv run --frozen python -m app.cli.init_auth_database --path "$PWD/.local/auth/auth.sqlite3"
```

目标 `auth.sqlite3` 和 `auth.sqlite3.jwt-secret` 必须都不存在；已有时换自有新文件名，不删除旧文件重跑。命令独占创建库和秘密文件，权限为 `0600`，父目录须自行准备；启动不自动建库、升级或修复旧库。秘密文件持久保存，不打印、不截图、不提交，不用 `cat` 查看；后端重启复用同一秘密，有意轮换后旧令牌失效。

`WEKNORA_AUTH_DB_PATH` 显式指定已初始化库；相对路径锚定后端工程根。默认库就是上面的隔离路径。默认读取 `<库路径>.jwt-secret`，也可通过既有安全配置注入至少 `32` 字节的 `JWT_SECRET`，不要在命令历史或文档写入真实值。无有效库／秘密时认证返回脱敏 `503`，公共 `/health` 不受影响。数据库含身份信息和原结构的明文 `JWT` 记录；库与秘密都不可共享备份或提交。

### 分开启动，只使用已确认空闲端口

先只读检查示例端口是否有监听，出现任何占用就另选端口，不停止未知进程；此检查不保证随后没有竞争，占用时让启动失败并另选端口。

```sh
lsof -nP -iTCP:18080 -sTCP:LISTEN
lsof -nP -iTCP:15400 -sTCP:LISTEN
```

后端终端从 `refactor/` 开始，保持运行：

```sh
cd python/backend
WEKNORA_AUTH_DB_PATH="$PWD/.local/auth/auth.sqlite3" uv run --frozen uvicorn app.main:app --no-proxy-headers --host 127.0.0.1 --port 18080
```

前端另开终端，从 `refactor/` 开始，需 `Node.js >=22.12`、`pnpm 10.11.0`：

```sh
cd python/frontend
pnpm install --frozen-lockfile
FRONTEND_PORT=15400 BACKEND_PROXY_TARGET=http://127.0.0.1:18080 pnpm dev --host 127.0.0.1
```

打开 `http://127.0.0.1:15400/#/register`，注册后到登录，再进入 `/#/account` 中性加载视图；仅真实 `me` 成功才显示身份与空间。已有令牌首次 `me` 网络／`500/503` 失败时在账户错误区复用原会话“重试读取账户”，不要重新提交密码；持续 `403` 隐藏身份但可点真实退出撤销全部会话。已有凭据访问登录页也回到账户恢复视图；`401` 保留原刷新／清理逻辑。刷新页面恢复，退出调用服务器撤销。完整体验步骤见前端说明。更换端口需同时更换代理目标和浏览器入口；只在自己启动服务的终端用 `Ctrl+C` 停止。

**警告：现有 `python/` 下的 `npm run dev` 不支持认证运行，不要执行。** 现有 `python/scripts/dev.mjs` 会向占用默认 `8080`、`5400` 的监听进程发送 `SIGTERM`，并不是无害的端口检测；后端端口仍固定为 `8080`。本轮不修改启动器，自检只用自有空闲端口分开启动。下方统一启动命令保留为历史，不构成安全默认建议。

### 检查与状态口径

可在后端目录运行 `uv run --frozen python -m ruff check .` 和 `uv run --frozen python -m pytest -q`；命令存在不表示已执行。初始化、真实 `HTTP`、故障回滚、并发轮换、浏览器和重启恢复证据已按来源分列在本轮学习指南第 `6` 节；本文作者未重跑。`Ruff`／构建不是 `API/E2E` 通过，不借用旧任务计数。实际函数与行号已只读核对并集中在指南第 `2` 节，旧健康源码行号仅是当时快照。

## 历史记录范围

下文“当前／本轮”均指其各自历史增量，不覆盖本节 `2026-11-22` 身份业务；旧路由 `/#/health`、`/#/progress` 在本轮改为公开工作台子页的兼容跳转。

当前增量仅实现 `S2.2` 显式本地 `SQLite` 连接检查子项；首轮 `FAILED/P1-01` 经文件头预检窄修后独立复审 `PASSED`，`TASK-04` 新增 `117` 项、全套 `128` 项独立测试通过（含健康 `11` 项）。业务数据、`schema`/迁移、`ORM` 未实现，整个 `S2` 未验收。运行合同和练习见第 `6` 节，前文健康检查记录保留历史证据，不作为本轮验证结论。

## 历史增量：第一个健康检查

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

历史统一入口曾在 `python/` 使用下列命令；当前认证不支持，**不要执行**，改用上方带 `--no-proxy-headers` 的分端命令：

```sh
npm run dev
```

该命令会在 `python/backend` 中运行本 README 后续所示的 Uvicorn 命令，并在 `python/frontend` 中启动 Vite。后端单独调试时仍可按本节命令执行。

保持后端终端运行：

```sh
uv run --frozen uvicorn app.main:app --no-proxy-headers --host 127.0.0.1 --port 8080 --reload
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
uv run --frozen uvicorn app.main:app --no-proxy-headers --host 127.0.0.1 --port 8081 --reload
```

同时在前端目录以 `BACKEND_PROXY_TARGET=http://127.0.0.1:8081 pnpm dev --host 127.0.0.1` 启动或重启开发服务器。前端端口冲突时使用 `FRONTEND_PORT=5401`，页面入口同步改为 `http://127.0.0.1:5401`；Vite 的 `strictPort` 不会悄悄换端口。

## 5. 从入口理解处理方法

冻结的方法映射是 `app/main.py` 的 `create_app()` 创建应用并注册路由、模块级 `app` 供 uvicorn 导入、`health()` 返回 JSON 并设置身份 header。`app.main:app` 左边是 Python 模块，右边是模块中的应用对象。常量健康响应无需额外 service/repository 分层。

实际源码已核对：`app/main.py:8–12` 为 create_app，10 行关闭重定向、11 行注册路由；15–18 行为 health（17 行 header）；21 行导出 app。逐步讲解见[本轮学习指南](../../artifacts/weknora-python-vue3-rebuild/03-code/learning-guide.md)，接口细节见[API 文档](../../artifacts/weknora-python-vue3-rebuild/03-code/api-docs.md)。

完成本轮独立审核、测试与知识记录后，由 main 持久化 `awaiting_user_continue=true` 并暂停。下一小需求仅在用户明确“继续”后确认，并使用独立增量任务目录，不覆盖本轮历史。

## 6. 当前增量：显式本地 `SQLite` 连接检查

### 6.1 运行目录、参数与边界

先按第 `1` 节准备锁定环境；以下命令的当前工作目录必须是 `python/backend/`，不是 `python/` 或仓库根目录。独立命令无需启动后端或前端，不改变 `GET /health`。

```sh
uv run --frozen python -m app.cli.check_database --path PATH [--create] [--json]
```

方括号表示可选项，不是实际输入。`--path PATH` 必填；相对路径相对本次调用的当前工作目录，允许绝对路径但不会回显。不读取环境变量或 `.env`，不搜索或回退任何库，不展开 `~` 或环境变量，不裁剪非空文件名的空格。仅支持 `--path`、`--create`、`--json`、`-h/--help`，不支持位置参数、选项缩写、任意查询或连接字符串。

默认只检查现存普通独立文件，通过编码后的 `Path.as_uri()` 加固定 `?mode=ro` 只读打开。`--create` 仅以 `O_CREAT|O_EXCL`、权限 `0o600` 独占创建不存在的新文件，**不会创建父目录**、覆盖、截断或删除目标。用户必须先自行创建自有练习目录；缺失父目录失败。最终符号链接（含悬空链接）、目录、设备、管道、空白/空字节路径、`:memory:`、`file:` 和含 `://` 的地址拒绝；创建模式已有目标（包括链接、零字节文件）优先报 `target_exists`。父目录可规范解析，不承诺防御同机恶意竞态。

仅支持关闭后的独立 `rollback` 数据库或零字节空文件；存在同目标的 `-wal`、`-shm`、`-journal` 副文件即拒绝。无副文件也不代表支持持久化 `WAL`：连接前以 `rb` 最多读 `100` 字节并显式关闭，非空文件必须有完整正确的 `SQLite format 3` 零结尾 magic，且偏移 `18`（写版本）/`19`（读版本）均为 `1`。持久化 `WAL`、混合或未知版本返回 `invalid_target/3`，表示不支持，不表示合法 `WAL` 文件损坏。短非空头或错误 magic 返回 `database_check_failed/4`，头打开/读取失败返回 `access_failed/4`，关闭失败优先返回 `close_failed/5`；拒绝或读取/关闭失败均不连接 `SQLite`。不建议改写现有库，不修改 `journal_mode`、不删除日志、不使用 `immutable=1`。文件名中的 `?`、`#`、空格、非英文字符会编码保留，不允许注入任意 `URI` 参数。

### 6.2 自有目录练习（全部为预期，不是执行证据）

从 `python/backend/` 开始，**用户显式运行 `mkdir` 新建自己拥有、此前不存在的目录**。示例目录已存在时换新名称，不删除旧目录来重跑。以下逐条执行；预期失败不会自动中止后续练习。

```sh
mkdir sqlite-check-exercise
uv run --frozen python -m app.cli.check_database --path sqlite-check-exercise/lesson.sqlite3 --create --json
uv run --frozen python -m app.cli.check_database --path sqlite-check-exercise/lesson.sqlite3 --json
uv run --frozen python -m app.cli.check_database --path sqlite-check-exercise/lesson.sqlite3 --create --json
uv run --frozen python -m app.cli.check_database --path sqlite-check-exercise/missing.sqlite3 --json
uv run --frozen python -m app.cli.check_database --path sqlite-check-exercise/absent-parent/new.sqlite3 --create --json
uv run --frozen python -m app.cli.check_database --path ':memory:' --json
uv run --frozen python -m app.cli.check_database --path sqlite-check-exercise/lesson.sqlite3
uv run --frozen python -m app.cli.check_database --help
```

预期依次是：显式建目录；创建成功（`0/ok`、`mode=create`、`created=true`）；现存文件只读成功（`0/ok`、`created=false`）；拒覆盖（`3/target_exists`）；缺文件（`3/target_not_found`）；缺父目录（`3/target_not_found`，目录仍不应出现）；非法目标（`3/invalid_target`）；安全单行文本成功；静态帮助。正常检查不建表、不写业务数据；示例不接原版或已有用户数据库。失败后仅自行检查自己拥有的练习资源，不自动删除。

新建结果可以仍是零字节：`SQLite` 接受零字节普通文件为空数据库，固定只读查询不强制生成文件头；现存零字节文件也可默认检查。短非空头或错误 magic 在连接前拒绝；其余非空无效文件仍须由只读 `schema` 查询识别，头预检通过不代表完整格式有效。创建后查询或关闭失败保留新文件，`created=true`；创建前失败为 `false`。创建文件不等于持久化业务记录、初始化结构或兼容原版。

### 6.3 输出字段、流与固定错误表

成功仅向 `stdout` 输出一行，失败仅向 `stderr` 输出一行，另一流为空。省略 `--json` 时是相同安全字段的单行文本摘要；不输出原始参数、文件名、路径、底层异常、堆栈、结构名称或业务数据。`--help` 返回 `0`，仅向 `stdout` 输出静态帮助，即使同时有 `--json` 也不是结果对象。参数解析失败也遵循安全输出，独立 `--json` 标记可启用错误对象。

预期只读成功对象（散列仅为占位，不是本轮日志）：

```json
{"engine":"sqlite","status":"ok","mode":"read_only","target":"local-file:0123456789ab","created":false,"checks":["select_1","schema_read"],"code":"ok","message":"Connection check passed; business schema not verified."}
```

| 字段 | 固定含义 |
| --- | --- |
| `engine` | 恒为 `sqlite` |
| `status` | `ok` 或 `error` |
| `mode` | `read_only` 或 `create`；解析未完成时可为 `null` |
| `target` | `local-file:` 加规范内部绝对路径按 `UTF-8` 编码的 `SHA-256` 前 `12` 位小写十六进制；合法目标尚不能确定时为 `null` |
| `created` | 布尔值，只表示本次是否成功独占创建新文件 |
| `checks` | 成功固定 `["select_1","schema_read"]`；失败固定 `[]` |
| `code` | 下表固定代码 |
| `message` | 下表固定安全消息 |

定位散列随目标变化，只供练习比较目标，不是凭据、安全身份或全局唯一标识；不会回显原始文件名。失败保留相同字段集合，`status=error`，不新增 `detail`。

| 退出码 | `code` | 固定 `message` |
| --- | --- | --- |
| `0` | `ok` | `Connection check passed; business schema not verified.` |
| `2` | `invalid_arguments` | `Use --path PATH with optional --create and --json; see --help.` |
| `3` | `invalid_target` | `Use an explicit standalone local regular file with an existing parent directory.` |
| `3` | `target_not_found` | `The explicit target or its parent does not exist; create the parent yourself and use --create only for a new file.` |
| `3` | `target_exists` | `Creation refused because the target already exists; choose a new file.` |
| `4` | `access_failed` | `Cannot access the explicit target; check permissions and availability.` |
| `4` | `database_check_failed` | `Read-only SQLite checks failed; use a valid standalone SQLite file.` |
| `5` | `close_failed` | `Resource release failed; the connection check is not successful.` |
| `6` | `internal_error` | `Unexpected local check failure; no successful check is reported.` |
| `130` | `interrupted` | `Connection check interrupted; no successful check is reported.` |

缺参、未知选项及非法形式归 `invalid_arguments`；路径类型或副文件问题归 `invalid_target`；文件访问/独占创建的其他系统错误归 `access_failed`；驱动打开、查询或探测结果异常归 `database_check_failed`。任一资源释放失败归 `close_failed`，优先于查询错误或中断；普通未预期异常归 `internal_error`，中断清理后归 `interrupted`，绝不先报成功。

### 6.4 方法与验证边界

以下是批准方案冻结的方法定位，不是逐行源码核查：`app/database_check.py` 的 `resolve_database_target(raw_path, *, create, base_dir)` 校验输入及文件目标，不连库、不建目录；`check_database(raw_path, *, create=False, base_dir=None)` 默认取调用时 `Path.cwd()`，负责可选独占创建、单连接单游标检查与释放。`DatabaseCheckResult` 和 `DatabaseCheckError` 承载安全结果/错误。`app/cli/check_database.py` 的 `build_parser()` 解析无缩写选项；`main(argv=None)` 调用检查、分流输出并返回整数，模块入口只退出。不为这一小项建立空 `config.py`、服务或仓储层。

文件是载体，连接是本次打开资源，表是数据库结构。`SELECT 1` 只证明连接能执行固定常量查询；`SELECT name FROM sqlite_schema LIMIT 1` 至多取一行并丢弃，只触发最窄格式/结构解析，不证明完整 `integrity_check`、业务表、迁移、事务或原版兼容。两句均无动态输入，不读取业务记录。

新建文件描述符、连接前只读文件头资源、游标、连接都必须显式关闭；头资源关闭成功后才允许连接。`with sqlite3.connect(...)` 只是事务语义，不保证关闭。游标关闭失败仍尝试关闭连接；全部释放成功后才产生成功结果。该独立命令不接应用启动流程、不新增 `HTTP API`、不改变健康接口。

本轮首轮 `FAILED/P1-01` 历史保留，头预检修复后独立复审 `PASSED`（`P0/P1/P2=0`）；`TASK-04` 独立新增资源/函数 `88` 项和真实子进程 `CLI 29` 项，共 `117` 项，全套含健康 `11` 项为 `128 passed`，失败/跳过/阻塞均为 `0`。真实正常关闭、无副文件、头版本 `2/2` 的持久化 `WAL` 已独立回归，确认拒绝且目标/目录不变；Ruff、格式、前端构建及最窄进度导航通过，只有既有弃用警告与 favicon `404`。这是同步正式证据，不是本文重跑测试，也不新增前端行为；业务 `schema`、`ORM`、迁移与原版兼容未验证。见[独立审查](../../artifacts/weknora-sqlite-connection/03-code/code-review-report.md)、[正式测试](../../artifacts/weknora-sqlite-connection/04-e2e/test-report.md)、[新增用例](../../artifacts/weknora-sqlite-connection/04-e2e/added-cases.md)与[学习指南](../../artifacts/weknora-sqlite-connection/03-code/learning-guide.md)。完成本需求审查、测试、知识与讲解后由主线程暂停，等待用户明确继续，不自动推进 `ORM` 或迁移。
