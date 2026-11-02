# WeKnora 前端知识点与可迁移能力梳理

> 基于 `frontend` 当前源码、依赖、构建配置、核心 API、状态管理、路由、组件、嵌入页和测试目录整理。

## 1. 项目画像

| 项目 | 结论 |
| --- | --- |
| 技术栈 | `Vue 3`、`TypeScript`、`Vite`、`Pinia`、`Vue Router`、`Less`、`TDesign Vue Next` |
| 规模 | `src` 约 `232` 个 `.vue`、`489` 个 `.ts`；组件目录约 `148` 个文件；仓库测试文件约 `247` 个 |
| 入口 | `index.html` 主应用；`embed.html` 嵌入式聊天；对应 `src/main.ts`、`src/embed-main.ts` |
| 业务 | 多租户知识库、文档处理、`AI Agent`、流式问答、`Wiki`、组织管理、工具箱和嵌入式聊天 |
| 通信 | 普通请求统一走 `Axios`；聊天和进度使用 `SSE` / `fetch-event-source` |
| 国际化 | `vue-i18n` 支持 `zh-CN`、`zh-TW`、`en-US`、`ru-RU`、`ko-KR`、`ja-JP` |
| 部署 | 浏览器、`Nginx` 反向代理、`Wails` 桌面运行时和第三方嵌入页面 |

## 2. 最值得迁移的知识点

### 2.1 双入口与嵌入式应用

证据：`src/main.ts`、`src/embed-main.ts`、`index.html`、`embed.html`、`vite.config.ts`。

主应用与嵌入式聊天共用能力，但有独立启动流程、鉴权和打包策略。迁移到其他项目时，可以用多个 `Vite` `HTML` 入口同时产出后台和嵌入页：

1. 每个入口使用独立 `main.ts`。
2. 在 `rollupOptions.input` 声明多个入口。
3. 嵌入页单独处理宿主通信、Token 交换和受保护资源。
4. 嵌入页不依赖主应用登录态。

### 2.2 统一请求层

证据：`src/utils/request.ts`、`src/utils/api-base.ts`、`src/api/*`。

请求层集中处理 `Base URL`、`Bearer Token`、`X-Tenant-ID`、`Accept-Language`、`X-Request-ID`、超时、错误和文件场景。业务 API 按 `chat`、`knowledge-base`、`tenant`、`model`、`wiki`、`embed` 等领域拆分。

可迁移最小结构：`request.ts` 负责拦截器；`api/<domain>` 负责业务接口；`api-base.ts` 负责浏览器、桌面和代理路径。

### 2.3 并发 `401` 刷新

证据：`src/utils/authRefresh.ts`、`src/utils/request.ts`、`src/api/chat/streame.ts`。

`refreshAccessTokenShared()` 同时服务 `Axios` 和原生 `SSE`。刷新期间的请求进入队列，刷新成功后一起重试；失败则清理会话并跳转登录。

这是登录型项目通用的基础设施。迁移时必须保留：单飞刷新、旧 Token 不覆盖新 Token、刷新失败清理队列和凭据。

### 2.4 流式聊天状态机

证据：`src/api/chat/streame.ts`、`src/api/chat/streame.test.ts`、`src/api/chat/streameOverlap.test.ts`。

`useStream()` 管理 `output`、`isLoading`、`isStreaming`、`error`、`AbortController` 和请求代际。它处理 `SSE` 解析、取消、新请求覆盖旧请求、增量缓冲、节流渲染、认证重试、附件、工具调用和页面上下文。

适合迁移到 `LLM`、实时日志、长任务进度和生成式编辑器。

### 2.5 上传队列与解析轮询

证据：`src/stores/uploadQueue.ts`、`src/stores/uploadTasks.ts`、`src/stores/uploadTasksCore.ts`。

上传系统具备并发上限、取消、重试、进度、批次、解析轮询和错误分类。关键做法：使用 `AbortController`；通过 `generation` 防止旧异步任务回写；连续多次轮询缺失后才判断删除；注入网络和计时器以便测试；把 `File` 和取消句柄放进非响应式 `Map`。

