# WeKnora `frontend` 技术架构与从 `0` 到 `1` 实现指南

本文基于当前 `frontend` 源码整理，目标是帮助你按照真实项目的演进顺序，自己实现一个功能相近的 `Vue 3` 前端。重点是理解边界、数据流和高难点，而不是复制全部业务页面。

## 1. 先建立整体认知

当前前端是一个多入口、带登录和多租户能力的知识库问答应用：

```text
index.html ──> src/main.ts ──> App.vue ──> RouterView
                                      ├─ 登录 / 工作空间
                                      ├─ 知识库 / 文档 / 检索
                                      ├─ 聊天 / Agent / 工具调用
                                      └─ 设置 / 组织 / 模型 / 集成

embed.html ─> src/embed-main.ts ─> EmbedPage
                                     └─ 可嵌入式聊天
```

核心技术栈：

| 层次 | 技术 | 作用 |
| --- | --- | --- |
| 构建 | `Vite 7` | 开发服务器、代理、生产构建、代码拆分 |
| UI | `Vue 3` + `TDesign Vue Next` | 组件化页面和交互 |
| 类型 | `TypeScript` + `vue-tsc` | 页面、接口、状态的静态类型检查 |
| 状态 | `Pinia` | 登录态、租户、资源、上传、设置和聊天状态 |
| 路由 | `Vue Router 4` | 页面导航、懒加载、认证和能力守卫 |
| 网络 | `Axios` + `fetch-event-source` | 普通请求和 `SSE` 流式请求 |
| 样式 | `Less` + CSS 变量 | 全局主题、组件覆盖和局部样式 |
| 富文本 | `marked`、`DOMPurify`、`highlight.js`、`KaTeX`、`Mermaid` | Markdown、代码、公式和图表渲染 |
| 测试 | `tsx --test`、浏览器端测试脚本 | 工具、状态、流式协议和关键页面测试 |

依赖和脚本的完整定义在 `frontend/package.json`。

## 2. 目录和职责

```text
frontend/
├── index.html                 # 主应用 HTML 入口
├── embed.html                 # 嵌入式聊天 HTML 入口
├── vite.config.ts             # 多入口、代理、拆包和资源插件
├── src/
│   ├── main.ts                # 主应用启动
│   ├── embed-main.ts          # 嵌入页启动
│   ├── App.vue                # 全局壳、全局浮层和全局副作用
│   ├── router/                # 路由、导航守卫、权限入口
│   ├── api/                   # 按业务域封装后端接口
│   ├── stores/                # Pinia 全局状态和跨页面资源
│   ├── views/                 # 页面级业务模块
│   ├── components/            # 跨页面公共组件
│   ├── composables/           # 可复用组合式逻辑
│   ├── hooks/                 # 通用业务 Hook
│   ├── types/                 # 跨模块类型
│   ├── utils/                 # 请求、鉴权、渲染、安全等纯能力
│   ├── config/                # 路由、能力、工具和部署配置
│   ├── i18n/                  # 多语言运行时和翻译审计
│   ├── assets/                # 主题、图标、图片和样式
│   └── directives/            # 自定义指令，例如稳定 HTML 更新
├── public/                    # 不参与打包处理的静态资源和运行时配置
├── e2e/                       # 浏览器级场景
└── Dockerfile                 # `Vite` 构建后由 `Nginx` 提供静态文件
```

建议按“业务域”理解，而不是把所有 `API`、组件和页面当成同一层。一个知识库功能通常会同时涉及 `api/knowledge-base`、`stores/chatResources`、`views/knowledge`、若干公共组件和类型。

## 3. 启动过程：先实现最小骨架

### 第一步：准备项目

```bash
npm create vite@latest frontend -- --template vue-ts
cd frontend
npm install vue-router pinia axios
npm install tdesign-vue-next vue-i18n
npm install -D less vue-tsc
```

实际项目使用 `npm ci`，因为 `package-lock.json` 固定了依赖版本。学习实现时先保留 `npm`，不要一开始引入额外框架。

### 第二步：实现主入口

`src/main.ts` 的职责依次是：

