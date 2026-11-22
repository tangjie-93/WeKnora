---
task_id: WEKNORA-REBUILD-20261120
stage: TASK-03
author: 开发工程师
date: 2026-11-20
run_mode: auto
---

# Python 后端变更记录

## 当前增量：`2026-11-21` 显式本地连接检查

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
