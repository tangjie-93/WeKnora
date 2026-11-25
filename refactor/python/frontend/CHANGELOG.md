---
task_id: WEKNORA-KNOWLEDGE-BASE-MANAGEMENT-20261124
stage: TASK-03
author: 开发工程师
date: 2026-11-24
run_mode: auto
---

# `Vue` 前端变更记录

## `Unreleased` — `2026-11-25`：同步本轮独立验证

- 独立复审 `PASSED/P0=0/P1=0/P2=0`；首轮 `FAILED/P1=3` 及 `CR-001–003` 修复历史保留，见[复审第九节](../../artifacts/weknora-knowledge-base-management/03-code/code-review-report.md#9-第一次定向复审与当前结论2026-11-25)。
- 独立 `TASK-04` 测试执行 `passed/completed`：前端新增 `42`／全量 `83=41+42`，后端新增 `186`／全量 `406=220+186`；浏览器业务 `11` 加旧导航 `5` 共 `16` 组，和测试数分列。创建、重载／重启、错误恢复、隔离、桌面／移动／键盘已验证，`Ruff`、类型、私有空 `envDir` 安全等价构建及 `9` 份迁移资产逐字节核验通过，无关键测试阻塞。见[测试报告](../../artifacts/weknora-knowledge-base-management/04-e2e/test-report.md)、[用例清单](../../artifacts/weknora-knowledge-base-management/04-e2e/added-cases.md)；两份文件已提供，旧未落盘语是历史，本文不重跑。
- **主线程最新通知：`TASK-04 leader` 独立质量门禁 `PASSED`（`9` 项硬门禁、`3` 项软门禁），旧待审核仅历史；不据此宣称知识沉淀或整个工作流完成。** 下方待核对／独立 `not-run` 为开发快照；旧认证 `220/41` 非当前全量，开发 `357/537` 只属开发断言。仍仅空库创建／列表、`100` 容量、空模型与不可用引擎，无模型、上传／问答、共享、编辑或删除。独立测试服务已停止、私有库／配置已清理，演示地址需协调者另行确认，不复用已删除配置或运行默认读 `.env*` 的前端配置。

## 历史开发快照 — `2026-11-24`：真实空知识库产品切片

- 新受保护入口 `/#/knowledge-bases` 沿用 `Element Plus/ProductLayout`，增加空／加载／失败／真实列表和仅名称／描述创建弹窗；保留账户、健康、进度、兼容路由以及根／登录后进入账户的行为。补最小窄屏菜单与键盘／焦点操作，不回退旧布局；组合源码与真实体验待协调者／独立阶段验证。
- 适配 `POST /api/v1/knowledge-bases` 的 `201/success/data` 与 `GET` 的 `200/success/data[]`、空数组 `[]`、`no-store`；仅当前真实空间可启用。查询键含 `epoch/userID/tenantID/creator`，会话切换清理知识库与认证而不清健康；迟到成功／错误／`finally` 不改变新用户缓存、草稿或提交锁。提交不自动重试，成功后取消旧查询再重查；结果未确认先核对列表，重查失败不谎报创建失败。
- 后端严格白名单 `name/description/type/embedding_model_id/summary_model_id`，名称去规定首尾空白后非空、最多 `255` 字符，描述原样最多 `4000`；仅文档类型、空模型，未知／重复字段、非法正文／参数明确拒绝，正文限 `1 MiB`。列表仅单个 `creator`，无分页／共享；最多 `100` 条，创建到上限 `400/1000`、列表 `LIMIT 101` 超界 `503/1008`，不截断。
- 空模型真实持久化，引擎 `unavailable/unavailable`，`capabilities` 不是就绪承诺；存储只核对非秘密默认／实例／别名及允许集合，固定 `local/minio/cos/tos/s3/oss/ks3/obs` 回退，无可用租户默认提供方时 `s3,local` 仍选 `local`，失效具体默认不跳过。创建提交后尽力写 `kb.created`，不创建模型、桶、目录、集合或任务，不改迁移／清单字节或读取不存在的画像列。
- 损坏已存配置／租户默认存储配置的 `JSON`、结构、字段类型为 `500/1007`；合法但超子集为 `503/1008`。两接口合法 `Bearer` 形式中令牌部分 `UTF-8` 超过 `4096` 字节保持 `400/1010 Authentication token is too long` 且不回显。无效身份／越权不伪装空态，不复用用户名重复或密码规则错误提示。
- 启动器当前默认 `18080/15400`，环境覆盖 `BACKEND_PORT/FRONTEND_PORT/BACKEND_PROXY_TARGET`，已带 `--no-proxy-headers` 并初始化缺失默认库，但仍会 `SIGTERM` 监听者；旧端口／缺安全参数描述仅历史。本轮不运行；验证分端使用自有临时库与空闲端口，不读 `.env`／用户库／秘密，不调用付费模型。
- 本文开发运行自检、独立审查、`TASK-04` 接口／浏览器 `not-run/待验证`，无新通过计数。仅空库创建／列表，不是完整 `CRUD/S5`，详情、编辑、删除、共享、置顶写入、模型平台、上传、解析、检索、问答均未交付。学习指南正文交协调者待写，本文作者未落盘；详见[当前说明](./README.md)与[唯一进度](../../docs/从0到1重构WeKnora/13-进度与验收记录.md)，必要交付与讲解后暂停等明确继续。

**前端启动安全补充：** 项目 `vite.config.ts` 的 `loadEnv()` 会读取工程 `.env*`，传端口变量不能禁读；本轮不得用默认 `pnpm dev` 作为禁读环境的验证入口。体验只采用协调者明确提供的自有演示地址，未提供则 `blocked/待提供`，不猜测在线；独立重现需由验证阶段提供私有空目录 `envDir`、不调用项目 `loadEnv` 的临时配置。下方默认命令仅历史，本文不创建或修改配置。

## 历史最终正式验证：`2026-11-22`

- 独立复审 `PASSED/P0=0/P1=0/P2=0`；独立 `TASK-04 PASSED/completed`，新增前端 `14`／全套 `41 passed`，浏览器 `29` 场景组；后端新增 `92`／全套 `220 passed`，必需失败／阻塞为 `0`，静态／类型／构建通过，无生产缺陷。
- 真实账户旅程、首次 `me` 失败恢复／`403` 退出、`CR-001–005`、响应式／键盘、单次刷新、迟到响应／用户隔离、待撤销重载重试与后端重启已独立回归。[正式测试](../../artifacts/weknora-product-auth/04-e2e/test-report.md)、[新增用例](../../artifacts/weknora-product-auth/04-e2e/added-cases.md)保留两处测试自身问题与修正、上游警告；[复审](../../artifacts/weknora-product-auth/03-code/code-review-report.md)保留首轮失败。
- 本文不重跑测试，下方开发 `PASS`、首轮 `FAILED` 与“独立未执行”均为历史，不覆盖当前结论。主产品账户／空间、辅助工作台、五接口与 `v7` 认证结构子集边界不变；安全启动保留 `--no-proxy-headers`，旧统一入口不支持认证。无知识库 `CRUD`、全量迁移或生产／`PostgreSQL`／跨浏览器矩阵通过声明；收尾后暂停等待用户明确继续。

## 历史审查、修复与开发快照

## 审核纠正：`2026-11-22`，修复开发自检已同步、独立复审未执行

- 首轮独立 `CODE-REVIEW FAILED`（`P0=0/P1=3/P2=2`），保留下方原开发自检 `PASS` 为修复前快照；独立复审未执行，`TASK-04 not-run`。
- `CR-001`：`Vite` 剥除不可信转发头，后端受支持命令均带 `--no-proxy-headers`，经代理按实际代理对端共享限流桶。旧统一 `npm run dev` 无安全参数且会停止监听者，不支持认证运行、不要执行。
- `CR-003`：已有令牌首次 `me` 失败时提供原会话恢复／真实退出，不把重新登录当恢复；`401` 仍清理、`403` 仍隐藏身份且可退出。`CR-002` 的认证原始字节／深度错误同步统一封装，实际恢复／代理源码已核对，协调者恢复浏览器 `7` 项、真实换头限流／剥头、原始字节 `14` 项／受控递归 `3` 项及最终回归开发自检通过，来源与限制见[学习指南](../../artifacts/weknora-product-auth/03-code/learning-guide.md)。

## `Unreleased` — `2026-11-22`：账户与空间主产品（开发自检快照）

- 产品主入口改为真实注册、登录与受保护 `/#/account`；工作台仅一个辅助模块，包含公共 `/#/workbench/health`、`/#/workbench/progress`。旧 `/#/health`、`/#/progress` 兼容跳转，未知地址可恢复，不再用教学长文或假知识库卡片占据首页。
- 使用 `POST /api/v1/auth/register`、`POST /api/v1/auth/login`、`POST /api/v1/auth/refresh`、`GET /api/v1/auth/me`、`POST /api/v1/auth/logout`。注册后回登录、不自动登录；刷新请求 `refreshToken` 与响应 `access_token/refresh_token` 保持原字段，账户数据仅来自 `me.data`。
- `Pinia` 管会话凭据与 `epoch`，`vue-query` 管唯一身份数据；本标签 `sessionStorage` 恢复、单次共享刷新、退出待撤销重试和迟到响应隔离已按实际源码只读核对。`Vite` 同源开发代理增加 `/api/v1`，保留精确健康代理与手动检测／切离取消行为。
- 后端为原版 `SQLite 000000–000007` 完整前缀的 `v7` 认证结构子集，不是全量迁移或整个 `S2/S3` 验收；知识库、上传、问答、模型配置和多空间协作未交付。初始化／持久秘密／自有空闲端口／统一启动器停止端口监听者的警告见[前端说明](./README.md)。
- 状态：实际源码／行号已只读核对；开发者本轮 `pnpm build`／既有 `Node 27` 项通过，协调者真实浏览器核心旅程、桌面／移动／键盘、并发刷新、迟到隔离和退出故障恢复自检通过；受控客户端 `6` 项／存储 `7` 项另列。本文未重跑；本轮独立 `CODE-REVIEW/TASK-04` 仍为 `not-run`，历史构建／浏览器计数不得代替本轮。见[学习指南](../../artifacts/weknora-product-auth/03-code/learning-guide.md)与[认证接口文档](../../artifacts/weknora-product-auth/03-code/api-docs.md)。未提交、推送或发布。

以下保留旧增量历史；旧根跳健康页、仅健康代理和无会话存储等内容仅代表相应日期。

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