1. `createApp(App)` 创建 Vue 应用。
2. 注册 `TDesign`、`Pinia`、路由和 `i18n`。
3. 载入全局主题和组件样式。
4. 在有登录凭据时刷新 `/auth/me`，恢复用户、租户和能力。
5. 等待 `router.isReady()` 后再挂载，避免首屏先闪出错误页面。
6. 安装全局错误和浏览器行为保护。

对应源码：`frontend/src/main.ts`。

先做一个最小版本：

```ts
const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
```

确认能显示首页后，再逐个加入主题、错误处理和会话恢复。

### 第三步：实现 `App.vue`

当前 `App.vue` 不负责具体页面业务，主要负责：

- 渲染 `<RouterView />`。
- 挂载全局编辑器、资源预览、上传确认等浮层。
- 消费 `OIDC` 回调。
- 监听登录状态并轮询待处理邀请。
- 触发桌面端更新检查。

实现顺序建议是先只保留 `RouterView`，确认路由工作后，再把跨页面浮层移动到这里。不要把所有页面请求都放进 `App.vue`。

## 4. 路由和认证：第二个实现阶段

`frontend/src/router/index.ts` 是权限入口，不只是 URL 映射。

### 4.1 路由元信息

路由通过 `meta` 描述进入条件：

```ts
meta: {
  requiresAuth: true,
  requiresInit: true,
  requiredCapability: 'agents',
}
```

建议先实现四类页面：

1. `/login`：公开页面。
2. `/platform/knowledge-bases`：需要登录和工作空间。
3. `/onboarding/workspace`：已登录但没有有效租户。
4. `/platform/agents`：需要部署能力或管理员能力。

### 4.2 守卫执行顺序

真实项目的守卫大致按以下顺序判断：

1. 是否正在处理 `OIDC` 回调。
2. 是否需要恢复桌面 `Lite` 模式上次路径。
3. 公开页面直接放行。
4. 无登录态时尝试从 `localStorage` 恢复 Token。
5. Token 无效时尝试自动初始化或跳转登录。
6. 已登录但没有租户时跳转工作空间引导。
7. 检查部署能力、系统管理员和当前用户角色。
8. 最后进入目标页面。

学习实现时先完成“登录、恢复 Token、退出、路由拦截”四件事，再加入多租户和能力控制。

## 5. 请求层：所有接口的基础

### 5.1 请求层职责

`frontend/src/utils/request.ts` 创建 `Axios` 实例并统一处理：

- `Base URL`。
- `Authorization: Bearer <token>`。
- 当前租户的 `X-Tenant-ID`。
- `Accept-Language`。
- `X-Request-ID`。
- 超时和上传超时。
- `401` 刷新 Token。
- 错误格式统一。
- Blob 下载失败时恢复后端 JSON 错误。

业务 API 文件只负责表达业务：

```ts
export function listKnowledgeBases() {
  return request.get('/api/v1/knowledge-bases')
}
```

不要在每个页面里自行拼 Token、租户头和错误提示。

### 5.2 并发 Token 刷新

`frontend/src/utils/authRefresh.ts` 是一个重要的生产模式：

1. 第一个请求发现 `401`，启动一次刷新。
2. 其他同时失败的请求进入 `failedQueue`。
3. 刷新成功后，所有请求使用新 Token 重试。
4. 刷新失败后清理登录相关存储并跳转登录。
5. 刷新 Token 轮换时，必须保存服务端返回的新 Refresh Token。

这里不能简单地让每个 `401` 都单独调用 `/auth/refresh`，否则轮换型 Refresh Token 会互相覆盖。

## 6. 状态管理：Pinia 的边界

### 6.1 登录和租户状态

`frontend/src/stores/auth.ts` 保存：

- 当前用户。
- 当前租户和默认租户。
- Access Token、Refresh Token。
- 成员关系和能力。
- Lite 模式。
- 当前知识库。

登录状态属于跨页面共享状态；输入框内容、弹窗开关和临时筛选条件通常应留在页面或组件中。

### 6.2 资源快照

`frontend/src/stores/chatResources.ts` 共享知识库、Agent、模型、联网搜索和沙箱配置。页面不应该重复请求同一份空间资源。

`frontend/src/stores/resourceCache.ts` 和 `versionedRequest.ts` 解决两个常见竞态：

