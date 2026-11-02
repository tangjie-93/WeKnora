# WeKnora 外部项目集成方案

本文说明另一个业务项目如何调用 WeKnora，完成知识库创建、文档上传、检索和流式对话。

## 部署地址与 Swagger

WeKnora 后端默认使用 `8080` 端口，接口前缀是 `/api/v1`。

后端直接暴露且 `GIN_MODE=debug` 时：

```text
http://10.10.14.40:8080/swagger/index.html
http://10.10.14.40:8080/swagger/doc.json
```

你现在访问的 `http://10.10.14.40/platform/knowledge-bases` 是前端 SPA 路由。经实际访问验证，当前部署状态是：`/swagger/index.html` 和 `/swagger/doc.json` 返回前端 `index.html`，后端 `:8080/swagger/*` 返回 `401`。因此当前部署还没有可用的 Swagger 地址。

已在 `frontend/nginx.conf` 增加 `/swagger/` 到后端的代理。重新构建并部署前端后，若外层网关把 `/platform` 前缀剥掉，地址为：

```text
http://10.10.14.40/platform/swagger/index.html
```

若外层网关不剥掉前缀，需要在外层网关增加同样的转发：

```nginx
location /platform/swagger/ {
    proxy_pass http://weknora-frontend/swagger/;
}
```

Swagger 只在 Go 后端 `GIN_MODE != release` 时注册。生产环境默认是 `release`，因此还需要在后端环境变量中设置：

```env
GIN_MODE=debug
```

然后重新创建后端容器，不能只执行普通重启：

```bash
docker compose up -d --force-recreate app frontend
```

验证：

```bash
curl -i http://10.10.14.40/platform/swagger/index.html
curl -i http://10.10.14.40/platform/swagger/doc.json
```

两者都应返回 `200`，第二个响应应为 Swagger JSON，而不是前端 HTML。

## 鉴权

集成项目的后端先调用：

```http
POST /api/v1/auth/login
Content-Type: application/json
```

```json
{
  "email": "integration@example.com",
  "password": "your-password"
}
```

保存响应中的 `token`、`refresh_token` 和 `active_tenant.id`。后续接口携带：

```http
Authorization: Bearer <token>
X-Tenant-ID: <tenant_id>
```

Token 过期时调用 `POST /api/v1/auth/refresh`，请求体为：

```json
{
  "refresh_token": "<refresh_token>"
}
```

建议单独创建一个集成账号，只加入目标空间，不要在业务系统中保存系统管理员密码。

## 创建知识库

```http
POST /api/v1/knowledge-bases
Authorization: Bearer <token>
X-Tenant-ID: 1
Content-Type: application/json
```

```json
{
  "name": "产品文档库",
  "description": "产品说明书和 FAQ",
  "chunking_config": {
    "chunk_size": 600,
    "chunk_overlap": 80
  }
}
```

保存响应中的 `data.id`，记为 `knowledge_base_id`。

创建和上传需要 `contributor` 或更高租户角色。检索和对话需要当前账号拥有该空间访问权限。

## 上传文档

```http
POST /api/v1/knowledge-bases/{knowledge_base_id}/knowledge/file
Content-Type: multipart/form-data
Authorization: Bearer <token>
X-Tenant-ID: 1
```

```bash
curl -X POST \\
  "http://10.10.14.40/api/v1/knowledge-bases/<kb_id>/knowledge/file" \\
  -H "Authorization: Bearer <token>" \\
  -H "X-Tenant-ID: 1" \\
  -F "file=@./product-manual.pdf"
```

接口会执行文件保存、解析、分块和向量化，完成后返回文档信息。重点字段：

```json
{
  "id": "knowledge-id",
  "parse_status": "completed",
  "error_message": ""
}
```

上传后检查 `parse_status`。如果失败，读取 `error_message`。生产调用方应设置较长的上传超时时间，并保留失败重试入口。

## 检索

```http
POST /api/v1/knowledge-bases/{knowledge_base_id}/hybrid-search
Authorization: Bearer <token>
X-Tenant-ID: 1
Content-Type: application/json
```

```json
{
  "query": "如何重置密码？",
  "top_k": 5
}
```

返回的 `data` 是相关分块列表，包含 `content`、`score`、`knowledge_id` 和 `chunk_index`。业务系统可以直接展示这些结果，也可以自行拼接答案。

## 对话

先创建会话：

```http
POST /api/v1/sessions
```

```json
{
  "title": "产品问答",
  "knowledge_base_id": "<kb_id>"
}
```

保存响应中的 `data.id`，记为 `session_id`。然后调用：

```http
POST /api/v1/knowledge-chat/{session_id}
Accept: text/event-stream
Content-Type: application/json
```

```json
{
  "query": "产品支持哪些登录方式？"
}
```

这是 SSE 流，不是普通 JSON。调用方需要处理：

- `references`：引用的文档分块。
- `answer`：增量答案，按顺序拼接 `data.content`。
- `complete`：本轮回答结束。
- `error`：模型调用失败。

代理层必须关闭 SSE 缓冲，并设置足够长的读取超时时间：

```nginx
proxy_buffering off;
proxy_read_timeout 3600s;
proxy_http_version 1.1;
```

同一个 `session_id` 可以连续提问，WeKnora 会读取会话历史。

## 推荐的业务封装

在另一个项目中封装一个 `WeKnoraClient`，统一负责：

1. 登录和 Token 缓存。
2. Token 刷新和一次重试。
3. 注入 `Authorization`、`X-Tenant-ID`。
4. 统一解析 `{ success, data, error }`。
5. 上传文档和解析状态查询。
6. SSE 的 `answer`、`references`、`complete`、`error` 处理。

业务数据库建议保存以下映射：

| 业务字段 | WeKnora 字段 |
| --- | --- |
| `project_id` | 业务项目 ID |
| `weknora_tenant_id` | 租户 ID |
| `weknora_knowledge_base_id` | 知识库 ID |
| `weknora_knowledge_id` | 文档 ID |
| `weknora_session_id` | 会话 ID |

## 生产安全边界

- 只通过 HTTPS 暴露接口。
- 不在浏览器保存集成账号密码或长期 refresh token。
- 限制 `CORS_ALLOW_ORIGINS` 为实际前端域名。
- 限制上传大小和上传类型。
- 对外层网关设置上传超时和 SSE 读取超时。
- 为集成账号设置最小租户权限。
- Swagger 只建议在内网或测试环境开启；生产环境完成联调后恢复 `GIN_MODE=release`。

## 调用顺序

```text
登录
  → 创建知识库
  → 上传文档
  → 检查 parse_status
  → hybrid-search 检索
  → 创建 session
  → knowledge-chat/{session_id} 消费 SSE
```