这套模式可迁移到文件、图片、附件和导入任务。

### 2.6 版本化资源缓存

证据：`src/stores/resourceCache.ts`、`src/stores/versionedRequest.ts`。

缓存区分快照、飞行请求、显式失效和强制刷新，并用版本号防止旧响应覆盖新数据。对模型列表、成员列表、知识库详情、设置和权限能力都适用。

建议迁移 `ensure()`、`invalidate()`、`markLoaded()` 三个核心操作，而不是在页面中复制缓存逻辑。

### 2.7 多租户上下文

证据：`src/stores/auth.ts`、`src/stores/organization.ts`、`src/utils/request.ts`、`src/router/index.ts`。

默认租户、当前激活租户、成员关系和请求头分开维护。切换租户后所有后续请求持续携带当前 `X-Tenant-ID`，并重新协调用户和权限。

迁移时要明确默认租户与激活租户的区别、切换后的缓存失效、跨租户路由和权限刷新。

### 2.8 路由元信息与能力控制

证据：`src/router/index.ts`、`src/config/deploymentCapabilities.ts`、`src/config/settingsAccess.ts`、`src/config/toolbox.ts`。

路由元信息表达登录、初始化、租户和能力要求，守卫集中执行自动登录、初始化、权限、旧路径兼容和桌面恢复。

可迁移形态：

```ts
meta: { requiresAuth: true, requiresInit: true, requiredCapability: 'agents' }
```

### 2.9 国际化治理

证据：`src/i18n/index.ts`、`src/i18n/localeKeyAudit.ts`、`src/i18n/localeGapScan.ts`、`src/i18n/locales/*`。

项目有多语言运行时、默认语言解析、组件库语言同步、翻译键审计和缺口扫描。多语言项目建议早期就接入键审计，避免后期补齐成本过高。

### 2.10 安全 Markdown 与稳定流式渲染

证据：`src/directives/stableHtml.ts`、`src/utils/security.ts`，以及 `DOMPurify`、`marked`、`highlight.js`、`katex`、`mermaid` 依赖。

项目支持 Markdown、代码高亮、数学公式、`Mermaid` 和受保护图片，并使用自定义 `DOM morph` 尽量复用已经绘制的图片和图表节点，避免流式刷新闪烁。

迁移时必须同时考虑 `DOMPurify` 白名单、受保护资源鉴权、图表降级、图片节点复用和避免粗暴替换整棵 `innerHTML`。

## 3. 项目亮点

1. **领域拆分清晰**：`src/api`、`src/stores`、`src/views`、`src/composables`、`src/config`、`src/types`、`src/utils` 边界明确，适合按业务域抽取。
2. **长任务体验完整**：文档上传覆盖进度、取消、重试、解析轮询、失败状态和刷新后的状态恢复。
3. **多运行时兼容**：同时考虑浏览器、`Nginx`、`Wails` 桌面端和第三方嵌入。
4. **生产拆包有针对性**：`vite.config.ts` 将 `Mermaid`、`marked`、`KaTeX`、`highlight.js` 等拆分，并减少 `embed` 首屏预加载。
5. **基础设施测试充分**：测试覆盖请求缓存、Token 刷新、上传队列、流式请求重叠、路由、权限、国际化、稳定 HTML 和浏览器连接。
6. **嵌入式聊天链路完整**：`useEmbedBridge`、`views/embed` 和 `public/weknora-widget.js` 形成配置加载、Token 交换、会话创建和聊天展示闭环。
7. **主题层可复用**：`src/assets/theme` 与 `useTheme` 提供品牌色、暗色模式、字体、圆角、阴影和组件状态覆盖。

## 4. 迁移优先级

| 优先级 | 内容 | 适用原因 |
| --- | --- | --- |
| `P0` | `request.ts` + `authRefresh.ts` | 所有登录型应用都能受益 |
| `P0` | `useStream()` | `AI` 和实时生成核心能力 |
| `P0` | `resourceCache` / `versionedRequest` | 解决并发和旧响应覆盖 |
| `P1` | `uploadQueue` | 文档、图片和长任务通用 |
| `P1` | 路由能力模型 | 多角色、多租户和可选模块通用 |
| `P1` | `vue-i18n` 审计 | 多语言项目越早接入越省成本 |
| `P1` | `stableHtml` + Markdown 安全链 | 聊天和知识库场景有价值 |
| `P2` | 双入口 `embed` | 需要第三方嵌入时迁移 |
| `P2` | `Wails` 兼容层 | 需要桌面端时迁移 |