- 同一时间多个页面挂载，只允许一个请求飞行。
- 写操作后旧请求返回，不能把新数据覆盖回旧快照。

核心思想是给请求分配版本号：只有请求开始时的版本仍然有效，才允许执行 `apply`。

### 6.3 上传任务状态

`frontend/src/stores/uploadTasks.ts` 把上传任务放到全局，因此用户切换页面后上传不会中断。具体队列逻辑拆在 `uploadQueue.ts`、`uploadTasksCore.ts`：

- 限制并发上传数。
- 每个文件独立 `AbortController`。
- 记录进度、批次和失败原因。
- 上传成功后轮询后端解析状态。
- 连续多次查询不到记录才判断文档被删除，避免偶发空响应造成误报。

实现时先做单文件上传，再加入并发队列、取消、重试和解析轮询。

## 7. 页面和 API 的组织方式

### 7.1 页面模块

主要页面域包括：

| 页面域 | 目录 | 主要职责 |
| --- | --- | --- |
| 登录 | `views/auth` | 登录、注册、工作空间引导 |
| 平台壳 | `views/platform` | 侧栏、布局、设置入口 |
| 知识库 | `views/knowledge` | 知识库、文档、Wiki、检索 |
| 聊天 | `views/chat` | 消息时间线、输入框、流式回答 |
| Agent | `views/agent` | Agent 列表和编辑 |
| 组织 | `views/organization` | 成员、邀请、共享资源 |
| 系统 | `views/system` | 用户、模型、运行队列和系统配置 |
| 工具箱 | `views/toolbox` | 沙箱、浏览器和其他工具 |
| 嵌入 | `views/embed` | 外部站点嵌入式聊天 |

页面组件负责布局和用户交互，接口调用放在 `api/`，跨页面数据放在 `stores/`，复杂交互放在 `composables/`。

### 7.2 API 按领域拆分

当前 API 目录包括 `auth`、`chat`、`knowledge-base`、`model`、`agent`、`tenant`、`organization`、`wiki`、`embed` 等。每个领域应包含：

1. 请求函数。
2. 请求参数类型。
3. 返回数据类型。
4. 必要的转换和错误判断。

不要让页面直接依赖后端返回的任意 `any`，至少为关键数据建立接口类型。

## 8. 流式聊天：从简单到完整

这是整个前端最值得单独实现的部分。

### 8.1 最小版本

使用 `fetch-event-source` 发起 `POST`，监听 `onmessage`：

```ts
await fetchEventSource('/api/v1/chat', {
  method: 'POST',
  body: JSON.stringify({ query }),
  onmessage(event) {
    const data = JSON.parse(event.data)
    if (data.type === 'answer') output.value += data.content
  },
})
```

### 8.2 真实项目需要解决的问题

`frontend/src/api/chat/streame.ts` 和 `composables/useChatStreamHandler.ts` 还处理：

- `AbortController` 取消。
- 新请求代际覆盖旧请求，避免旧响应回写页面。
- 初始连接状态和持续流状态分离。
- `401` 后刷新 Token 并重放握手。
- 心跳和空闲超时。
- 服务端关闭连接后的有限重连。
- 工具调用、工具结果、思考、引用、附件和协作任务事件。
- 回答事件的替换、截断和补发。
- 前端渲染节流，避免每个 token 都触发完整页面更新。

建议按以下版本逐步实现：

1. 只有 `answer` 和 `complete` 两类事件。
2. 加入取消和错误状态。
3. 加入请求代际 `generation`。
4. 加入 Token 刷新重试。
5. 加入 `thinking`、`references`、`tool_call` 和 `tool_result`。
6. 最后实现 Agent 协作、暂停、审批和断线恢复。

### 8.3 前端流式状态机

可以把每轮回答建模为：

```text
idle
  ↓ start
connecting ──401──> refreshing ──成功──> connecting
  ↓ headers
streaming
  ├─ answer       -> 累积答案
  ├─ thinking     -> 更新思考区
  ├─ tool_call    -> 创建工具卡片
  ├─ tool_result  -> 填充工具结果
  ├─ references   -> 更新引用
  ├─ complete     -> completed
  ├─ error        -> failed
  └─ cancel       -> idle
```

