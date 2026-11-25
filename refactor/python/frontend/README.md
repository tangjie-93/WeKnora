---
task_id: WEKNORA-KNOWLEDGE-BASE-MANAGEMENT-20261124
stage: TASK-03
author: 开发工程师
date: 2026-11-24
run_mode: auto
---

# `WeKnora` 前端：账户与空间，工作台为辅助

## 当前独立验证结论（`2026-11-25`）

本轮独立复审 `PASSED`，当前 `P0/P1/P2=0`；首轮 `FAILED/P1=3` 和可空创建者、配置分类、嵌套默认存储校验的修复历史保留，见[复审第九节](../../artifacts/weknora-knowledge-base-management/03-code/code-review-report.md#9-第一次定向复审与当前结论2026-11-25)。独立 `TASK-04` 测试执行 `passed/completed`：后端新增 `186`／全量 `406=220+186`，前端新增 `42`／全量 `83=41+42`；真实浏览器业务 `11` 加旧导航 `5` 共 `16` 场景组，不能与测试数相加。`Ruff`、类型检查、私有空 `envDir` 的安全等价构建及 `9` 份迁移资产逐字节核验通过，无关键测试阻塞。

[正式测试报告](../../artifacts/weknora-knowledge-base-management/04-e2e/test-report.md)与[用例清单](../../artifacts/weknora-knowledge-base-management/04-e2e/added-cases.md)已提供实际证据，包括创建／重载／自有后端重启、错误恢复、双用户及迟到响应隔离、桌面／移动／键盘／焦点；测试自身失败和修正、既有弃用与构建体积警告保留，不将预期故障注入网络错误当成应用异常。本文同步而非重跑；报告中的旧未落盘交接语仅属历史。**主线程最新通知：`TASK-04 leader` 独立质量门禁已 `PASSED`（`9` 项硬门禁、`3` 项软门禁）；先前待审核为历史，不再代表当前状态。本文不据此宣称知识沉淀或整个工作流已完成。**

下方并行交付、待核对及独立 `not-run` 是 `2026-11-24` 快照；旧认证 `220/41` 不是当前全量，开发 `357/537` 仅开发断言。仍只空库创建／列表，`100` 容量、空模型与不可用引擎不变，不开放模型、上传／问答、共享、编辑、删除。独立测试服务已停止、私有库／配置已清理；体验须用协调者另行确认的自有地址，不猜测在线或运行默认读 `.env*` 的前端配置。

## 历史开发快照：真实空知识库产品入口（`2026-11-24`）

本轮在现有 `Element Plus` 产品壳增加受保护 `/#/knowledge-bases`，只交付当前个人空间空文档知识库创建／真实列表，不是完整 `CRUD` 或整个 `S5`。根入口与登录后仍进入 `/#/account`，账户、服务检测、开发进度及旧兼容地址保留；工作台仅辅助，进度页不是实时 `trace`。本文按审核方案和读取时源码同步，组合实现待协调者最终核对，不能以并行方案冒称已运行。本工作者未运行测试、构建、服务、启动器或浏览器；本轮开发运行自检、独立审查、`TASK-04` 接口／浏览器均 `not-run/待验证`。旧认证通过计数仅属于旧任务。

### 1. 产品操作（预期步骤，不是执行证据）

1. 按下方安全分端方式使用自有临时库与已确认空闲端口，注册、登录，等待真实 `me` 成功。首次身份恢复失败应在账户重试或真实退出，不能把失败显示为知识库空态；`owner` 仅为个人空间所有者。
2. 从产品侧栏或窄屏菜单进入“知识库”即 `/#/knowledge-bases`；应明确区分加载、失败、真实空列表和列表。仅 `owner/admin/contributor` 可创建，`viewer` 可列表不可创建。
3. 打开创建弹窗，仅填名称与描述。名称去两端规定空白后非空、最多 `255` 字符；描述原样保存、最多 `4000` 字符。确认与回车共用一次提交，提交中不可重复点击，不提供模型选择、上传、问答或空壳操作。
4. 成功后重新查询原空间，展示服务端真实名称、描述、标识、时间、计数和“模型未配置”；刷新页面以及仅重启自己启动的后端后再次核对。重复名称允许，不能只凭名称判定是否为同一记录。
5. 观察“全部／我创建的／其他人创建的”筛选。列表只读同租户、未删除、非临时记录；现有个人置顶读取优先，不开放置顶写入。当前空间最多 `100` 条，创建到上限明确失败；列表超上限显式失败，不能把截断或错误画作空库。
6. 网络中断、超时或取消时，创建结果可能未确认；先刷新原空间列表核对，不自动重复 `POST`。已确认创建成功但重查失败，分别显示两件事，不谎报创建失败。关闭弹窗／退出只取消接收，不保证服务端回滚。
7. 用另一自有测试用户核对空间隔离及退出，不展示旧缓存／迟到响应；检查桌面、窄屏、键盘菜单、弹窗焦点恢复和长名称换行。此处是待独立验证清单，不是体验通过声明。交付必要审核、验证和讲解后暂停，等用户明确继续下一业务。

### 2. 请求、状态与边界

- `POST /api/v1/knowledge-bases` 成功 `201/success/data`，`GET` 同路径成功 `200/success/data[]`、空列表 `[]`；新接口响应均 `Cache-Control:no-store`。创建严格只接受 `name/description/type/embedding_model_id/summary_model_id`；页面只发名称、描述。`type` 仅省略／空／`document`，两个模型字段仅省略或空串，不能为 `null` 或非空。未知／重复字段、非法正文／类型、非 `application/json`、超过 `1 MiB` 正文均为 `400/1000`。
- 列表只允许单个 `creator`；`mine/others` 筛选，其他单值不筛选。未知／重复参数及共享、分页参数拒绝。原版普通列表无分页，本轮仍返回数组：空间容量 `100`，创建写锁内检查，达到上限 `400/1000`；列表 `LIMIT 101` 探测超界 `503/1008`，不截断。
- 空模型真实持久化；`capabilities.vector/keyword=true` 只表示配置，实际向量引擎 `unavailable/unavailable`，不等于上传、检索或问答就绪。分块零值、画像 `null` 与真实计数投影见[后端说明](../backend/README.md)，不查询不存在的画像列、不运行迁移，原前缀和清单字节不变。
- 存储只校验非秘密元数据；具体默认实例不可跳过失效，需同租户、有效且允许。无默认实例才解析兼容别名，无别名不伪造绑定。提供方回退顺序固定 `local → minio → cos → tos → s3 → oss → ks3 → obs`；无可用租户默认提供方时 `STORAGE_ALLOW_LIST=s3,local` 仍选 `local`。不创建桶、目录、模型、向量集合或任务。
- 认证和业务同连接／一致事务；创建提交前失败回滚，提交后尽力写真实主体 `kb.created` 审计，审计失败不逆转业务成功。无外部或付费模型调用。知识库编辑、删除、详情、共享、上传、解析、检索、问答、模型平台、接口密钥和全量旧库兼容均未交付。

### 3. 失败恢复与源码阅读

| 失败 | 处理 |
| --- | --- |
| 已存配置／租户默认存储配置的非法 `JSON`、结构／字段类型损坏 | `500/1007 Knowledge base storage failure`，不当未配置或清空旧数据 |
| 配置可解析且结构／字段类型合法，但超出本轮子集 | `503/1008 Knowledge base configuration is outside supported scope`，与损坏配置严格区分 |
| 合法 `Bearer <token>` 形式、令牌部分 `UTF-8` 超过 `4096` 字节 | 两接口保留 `400/1010 Authentication token is too long`，不回显凭据；非法租户头也为 `400/1010` |
| 无效／过期令牌、无效成员或跨空间 | `401/1001`、`403/1002`，不伪装无数据，不显示认证密码规则或用户名重复等误导提示 |
| 创建结果未确认／创建成功但重查失败 | 先核对列表，绝不自动重试非幂等创建；区分创建成功与重查失败 |

按冻结设计阅读 `src/views/knowledge/index.vue`／`components/CreateKnowledgeBaseDialog.vue` → `src/hooks/useKnowledgeBases.ts` 的 `submit()` → `src/api/knowledge-bases.ts` 的 `createKnowledgeBase()` → 既有 `src/api/client.ts` 的 `requestJson()` → 后端业务。创建成功后取消旧列表、提升代际再由 `fetchKnowledgeBases()` 重查。查询键为 `['knowledge-bases',epoch,userID,tenantID,creator]`，只有当前真实身份可启用；`retry:false/gcTime:0`，所有成功／失败／`finally` 均检查归属，退出清理认证和知识库缓存但不清健康缓存。上述新增方法为冻结集成合同，本文读取时仍有文件待并行交付；静态链路不是实际运行 `trace`。

### 4. 当前启动器事实与安全入口

已核对 `python/scripts/dev.mjs`：默认后端 `18080`、前端 `15400`，可用 `BACKEND_PORT/FRONTEND_PORT/BACKEND_PROXY_TARGET` 覆盖；后端现在已带 `--no-proxy-headers`，缺失默认认证库和秘密会初始化。仍会向占用目标端口的进程发送 `SIGTERM`，并固定注入默认 `.local/auth/auth.sqlite3`，不能拿它做隔离临时库验证。本轮不运行／修改启动器。下方“固定旧端口／无安全参数／不支持认证”仅为旧版本历史，不代表当前事实；前端单独启动的 `Vite` 裸默认仍为 `5400`、代理 `8080`，与启动器注入默认不同。

推荐验证：分开启动自己拥有的临时环境，显式初始化新库、保存侧车秘密，后端显式 `WEKNORA_AUTH_DB_PATH` 并带 `--no-proxy-headers`；前端显式设置空闲 `FRONTEND_PORT` 与匹配的 `BACKEND_PROXY_TARGET`。参考下方分端命令，验证时换临时目录，已有库／秘密绝不覆盖。不要读 `.env`、用户库或秘密内容，不杀未知进程，只停止自己创建的服务。

依据为[技术方案](../../artifacts/weknora-knowledge-base-management/02-design/tech-design.md)和[执行计划](../../artifacts/weknora-knowledge-base-management/02-design/execution-plan.md)。本任务学习指南正文已交协调者待机械写入 `artifacts/weknora-knowledge-base-management/03-code/learning-guide.md`，本工作者未写该文件；接口文档由并行任务交付。仍只维护[唯一进度入口](../../docs/从0到1重构WeKnora/13-进度与验收记录.md)，不自动开始下一业务。

**前端启动安全补充：** 当前 `vite.config.ts` 调用 `loadEnv(mode, process.cwd(), '')`，默认 `pnpm dev` 即使显式传端口也可能读取工程 `.env*`；设置进程变量不等于禁读文件。下方默认前端命令仅保留历史，不用于本轮禁读 `.env` 的验证。当前体验只使用协调者另行明确提供的自有演示地址；没有已提供地址时记录 `blocked/待提供`，不要猜测服务在线或运行默认前端配置。独立重现须先准备使用私有空目录 `envDir`、且不调用项目 `loadEnv` 的临时配置，由验证阶段提供具体入口，本文不创建或修改配置。

## 历史：认证正式验证结论（`2026-11-22`）

独立复审 **`PASSED`**，未解决 `P0/P1/P2=0`；独立 `TASK-04 PASSED/completed`：后端新增 `92`／全套 `220 passed`，前端新增 `14`／全套 `41 passed`，真实浏览器 `29` 场景组通过，必需 `failed/blocked=0`。注册登录／`me`／重载／退出、首次 `me` 失败复用会话、`403` 真退出、可空字段、主内容焦点、响应式／键盘、轮换退出竞态及后端重启恢复均已独立回归。类型检查／构建与静态检查通过，未发现生产缺陷；本文只同步报告，不重新执行。

见[独立复审](../../artifacts/weknora-product-auth/03-code/code-review-report.md)、[正式测试](../../artifacts/weknora-product-auth/04-e2e/test-report.md)、[新增用例](../../artifacts/weknora-product-auth/04-e2e/added-cases.md)。首轮 `FAILED` 和后续开发修复证据保留；以下旧“独立未执行／not-run”只指当时快照，**不覆盖当前通过结论**。两处浏览器测试自身问题修正留审计，既有上游弃用警告保留；生产、`PostgreSQL`、多实例、真实模型、知识业务、跨浏览器与压力基准仍范围外 `not-run`。

账户／空间是主产品，工作台仅辅助；五接口与原版 `SQLite 0–7/v7` 认证子集不等于知识库 `CRUD` 或全量迁移完成。继续使用下方自有新库、持久秘密和带 `--no-proxy-headers` 的分端启动，旧统一启动器禁止用于认证。临时服务／进程仅为报告时点，以 `owned-services.json` 为准；主线程收尾暂停，下一需求需用户明确继续。

## 历史审核与修复过程（以下状态仅属对应时点）

> **当前审核纠正（`2026-11-22`）：** 独立 `CODE-REVIEW` 首轮 `FAILED`（`P0=0/P1=3/P2=2`）；下方开发自检 `PASS` 是修复前历史，不等于独立通过。`CR-001` 要求真实对端限流与代理剥除不可信转发头，`CR-002` 要求非法编码／过深 `JSON` 的统一 `400/1010`，`CR-003` 要求登录得到令牌后首次 `me` 失败可复用原会话重试或真实退出。修复实际源码已核对，协调者真实浏览器恢复 `7` 项通过（首次 `me` 连续失败后重试到恢复仅一次登录、`403` 真退出，并验证可空显示／跳至主内容），真实换头限流／剥头和原始字节封装自检及最终回归通过；独立复审未执行，`TASK-04` 仍为 `not-run`。见[首轮审查](../../artifacts/weknora-product-auth/03-code/code-review-report.md)。
>
> 后端必须以 `--no-proxy-headers` 启动，不能把 `X-Forwarded-For` 当可信身份；`Vite` 同时剥除不可信转发头，经代理访问共享本地代理的真实对端限流桶。现有统一 `npm run dev` 不带此安全参数且会停止端口监听者，**不是受支持的认证运行入口，不要运行**。使用下方分端命令；旧启动及旧验证记载仅保留审计历史。

## 本增量实现与修复前开发自检快照（`2026-11-22`）

主产品以真实注册、登录、账户与当前个人空间为中心，不再把学习工作台当首页。已只读核对实际函数／行号，开发者报告本轮 `pnpm build` 与既有 `Node 27` 项通过；协调者真实浏览器注册 → 登录 → `me` → 重载 → 退出、旧令牌拒绝、桌面／移动无横溢、键盘、并发真实刷新、迟到响应隔离及退出故障重试通过。受控客户端 `6` 项和存储 `7` 项自检与真实服务器行为分列在学习指南第 `6` 节，本文作者未重跑。本轮独立 `CODE-REVIEW/TASK-04` 仍为 `not-run`，旧报告和开发自检均不等于本轮独立验收。

### 页面和接口

| 页面 | 本轮职责 |
| --- | --- |
| `/#/login`、`/#/register` | 独立品牌页与真实表单；注册成功回登录，不自动登录 |
| `/#/account` | 受保护主业务屏幕，账户／空间／成员来自真实 `GET /api/v1/auth/me`，不从演示数据构造 |
| `/#/workbench/health`、`/#/workbench/progress` | 单个辅助工作台模块内的公共页面；服务检测仍手动触发，进度仍是版本化事实，不读取工作流状态 |
| `/#/health`、`/#/progress` | 以 `replace` 兼容跳转到对应工作台子页 |
| `/#/`、未知地址 | 根入口按身份去登录或账户；未知地址显示可恢复的未找到页面 |

本轮调用五个原版兼容接口：`POST /api/v1/auth/register`、`POST /api/v1/auth/login`、`POST /api/v1/auth/refresh`、`GET /api/v1/auth/me`、`POST /api/v1/auth/logout`。注册只返回 `201/user`；登录令牌字段为 `token/refresh_token`；刷新请求是 `refreshToken`，返回 `access_token/refresh_token`；`me` 为 `success/data`。确认密码仅在表单校验，不发往服务器。认证数据采用原版 `SQLite 000000–000007` 完整前缀，是 `v7` 认证结构覆盖子集，不是全量迁移或整个 `S2/S3` 验收。知识库、模型配置、上传和问答未交付，无假卡片或空壳按钮。

### 安全安装、初始化与启动

先按[后端当前说明](../backend/README.md)在自有新库显式初始化，持久保存 `<库路径>.jwt-secret`，不要读取现有 `.env`、原版库或任何用户数据库。新库和秘密均以 `0600` 创建，拒绝覆盖；服务启动不自动迁移。秘密缺失／数据库未初始化时身份接口 `503`，不是成功空账户；此时公共 `/health` 仍可用。

需要 `Node.js >=22.12` 与 `pnpm 10.11.0`；示例从 `refactor/` 开始，先确认 `18080/15400` 没有监听；有占用就换端口，绝不停止未知进程。后端终端：

```sh
cd python/backend
uv sync --frozen --extra dev
mkdir -p .local/auth
uv run --frozen python -m app.cli.init_auth_database --path "$PWD/.local/auth/auth.sqlite3"
WEKNORA_AUTH_DB_PATH="$PWD/.local/auth/auth.sqlite3" uv run --frozen uvicorn app.main:app --no-proxy-headers --host 127.0.0.1 --port 18080
```

初始化只运行一次；如库或侧车秘密已存在，保留并使用已初始化自有库，不重新覆盖。前端另开终端，从 `refactor/` 开始：

```sh
cd python/frontend
pnpm install --frozen-lockfile
FRONTEND_PORT=15400 BACKEND_PROXY_TARGET=http://127.0.0.1:18080 pnpm dev --host 127.0.0.1
```

浏览器入口 `http://127.0.0.1:15400/`。请求使用同源 `/api/v1` 与 `/health`，由 `Vite` 开发代理转发；更换后端端口必须同步 `BACKEND_PROXY_TARGET`。`pnpm build` 包含类型检查和构建，但不证明浏览器或服务端业务通过。生产反向代理不属于本轮。

**统一启动器警告：** `python/` 下的 `npm run dev` 会先给占用默认 `8080/5400` 的监听进程发送 `SIGTERM`，不是只检查端口。后端启动端口固定 `8080`，不能以修改前端变量来保证不触碰这两个端口。本轮自检优先使用自有空闲端口分开启动；即使默认端口空闲，也不支持用此统一入口运行认证，必须采用带 `--no-proxy-headers` 的分端命令。停止服务只在自己启动的终端按 `Ctrl+C`。

### 浏览器体验步骤（预期，不是已执行结论）

1. 进入 `/#/register`，输入自选用户名、邮箱、密码和确认密码。用户名为 `2–50` 字符；注册密码为 `8–32` 字符、至少一个 `ASCII` 字母和数字，且 `UTF-8 <=72` 字节。邮箱和用户名不静默裁剪或转小写，勿输入首尾空白。成功应转到登录页并提示，不把密码、邮箱或令牌放在地址中。
2. 登录得到令牌后进入中性账户加载页，唯一 `me` 查询成功才显示真实用户名、邮箱、空间、成员角色和状态；首个 `me` 网络／`500/503` 失败时在账户错误区点击“重试读取账户”，复用已有令牌，不重新登录、不新增会话；`403` 隐藏身份并保留真实“退出登录”。刷新或直接访问登录页时已有令牌也转到账户恢复页；`401` 仍走原刷新／清理逻辑。`owner` 是个人空间所有者，不是系统管理员。错误密码、重复注册、字段错误和网络错误应明确反馈，不展示旧成功。
3. 刷新账户页面，凭据从本标签 `sessionStorage` 恢复，身份由 `me` 重新获取。关闭标签不保证保持登录；访问令牌过期才需刷新，不必为了体验强行等待到期。
4. 退出应先隐藏账户并清理可恢复凭据／身份缓存，再调用真实服务端撤销用户全部会话。网络失败只能显示“本地已清除，服务端撤销未确认”，保留待撤销重试入口；重载后仍待撤销，不恢复登录，新登录前先解决待撤销。
5. 不登录也可访问工作台健康页；进入页面不自动检测。手动检测成功后只停止自己启动的后端再重试，失败不能展示上次成功；恢复后可重试。旧工作台地址应兼容跳转，`hash` 页面导航不是后端 `HTTP` 路由。
6. 用桌面 `1440×900`、移动 `375×812` 和键盘体验表单／导航／退出；记录布局、焦点、加载与错误，不能只凭构建声明无横向溢出或无障碍验收。

### 状态、安全与阅读入口

`Pinia` 只管理令牌、会话状态、`epoch` 和待撤销状态，不复制 `user/tenant`；`vue-query` 是 `me` 的唯一服务端数据来源。并发 `401` 使用单次共享刷新，原请求最多重试一次；迟到响应不得跨 `epoch` 回填旧身份。`sessionStorage` 中的 `Bearer` 凭据可被 `XSS` 读取，是本机兼容选择而非生产安全承诺；不使用不可信 `v-html`，不记录密码／令牌，不截图或分享存储内容。旧访问令牌不会因刷新立即撤销，退出才撤销所有会话。

实际调用链与最终源码定位见[本轮学习指南](../../artifacts/weknora-product-auth/03-code/learning-guide.md)，五接口细节见[认证接口文档](../../artifacts/weknora-product-auth/03-code/api-docs.md)，唯一阶段进度见[进度与验收记录](../../docs/从0到1重构WeKnora/13-进度与验收记录.md)。实际源码与行号已只读核对，运行结论只同步开发者／协调者证据，本文未重跑；开发自检、独立代码审查、独立测试必须分列。完成本业务必要交付后由主线程暂停，不自动开始知识库。

## 历史记录范围

下文“本轮／当前”均是对应旧增量快照。旧根跳健康页、仅健康代理、无登录与无 `sessionStorage` 的描述不适用于上方新认证合同；历史测试计数及链接原样保留。

本轮范围是共享导航外壳与“服务检测／开发进度”两个页面，按已审核的 `C1–C5` 合同同步说明，不把方案当作运行证据。健康请求仍通过同源相对 `GET /health`，经 `Vite` 开发代理访问 `Python FastAPI`；请求状态由 `@tanstack/vue-query` 管理，`Pinia` 只注册、不复制服务端结果。本轮无后端行为变化，数据库、上传、解析、检索、问答未开始，整个 `S1` 未全量验收。

**本轮实际验证（`2026-11-21`）：** 独立 CODE-REVIEW 为 `PASSED`，`P0/P1=0`，唯一 `P2` 报告定位文字已修正；TASK-04 本增量实际重跑 `27` 项 Node 测试与 `25` 个浏览器组（导航 `13`、健康回归 `11`、真实服务 `1`），均通过，必要项 failed/blocked 为 `0`，frozen 安装与类型检查／构建通过，未发现生产缺陷。证据：[独立审查](../../artifacts/weknora-learning-workbench/03-code/code-review-report.md)、[正式测试报告](../../artifacts/weknora-learning-workbench/04-e2e/test-report.md)、[测试用例](../../artifacts/weknora-learning-workbench/04-e2e/added-cases.md)；原理见[本轮学习指南](../../artifacts/weknora-learning-workbench/03-code/learning-guide.md)。本次仅同步已存在报告，不重跑测试；本轮只做导航增量，无后端行为变化。进度页仍是版本化静态事实，不是实时服务状态、工作流状态或运行 `trace`。真实失败恢复采用浏览器 offline/online，未停后端；取消与迟到响应含明确标注的受控注入，不冒称真实服务端故障。以下两段保留上一健康子项历史，不混用旧计数；数据库、上传、解析、检索、问答未开始，整个 `S1` 未全量验收，必要收尾与讲解后暂停等明确继续。

**开发阶段快照（2026-11-20）：** 2026-11-20 主 developer 已真实完成 uv frozen dev 同步、锁一致性、Ruff、pnpm 10.11.0 frozen 安装与 vue-tsc/Vite 构建，均 exit 0；直连/代理 GET 返回精确 JSON 与 Python header；浏览器初始零请求、键盘触发成功、停本次后端后代理 HTTP 500 失败且隐藏旧成功、重启后恢复均通过。受控延迟转发确认请求中禁用且重复点击仅一次请求；network/http/protocol/timeout 为显式故障注入自检，不是后端真实业务错误。独立 CODE-REVIEW/TASK-04 尚未执行，测试 not-run，不算独立验收通过。

**上一健康子项验证更新（`2026-11-21`，历史证据）：** 独立 CODE-REVIEW 已 PASSED（P0/P1/P2 均 0）；TASK-04 已 completed，38 项自动测试（pytest 11 + Node 27）与 11 个浏览器检查组全部 passed，必需行为 failed/blocked 均 0。测试执行日期按正式报告为 2026-11-20（UTC），本次文档同步日期为 2026-11-21；不是重新执行测试。 [独立审查](../../artifacts/weknora-python-vue3-rebuild/03-code/code-review-report.md) · [正式测试报告](../../artifacts/weknora-python-vue3-rebuild/04-e2e/test-report.md) · [新增用例](../../artifacts/weknora-python-vue3-rebuild/04-e2e/added-cases.md)。上述待执行/not-run 仅属开发阶段历史，当前以正式报告为准；仅健康子项，不表示全 S1 或上传问答完成。main 收尾后暂停等待用户明确继续，本轮未提交推送。

## 1. 安装与构建

需要 Node.js >= 22.12、pnpm 10.11.0 和 Python 后端（若要点击成功）。从 `refactor/` 进入前端目录：

```sh
cd python/frontend
node --version
pnpm --version
pnpm install --frozen-lockfile
pnpm build
```

`package.json` 的 `build` 应包含 `vue-tsc --noEmit && vite build`。`pnpm-lock.yaml` 是唯一前端锁文件；不要用 npm install 或补写 `package-lock.json` 替代它。Corepack 不可用时按项目环境安装指定 pnpm，工具或 registry 受限则记录 blocked，不把另一台机器的构建当作本机证据。

## 2. 启动与配置

### 从 `python/` 根目录同时启动前后端

历史统一入口曾在 `python/` 使用下列命令；当前认证不支持，**不要执行**，改用上方带 `--no-proxy-headers` 的分端命令：

```sh
npm run dev
```

该命令由 `python/scripts/dev.mjs` 管理两个现有开发进程；前端单独调试时仍可在本目录执行 `pnpm dev --host 127.0.0.1`。

默认启动：

```sh
npm run dev
```

统一命令会自动初始化本地认证数据库（仅首次执行）、启动带安全代理参数的 FastAPI 后端和 Vue 前端。打开 `http://127.0.0.1:15400/#/register` 开始注册。

前端单独调试时：

```sh
pnpm dev --host 127.0.0.1
```

打开 `http://127.0.0.1:5400/`，按本轮合同根入口跳转到 `/#/health`；“开发进度”为 `http://127.0.0.1:5400/#/progress`。两条导航支持直接访问、刷新和浏览器前进／后退；未知 hash（如 `/#/missing`）保留错误地址并显示未找到，通过返回服务检测链接恢复到 `/#/health`，不是第三个业务入口。

`Vite` 默认只监听本机、`strictPort=true`，并且只将 HTTP `/health` 代理到 `http://127.0.0.1:8080`。`/#/health` 是浏览器页面，`GET /health` 是网络请求：hash 不发送给服务器，点击导航本身不调用后端。裸 `/progress` 不承诺为页面深链接，裸 `/health` 仍走开发代理。浏览器请求不拼接后端绝对地址；生产静态站点仍需既有部署提供请求转发，hash 路由不会带上 `Vite` 开发代理，本轮不改部署。

可在启动前用无秘密环境变量改地址：

```sh
BACKEND_PROXY_TARGET=http://127.0.0.1:8081 FRONTEND_PORT=5401 pnpm dev --host 127.0.0.1
```

此时后端应以 8081 运行，页面入口是 `http://127.0.0.1:5401`。也可写入本地 `.env`；不要把真实凭据或生产地址放入 `.env.example`。端口被占用时不要让工具自动换端口，也不要停止不明进程；选择空闲端口后同步前端入口和代理目标。

## 3. 亲自点击成功、停止后端失败与恢复

1. 先启动本次 Python 后端，再启动 Vite。打开页面和浏览器 Network，确认初始是“待检测”，没有自动发出 `/health`。
2. 点击“检测后端连接”。按钮进入请求中并防止重复点击；请求成功后核对 Network 中的相对 `/health`、200、`status: ok` 和 `X-WeKnora-Implementation: python-fastapi`，再对照页面显示。
3. 只停止本次启动的 Python 进程，保留前端。再次点击，页面应进入失败并给固定诊断，不能保留旧成功结果冒充本次成功。代理失败的响应可能被归为 HTTP 或 protocol；不要把它写成 FastAPI 业务错误。
4. 重启本次 `Python` 服务，再点击；页面应恢复成功。上一健康子项真实页面验证观察到成功→停后端代理 HTTP 500→恢复成功，历史独立结果见文首报告；本轮导航回归须以本任务正式报告确认。
5. 在请求未返回时切到 `/#/progress` 或未知页：按合同健康组件卸载并取消在途请求；立即返回 `/#/health` 应为待检测，不展示旧成功或迟到响应。进入页面、窗口聚焦和网络重连都不应自动检测。这里是体验检查步骤，不是本 worker 已执行的测试。

前端成功条件不是只有 HTTP 200：还必须是 JSON、对象 `status` 为 `ok`、身份 header 正确。`fetchHealth` 的固定错误分类为 `network`、`timeout`、`http`、`protocol`；超时阈值为 5000ms。页面不渲染代理返回的 HTML、堆栈或任意原始错误正文。请求取消不伪造成超时或成功。

## 4. 从点击到页面更新的源码阅读顺序

先区分两条链；以下路由位置来自本轮冻结合同，不为并行新增源码编造行号，实际实现由主线程集成核对：

- 页面导航：`src/layouts/WorkbenchLayout.vue` 的 `RouterLink` → `src/router/index.ts` 的 `createRouter` / `createWebHashHistory(import.meta.env.BASE_URL)` 匹配 hash → `src/App.vue` 的 `RouterView` 渲染页面；`src/main.ts` 在挂载前注册 router，并保留原有插件。外壳只有一个 `main`，每页一个 `h1`；两条导航有精确当前项与键盘焦点。
- 请求检测：健康页内主动点击 → `onCheckClick()` → `check()` → `query.refetch()` → `fetchHealth()` → `Vite` HTTP `/health` 代理 → `FastAPI`。页面导航不是 `fetch`，`RouterView` 不是后端 HTTP 路由。

按实际文件阅读健康链，而不是把静态说明当运行 `trace`：

1. `src/views/health/components/HealthPanel.vue` 的 `onCheckClick()` 接收按钮事件并调用 `check()`。
2. `src/views/health/hooks/useHealthCheck.ts` 的 `useHealthCheck()` 建立禁用自动请求的 query，`check()` 主动 `refetch`，以 `idle/checking/success/failure` 映射页面状态并保护并发点击。
3. `src/api/health.ts` 的 `fetchHealth(signal?)` 用相对 `/health` 发请求，校验 HTTP、内容类型、JSON 形状和 Python 身份，并清理 5000ms 超时资源。
4. `vite.config.ts` 的 `server.proxy` 只负责开发期转发，不是业务方法，也不记录 trace。
5. `python/backend/app/main.py` 的 FastAPI `health()` 返回精确 JSON 和身份 header；响应沿代理回到 fetch，再由 query 更新页面模板。

本 worker 已只读核实定位：`src/views/health/components/HealthPanel.vue:47–49` 的 `onCheckClick()`；`src/views/health/hooks/useHealthCheck.ts:12–67` 的 `useHealthCheck()`、`48–57` 的 `check()`、`60–64` 的 `dispose()` / `onScopeDispose(dispose)`；`src/api/health.ts:33–74` 的 `fetchHealth()`（`37–41` 转发取消信号、`45` 发请求、`70–72` 清理）；`vite.config.ts:23–28` 的开发代理。健康目录保持 `src/views/health/components/` 与 `src/views/health/hooks/`，不迁回旧全局目录。

按合同 `RouterView` 不使用 `KeepAlive`：离开健康页触发已有 `dispose()` → `cancelQueries()` → `AbortSignal` → 请求中止；`gcTime: 0` 与新组件局部状态配合，重入为待检测。路由集成后的取消、快速重入和迟到响应行为由本轮正式测试验证。本轮不新增或修改 HTTP API，因此不新增 API 文档任务；上一健康合同文档属于历史任务，不冒充本轮产物。

## 5. 本轮边界与下一步

刷新或重新进入健康页应回到待检测；没有数据库、`localStorage`、`sessionStorage`、`JSONL` 或 `trace` 表。健康结果只表示当前 `Python` HTTP 应用响应，不表示数据库、模型、队列或完整业务可用。数据库、上传、解析、检索、问答未开始，`SSE` 和全量 `/api/v1` 兼容仍未实现，整个 `S1` 未全量验收。

`/#/progress` 仅展示版本化静态事实：上一健康子项的历史验收、本轮导航范围与结论定位、未开始业务和单需求暂停策略；不读取本机文件或 `workflow-state.json`、不请求 API、不展示整体完成率。页面中的仓库路径需在仓库打开，不当作 `Vite` 能访问的下载链接。本轮只增加导航切片，无后端行为变化。

完成独立审核、测试和知识记录后，主线程会暂停并持久化等待用户继续。下一项应由用户明确继续后，在新的增量任务目录中重新确认，不自动接着实现。
