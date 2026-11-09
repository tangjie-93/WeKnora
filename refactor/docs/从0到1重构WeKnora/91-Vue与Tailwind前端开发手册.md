# 前端动手指南：用 `Vue 3` 与 `Tailwind CSS` 逐步复刻 `WeKnora`

[返回目录](./00-目录.md) · [详细实施步骤](./00-目录.md) · [进度记录](./13-进度与验收记录.md)

前端就是用户实际看见并操作的部分。这里从一个能显示的页面开始，逐步加入登录、知识库、上传和聊天，最后对齐原版所有页面与交互。你不需要一开始就读懂原版全部组件。

先读[总路线](01-总路线与学习方法.md)确定当前阶段；后端步骤见[后端指南](90-Python后端开发手册.md)；陌生词语和完整功能清单见[学习词典与功能地图](92-知识词典与原版功能地图.md)。本目录所有章节统一使用 `S0–S10`。

源码路径从仓库根目录 `WeKnora/` 计算。新代码放在 `refactor/python/frontend/`；本文核验时它尚不存在。下文标注的文件和命令是你接下来要创建和执行的内容。

## 1. 先理解页面由什么组成

以知识库列表为例：`Vue` 把“标题、创建按钮、知识库卡片”组织成组件；`TypeScript` 说明一条知识库数据有哪些字段；`API` 把数据从后端取回来；样式决定它们的位置和颜色。

| 工具 | 在本项目里做什么 | 第一次需要它的阶段 |
| --- | --- | --- |
| `Vue 3` | 将数据渲染为页面，响应点击与输入 | `S1` |
| `TypeScript` | 提前发现字段和函数使用错误 | `S1` |
| `Vite` | 启动开发页面、代理请求、打包 | `S1` |
| `TDesign Vue Next` | 提供原版正在使用的按钮、表单、表格、弹窗 | `S1` |
| `Tailwind CSS ^4.3.3` | 用工具类写布局、尺寸、间距和响应式样式 | `S1` |
| `Vue Router` | 根据地址展示页面，控制进入条件 | `S3` |
| `Pinia` | 保存登录、租户、上传等跨页面共享状态 | `S3` |
| `Axios` | 统一普通请求、鉴权和错误处理 | `S3` |
| `fetch-event-source` | 接收聊天中持续到来的消息 | `S8` |
| 富文本与预览库 | 显示代码、公式、图表和不同格式的文档 | `S6–S9` |

原版前端是浏览器应用，也包含嵌入页和桌面运行时分支，不是 `uni-app`。这里不套用小程序页面和生命周期规则。

## 2. `S0`：把“样式一样”记录下来

先看原版 `frontend/src/views/platform/index.vue` 与 `frontend/src/views/knowledge/KnowledgeBaseList.vue`，再在原版浏览器中操作。记录侧栏、内容区域、卡片、按钮、弹窗各自的位置；到开发者工具的计算样式中查实际颜色、字体和间距。

不要凭印象把所有间距换成 `p-4`，也不要把绿色统一写成 `green-500`。复刻时以原版计算结果为准；不在默认刻度里的值可使用 `px-[18px]` 这样的精确值，反复使用的值再归入主题变量。

先保存这些参照：

| 参照 | 原版来源 | 后续如何使用 |
| --- | --- | --- |
| 组件与版本 | `frontend/package.json`、`frontend/package-lock.json` | 对齐 `TDesign` 和图标版本，减少默认外观差异 |
| 品牌色、背景、字体、圆角、阴影 | `frontend/src/assets/theme/theme.css` | 直接复用变量，避免重建另一套主题 |
| 组件特殊外观 | `frontend/src/assets/theme/tdesign-overrides.less` | 保留原版覆盖规则 |
| 图标、图片 | `frontend/src/assets/`、`frontend/public/` | 按引用复制素材及关联文件，保留许可 |
| 主题和字体行为 | `frontend/src/composables/useTheme.ts`、`useFont.ts` | 后续对齐主题切换、偏好与首屏初始化 |
| 页面及弹窗 | `frontend/src/views/`、`frontend/src/components/` | 逐页确认内容、状态和交互 |

