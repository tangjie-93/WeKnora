<template>
    <div class="not-found-page">
        <RouterLink class="brand" to="/"><span class="brand-mark" aria-hidden="true">W</span>WeKnora</RouterLink>
        <main class="panel not-found-page__panel"><p class="eyebrow">404 · PAGE NOT FOUND</p><h1>这个页面暂不存在</h1><p class="muted">地址可能已变更。你可以返回账户入口，或使用辅助工作台。</p><div class="not-found-page__actions"><RouterLink class="primary-button" to="/">返回账户或登录</RouterLink><RouterLink class="secondary-button" to="/workbench/health">打开工作台</RouterLink></div></main>
    </div>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router';
</script>

<style scoped lang="less">
.not-found-page {
    max-width: 900px;
    padding: 18px 16px;
    margin: auto;

    & .not-found-page__panel { padding: 18px; margin-top: 18px; }
    & .not-found-page__actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 18px; }
}
</style>
