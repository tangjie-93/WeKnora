<template>
    <main class="mx-auto max-w-3xl space-y-8 px-5 py-10 sm:px-8">
        <header class="space-y-3">
            <p class="text-sm text-slate-600">WeKnora · Python / Vue 重构 · 首个小需求</p>
            <h1 class="text-2xl font-semibold">检测 Python 后端连接</h1>
            <p>本轮仅验证 HTTP 应用能否响应，不表示数据库、模型或其他业务已接入或健康。</p>
            <p>页面不会自动检测。结果仅保留在本页内存中，刷新后回到待检测。</p>
        </header>
        <HealthPanel />
    </main>
</template>

<script setup lang="ts">
import HealthPanel from './components/HealthPanel.vue';
</script>