至少记录亮色、暗色、正常内容、空内容、加载、失败、无权限和弹窗状态。选择固定浏览器、视口、缩放、字体和测试数据，例如桌面 `1440 × 900`，并另选原版支持的窄屏尺寸。示例尺寸是测试条件，不是让原版适应新的设计。

**过关：** 你能指出一个页面的颜色和尺寸来自哪里，并有对应截图；没有启动原版时，这一项保持待验收。

## 3. `S1`：创建一个能启动的工程

### 3.1 安装工具并确认目录

准备 `Node.js`、`npm` 和编辑器。下面使用 `create-vite@7` 创建模板；其声明支持 `Node.js ^20.19.0 || >=22.12.0`。初次安装选满足条件且仍受维护的版本，执行 `node -v` 确认。

从 `refactor/` 执行，**仅在 `python/frontend/` 不存在时运行创建命令**；若已存在，继续已有工程，不覆盖它：

```bash
mkdir -p python
cd python
npm create vite@7 frontend -- --template vue-ts
cd frontend
npm install
npm install 'tdesign-vue-next@^1.19.2' 'tdesign-icons-vue-next@0.4.4'
npm install -D 'tailwindcss@^4.3.3' '@tailwindcss/vite@^4.3.3' less
```

`TDesign` 范围对应本次阅读的原版清单；做正式截图基线时，以 `S0` 记录的原版锁文件解析版本安装，避免范围内的新版本改变外观。新项目生成的 `package-lock.json` 要保留，之后使用 `npm ci` 复现依赖。

`^4.3.3` 表示允许安装不低于 `4.3.3` 且低于 `5.0.0` 的兼容版本，不等于永远安装 `4.3.3`。核验日 `2026-11-09`，`npm` 可查询到 `tailwindcss@4.3.3` 和 `@tailwindcss/vite@4.3.3`；插件声明兼容 `Vite ^5.2.0 || ^6 || ^7 || ^8`。

动手时可以再次核对：

```bash
npm view tailwindcss@4.3.3 version
npm view @tailwindcss/vite@4.3.3 peerDependencies
npm ls tailwindcss @tailwindcss/vite vite
```

若安装报 `EACCES` 并指向 `~/.npm`，先改用当前用户可写的临时缓存，例如 `npm --cache /tmp/weknora-npm-cache install`；创建工程等其他 `npm` 命令也可添加同样的 `--cache` 参数。本次临时验证遇到过此问题，不需要为此使用 `sudo npm install` 或修改项目权限。

这里是新工程。不要整段复制原版 `package.json`：其中有 `lightningcss: "none"` 覆盖规则，而新的 `Tailwind` 构建链会用到相关工具。按当前阶段添加依赖，其他原版依赖随功能引入。

### 3.2 接上 `Tailwind` 与开发代理

替换新工程的 `vite.config.ts`：

```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    port: 5400,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8080', changeOrigin: true },
    },
  },
})
```

代理的意思是：浏览器请求前端同一地址下的 `/api`，开发服务器转发到后端。业务代码不用写死后端地址。后续文件预览补 `/files`，工具与沙箱阶段补 `/mcp/`、`WebSocket` 及长连接配置，参考原版 `frontend/vite.config.ts`。

