<template>
    <header class="app-page-header">
        <div>
            <p v-if="eyebrow" class="app-page-header__eyebrow">{{ eyebrow }}</p>
            <h1>{{ title }}</h1>
            <p v-if="description" class="app-page-header__description">{{ description }}</p>
        </div>
        <div v-if="$slots.actions" class="app-page-header__actions"><slot name="actions" /></div>
    </header>
</template>

<script setup lang="ts">
defineProps<{
    eyebrow?: string;
    title: string;
    description?: string;
}>();
</script>

<style scoped lang="less">
.app-page-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 14px;

    &__eyebrow {
        margin: 0 0 4px;
        color: var(--el-color-primary);
        font-size: 12px;
        font-weight: 600;
    }

    & h1 {
        margin: 0;
        color: var(--el-text-color-primary);
        font-size: 22px;
        line-height: 1.25;
    }

    &__description {
        max-width: 720px;
        margin: 5px 0 0;
        color: var(--el-text-color-secondary);
        font-size: 13px;
        line-height: 1.5;
    }

    &__actions {
        display: flex;
        flex: none;
        gap: 8px;
    }
}
</style>
