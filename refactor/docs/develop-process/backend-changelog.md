---
task_id: WEKNORA-KNOWLEDGE-BASE-MANAGEMENT-20261124
stage: TASK-03
author: 开发工程师
date: 2026-11-24
run_mode: auto
---

# `Python` 后端变更记录

## 当前独立验证结论（`2026-11-25`）

- 独立复审 `PASSED/P0=0/P1=0/P2=0`，首轮 `FAILED/P1=3` 及可空创建者、配置分类、嵌套存储类型校验的修复保留在[复审第九节](../../artifacts/weknora-knowledge-base-management/03-code/code-review-report.md#9-第一次定向复审与当前结论2026-11-25)。
- 独立 `TASK-04` 测试执行 `passed/completed`：后端新增 `186`／全量 `406=220+186`，前端新增 `42`／全量 `83=41+42`；浏览器业务 `11` 加旧导航 `5` 共 `16` 组，计数分列。`Ruff`、类型、私有空 `envDir` 安全等价构建及 `9` 份迁移资产逐字节核验通过，无关键测试阻塞；见[正式测试](../../artifacts/weknora-knowledge-base-management/04-e2e/test-report.md)与[用例](../../artifacts/weknora-knowledge-base-management/04-e2e/added-cases.md)。正式文件已提供，旧未落盘交接语仅历史；本文未重跑。
- **主线程最新通知：`TASK-04 leader` 独立质量门禁 `PASSED`（`9` 项硬门禁、`3` 项软门禁），旧待审核仅历史；不据此宣称知识沉淀或整个工作流完成。** 下方并行交付／待核对／独立 `not-run` 仅开发快照，旧认证 `220/41` 非当前全量、开发 `357/537` 仅开发断言。范围仍空库创建／列表、`100` 容量、空模型、不可用引擎，无模型、上传／问答、共享、编辑或删除。独立服务已停止、临时库／配置已清理；体验地址另行确认，不运行默认读 `.env*` 的前端配置。

## 历史开发快照：`2026-11-24` 空知识库创建与列表

- 路由模块为 `POST /api/v1/knowledge-bases`（`201/success/data`）及 `GET` 同路径（`200/success/data[]`、空数组 `[]`），新响应 `no-store`。冻结方案已读，最终组合源码由协调者核对；本工作者未执行服务或测试，不以方案证明行为通过。
- 严格只接受 `name/description/type/embedding_model_id/summary_model_id`：名称去规定首尾空白、非空且最多 `255` 字符，描述原样最多 `4000`；仅文档类型与空模型。未知／重复键、非法正文／类型与超过 `1 MiB` 正文 `400/1000`；列表仅单个 `creator`，拒绝未知／重复、分页、共享参数。重复名称允许，创建不重试。
- 认证与业务同连接／一致事务；`owner/admin/contributor` 创建，`viewer` 仅列表，`owner` 非系统管理员；可信主体／租户／标识／时间由服务端确定。写锁内空间容量 `100`，创建到上限 `400/1000`；列表 `LIMIT 101` 超界 `503/1008`，不截断，个人置顶、创建者与计数有界批量读取。
- 空模型／零值配置真实持久化，引擎 `unavailable/unavailable`，`capabilities` 不代表就绪。存储只读非秘密默认／实例／别名元数据，具体默认失效不能跳过，同租户、有效、允许集合校验；提供方固定 `local/minio/cos/tos/s3/oss/ks3/obs` 回退，无可用租户默认提供方时 `STORAGE_ALLOW_LIST=s3,local` 仍选 `local`。不创建桶／目录／集合／模型／任务。
- 提交前失败回滚，提交后同连接尽力追加真实主体 `kb.created`，审计失败不改变已提交成功。损坏已存配置或租户默认存储配置的 `JSON`／结构／字段类型 `500/1007 Knowledge base storage failure`；合法但超子集 `503/1008 Knowledge base configuration is outside supported scope`。合法 `Bearer` 形式的令牌部分 `UTF-8` 超 `4096` 字节保留 `400/1010 Authentication token is too long`，两接口适用、不回显令牌。
- 原版迁移 `000000–000007` 与清单字节不改，不查询缺失画像列、不增迁移／依赖或改用户旧库；认证五接口、健康和框架 `404/405/Allow` 保持。不宣称完整 `CRUD/S5`，无详情／编辑／删除／共享／置顶写入、模型平台、上传／解析／检索／问答、接口密钥或全量旧库兼容。
- 当前启动器源码默认 `18080/15400`，支持 `BACKEND_PORT/FRONTEND_PORT/BACKEND_PROXY_TARGET`，已带 `--no-proxy-headers` 且可初始化缺失默认库，但仍向占用目标端口进程发 `SIGTERM`。旧固定 `8080/5400`、无安全参数结论仅历史；本轮不执行启动器，验证分端用自有临时库／空闲端口，不读 `.env`／用户库／秘密或调用模型，只停止自有进程。
- 开发运行自检、独立 `CODE-REVIEW`、`TASK-04` 接口／浏览器均 `not-run/待验证`，旧任务计数不复用。创建不确定先核对列表，成功后重查失败不等于创建失败；学习指南正文返回协调者待写，本工作者未落盘。见[后端说明](../../python/backend/README.md)、[本轮方案](../../artifacts/weknora-knowledge-base-management/02-design/tech-design.md)与[唯一进度](../从0到1重构WeKnora/13-进度与验收记录.md)。必要交付与讲解后暂停，等待明确继续。

**前端启动安全补充：** 项目 `vite.config.ts` 的 `loadEnv()` 会读取工程 `.env*`，传端口变量不能禁读；本轮不得用默认 `pnpm dev` 作为禁读环境的验证入口。体验只采用协调者明确提供的自有演示地址，未提供则 `blocked/待提供`，不猜测在线；独立重现需由验证阶段提供私有空目录 `envDir`、不调用项目 `loadEnv` 的临时配置。下方默认命令仅历史，本文不创建或修改配置。

## 历史：认证正式结论（`2026-11-22`）

独立复审 `PASSED/P0=0/P1=0/P2=0`；独立 `TASK-04 PASSED/completed`：后端新增 `92`／全套 `220 passed`，前端新增 `14`／全套 `41 passed`，浏览器 `29` 场景组，必需失败／阻塞 `0`，静态／类型／构建通过，无生产缺陷。五接口、原版 `SQLite 0–7/v7` 认证结构、事务／身份／轮换退出／重启及 `CR-001–005` 均有独立验证，非全量迁移或知识库 `CRUD`。

[复审](../../artifacts/weknora-product-auth/03-code/code-review-report.md)、[正式测试](../../artifacts/weknora-product-auth/04-e2e/test-report.md)、[新增用例](../../artifacts/weknora-product-auth/04-e2e/added-cases.md)保留首轮失败、两处测试自身问题修正与既有上游警告；本文未重跑。生产／`PostgreSQL`／跨浏览器矩阵等范围外仍 `not-run`；受支持分端启动必须 `--no-proxy-headers`，旧统一启动器禁止用于认证。主线程收尾暂停，等待用户明确继续。

## 历史：首轮审核纠正与修复（下方未执行状态仅属当时）

首轮独立 `CODE-REVIEW FAILED`（`P0=0/P1=3/P2=2`），下方开发 `PASS` 保留为修复前历史；独立复审未执行，`TASK-04 not-run`。`CR-001` 要求受支持后端命令带 `--no-proxy-headers`，开发代理剥除不可信转发头，限流按真实连接对端而非转发身份；现有统一 `npm run dev` 无安全参数且会停止监听者，不支持认证运行、不要执行。`CR-002` 要求认证非法编码／过深 `JSON` 统一 `400/1010`，不影响健康与非认证 `404/405`；`CR-003` 联动前端已有令牌后的 `me` 恢复／真实退出。修复实际源码／最终行号已核对，真实换头限流／剥头、原始字节 `14` 项、受控递归 `3` 项、协调者恢复浏览器 `7` 项与最终回归均开发自检通过；自然深度基线已安全，不冒称复现，来源见[学习指南](../../artifacts/weknora-product-auth/03-code/learning-guide.md)，不预写复审通过。

本文件记录 `refactor/python/backend/` 的实际开发进度。前端状态请查看[前端变更记录](./frontend-changelog.md)，双端总览请查看[开发变更总览](./changelog.md)。

## 1. 修复前实现与自检快照（当前审核状态以上方纠正为准）

- 当前为 `Unreleased` 身份业务增量：真实账户与个人空间是主产品，工作台仅辅助；本节已核对实际源码／行号并同步本轮开发自检快照。
- 五条路由：`POST /api/v1/auth/register`（`201/user`，不自动登录）、`POST /api/v1/auth/login`（`token/refresh_token`）、`POST /api/v1/auth/refresh`（请求 `refreshToken`，响应 `access_token/refresh_token`）、`GET /api/v1/auth/me`（`success/data`）、`POST /api/v1/auth/logout`（撤销用户全部会话）。用户／个人空间／`owner` 成员注册事务、`bcrypt` 与入库 `JWT` 为本轮真实业务边界。
- 原版 `SQLite 000000–000007` 八份完整 `up.sql` 与 `auth-sqlite-prefix-v7` 只覆盖 `v7` 认证结构基线，不是全量迁移、生产升级或整个 `S2/S3` 验收。知识库、上传、模型配置、问答、协作与 `PostgreSQL` 不在本轮。
- 自有新库显式初始化并生成持久 `0600` 侧车秘密，不读取现有 `.env`／原版库，不覆盖旧文件；安全分端启动和统一启动器会停止默认 `8080/5400` 监听者的警告见[后端说明](../../python/backend/README.md)。
- 实际函数／行号已只读核对；开发者报告本轮既有 `pytest 128`、`Ruff` 与认证自检 `108` 项通过，协调者真实网络 `13` 项、浏览器及重启自检通过；本文未重跑，受控与真实服务证据分列，本轮独立 `CODE-REVIEW/TASK-04` 仍为 `not-run`。实际链路见[学习指南](../../artifacts/weknora-product-auth/03-code/learning-guide.md)，合同见[认证接口文档](../../artifacts/weknora-product-auth/03-code/api-docs.md)。历史健康与连接检查通过不证明本轮认证通过。

### 历史增量：`2026-11-21` 连接检查模块

- 从 `python/backend/` 运行 `uv run --frozen python -m app.cli.check_database --path PATH [--create] [--json]`，显式目标、默认只读；创建只占有新文件，不建父目录、不覆盖、不初始化业务表。
- 首轮 `P1-01` 审查失败后窄修：连接前只读最多 `100` 字节并关闭，仅允许 `rollback`/零字节；持久化 `WAL` 即使无副文件也返回 `invalid_target/3`，不是损坏判定。不改日志模式、不删副文件，修复后独立复审 `PASSED/P0/P1/P2=0`，首轮失败历史保留。
- 方法边界：`resolve_database_target` 校验目标，`check_database` 固定查询与释放，`build_parser`/`main` 负责独立命令；不修改 `GET /health` 或新增 `HTTP API`。
- 参数、输出和失败练习见[后端说明](../../python/backend/README.md#6-当前增量显式本地-sqlite-连接检查)。本轮 `TASK-04` 独立新增 `117` 项（资源/函数 `88`、真实 `CLI 29`），全套 `128 passed`（含健康 `11`）；真实关闭无副文件 `WAL 2/2` 回归、Ruff/格式/前端构建/最窄进度导航通过。见[正式测试](../../artifacts/weknora-sqlite-connection/04-e2e/test-report.md)；只同步已执行证据，不重跑或新增前端行为，业务 `schema`/迁移/`ORM` 未验证。
- 完成本需求审核、测试、知识与讲解后由主线程暂停，等待用户明确继续；未提交或推送。

## 2. `2026-11-21`：统一开发启动命令

### Added

- 在 `python/` 根目录提供 `npm run dev` 统一启动入口。
- 启动器从 `python/backend` 执行现有 `uv run --frozen uvicorn ...` 命令。
- 启动前自动停止占用 `8080` 的旧监听进程，并在退出时联动清理前端进程。

### 验证

- `node --check python/scripts/dev.mjs` 通过。
- `GET http://127.0.0.1:8080/health` 返回 `200` 和 `{"status":"ok"}`。

## 3. `2026-11-20`：首个健康检查增量

### Added

- 建立最小 `FastAPI` 应用和 `GET /health` 路由。
- 成功响应固定为 `200` 和 `{"status":"ok"}`。
- 增加 `X-WeKnora-Implementation: python-fastapi` 诊断 `header`，用于本地识别误连服务，不承担鉴权职责。
- 补充 `uv` 锁定安装、启动、代理检查和 `Ruff` 检查说明。

### 兼容范围

本轮只对齐健康接口的路径、方法和成功响应子集。尾斜杠、未知路径和错误方法按本轮 `FastAPI` 合同返回 `404` 或 `405`，不声称全量 `Go` 框架行为兼容。

未连接数据库或模型，未创建业务表；登录、上传、解析、检索、问答、`SSE` 和 `trace` 均未实现。

### 验证与证据

- 独立代码审查：通过，`P0/P1/P2` 均为 `0`。
- 正式测试：后端 `pytest 11` 项通过；双端合计 `38` 项自动测试和浏览器 `11` 组检查通过。
- 证据：[代码审查报告](../../artifacts/weknora-python-vue3-rebuild/03-code/code-review-report.md)、[正式测试报告](../../artifacts/weknora-python-vue3-rebuild/04-e2e/test-report.md)、[新增用例](../../artifacts/weknora-python-vue3-rebuild/04-e2e/added-cases.md)。
- 测试执行日期为 `2026-11-20`（`UTC`）；本文件于 `2026-11-21` 同步，未因本次整理重新执行后端测试。

### 已知告警与边界

- `pytest` 有 `1` 条上游 `StarletteDeprecationWarning`（`httpx/TestClient`），未为消警增加依赖。
- 数据库、真实模型、内部 `Python 500` 注入和全量业务路由不在本轮验收范围。
- 本轮未提交、未推送、未发布。
