# 阶段验收报告 · phase8b

- 阶段：**Phase 8B 集成：MCP Client（Service）管理 + 凭证/审批/目录**
- 执行时间：2026-11-01 10:26:45
- 结果：**12/13 通过**

| # | 步骤 | 结果 | 详情 |
|---|---|---|---|
| 1 | phase8b 阶段测试用例已编写 | ✅ | tests/e2e/test_mcp_service_api.py |
| 2 | ruff 静态检查 | ❌ | notations  4 \| \|  5 \| \| from datetime import UTC, datetime  6 \| \|  7 \| \| from sqlalchemy import select  8 \| \| from sqlalchemy.ext.asyncio import Async… |
| 3 | pytest 自动化测试 | ✅ | 115 passed, 2 skipped in 509.43s (0:08:29) |
| 4 | 创建知识库并上传文档 | ✅ | d6c47ae8-6267-4007-9182-e20477fa0f68 |
| 5 | 创建自举 MCP 端点 | ✅ | 2cc6551f-87c3-4a86-afe6-94548976d1cb |
| 6 | 创建 MCP 服务（指向自举端点） | ✅ | ad49eee9-adb2-49b2-ad8a-903365c7cc78 |
| 7 | MCP 服务测试连接 | ✅ | tools=4 |
| 8 | MCP 服务工具列表 | ✅ | tools=4 |
| 9 | 持久化目录 refresh/get | ✅ | metadata tools=4 |
| 10 | 凭证子资源 put/clear | ✅ | credentials put/clear ok |
| 11 | 工具审批策略 | ✅ | tool approval set |
| 12 | 数据库落盘校验 | ✅ | services=1 metadata=1 approvals=1 |
| 13 | 删除 MCP 服务 | ✅ | deleted |

## 服务端日志（尾部）

