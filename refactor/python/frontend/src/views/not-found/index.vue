<template>
    <section class="space-y-4">
        <h1 class="text-2xl font-semibold">未找到页面</h1>
        <p>这个地址没有对应的学习页面。当前仅提供服务检测与开发进度。</p>
        <RouterLink class="not-found-page__link" to="/health">返回服务检测</RouterLink>
    </section>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router';
</script>

<style scoped>
.not-found-page__link {
    text-decoration: underline;
    text-underline-offset: 0.25em;

    &:focus-visible {
        outline: 2px solid currentColor;
        outline-offset: 4px;
    }
}
</style>