## 5. 不建议整包复制的内容

- 整个 `src/views`：产品业务耦合较高，应按模块选取。
- 整个 `theme.css`：包含大量 `TDesign` 专属变量，应先抽取品牌和通用状态。
- 所有 `Wails` 运行时代码：浏览器项目不需要。
- 全部知识库接口：非知识库项目只迁移请求层和领域拆分方式。
- 旧路径兼容和特定代理逻辑：目标项目没有相同历史包袱时不要复制。
- `weknora-widget.js`：应先确认目标项目的宿主通信和 Token 协议。

## 6. 推荐最小迁移包

1. `src/utils/request.ts`：请求实例、语言头、追踪头、错误归一化和超时。
2. `src/utils/authRefresh.ts`：并发刷新队列和失败清理。
3. `src/stores/resourceCache.ts`、`src/stores/versionedRequest.ts`：版本化缓存。
4. `src/api/chat/streame.ts`：抽取通用流式传输骨架。
5. `src/stores/uploadQueue.ts`：按目标业务删除知识库字段。
6. `src/router/index.ts`：只迁移路由元信息和守卫模式。
7. `src/i18n`：初始化、语言选择和翻译键审计。
8. `src/assets/theme`：变量层和组件覆盖层。

## 7. 推荐学习顺序

1. 运行骨架：`src/main.ts`、`src/App.vue`、`src/router/index.ts`、`vite.config.ts`。
2. 数据流：`src/utils/request.ts`、`src/api/auth`、`src/stores/auth.ts`、`src/stores/organization.ts`。
3. 高难交互：`src/api/chat/streame.ts`、`src/stores/uploadQueue.ts`、`src/stores/resourceCache.ts`、`src/directives/stableHtml.ts`。
4. 可扩展性：`src/i18n`、`src/config`、`src/views/embed`、`src/wailsjs` 和 `vite.config.ts`。

## 8. 当前项目的改进建议

- 新项目可按 `modules/<domain>` 进一步收拢 API、状态、页面和类型。
- 可把 `App.vue` 中的全局初始化拆成 `bootstrap`、`oidc` 和全局通知模块。
- 迁移 `stableHtml` 前应使用目标项目内容做安全和性能回归。
- 兼容历史路径和多运行时逻辑可以做成独立插件，减少主入口复杂度。

## 9. 快速索引

| 主题 | 文件 |
| --- | --- |
| 启动 | `src/main.ts` |
| 路由与权限 | `src/router/index.ts` |
| 请求封装 | `src/utils/request.ts` |
| Token 刷新 | `src/utils/authRefresh.ts` |
| 流式问答 | `src/api/chat/streame.ts` |
| 上传队列 | `src/stores/uploadQueue.ts` |
| 资源缓存 | `src/stores/resourceCache.ts`、`src/stores/versionedRequest.ts` |
| 多租户 | `src/stores/auth.ts`、`src/stores/organization.ts` |
| 国际化 | `src/i18n/index.ts`、`src/i18n/localeKeyAudit.ts` |
| 富文本安全 | `src/directives/stableHtml.ts`、`src/utils/security.ts` |
| 嵌入式聊天 | `src/views/embed/`、`src/composables/useEmbedBridge.ts` |
| 构建拆包 | `vite.config.ts` |
| 主题 | `src/assets/theme/`、`src/composables/useTheme.ts` |

## 10. 核验说明

本文是源码静态梳理文档，已核对目录、依赖、入口、请求层、流式传输、上传队列、缓存、路由、国际化、嵌入页和构建配置。未执行全量生产构建、全量测试和真实后端验收；文档中的亮点表示源码中已有实现或工程模式，不代表每个页面质量完全一致。
