# WeKnora 部署与使用说明

按以下顺序操作，启动核心服务并使用知识库、检索问答和智能体。模型服务需要自行配置；联网搜索、图谱、沙箱等可选能力暂不启用。

## 1. 检查服务器环境

服务器需要已安装 `Docker Engine`、`Docker Compose v2` 和 `OpenSSL`，并能访问镜像仓库和所用模型服务。执行以下命令，确认能显示版本：

```bash
docker --version
docker compose version
openssl version
```

若提示命令不存在，先安装相应工具，再继续。

## 2. 上传部署文件

将本机的 `server-deploy` 文件夹中的全部内容上传到服务器的 `/opt/weknora`，包括隐藏文件 `.env.example`，保留子目录结构。

确认文件直接位于 `/opt/weknora/docker-compose.yml`，不要多嵌套一层 `server-deploy`。

## 3. 创建配置文件

在服务器执行：

```bash
cd /opt/weknora
cp .env.example .env
chmod 600 .env
```

如果已经有 `.env`，跳过复制命令，避免覆盖已有配置和密钥。

## 4. 设置密码和密钥

依次执行下面的命令，保存每次输出的随机值：

```bash
openssl rand -hex 24
openssl rand -hex 24
openssl rand -hex 32
openssl rand -hex 16
```

打开配置文件（也可以使用服务器上的其他文本编辑器）：

```bash
nano .env
```

找到并修改下面四个已有配置项，将等号右侧替换成对应结果，不要重复添加同名配置：

```dotenv
DB_PASSWORD=第一个命令的结果
REDIS_PASSWORD=第二个命令的结果
JWT_SECRET=第三个命令的结果
SYSTEM_AES_KEY=第四个命令的结果
```

使用 `nano` 时，按 `Ctrl+O` 后回车保存，再按 `Ctrl+X` 退出。首次部署使用以下基础配置，其余项可保留模板默认值：

```dotenv
COMPOSE_PROFILES=
STORAGE_TYPE=local
RETRIEVE_DRIVER=postgres
NEO4J_ENABLE=false
LANGFUSE_ENABLED=false
WEKNORA_SANDBOX_DOCKER_ENABLED=false
```

基础部署使用本地文件存储和 `PostgreSQL` 检索。图片理解、音频转写和重排按需在网页添加对应模型。

妥善备份 `.env`。已有部署升级时不要重新生成上述值，尤其是 `SYSTEM_AES_KEY`，丢失会导致已加密凭证无法恢复。

## 5. 下载镜像并启动

逐条执行，上一条成功后再继续：

```bash
docker compose config --quiet
docker compose pull
docker compose up -d --no-build
docker compose ps
```

第一条没有输出且没有报错即表示配置校验通过。首次下载镜像可能需要一些时间。最后确认 `frontend`、`app`、`docreader`、`postgres`、`redis` 已运行，带健康检查的服务等待其变为 `healthy`。

如果启动失败或容器反复重启，查看日志：

```bash
docker compose logs --tail=100 app docreader postgres redis frontend
```

默认前端使用服务器的 `80` 端口。如果已被占用，将 `.env` 中的 `FRONTEND_PORT` 改为其他空闲端口，例如 `8088`，再执行 `docker compose up -d --no-build`。

### Swagger / OpenAPI（仅联调环境）

本部署包默认使用 `GIN_MODE=release`，生产模式不会注册 Swagger 路由。仅修改本机源码目录不会修改已运行容器；当前部署使用的是 `docker-compose.yml` 中的预构建镜像和 `--no-build` 启动方式。

如果需要在内网临时联调，请在服务器 `/opt/weknora/.env` 中修改：

```dotenv
GIN_MODE=debug
```

然后重新创建 `app` 和 `frontend` 容器：

```bash
cd /opt/weknora
docker compose up -d --no-build --force-recreate app frontend
docker compose ps
```

验证命令：

```bash
curl -i http://服务器地址/swagger/index.html
curl -i http://服务器地址/swagger/doc.json
```

第二个地址必须返回 JSON，不能返回 `<!DOCTYPE html>`。如果仍返回前端首页，说明当前 `frontend` 镜像没有 `/swagger/` 代理配置，需要更新到包含该配置的镜像版本或重新构建并发布前端镜像。联调完成后将 `GIN_MODE` 恢复为 `release` 并重新创建 `app`。

## 6. 打开网页并配置模型

在服务器防火墙或云安全组中允许你的访问来源连接前端端口（默认 `TCP 80`），然后在浏览器打开：

```text
http://你的服务器IP
```

如果上一步改为 `8088`，则访问 `http://你的服务器IP:8088`。

按页面引导注册账号，在「设置 → 模型」添加：

1. 对话模型：填写模型名称、服务地址和 `API Key`。
2. 向量模型：填写对应模型服务配置，用于知识库检索。

然后创建知识库，选择相应模型，上传文档，等待解析完成后提问。部署包不包含模型权重；模型服务必须可从服务器访问。使用本地 `Ollama` 时，还需先启动模型服务并按实际地址设置 `.env` 中的 `OLLAMA_BASE_URL`。