```
2026-11-01 10:26:25,259 | INFO  | app.access | rid=82fb764b6cf64cb7b0f062969dd39dac | POST /api/v1/mcp-services -> 200
2026-11-01 10:26:25,259 | INFO  | uvicorn.access | rid=82fb764b6cf64cb7b0f062969dd39dac | 127.0.0.1:49245 - "POST /api/v1/mcp-services HTTP/1.1" 200
2026-11-01 10:26:28,805 | INFO  | app.access | rid=5a1d23e2530d443b83498e7ae6ed9991 | POST /mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb -> 200
2026-11-01 10:26:28,807 | INFO  | uvicorn.access | rid=5a1d23e2530d443b83498e7ae6ed9991 | 127.0.0.1:61509 - "POST /mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb HTTP/1.1" 200
2026-11-01 10:26:28,810 | INFO  | httpx | rid=2660e0cb24b244d7a1aa07a4b6d5b5a5 | HTTP Request: POST http://127.0.0.1:62356/mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb "HTTP/1.1 200 OK"
2026-11-01 10:26:31,990 | INFO  | app.access | rid=ac15b2d12ac74bf8abd8cc042df8efa0 | POST /mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb -> 200
2026-11-01 10:26:31,991 | INFO  | uvicorn.access | rid=ac15b2d12ac74bf8abd8cc042df8efa0 | 127.0.0.1:64000 - "POST /mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb HTTP/1.1" 200
2026-11-01 10:26:31,994 | INFO  | httpx | rid=2660e0cb24b244d7a1aa07a4b6d5b5a5 | HTTP Request: POST http://127.0.0.1:62356/mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb "HTTP/1.1 200 OK"
2026-11-01 10:26:31,998 | INFO  | app.access | rid=2660e0cb24b244d7a1aa07a4b6d5b5a5 | POST /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/test -> 200
2026-11-01 10:26:31,998 | INFO  | uvicorn.access | rid=2660e0cb24b244d7a1aa07a4b6d5b5a5 | 127.0.0.1:49245 - "POST /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/test HTTP/1.1" 200
2026-11-01 10:26:35,226 | INFO  | app.access | rid=95833b9619774c55ae8af4c80f936a94 | POST /mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb -> 200
2026-11-01 10:26:35,226 | INFO  | uvicorn.access | rid=95833b9619774c55ae8af4c80f936a94 | 127.0.0.1:63373 - "POST /mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb HTTP/1.1" 200
2026-11-01 10:26:35,227 | INFO  | httpx | rid=2ccd1d41911446518e7dc0a59ae18bb3 | HTTP Request: POST http://127.0.0.1:62356/mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb "HTTP/1.1 200 OK"
2026-11-01 10:26:37,577 | INFO  | app.access | rid=0fadeee6333b44f6a5d892ce41697eba | POST /mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb -> 200
2026-11-01 10:26:37,578 | INFO  | uvicorn.access | rid=0fadeee6333b44f6a5d892ce41697eba | 127.0.0.1:57768 - "POST /mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb HTTP/1.1" 200
2026-11-01 10:26:37,579 | INFO  | httpx | rid=2ccd1d41911446518e7dc0a59ae18bb3 | HTTP Request: POST http://127.0.0.1:62356/mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb "HTTP/1.1 200 OK"
2026-11-01 10:26:37,581 | INFO  | app.access | rid=2ccd1d41911446518e7dc0a59ae18bb3 | GET /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/tools -> 200
2026-11-01 10:26:37,582 | INFO  | uvicorn.access | rid=2ccd1d41911446518e7dc0a59ae18bb3 | 127.0.0.1:49245 - "GET /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/tools HTTP/1.1" 200
2026-11-01 10:26:41,327 | INFO  | app.access | rid=b1194bf3d64848b9a81779891ad08990 | POST /mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb -> 200
2026-11-01 10:26:41,331 | INFO  | uvicorn.access | rid=b1194bf3d64848b9a81779891ad08990 | 127.0.0.1:53407 - "POST /mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb HTTP/1.1" 200
2026-11-01 10:26:41,333 | INFO  | httpx | rid=50096c1c9ea9465993733e6e363fbb83 | HTTP Request: POST http://127.0.0.1:62356/mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb "HTTP/1.1 200 OK"
2026-11-01 10:26:45,062 | INFO  | app.access | rid=07e2bc111e0e47d887eafcdfde5e4374 | POST /mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb -> 200
2026-11-01 10:26:45,062 | INFO  | uvicorn.access | rid=07e2bc111e0e47d887eafcdfde5e4374 | 127.0.0.1:61183 - "POST /mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb HTTP/1.1" 200
2026-11-01 10:26:45,065 | INFO  | httpx | rid=50096c1c9ea9465993733e6e363fbb83 | HTTP Request: POST http://127.0.0.1:62356/mcp/2cc6551f-87c3-4a86-afe6-94548976d1cb "HTTP/1.1 200 OK"
2026-11-01 10:26:45,127 | INFO  | app.access | rid=50096c1c9ea9465993733e6e363fbb83 | POST /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/metadata/refresh -> 200
2026-11-01 10:26:45,127 | INFO  | uvicorn.access | rid=50096c1c9ea9465993733e6e363fbb83 | 127.0.0.1:49245 - "POST /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/metadata/refresh HTTP/1.1" 200
2026-11-01 10:26:45,152 | INFO  | app.access | rid=fae9da8f3c544cdeaee18c2544ff29fe | GET /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/metadata -> 200
2026-11-01 10:26:45,153 | INFO  | uvicorn.access | rid=fae9da8f3c544cdeaee18c2544ff29fe | 127.0.0.1:49245 - "GET /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/metadata HTTP/1.1" 200
2026-11-01 10:26:45,214 | INFO  | app.access | rid=b7a750076b294a68bffcc0a5713aebc1 | PUT /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/credentials -> 200
2026-11-01 10:26:45,214 | INFO  | uvicorn.access | rid=b7a750076b294a68bffcc0a5713aebc1 | 127.0.0.1:49245 - "PUT /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/credentials HTTP/1.1" 200
2026-11-01 10:26:45,256 | INFO  | app.access | rid=7d58cbfd899147e0bb704751ec90f729 | DELETE /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/credentials/client_secret -> 200
2026-11-01 10:26:45,256 | INFO  | uvicorn.access | rid=7d58cbfd899147e0bb704751ec90f729 | 127.0.0.1:49245 - "DELETE /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/credentials/client_secret HTTP/1.1" 200
2026-11-01 10:26:45,311 | INFO  | app.access | rid=56d9ec865e7440768093eba84c9fc07c | PUT /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/tool-approvals/search_knowledge -> 200
2026-11-01 10:26:45,312 | INFO  | uvicorn.access | rid=56d9ec865e7440768093eba84c9fc07c | 127.0.0.1:49245 - "PUT /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/tool-approvals/search_knowledge HTTP/1.1" 200
2026-11-01 10:26:45,340 | INFO  | app.access | rid=642d90ac8ecc420cadbb6f2efb1f4078 | GET /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/tool-approvals -> 200
2026-11-01 10:26:45,341 | INFO  | uvicorn.access | rid=642d90ac8ecc420cadbb6f2efb1f4078 | 127.0.0.1:49245 - "GET /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78/tool-approvals HTTP/1.1" 200
2026-11-01 10:26:45,408 | INFO  | app.access | rid=3b8381d67bf24e4f8ae0cb5d0ae29151 | DELETE /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78 -> 200
2026-11-01 10:26:45,409 | INFO  | uvicorn.access | rid=3b8381d67bf24e4f8ae0cb5d0ae29151 | 127.0.0.1:49245 - "DELETE /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78 HTTP/1.1" 200
2026-11-01 10:26:45,435 | INFO  | app.access | rid=d579fb793a87491db857db6e90270899 | GET /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78 -> 404
2026-11-01 10:26:45,435 | INFO  | uvicorn.access | rid=d579fb793a87491db857db6e90270899 | 127.0.0.1:49245 - "GET /api/v1/mcp-services/ad49eee9-adb2-49b2-ad8a-903365c7cc78 HTTP/1.1" 404
```
