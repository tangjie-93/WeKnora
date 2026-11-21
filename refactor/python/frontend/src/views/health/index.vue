<template>
    <section class="space-y-8">
        <header class="space-y-3">
            <p class="text-sm text-slate-600">服务检测 · 手动检查 HTTP 应用响应</p>
            <h1 class="text-2xl font-semibold">检测 Python 后端连接</h1>
            <p>本轮仅验证 HTTP 应用能否响应，不表示数据库、模型或其他业务已接入或健康。</p>
            <p>页面不会自动检测。离开本页会取消在途请求；再次进入或刷新后回到待检测。</p>
        </header>
        <HealthPanel />
    </section>
</template>

<script setup lang="ts">
import HealthPanel from './components/HealthPanel.vue';
</script>
