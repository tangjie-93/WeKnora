<template>
    <div class="workbench-layout mx-auto max-w-3xl px-5 py-8 sm:px-8">
        <header class="space-y-4 border-b border-slate-200 pb-6">
            <p class="text-xl font-semibold">WeKnora 学习工作台</p>
            <p class="text-sm text-slate-600">Python / Vue 重构 · 每轮一个需求，验证与讲解后暂停。</p>
            <nav class="flex flex-wrap gap-3" aria-label="工作台导航">
                <RouterLink class="workbench-layout__link" to="/health" exact-active-class="workbench-layout__link--current">服务检测</RouterLink>
                <RouterLink class="workbench-layout__link" to="/progress" exact-active-class="workbench-layout__link--current">开发进度</RouterLink>
            </nav>
        </header>
        <main class="min-w-0 py-8">
            <slot />
        </main>
    </div>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router';
</script>

<style scoped>
.workbench-layout {
    & .workbench-layout__link {
        border: 1px solid #64748b;
        border-radius: 0.375rem;
        padding: 0.5rem 1rem;

        &.workbench-layout__link--current {
            border-color: currentColor;
            background: #f1f5f9;
            font-weight: 700;
            text-decoration: underline;
            text-underline-offset: 0.25em;
        }

        &:focus-visible {
            outline: 2px solid currentColor;
            outline-offset: 4px;
        }
    }
}
</style>
