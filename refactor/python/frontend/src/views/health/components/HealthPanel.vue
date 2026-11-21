<template>
    <section class="health-panel space-y-6" aria-label="健康检查">
        <p>请求：<code>GET /health</code>（同源开发代理，最长等待 5 秒，无自动重试）。</p>
        <button class="rounded border border-slate-700 px-4 py-2 font-medium" type="button" :disabled="state === 'checking'" @click="onCheckClick">
            {{ state === 'checking' ? '正在检测…' : '检测后端连接' }}
        </button>
        <div class="space-y-2" role="status" aria-live="polite" aria-atomic="true" :aria-busy="state === 'checking'">
            <p>状态：{{ stateLabels[state] }}</p>
            <template v-if="state === 'success' && result">
                <p>HTTP：{{ result.httpStatus }}；Python 标记：<code>{{ result.implementation }}</code></p>
                <p>响应 JSON：<code>{{ JSON.stringify({ status: result.status }) }}</code></p>
                <p>此标记仅用于诊断误连，不是鉴权或可信身份证明。</p>
            </template>
            <p v-if="state === 'failure' && error">失败分类：<code>{{ error.kind }}</code>。{{ error.message }}</p>
            <p v-if="checkedAt">最近检测终态时间（浏览器本地）：<time :datetime="new Date(checkedAt).toISOString()">{{ new Date(checkedAt).toLocaleString() }}</time></p>
        </div>
        <p>这是请求状态，非后端逐方法追踪。未接入数据库、模型、登录、上传或问答。</p>
        <details>
            <summary class="cursor-pointer font-medium">查看源码方法与请求原理</summary>
            <ol class="mt-3 list-decimal space-y-3 pl-6">
                <li><code>python/frontend/src/views/health/components/HealthPanel.vue · onCheckClick()</code>：按钮调用检测方法，不自行生成结果。</li>
                <li><code>python/frontend/src/views/health/hooks/useHealthCheck.ts · useHealthCheck() / check()</code>：手动触发 vue-query；请求中禁止重复调用，卸载时取消请求。</li>
                <li><code>python/frontend/src/api/health.ts · fetchHealth(signal)</code>：真实请求相对地址，检查 HTTP、JSON 与 Python 标记；分类错误并清理超时资源。</li>
                <li><code>python/frontend/vite.config.ts · server.proxy</code>：开发服务器将健康请求转发给配置的 Python 地址，这是配置而非业务方法。</li>
                <li><code>python/backend/app/main.py · create_app() / health()</code>：注册健康路由，返回 <code>{"status":"ok"}</code> 和 Python 响应标记，不检查外部依赖。</li>
                <li><code>HealthPanel.vue · template</code>：根据 query 的真实状态显示结果；新请求或失败时隐藏旧成功。此列表只是静态源码说明，不表示各方法已执行成功。</li>
            </ol>
        </details>
    </section>
</template>

<script setup lang="ts">
import { useHealthCheck } from '../hooks/useHealthCheck';

const { state, result, error, checkedAt, check } = useHealthCheck();
const stateLabels = {
    idle: '待检测',
    checking: '请求中',
    success: '连接成功（仅 HTTP 存活）',
    failure: '检测失败',
};

/**
 * 将真实按钮操作交给手动查询；成功或失败由 query 状态展示，资源由请求层和作用域清理。
 * @returns 检测完成后结束，不生成模拟进度或追踪事件。
 */
async function onCheckClick(): Promise<void> {
    await check();
}
</script>

<style scoped>
.health-panel {
    & button {
        &:disabled {
            cursor: wait;
            opacity: 0.65;
        }
    }

    & :is(button, summary):focus-visible {
        outline: 2px solid currentColor;
        outline-offset: 4px;
    }
}
</style>