公网长期使用时配置域名、`HTTPS` 和访问控制。默认后端还映射了 `8080` 端口，限制不必要的外部访问。

## 7. 可选能力与部署方案

本目录包含核心服务及主 `Compose` 文件中可选服务的部署材料；不包含镜像本身、模型权重、付费服务账号、业务数据或你的密钥。上传目录后仍需下载镜像，并在网页中配置模型和能力。本机 `Docker` 沙箱、对外 `MCP` 服务和 `ODL hybrid` 服务需要另行部署，本目录不提供它们的启动配置。

“所有容器启动”不等于“所有功能可用”。向量库和文件存储是可替换方案，不需要同时运行所有后端。图形桌面需要外部沙箱，浏览器控制需要用户端扩展，第三方渠道需要各平台应用凭证。服务器部署也不包含桌面客户端独有的本机能力。

| 能力 | 容器或外部条件 | 还需完成的配置 |
| --- | --- | --- |
| 文档知识库、检索问答、智能体 | 核心服务 | 添加对话模型、向量模型，创建知识库及智能体 |
| 重排、图片理解、音频转写 | 对应模型服务 | 在模型设置添加对应类型，并在知识库或智能体中选用 |
| 联网搜索 | `searxng`，或外部搜索服务 | 添加搜索提供者，智能体开启搜索工具 |
| 知识图谱 | `neo4j` | 全局开关、凭证、知识库图谱选项和抽取模型 |
| 对象存储 | `minio` 或云对象存储 | 配置存储后端、桶和访问地址；不是基础功能的必需项 |
| 调用追踪与用量分析 | `langfuse` 或外部实例 | 配置实例、真实项目密钥 |
| 技能脚本执行、交互式终端 | `Docker`、`E2B` 或 `Cube` 沙箱 | 添加沙箱后端，安装技能，智能体绑定后端并授权工具 |
| 图形桌面 | `E2B` 或 `Cube` 桌面模板 | 模板、服务凭证及 `desktop_enabled`；本机 `Docker` 沙箱不支持图形桌面 |
| 智能体调用外部 `MCP` 工具 | 外部 `MCP` 地址 | 网页添加服务、鉴权并授权工具，无需部署本系统的对外 `MCP` 服务 |
| 外部客户端通过 `MCP` 调用本系统 | 另行部署的 `MCP` 服务 | 系统 `API Key` 和 `MCP` 访问令牌 |
| `ODL hybrid` 文档解析 | 另行部署的 `ODL hybrid` 服务 | 配置可达的服务地址，启用解析配置并选择对应解析器 |
| 浏览器控制、第三方渠道、企业登录 | 浏览器扩展或对应外部平台 | 按产品设置配置扩展连接、应用凭证、回调地址；`Dex` 示例不能替代企业身份系统配置 |

以下命令均在同一部署目录（例如 `/opt/weknora`）中执行。配置块需编辑合并到现有 `.env`：已有同名项就替换，不要重复追加，也不要覆盖整个文件。`COMPOSE_PROFILES` 是 `Docker Compose` 自带选项，用于保存要启动的服务组；追加服务组时保留已启用的组。

建议先跑通基础部署，再逐项增加能力。同一目录只部署一套系统，以下方案是能力组合。环境模板已清空 `Langfuse` 示例密钥，配置真实项目密钥后再启用追踪。

### 7.1 联网搜索与知识图谱

在基础部署上增加联网搜索和图谱，仍使用本地文件存储与原向量库。

```dotenv
COMPOSE_PROFILES=searxng,neo4j
NEO4J_ENABLE=true
NEO4J_URI=bolt://neo4j:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=替换为独立强密码
SEARXNG_SECRET=替换为随机密钥
```

可用 `openssl rand -hex 32` 生成搜索服务密钥。填写后执行：

```bash
docker compose config --quiet
docker compose pull
docker compose up -d --no-build
```

网页中还需配置：

1. 添加类型为 `SearXNG` 的搜索提供者，实例地址填 `http://searxng:8080`，为智能体启用搜索工具。
2. 在知识库配置中启用知识图谱并选择抽取所用模型。已有文档不会仅因启动 `Neo4j` 自动补齐图谱，需要按页面支持的流程重新解析或导入。

`searxng` 地址用于容器之间访问，不能直接作为你电脑浏览器的访问地址。搜索服务还需要能连接外部搜索引擎。

### 7.2 调用追踪

在联网搜索与知识图谱配置基础上启用自建 `Langfuse`；下例保留已启用的服务组：

```dotenv
COMPOSE_PROFILES=searxng,neo4j,langfuse
LANGFUSE_ENABLED=false
LANGFUSE_CLICKHOUSE_PASSWORD=替换为独立强密码
LANGFUSE_MINIO_PASSWORD=替换为独立强密码
LANGFUSE_SALT=替换为随机值
LANGFUSE_ENCRYPTION_KEY=替换为64位十六进制值
LANGFUSE_NEXTAUTH_SECRET=替换为随机值
LANGFUSE_NEXTAUTH_URL=http://服务器地址:3000
LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT=http://服务器地址:9100
```

