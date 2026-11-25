<template>
    <section class="health-page">
        <AppPageHeader eyebrow="服务检测" title="检测 Python 后端连接" description="仅验证 HTTP 应用响应，不代表数据库、模型或其他业务已接入。" />
        <HealthPanel />
    </section>
</template>

<script setup lang="ts">
import AppPageHeader from '../../components/layout/AppPageHeader.vue';
import HealthPanel from './components/HealthPanel.vue';
</script>
