# WeKnora 本地部署与使用说明

## 1. 它是什么

WeKnora 可以理解成一个“企业资料问答和智能助手平台”。你把 PDF、Word、Excel、网页等资料放进去，它会先读懂资料、切成小段、建立索引；之后你用自然语言提问，它从资料中找依据，再让大语言模型组织答案，并把引用的原文显示出来。

它有三块核心能力：

1. **RAG 知识问答**：针对你的资料回答问题，并显示引用来源。
2. **Agent 智能体**：处理多步骤任务，可以检索知识、读取文档、调用搜索、MCP 工具和技能沙箱。
3. **Wiki 知识整理**：从文档中整理人物、产品、概念和相互关系，生成可浏览、可编辑、可回滚的 Wiki。

它自己不是大语言模型，而是“资料管理、检索、模型调用和对话界面”的平台，需要连接 Ollama 或远程模型 API。

## 2. 它是怎么工作的

一次普通问答大致经过：

1. 上传文档。
2. `docreader` 解析 PDF、Office、图片和 OCR 内容。
3. 后端把文档切成小段。
4. Embedding 模型把小段转换为向量，同时建立关键词索引。
5. 提问时同时进行关键词搜索和向量搜索。
6. 合并相关内容，必要时用 Rerank 模型重新排序。
7. LLM 根据这些内容生成答案。
8. 前端流式显示答案和引用片段。

所以，回答质量主要取决于三件事：文档解析是否成功、检索是否找到了正确内容、模型是否足够好。

## 3. 仓库目录

仓库位置：`D:\programs\ai\WeKnora`

| 目录 | 作用 |
| --- | --- |
| `frontend/` | Vue 3 + TypeScript 前端 |
| `cmd/` | 后端、CLI、桌面端程序入口 |
| `internal/` | Go 后端核心业务 |
| `config/` | 默认配置、模型、提示词和 Agent 配置 |
| `docreader/` | 文档解析 gRPC 服务 |
| `docker/` | 各个 Dockerfile |
| `docker-compose.yml` | 标准部署配置 |
| `docker-compose.dev.yml` | 开发模式配置 |
| `helm/` | Kubernetes 部署 Chart |
| `migrations/` | 数据库迁移 |
| `scripts/` | 启动、检查、构建和迁移脚本 |
| `website-docs/` | 详细产品文档 |

当前仓库是 `main` 分支，版本为 `0.8.3`。

## 4. 推荐部署方式

推荐使用 **Docker Compose 标准部署**。这样宿主机不需要单独安装 Go、Python 或 Node.js。

| 服务 | 作用 | 默认端口 |
| --- | --- | --- |
| `frontend` | 网页界面和 Nginx 代理 | `80` |
| `app` | Go 后端、API、权限和问答流程 | `8080` |
| `postgres` | 数据库、全文检索和默认向量检索 | 容器内 `5432` |
| `redis` | 流式输出、异步任务和队列 | 容器内 `6379` |
| `docreader` | 文档解析、Office 和 OCR | 容器内 `50051` |

可选服务：

- Ollama：本地模型。
- Qdrant、Milvus、Weaviate、Doris：替代默认 PostgreSQL 的向量检索。
- MinIO：S3 兼容对象存储。
- Neo4j：知识图谱。
- SearXNG：自建联网搜索。
- Langfuse：记录模型调用、Agent 步骤和 Token。
- MCP Server：让 Cursor、Claude 等外部工具连接 WeKnora。

## 5. Windows 前提

