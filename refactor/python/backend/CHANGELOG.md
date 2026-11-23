---
task_id: WEKNORA-PRODUCT-AUTH-20261122
stage: TASK-03
author: 开发工程师
date: 2026-11-22
run_mode: auto
---

# `Python` 后端变更记录

## 最终正式验证：`2026-11-22`

- 独立复审 `PASSED/P0=0/P1=0/P2=0`；独立 `TASK-04 PASSED/completed`，新增后端 `92`／全套 `220 passed`，新增前端 `14`／全套 `41 passed`，浏览器 `29` 场景组，必需失败／阻塞均 `0`。`CR-001–005`、真实安全启动链、注册事务、身份／轮换／全会话退出和重启恢复独立通过；静态／类型／构建通过，无生产缺陷。
- [正式测试](../../artifacts/weknora-product-auth/04-e2e/test-report.md)与[新增用例](../../artifacts/weknora-product-auth/04-e2e/added-cases.md)记录两处测试自身问题的修正及既有上游警告；[复审报告](../../artifacts/weknora-product-auth/03-code/code-review-report.md)保留首轮 `FAILED`。本文同步而非重跑；下方“复审未执行／not-run”只属历史。
- 主产品账户／空间、辅助工作台、五接口及原版 `SQLite 0–7/v7` 认证子集边界不变；带 `--no-proxy-headers` 的分端启动为支持入口，旧统一启动器禁止用于认证。全量迁移、知识库 `CRUD`、生产／`PostgreSQL`／跨浏览器矩阵等仍未验收；主线程收尾暂停，下一需求等待明确继续。

## 历史审查、修复与开发快照

## 审核纠正：`2026-11-22`，修复开发自检已同步、独立复审未执行

- 首轮独立 `CODE-REVIEW FAILED`（`P0=0/P1=3/P2=2`）已否定下方修复前开发自检对遗漏边界的覆盖；保留原 `PASS` 历史，独立复审未执行，`TASK-04 not-run`，不预写通过。
- `CR-001`：所有受支持后端命令补 `--no-proxy-headers`，按真实连接对端而非 `X-Forwarded-For` 限流；`Vite` 剥除不可信转发头。旧统一 `npm run dev` 未带安全参数且停止端口监听者，不支持认证运行、不要执行。
- `CR-002`：认证请求非法编码／过深 `JSON` 须统一 `400/1010`，保留健康及非认证框架 `404/405`；需真实字节级证据，不能引用旧合法输入自检代替。
- `CR-003`：登录已有令牌而首个 `me` 失败，应复用原会话恢复或真实退出，不能要求再次提交密码并遗留会话；实际修复入口已在释放后核对；真实换头限流／代理剥头、原始字节 `14` 项、受控递归 `3` 项、协调者浏览器恢复 `7` 项与最终回归均为修复开发自检通过，非自然深度复现或独立通过。证据集中在[学习指南](../../artifacts/weknora-product-auth/03-code/learning-guide.md)。

## 当前增量：`2026-11-22` 真实账户与个人空间（开发自检快照）

- 主产品交付真实账户／个人空间，工作台仅辅助；冻结五路由为 `POST /api/v1/auth/register`、`POST /api/v1/auth/login`、`POST /api/v1/auth/refresh`、`GET /api/v1/auth/me`、`POST /api/v1/auth/logout`。
- 注册成功为 `201/user`，不自动登录；用户、个人空间、`owner` 成员同一事务。登录返回 `token/refresh_token`；刷新请求 `refreshToken`，响应 `access_token/refresh_token`；`me` 为 `success/data`，退出撤销用户全部会话。
- 认证结构采用原版 `SQLite 000000–000007` 八份完整迁移和 `auth-sqlite-prefix-v7` 独立元数据；只覆盖 `v7` 认证基线，不是全量迁移／生产升级或整个 `S2/S3` 验收。知识库、上传、问答、模型配置、空间协作和 `PostgreSQL` 范围外。
- 显式初始化自有新库和持久 `0600` 侧车秘密；拒绝覆盖或接入旧原版库，不读现有 `.env`。原 `/health` 和独立只读连接检查保持各自边界；分端安全启动及统一启动器会停止 `8080/5400` 端口监听者的警告见[后端说明](./README.md)。
- 实际源码／行号已只读核对；开发者报告本轮既有 `pytest 128`、`Ruff` 与认证自检 `108` 项通过，协调者真实网络 `13` 项及浏览器／重启自检通过。本文未重跑，开发自检与受控故障证据分列，独立 `CODE-REVIEW/TASK-04` 仍为 `not-run`，不借用历史通过计数。见[学习指南](../../artifacts/weknora-product-auth/03-code/learning-guide.md)与[认证接口文档](../../artifacts/weknora-product-auth/03-code/api-docs.md)。未提交、推送或发布。

以下保留旧增量历史；其中“当前／本轮”仅指相应日期，不代表本轮认证状态。

## 历史增量：`2026-11-21` 显式本地连接检查