`LANGFUSE_ENCRYPTION_KEY` 使用 `openssl rand -hex 32` 生成；其他随机值可分别使用同样命令生成。服务器地址必须从实际浏览器可达，使用反向代理时改成对应的 `HTTPS` 地址。

```bash
docker compose config --quiet
docker compose pull
docker compose up -d --no-build
```

打开 `http://服务器地址:3000`，完成账号和项目初始化，生成项目密钥。然后编辑 `.env`：

```dotenv
LANGFUSE_ENABLED=true
LANGFUSE_HOST=http://langfuse-web:3000
LANGFUSE_PUBLIC_KEY=填写真实项目公钥
LANGFUSE_SECRET_KEY=填写真实项目私钥
```

```bash
docker compose up -d --no-build app
```

也可以直接接入已有 `Langfuse`：不启用该服务组，填写已有实例的地址与密钥即可。

### 7.3 对象存储与向量库

启用 `MinIO` 时，在现有 `COMPOSE_PROFILES` 后加入 `minio`，并设置：

```dotenv
STORAGE_TYPE=minio
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY_ID=weknoraadmin
MINIO_SECRET_ACCESS_KEY=替换为独立强密码
MINIO_BUCKET_NAME=weknora
MINIO_USE_SSL=false
```

```bash
docker compose pull
docker compose up -d --no-build
```

通过 `http://服务器地址:9001` 检查桶和权限，并在网页存储设置中确认对应后端。上面的内网端点只适合容器内访问；如需外部渠道访问对象链接，应配置服务器和外部平台均可访问的对象存储域名与协议。迁移已有本地文件需要单独迁移数据，修改变量不会自动搬运旧文件。

默认 `PostgreSQL` 已支持检索，不必为“全功能”安装额外向量库。确有需要时，可选择 `qdrant`、`milvus`、`weaviate` 或 `doris` 服务组，按 `.env.example` 的对应连接字段和网页向量库设置配置。不要直接切换已有知识库的后端而忽略向量数据迁移或重建。

### 7.4 需另行部署的能力

技能脚本执行和图形桌面可在网页「设置 → 沙箱后端」接入已有的 `E2B` 或 `Cube` 服务，配置模板、凭证和工具授权；图形桌面还需开启 `desktop_enabled`。本目录不挂载本机 `Docker socket`，默认关闭 `Docker` 沙箱。

对外提供 `MCP` 或使用 `ODL hybrid` 解析时，需要单独部署对应服务并配置鉴权或连接地址。本目录保留了 `mcp-server/` 源码及 `docker/Dockerfile.odl-hybrid` 构建材料，主 `Compose` 文件不定义这两个服务。仅设置 `COMPOSE_PROFILES=mcp,odl-hybrid` 不会启动它们。

智能体调用外部 `MCP` 工具只需在网页配置外部服务，无需部署本系统的对外 `MCP` 服务。

## 8. 后续操作

在 `/opt/weknora` 目录执行：

```bash
# 查看服务状态
docker compose ps

# 查看最近日志
docker compose logs --tail=100 app

# 修改 .env 后应用配置
docker compose up -d --no-build

# 暂时停止服务，保留数据
docker compose stop

# 再次启动
docker compose up -d --no-build
```

修改 `.env` 后执行 `docker compose up -d --no-build` 才会更新容器环境，单独 `restart` 不会加载新的环境变量。

从 `COMPOSE_PROFILES` 删除服务组不会自动停止已运行的容器。需要停用时先用原配置执行 `stop 服务名`，再修改服务组和应用开关。停用前确认应用已不依赖该服务。

## 9. 数据与升级注意事项

数据库、上传文件等存储在 `Docker` 命名数据卷中，不在本目录内。迁移服务器时，需要另外备份和迁移数据卷以及 `.env`；只复制此目录不会迁移已有数据。原配置的 `Redis` 未配置独立持久化卷，本包保持原行为。

不要执行 `docker compose down -v`，该命令会删除本项目的数据卷。升级前备份数据和密钥，核对目标版本的升级说明及配置变更，再更新 `.env` 中的版本并执行拉取和启动命令。

保持部署目录或 `Compose` 项目名称稳定，否则可能创建新的数据卷，看起来像数据丢失。不要与另一套使用相同容器名的部署同时启动。

## 10. 验收与验证范围

验收应覆盖已启用能力的实际操作：上传文档并完成问答、搜索返回结果、图谱抽取成功、追踪出现记录、沙箱脚本完成并能下载产物、外部客户端成功调用 `MCP`。只看容器状态无法证明这些业务链路都正常。

当前整理环境未安装 `Docker`，只完成静态文件与配置检查，未验证镜像拉取、构建、容器启动或上述业务流程。需在目标服务器检查镜像架构、网络、端口、资源和所选版本兼容性。
