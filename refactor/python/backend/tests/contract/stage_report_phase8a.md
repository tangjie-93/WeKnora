# 阶段验收报告 · phase8a

- 阶段：**Phase 8A 集成：MCP Endpoint（Server）+ 公开 Streamable HTTP**
- 执行时间：2026-10-30 15:07:39
- 结果：**14/14 通过**

| # | 步骤 | 结果 | 详情 |
|---|---|---|---|
| 1 | phase8a 阶段测试用例已编写 | ✅ | tests/e2e/test_mcp_endpoint_api.py |
| 2 | ruff 静态检查 | ✅ | All checks passed |
| 3 | pytest 自动化测试 | ✅ | 105 passed, 2 skipped in 379.29s (0:06:19) |
| 4 | 创建知识库并上传文档 | ✅ | 55c8500d-2288-4386-b4df-63096debc7c6 |
| 5 | MCP 端点工具目录 | ✅ | tools=12 |
| 6 | 创建 MCP 端点 | ✅ | 729104a7-8ad6-4d81-986b-2f25065ec9a6 |
| 7 | 端点详情/更新/列表 | ✅ | get/update/list ok |
| 8 | MCP initialize | ✅ | weknora |
| 9 | MCP tools/list | ✅ | tools=9 |
| 10 | MCP tools/call（检索/列表） | ✅ | 3 tools called |
| 11 | 轮换 token 后旧 token 失效 | ✅ | rotate ok, old token rejected |
| 12 | 禁用端点返回 403 | ✅ | disabled -> 403 |
| 13 | 数据库落盘校验 | ✅ | mcp_endpoints=1 |
| 14 | 删除端点 | ✅ | deleted |