需要安装 Docker Desktop for Windows，并使用 WSL 2 后端。Docker 官方要求支持的 Windows 版本、WSL 2、硬件虚拟化，并建议至少 8GB 内存。[Docker Windows 安装要求](https://docs.docker.com/desktop/setup/install/windows-install/)

安装并启动 Docker Desktop 后检查：

`@powershell
docker version
docker compose version
`

如果 WSL 尚未安装，可用管理员 PowerShell：

`@powershell
wsl --install
wsl --update
`

仓库已经在：

`
D:\programs\ai\WeKnora
`

## 6. 第一次部署

### 6.1 创建配置文件

`@powershell
cd D:\programs\ai\WeKnora
Copy-Item .env.example .env
`

`.env` 里重点检查：

`@dotenv
WEKNORA_VERSION=latest
APP_PORT=8080
FRONTEND_PORT=80

DB_USER=postgres
DB_PASSWORD=请改成自己的数据库密码
DB_NAME=WeKnora

REDIS_PASSWORD=请改成自己的 Redis 密码

STORAGE_TYPE=local
RETRIEVE_DRIVER=postgres

OLLAMA_OPTIONAL=true
OLLAMA_BASE_URL=http://host.docker.internal:11434

JWT_SECRET=
SYSTEM_AES_KEY=
`

不要长期使用模板里的默认数据库和 Redis 密码。`JWT_SECRET` 用于登录令牌，`SYSTEM_AES_KEY` 用于加密保存的凭据。第一次部署生成后要保存好，升级时继续使用原值。

有 Node.js 时可生成随机值：

`@powershell
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
node -e "console.log(require('crypto').randomBytes(16).toString('hex'))"
`

第一条填 `JWT_SECRET`，第二条填 `SYSTEM_AES_KEY`。

### 6.2 拉取并启动

`@powershell
docker compose pull
docker compose up -d
docker compose ps
`

检查后端：

`@powershell
curl.exe http://localhost:8080/health
`

正常会返回：

`@json
{"status":"ok"}
`

然后打开 `http://localhost`。

如果 80 端口被占用，把 `.env` 改成：

`@dotenv
FRONTEND_PORT=3000
`

然后访问 `http://localhost:3000`。

### 6.3 停止和升级

`@powershell
docker compose down
docker compose up -d
docker compose pull
docker compose up -d
`

`docker compose down` 一般只停止服务，数据还在。不要随便执行 `docker compose down -v`，它会删除数据库、上传文件和其他 Docker 数据卷。

## 7. 配置模型

至少需要两类模型：

1. **对话模型 LLM**：负责生成回答，例如 Qwen、DeepSeek、GPT。
2. **Embedding 模型**：把文档和问题转换成向量，用于语义搜索。

Rerank、图片理解 VLM、语音转写 ASR、知识图谱抽取都是可选项。

### 7.1 远程模型 API

这是最容易成功的方式。可以使用 DeepSeek、阿里云百炼、智谱、硅基流动或其他 OpenAI 兼容服务。

启动后在网页的知识库初始化向导中填写：

- 模型厂商或来源。
- API Base URL。
- API Key。
- 对话模型名称。
- Embedding 模型名称和向量维度。

先点“测试”，通过后再保存。

### 7.2 本地 Ollama

安装 Ollama 后运行：

`@powershell
ollama serve
ollama pull qwen3:8b
ollama pull nomic-embed-text
`

Docker 容器访问 Windows 宿主机上的 Ollama，要使用：

`
http://host.docker.internal:11434
`

不要写 `http://localhost:11434`，因为容器里的 localhost 指向容器自己。模型越大，回答可能越好，但占用的内存也越多，第一次建议先用中小模型验证流程。

## 8. 第一次使用

1. 打开 `http://localhost`。
2. 注册账号并登录。
3. 新建知识库。
4. 选择 `document` 文档库或 `faq` 问答库。
5. 在初始化向导配置 LLM 和 Embedding。
6. 点击测试确认模型连接正常。
7. 上传 PDF、Word、Markdown 等文件。
8. 等待文档状态变为 `completed`。
9. 进入对话页面，选择知识库并提问。
10. 点击回答中的引用，确认引用确实来自原文。

文档处理状态一般为：

`
pending -> processing -> finalizing -> completed
`

扫描 PDF、大文件和图片通常需要更长时间。

## 9. 标准版和 Lite 版

| 项目 | 标准版 | Lite 版 |
| --- | --- | --- |
| 启动方式 | Docker Compose，多服务 | 单个 Go 二进制 |
| 数据库 | PostgreSQL/ParadeDB | SQLite |
| 队列 | Redis + Asynq | 内存队列 |
| 多用户、多空间 | 完整支持 | 不提供共享空间 |
| 文档解析 | 完整解析链路 | 主要是 Simple 解析 |
| 适合场景 | 团队、生产、自托管 | 个人、离线、低资源 |

Lite 更轻，但从源码编译需要 Go 1.26、CGO 等依赖。普通用户直接使用 Docker 标准版更省事。

## 10. 启用可选功能

知识图谱：

`@powershell
docker compose --profile neo4j up -d
`

MinIO：

`@powershell
docker compose --profile minio up -d
`

Langfuse：

`@powershell
docker compose --profile langfuse up -d
`

完整功能：

`@powershell
docker compose --profile full up -d
`

`full` 会启动更多组件，内存和磁盘占用明显增加。Docker 沙箱如果需要挂载 `docker.sock`，相当于给容器很高的宿主机权限，生产环境要谨慎。

## 11. API

后端 API 默认地址：

`
http://localhost:8080/api/v1
`

认证方式：

| 方式 | 用途 |
| --- | --- |
| JWT Bearer Token | 网页登录和交互式调用 |
| `X-API-Key` | 服务端、脚本和自动化 |
| `X-Tenant-ID` | 多工作空间切换 |

服务端集成建议使用 API Key，不要把网页登录 JWT 长期写进脚本。完整 API 示例见：

`website-docs/01-getting-started/03-quickstart.md`

## 12. 开发模式

开发模式把 PostgreSQL、Redis 和 docreader 放进容器，但 Go 后端和 Vue 前端在宿主机运行，可以热更新：

`@bash
make dev-start
make dev-app
make dev-frontend
`

Windows 如果没有 Make，可以在 WSL 中执行，或直接参考 `scripts/dev.sh`。

源码开发需要 Go 1.26、CGO、Node.js、npm，以及 docreader 使用的 Python 3.10 和 uv。这些是“改源码并本地编译”才需要的，使用官方 Docker 镜像不需要在宿主机全部安装。

## 13. 常见排错

### `docker compose` 找不到

确认 Docker Desktop 已安装并启动，然后重新打开 PowerShell：

`@powershell
docker version
docker compose version
`

### 80 端口被占用

修改：

`@dotenv
FRONTEND_PORT=3000
`

然后重新执行：

`@powershell
docker compose up -d
`

### Ollama 连接失败

检查：

`@powershell
curl.exe http://127.0.0.1:11434/api/tags
`

WeKnora 内填写 `http://host.docker.internal:11434`，并确认对应模型已经下载。

### 文档一直是 processing

查看：

`@powershell
docker compose logs -f docreader
`

同时检查磁盘、文件大小限制和 Docker 内存。

### 没有引用或回答不准

依次确认：

1. 文档状态是否为 `completed`。
2. Embedding 模型是否成功。
3. 是否在正确知识库提问。
4. 文档是否真的包含答案。
5. 更换 Embedding 后是否重建索引。

### 修改配置未生效

环境变量改完后重建容器：

`@powershell
docker compose up -d --force-recreate
`

部分设置已经保存到数据库，网页“系统设置”里的值可能优先于 `.env`。

## 14. 数据和安全

1. 定期备份 PostgreSQL 数据卷和 `data-files` 文件卷。
2. 不要把服务直接暴露到公网，建议放在 HTTPS 反向代理和防火墙后。
3. 保存好 `JWT_SECRET` 和 `SYSTEM_AES_KEY`。
4. 不要把 API Key 提交到 Git。
5. 升级前阅读 `CHANGELOG.md` 和版本升级说明。
6. 生产环境不要默认开启不需要的 profile。
7. `docker compose down -v` 会清空数据卷，执行前先备份。

## 15. 最短运行路线

`@powershell
cd D:\programs\ai\WeKnora
Copy-Item .env.example .env
docker compose pull
docker compose up -d
docker compose ps
`

然后打开网页、注册账号、配置一个 LLM 和一个 Embedding 模型、上传 PDF、等待解析完成、提问并检查引用。最短流程跑通后，再考虑 Ollama、Neo4j、MinIO、Langfuse、MCP 或 Agent 沙箱。

## 16. 仓库内优先阅读的文件

- `README_CN.md`：项目概览和快速开始。
- `website-docs/01-getting-started/02-installation.md`：安装部署。
- `website-docs/01-getting-started/03-quickstart.md`：首次问答。
- `website-docs/01-getting-started/04-configuration.md`：配置说明。
- `docs/LITE.md`：Lite 与标准版区别。
- `.env.example`：完整环境变量模板。
- `docker-compose.yml`：标准服务编排。
- `docker-compose.dev.yml`：开发环境编排。
- `Makefile`：常用命令。

官方项目地址：[Tencent/WeKnora](https://github.com/Tencent/WeKnora)