- 仅实现 `S2.2` 显式本地 `SQLite` 连接检查子项，修复后独立复审及必要独立测试通过；独立命令 `uv run --frozen python -m app.cli.check_database --path PATH [--create] [--json]` 从 `python/backend/` 运行，合同与练习见 [README 第 `6` 节](./README.md#6-当前增量显式本地-sqlite-连接检查)。
- 显式目标，无环境回退；默认只读现存独立普通文件，显式创建不建父目录、不覆盖。固定查询后关闭资源，不读取业务数据。
- 不修改 `GET /health` 或新增 `HTTP API`。业务数据、`schema`/迁移、`ORM` 未实现，整个 `S2` 未验收。
- 首轮独立审查 `FAILED/P1-01`：无副文件的持久化 `WAL` 仍可能产生副文件；按复核方案窄修为连接前最多只读 `100` 字节并关闭，只支持 `rollback`/零字节，持久化 `WAL` 或未知版本以 `invalid_target/3` 拒绝，不等于文件损坏。不改日志模式、不删副文件；修复后原审核者复审 `PASSED/P0/P1/P2=0`，首轮失败历史保留。
- 本轮 `TASK-04` 独立新增 `117` 项（资源/函数 `88`、真实 `CLI 29`），全套 `128 passed`（含健康 `11`）；真实正常关闭无副文件的 `WAL 2/2` 拒绝且快照不变，Ruff/格式/前端构建/最窄进度导航通过。见[正式测试](../../artifacts/weknora-sqlite-connection/04-e2e/test-report.md)；仅同步证据、不重跑或新增前端行为，业务 `schema`/迁移/`ORM` 未验证。完成本需求验证与讲解后暂停等待明确继续，未提交或推送。

## 历史增量：[Unreleased] - 2026-11-20

### Added — `GET /health` 模块

- 已实现最小 FastAPI 工程与 `GET /health`：免鉴权、无参数，200 JSON 严格为 `{"status":"ok"}`，附本地诊断 header `X-WeKnora-Implementation: python-fastapi`。
- 配套 uv 锁定安装、启动和 Ruff 操作说明，见 [README](./README.md)。

### 兼容性与范围

仅对齐原版健康接口的路径、方法和成功 JSON 子集；新增身份 header 不是鉴权。关闭尾斜杠重定向的 404、错误方法的 405 按 FastAPI 本轮合同说明，不声称全量 Go 框架行为兼容。不连接数据库或模型，不创建业务表；登录、上传、解析、检索、问答、SSE 和 trace 均未实现。

### 当前独立验证状态（2026-11-21 同步）

独立 CODE-REVIEW 已 PASSED（P0/P1/P2 均 0）；TASK-04 已 completed，38 项自动测试（pytest 11 + Node 27）与 11 个浏览器检查组全部 passed，必需行为 failed/blocked 均 0。测试执行日期按正式报告为 2026-11-20（UTC），本次文档同步日期为 2026-11-21；不是重新执行测试。

[独立审查](../../artifacts/weknora-python-vue3-rebuild/03-code/code-review-report.md) · [正式测试报告](../../artifacts/weknora-python-vue3-rebuild/04-e2e/test-report.md) · [新增用例](../../artifacts/weknora-python-vue3-rebuild/04-e2e/added-cases.md)。下方 not-run 只记录开发阶段时点，不是当前独立测试状态。

保留告警/失败审计：pytest 有 1 条上游 StarletteDeprecationWarning（httpx/TestClient），未为消警增加依赖；pnpm ignored scripts（esbuild/vue-demi）及 url.parse 弃用提示未导致构建失败。TASK-04 首次从错误 cwd 调用 corepack pnpm --dir build，Corepack 先选到 pnpm 12.21.0 而失败；进入 python/frontend 后按固定 pnpm 10.11.0 重跑构建通过，未修改生产配置/锁。favicon 404、故障注入和停后端代理 500 属已说明的资源/诊断事件；最终浏览器应用异常与 warnings 均为空。

仅 S1 健康子项通过上述独立审查与行为测试，整个 S1、上传/解析/检索/问答及数据库/模型均未完成；内部 Python 500 注入、全浏览器/无障碍认证等报告列明 not-run 的项仍未执行。当前由 main 协调质量门禁与知识记录，收尾后暂停供用户查看；只有用户明确继续才新建独立增量目录，不自动实施下一需求。本轮未提交、未推送或发布；本文不改变 workflow-state、当前路由或暂停字段。

### 开发阶段快照（2026-11-20）

后端已编码；uv frozen dev 同步、uv lock --check、Ruff 均 exit 0；真实直连/代理 GET 200、精确 JSON 与 Python header 已核对，尾斜杠/未知路径 404、POST 405。浏览器成功、停服务失败与恢复已由 developer 自检；独立 TASK-04 not-run。数据库和真实模型为范围外 not-run。未提交、未推送或发布。

完成本轮审核、测试、知识记录后由 main 暂停，等待用户明确继续；下一增量使用独立任务目录。