## 9. Markdown、图片和安全渲染

聊天输出不是普通文本。当前依赖链支持：

- `marked`：Markdown 转 HTML。
- `highlight.js`：代码高亮。
- `KaTeX`：数学公式。
- `Mermaid`：流程图和架构图。
- `DOMPurify`：清理不安全 HTML。
- 自定义稳定 HTML 指令：尽量复用已有图片和图表节点，减少流式渲染闪烁。

关键文件：`src/utils/chatMarkdownRenderer.ts`、`src/utils/markdownDomPurify.ts`、`src/directives/stableHtml.ts`、`src/utils/security.ts`。

实现顺序：

1. 纯文本回答。
2. Markdown 段落和列表。
3. 代码高亮。
4. 图片和链接白名单。
5. 公式和 Mermaid。
6. 流式增量更新的节点复用。

任何服务端或模型输出都不能直接写入 `innerHTML`。图片、文件和引用链接还需要鉴权，不能只依赖前端隐藏 URL。

## 10. 多入口嵌入页

`embed.html` 与主应用完全独立，通过 `src/embed-main.ts` 启动。它只注册嵌入路由和 `EmbedPage`，不依赖主应用的登录态。

嵌入链路通常是：

```text
外部网站
  ↓ iframe / public widget
embed.html
  ↓ channelId
EmbedPage
  ↓ token 或签名交换
useEmbedBridge / useEmbedChatSession
  ↓
SSE 聊天和受保护资源预览
```

只有确实需要第三方嵌入时再实现这一部分；它会增加 Token 交换、跨窗口通信和宿主兼容成本。

## 11. `Vite`、代理和部署

`frontend/vite.config.ts` 的重要内容：

- `index.html` 和 `embed.html` 双入口。
- `@` 指向 `src`。
- `/api`、`/files`、`/mcp` 开发代理到后端。
- `/api` 开启 WebSocket 转发。
- 为 `Mermaid`、Markdown 和代码高亮设置独立 chunk。
- 构建后复制 `pdfjs` 的 WASM 资源。
- 注入前端版本和 Git commit。
- 对嵌入页减少大型依赖的预加载。

开发环境可以使用：

```bash
cd frontend
npm run dev
```

生产验证建议按顺序执行：

```bash
npm run type-check
npm run build
npm run preview
```

部署时由 `Dockerfile` 使用 Node 构建静态资源，再交给 `Nginx` 提供文件和反向代理。`nginx.conf` 还需要正确处理 `history mode` 的前端路由回退。

## 12. 推荐的从 `0` 到 `1` 实现路线

### 阶段 `0`：静态壳

验收：能启动、能切换两个静态页面、能使用 TypeScript。

- 初始化 `Vue 3 + TypeScript + Vite`。
- 配置 `@` 别名和 `Less`。
- 创建 `App.vue`、基础布局和首页。
- 加入 `Vue Router`。

### 阶段 `1`：登录和请求

验收：登录后刷新页面仍保持会话，`401` 能退出或刷新。

- 创建 `Axios` 实例。
- 实现登录、当前用户、退出。
- 用 `Pinia` 保存用户和 Token。
- 实现路由守卫。
- 加入并发 Token 刷新。

### 阶段 `2`：知识库 CRUD

验收：可以创建知识库、查看列表、编辑和删除。

- 建立 `api/knowledge-base`。
- 建立知识库列表和详情页面。
- 用领域 store 缓存列表。
- 写加载、空状态、失败和权限状态。

### 阶段 `3`：文件上传和后台任务

验收：多个文件可以并发上传，切页后任务仍显示，解析完成后列表刷新。

- 实现 `FormData` 上传和进度。
- 加入并发上限。
- 每个任务绑定 `AbortController`。
- 上传结束后轮询后端解析状态。
- 把任务 store 放到布局层或全局浮层。

### 阶段 `4`：知识检索和聊天

验收：用户提问后能看到逐字生成的回答，并能取消。

- 实现聊天会话列表。
- 实现 `SSE` 最小协议。
- 实现 `useStream`。
- 分离消息数据和流式临时状态。
- 加入 Markdown 渲染和引用。

### 阶段 `5`：Agent 和工具调用

验收：回答中能展示思考、工具调用、工具结果和最终答案。