这是 `Tailwind v4` 的 `Vite` 插件用法，不需要套用旧教程中的 `npx tailwindcss init -p`，也不需要为了这个最小工程创建 `tailwind.config.js`。依据见 [Tailwind 官方 Vite 安装指南](https://tailwindcss.com/docs/installation/using-vite)。

### 3.3 复制原版主题，再建立很薄的工具类入口

仍在新工程 `refactor/python/frontend/` 下执行；目标是刚创建的工程，没有自定义主题时才直接复制：

```bash
mkdir -p src/assets/theme
cp ../../../frontend/src/assets/theme/theme.css src/assets/theme/theme.css
cp ../../../frontend/src/assets/theme/tdesign-overrides.less src/assets/theme/tdesign-overrides.less
```

这是复用已有设计，不要求你重新手写这些样式。以后修改主题前先对照原版，别让副本各自演化。其他图片和字体按具体页面引用补齐。

创建 `src/assets/tailwind.css`：

```css
@layer theme, base, components, utilities;
@import "tailwindcss/theme.css" layer(theme);
@import "tailwindcss/utilities.css" layer(utilities);

@theme inline {
  --color-brand: var(--td-brand-color);
  --color-page: var(--td-bg-color-page);
  --color-surface: var(--td-bg-color-container);
  --color-content: var(--td-text-color-primary);
  --color-muted: var(--td-text-color-secondary);
  --color-line: var(--td-component-border);
  --radius-panel: var(--td-radius-extraLarge);
  --font-sans: var(--app-font-family);
}

@custom-variant dark (&:where([theme-mode="dark"], [theme-mode="dark"] *));

body {
  margin: 0;
}
```

这里做了三件事：只引入主题与工具类；把原版变量接到 `bg-surface`、`text-content` 等类名上；让暗色条件识别原版的 `theme-mode="dark"`。

没有引入 `preflight.css`，因为它会重置标题、边框等默认样式，容易改变现有组件和富文本。需要的基础规则按原版逐项保留，而不是同时引入两套全局重置。拆分导入方式见 [Preflight 官方说明](https://tailwindcss.com/docs/preflight)。变量映射方式见 [Theme 官方说明](https://tailwindcss.com/docs/theme)。

`Tailwind` 入口保持普通 `.css`。原版 `.less` 覆盖文件单独由 `Less` 编译；不要把 `@theme` 放进 `.less`。工具链和浏览器支持限制见 [Tailwind 兼容说明](https://tailwindcss.com/docs/compatibility)。

替换新工程的 `src/main.ts`：

```ts
import { createApp } from 'vue'
import TDesign from 'tdesign-vue-next'
import App from './App.vue'
import 'tdesign-vue-next/dist/tdesign.css'
import './assets/theme/theme.css'
import './assets/theme/tdesign-overrides.less'
import './assets/tailwind.css'

createApp(App).use(TDesign).mount('#app')
```

删除模板中原有的 `import './style.css'`，避免模板的居中、背景和按钮样式混入原版。原模板的演示组件不再引用即可。

### 3.4 用一个小页面验证安装

替换 `src/App.vue`。这只是工具安装练习，不是原版知识库页面的最终布局：

```vue
<template>
    <main class="min-h-screen bg-page p-6 font-sans text-content">
        <section class="mx-auto max-w-3xl rounded-panel bg-surface p-6">
            <h1 class="m-0 text-xl font-semibold">WeKnora 学习工程</h1>
            <p class="my-4 text-muted">下一步接入健康检查，再逐页复刻原版。</p>
            <a class="text-brand underline" href="/health" target="_blank" rel="noopener">
                查看后端健康状态
            </a>
        </section>
    </main>
</template>
```

另开终端，按后端指南启动 `8080` 服务；当前前端终端执行：

```bash
npm run dev
```

打开 `http://localhost:5400`。页面有主题颜色，点击链接能看见后端健康响应。随后再做一个小练习：在页面内使用 `fetch('/health')` 显示“检查中／正常／失败”，检查 `response.ok`，捕获网络异常，并提供重试按钮。这个练习完成后才算前后端联通，不要把静态文字当作服务状态。

**过关：** 页面正常；健康请求能到达后端；关闭后端后出现失败反馈；`npm run build` 通过。初始化模板的构建脚本应包含 `vue-tsc` 类型检查，先检查自己的 `package.json`，不能照搬原版仅运行 `vite build` 的同名脚本。

## 4. 怎样少写样式，还能保持原版外观

### 4.1 分工保持简单

| 需求 | 推荐实现 | 原因 |
| --- | --- | --- |
| 行列布局、间距、溢出 | `flex`、`grid`、`gap-*`、`overflow-*` | 不需要再定义一个局部样式类 |
| 品牌色、背景和文字 | `bg-surface`、`text-content`、`text-brand` | 值来自原版变量，主题切换自动继承 |
| 按钮、表单、菜单、弹窗 | 原版 `TDesign` 组件与参数 | 保留尺寸、键盘行为和状态 |
| 一处特殊尺寸 | `w-[具体值]` 等完整工具类 | 可以准确匹配，不强行凑刻度 |
| 多处相同的业务结构 | 提取真实业务组件 | 避免复制长模板，不为每组类名创建包装组件 |
| 富文本、复杂动画、第三方内部样式 | 复用少量专用 `CSS/Less` | 保留复杂表现，避免堆叠工具类补丁 |

工具类适合页面外层盒子。组件内部优先使用 `TDesign` 的属性和主题变量，不依赖随版本变化的内部节点做大面积覆盖。

### 4.2 避免三个常见误区

第一，颜色相同不代表样式相同。字号、行高、字重、圆角、阴影、边框、鼠标经过、选中和禁用状态都要比对。

第二，不要动态拼接半个类名，例如 `bg-${color}-500`。把可能值写成完整字符串，让构建器能扫描到；真正来自接口的任意尺寸可以使用受约束的样式变量，不把接口数据直接当作类名。

第三，最后导入不代表一定优先。普通未分层的原版样式可能覆盖 `@layer utilities` 内规则；不要全局加 `!important`。先在开发者工具定位冲突，再将布局类放到自己的外层容器，或通过原版主题变量调整。只有必要时才做局部覆盖，并复测弹窗和富文本。

## 5. `S2–S3`：接数据之前先接身份

`S2` 主要在后端完成数据库。前端不直接连接数据库，也不能把浏览器存储当数据库。你可以继续维护健康状态页，同时记录原版登录接口与数据类型。

进入 `S3` 再安装：

```bash
npm install vue-router pinia axios
```

按需建立这些目录，不用一次填满：

```text
src/
  main.ts                    注册组件库、Pinia、路由和主题
  App.vue                    放 RouterView 和真正全局的浮层
  router/index.ts            路由及进入条件
  api/auth/index.ts          登录等业务请求
  utils/request.ts           通用请求、身份、租户与错误
  stores/auth.ts             当前用户和工作空间
  types/                     可复用的请求、响应与业务类型
  views/auth/LoginPage.vue   登录与注册交互
  views/platform/            侧栏和内容区域
  assets/                    原版素材、主题及 Tailwind 入口
```

原版使用 `views/`，新工程沿用它。新增组件使用 `PascalCase.vue`；业务可复用类型集中在 `src/types/`。这是普通 `Vue` 工程，不需要额外引入另一套模块框架。

### 5.1 一次登录经过哪些文件

```text
用户填写表单
  → LoginPage 校验输入、显示提交中
  → api/auth 发起登录请求
  → utils/request 发送并统一处理错误
  → 后端验证后返回原版契约中的用户和令牌
  → stores/auth 保存当前会话
  → router 进入原版对应的工作空间或平台页
```

先按 `frontend/src/api/auth/` 与后端路由记录字段，别猜用户名字段叫 `name` 还是 `username`。请求前缀只能加一次：选择原版方式在接口函数里保留 `/api/v1`，就不要在客户端再次叠加同样前缀。

### 5.2 动手顺序与验收

1. 静态复刻原版登录表单，保留注册入口、校验、提交中和错误反馈。
2. 建立统一客户端，集中处理身份令牌、`X-Tenant-ID`、语言、请求标识和错误；令牌的保存及失效策略对齐原版。
3. 注册 `Pinia` 后再使用状态，注册路由，令 `App.vue` 渲染 `RouterView`。
4. 加入进入受保护页面的检查；恢复会话时显示明确加载和失败状态。
5. 实现并发刷新：同一批 `401` 等待一次刷新，成功后有限重试，失败后统一退出。普通请求与流式请求共用刷新逻辑。
6. 切换租户时终止旧请求、清理空间缓存，再加载新数据；后端仍独立校验权限。

参考 `frontend/src/utils/authRefresh.ts`、`frontend/src/stores/auth.ts` 和 `frontend/src/router/index.ts`。先读一次调用链，再逐步实现，别把整份原版启动逻辑搬过来却不知道副作用来源。

**过关：** 登录、刷新页面、退出、错误密码、过期令牌、直接访问受保护地址均有明确结果；切换空间不出现上一个空间的数据。用两个测试身份验证，不能只检查管理员。

## 6. `S4–S5`：完成模型和知识库页面

### 6.1 模型配置：先让调用结果可重复

模型页面依赖后端 `S4`，但静态布局可以先按原版做。依次完成模型列表、创建/编辑、类型选择、连接测试和默认设置。固定回答的假模型用于开发；真实模型连通性单独验收。

原版设置常驻全局弹窗，`/platform/settings` 通过路由协调打开，并非另一个重复的设置页。参考 `frontend/src/components/settings/` 与路由，不要实现成两套界面。

**过关：** 切换设置区域保持原版导航；列表不暴露完整密钥；连接失败能说明原因；刷新后配置仍在。

### 6.2 知识库：从一张卡片到完整操作

从原版 `KnowledgeBaseList.vue` 找到卡片和创建弹窗。先用固定数据复刻卡片，再把固定数组换成 `api/knowledge-base` 返回的数据。最后加入分页、创建、修改、删除及原版类型与设置。

页面应覆盖：加载、空列表、有内容、请求失败、无权限、删除确认和提交中。弹窗开关通常留在页面里；跨页面共享的知识库资源才进入 `Pinia`。

写操作成功后使相关列表缓存失效。如果旧请求随后返回，不能覆盖新记录；到这里再阅读 `resourceCache.ts`、`versionedRequest.ts`，用“先查询，后删除，旧查询最后返回”验证竞态保护。

**过关：** 创建后列表出现记录，刷新仍在；删除失败不会假装成功；另一个租户无法读取；卡片、弹窗和状态截图都对齐。至此你已经掌握大部分管理页面的基本做法。

## 7. `S6`：上传进度和解析进度是两件事

上传进度表示文件传送了多少，解析状态表示后端处理到哪一步。两个进度混在一起，会让用户看到“完成”后却无法提问。

按顺序实现：单文件选择 → `FormData` 上传 → 上传进度 → 后端文档状态 → 解析完成后刷新列表。不要手工设置带文件请求的 `multipart/form-data` 边界，让浏览器生成。

再加入多文件并发、取消、重试和切页保留。任务状态放在全局上传状态中，参考 `frontend/src/stores/uploadQueue.ts`、`uploadTasks.ts`、`uploadTasksCore.ts`。页面卸载清理自己的监听，不能顺手取消用户明确希望后台继续的上传。

原版 `parse_status` 包含 `pending`、`processing`、`finalizing`、`completed`、`failed`、`deleting`、`cancelled`。按源码解释显示文案，不另造一套对外状态。遇到失败展示可理解的原因；删除和重试要防止旧轮询把状态写回来。

预览从文本开始，按原版补齐 `PDF`、文档、表格、幻灯片和图片等支持范围。下载与图片请求也需要鉴权。格式库、字体、工作线程或 `WASM` 资源随对应预览引入，并测试生产构建后的路径。

**过关：** 上传后可离开再回来；重启页面能恢复后端任务状态；失败可重试；取消和删除后旧任务不再更新页面；预览和下载没有越权。

## 8. `S7–S8`：先找到依据，再显示回答

### 8.1 检索入口要跟原版一致

先用固定文档做检索练习：输入一个词，展示命中的段落、文档和位置。接通后端后核对范围、排序、数量和无结果提示。原版全局知识检索由命令面板承接，历史 `/platform/knowledge-search` 路径会重定向；最终入口和键盘交互要对齐这个行为。

检索练习页可以在开发中临时使用，但不能把它当成原版最终页面。

### 8.2 一轮聊天分三段实现

第一段是会话和历史：创建会话、发送用户消息、刷新后读取历史。第二段是流式答案：让回答逐步出现。第三段是引用、停止、错误恢复和完整消息操作。

参考 `frontend/src/api/chat/index.ts`。原版普通知识库问答使用 `/api/v1/knowledge-chat/:session_id`，智能体问答使用 `/api/v1/agent-chat/:session_id`；不能把示意的 `/api/v1/chat` 当作真实接口。

原版 `SSE` 是持续接收的文本事件流。外层事件名为 `message`，其 `data` 中的 `JSON` 使用 `response_type` 区分答案、引用和完成等业务消息。完整字段与结束规则以 `internal/types/chat.go`、`internal/handler/session/stream.go` 和 `frontend/src/api/chat/streame.ts` 为准。

不要把网络收到的一块字节当作一条完整事件。使用原版采用的解析库，按完整事件解析，再按业务类型分发；不要直接套用另一种模型厂商的流协议。

### 8.3 让状态变化清楚可控

```text
待输入 → 正在连接 → 正在接收 → 已完成
                   ├→ 已停止
                   └→ 失败或连接中断
```

这些是前端显示状态，不是用来替换后端协议。还要处理：

- 新一轮开始后，旧回调不能改写新消息；用请求代际标记或等效机制隔离。
- 用户停止时既取消前端连接，也按原版停止接口终止后端生成；只断浏览器连接不能保证后端停下。
- 断流保留已收到的内容并显示状态；不要盲目重发生成请求，导致重复消息与重复计费。
- 退出页面时清理属于页面的监听和请求；恢复历史以持久化消息为准。
- 刷新令牌、心跳、继续流、工具事件与最终状态按原版协议逐项补齐。

`frontend/src/api/chat/streame.ts` 负责传输，`frontend/src/composables/useChatStreamHandler.ts` 将业务事件转为页面状态。先学会普通回答，再扩展工具调用，不把全部逻辑塞进聊天页面。

### 8.4 富文本也需要原样复刻

先显示纯文本，再加入 `Markdown`、代码、公式、图表和受保护图片。富文本输出视为不可信数据：保留 `DOMPurify` 清理、链接和图片策略，不把模型输出直接交给 `v-html`。

参考 `chatMarkdownRenderer.ts`、`markdownDomPurify.ts`、`security.ts` 和 `directives/stableHtml.ts`。边接收边替换整棵内容会使图片和图表闪烁；最后补齐原版稳定节点更新和渲染节流。

富文本样式不必改成 `Tailwind`；既有排版、代码高亮和图表规则可以按原版复用。

**过关：** 回答、引用、代码和图表正确；停止后不再更新；断网后保留内容和错误；刷新可恢复历史；危险链接被处理；慢速长回答时页面仍能滚动操作。

## 9. `S9`：按功能地图复刻剩余页面

此时可以独立做出文档问答，但仍有大量原版功能。按总路线 `S9` 的顺序逐组实现；每组先看原版用户操作，再配合后端完成真实行为。

| 功能组 | 前端重点 | 必须验证 |
| --- | --- | --- |
| 知识管理全量 | 标签、文件夹、`FAQ`、`Wiki`、图谱、版本 | 批量操作范围、编辑冲突、刷新与来源 |
| 来源与预览 | 数据源同步、各格式预览、重新解析 | 失败提示、鉴权、生产资源路径 |
| 聊天与产物 | 编辑、重试、分支、回退、附件、语音和产物库 | 历史一致性、下载权限、状态恢复 |
| `Agent`、技能和记忆 | 配置、执行时间线、工具卡片 | 调用中、失败、审批、暂停和继续 |
| 工具箱与 `MCP` | 服务配置、凭据、环境、浏览器和沙箱 | 不泄露密钥、拒绝审批、取消清理 |
| 自动化与渠道 | 触发配置、执行历史、消息渠道 | 重复执行、连接失败、权限 |
| 组织与系统管理 | 邀请、共享、角色、用户、存储和运行队列 | 不同角色、切租户缓存、过期邀请 |
| 嵌入与其他入口 | 独立入口、宿主通信、渠道主题 | 凭据隔离、来源校验、嵌入下完整聊天 |
| 跨页面体验 | 多语言、主题、字体、命令面板和快捷键 | 原版所有语言、键盘可达、窄屏和暗色 |

原版 `embed.html` 有独立入口，参考 `src/embed-main.ts`、`views/embed/`、`useEmbedBridge.ts` 和 `public/weknora-widget.js`。嵌入页使用自己的鉴权交换，不能依赖主应用已经登录。宿主消息校验来源，不能在地址或示例代码内放长期密钥。

桌面壳、外部消息渠道和其他客户端使用真实运行环境另行验收。只在浏览器里隐藏掉相关按钮，不能算完整复刻。

## 10. `S10`：把验收做成可以重复的步骤

### 10.1 功能与视觉一起验

每个页面采用同一套步骤：

1. 原版与新项目使用相同测试数据、权限、主题、语言、视口和字体；等待加载完成。
2. 依次打开正常、空、错误、加载和弹窗状态，保存两边截图。
3. 比较布局、文字、图标、边框、阴影和焦点状态；只屏蔽确实动态的时间或模型文本，不能屏蔽整块有差异的区域。
4. 逐个点击并检查请求、提示和刷新后数据，再测试键盘、滚动和窄屏。
5. 记录差异、修复和复验结果；不能因截图像原版，就跳过行为检查。

到 `S3` 开始建立 `Vitest` 的请求/状态测试，到 `S5` 建立 `Playwright` 主流程；后续随风险补上传取消、跨租户、旧请求回写和流式中断。先添加依赖、配置和 `test` / `test:e2e` 脚本，再执行对应命令，当前仓库没有这套新工程现成测试。

自动截图比较需要先固定环境并审核基线。字体渲染差异可能产生少量噪点，阈值依据实际环境约定；不能用很高的容差掩盖布局问题。

### 10.2 生产构建也要打开看

```bash
npm ci
npm run build
npm run preview
```

`preview` 只帮助检查产物，不是正式生产服务器，也不代表已经配置全部后端代理。按实际端口访问，在预览或部署配置里补齐与开发一致的接口目标后再跑功能验收。

正式部署用静态服务器提供页面，处理路由刷新回退、`/api`、`/files` 和 `/mcp/` 代理。验证流式响应不被缓冲、长连接超时合理、`WebSocket` 能升级、嵌入地址返回正确入口，参考原版 `frontend/nginx.conf` 和 `vite.config.ts`。

## 11. 出问题时先看哪里

| 现象 | 先检查 |
| --- | --- |
| 工具类没有效果 | 插件是否注册、入口是否导入、类名是否完整、是否有原版规则覆盖 |
| 页面突然居中或按钮变样 | 模板 `style.css` 是否仍导入、是否误开 `Preflight` |
| 亮色正常但暗色不对 | 根节点是否设置 `theme-mode`，是否使用原版变量，弹窗挂载位置 |
| 请求出现两个 `/api/v1` | 客户端与业务函数是否都加了前缀 |
| 切租户看到旧数据 | 缓存是否隔离，旧请求是否仍能回写 |
| 上传结束仍不能提问 | 解析是否完成，是否只展示了上传状态 |
| 回答不显示或一直加载 | 实际路径、`response_type`、鉴权、终止事件及断流处理 |
| 生产预览缺图或文档打不开 | 资源路径、鉴权、工作线程与 `WASM` 是否进入产物 |

## 12. 本文的核验边界

本次整理静态核对了原版依赖、入口、主题、路由、请求、流式协议和相关功能源码，并查询 `Tailwind` 官方资料与指定包版本。文中方案保留 `TDesign`，用 `Tailwind` 减少新增布局样式；它不承诺零手写样式，也不自动证明视觉一致。

本次另将 `S1` 的配置、主题入口和页面示例提取到临时工程，以 `tailwindcss@4.3.3`、`@tailwindcss/vite@4.3.3` 和 `Vite 7` 实际安装并完成生产打包，确认主题工具类生成。此检查不是完整工程的类型检查或浏览器视觉验收。最小示例全量注册 `TDesign`，构建有大包提示；后续随页面拆分和按需加载优化，不能把这个教学产物直接当作生产性能验收结果。

新工程的完整功能、原版逐页视觉对比和生产部署，需要你按各阶段完成并保存证据。下一步回到[总路线](01-总路线与学习方法.md)，只推进自己当前所在的阶段。