- 定义事件联合类型。
- 建立前端消息时间线。
- 使用 `useChatStreamHandler` 把事件转换成 UI 状态。
- 增加工具审批和用户确认。

### 阶段 `6`：多租户和权限

验收：切换租户后资源、请求头、路由和权限都正确更新。

- 分离默认租户与当前激活租户。
- 所有请求带 `X-Tenant-ID`。
- 切换后清理或失效空间级缓存。
- 路由和按钮同时做前端能力控制，后端仍是最终权限边界。

### 阶段 `7`：生产能力

验收：暗色主题、国际化、错误恢复、生产构建和安全扫描可用。

- 加入 `vue-i18n` 和翻译键审计。
- 加入主题变量和减少动画支持。
- 加入 `DOMPurify` 和受保护资源访问。
- 拆分大型依赖 chunk。
- 加入 Docker/Nginx 部署。
- 补齐浏览器端关键流程测试。

## 13. 推荐学习和阅读顺序

1. `src/main.ts`、`src/App.vue`、`src/router/index.ts`：理解启动和页面进入。
2. `src/utils/request.ts`、`src/utils/authRefresh.ts`、`src/api/auth`：理解网络和登录。
3. `src/stores/auth.ts`、`src/stores/chatResources.ts`、`src/stores/resourceCache.ts`：理解全局状态和缓存。
4. `src/views/platform/index.vue`、`src/views/knowledge/KnowledgeBaseList.vue`：理解页面组合。
5. `src/api/chat/streame.ts`、`src/composables/useChatStreamHandler.ts`：理解流式协议。
6. `src/utils/chatMarkdownRenderer.ts`、`src/directives/stableHtml.ts`：理解安全渲染。
7. `src/stores/uploadQueue.ts`、`src/stores/uploadTasksCore.ts`：理解长任务和异步竞态。
8. `src/embed-main.ts`、`src/composables/useEmbedBridge.ts`：最后学习嵌入式应用。

## 14. 最容易踩坑的地方

| 问题 | 根因 | 正确做法 |
| --- | --- | --- |
| 多次同时刷新 Token | 每个 `401` 都独立刷新 | 单飞刷新 + 等待队列 |
| 旧请求覆盖新数据 | 异步响应返回顺序不确定 | 请求版本或代际校验 |
| 切页后上传消失 | 上传状态只在页面组件里 | 放到 Pinia 全局任务 store |
| SSE 取消后仍修改页面 | 旧回调没有失效 | `generation` + `AbortController` |
| Markdown XSS | 直接使用模型输出 HTML | `DOMPurify` 白名单清理 |
| 大型依赖首屏很慢 | Mermaid、PDF、编辑器全部同步加载 | 路由懒加载和 `manualChunks` |
| 租户数据串空间 | 缓存没有按租户失效 | 租户切换时清理空间级资源 |
| 后端不可用时整页白屏 | 异步启动没有兜底 | 全局错误处理、加载态和错误态 |

## 15. 建议自己实现的最小版本

如果目标是完整理解，而不是马上复刻所有页面，建议先做一个垂直闭环：

```text
登录
  → 知识库列表
  → 上传一个 Markdown 文件
  → 查询解析状态
  → 输入问题
  → SSE 流式回答
  → Markdown 安全渲染
```

这个闭环会覆盖项目最重要的架构：`Vue` 组件、路由守卫、`Pinia`、`Axios`、上传队列、轮询、`SSE`、取消、Markdown 和错误处理。完成后再逐步加入 Agent、模型设置、多租户、国际化和嵌入页。

## 16. 源码核对范围

本分析核对了 `frontend/package.json`、`src/main.ts`、`src/embed-main.ts`、`src/App.vue`、`src/router/index.ts`、`src/utils/request.ts`、`src/utils/authRefresh.ts`、`src/api/chat/streame.ts`、`src/composables/useChatStreamHandler.ts`、主要 Pinia store、`vite.config.ts`、`Dockerfile`、`index.html` 和 `embed.html`，并参考了已有的 `frontend/docs/frontend-knowledge-map.md`。

没有执行全量构建、浏览器验收或真实后端联调；文档中的调用关系和步骤来自源码静态分析。
