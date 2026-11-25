<template>
    <AuthLayout class="auth-form-layout" hide-header>
        <el-card class="auth-form-card" shadow="never">
            <AppBrand class="auth-form-card__brand" />
            <AppPageHeader :title="title" :description="description" />
            <slot />
            <p class="auth-form-card__footer"><slot name="footer" /></p>
        </el-card>
    </AuthLayout>
</template>

<script setup lang="ts">
import AppBrand from './AppBrand.vue';
import AppPageHeader from './AppPageHeader.vue';
import AuthLayout from './AuthLayout.vue';

defineProps({
    title: { type: String, required: true },
    description: { type: String, required: true },
});
</script>

<style scoped lang="less">
.auth-form-layout {
    & :deep(.auth-layout__main) {
        background-color: #081d1b;
        background-image:
            linear-gradient(#a8f7de0e 1px, transparent 1px),
            linear-gradient(90deg, #a8f7de0e 1px, transparent 1px),
            radial-gradient(ellipse at 18% 24%, #216e58, transparent 55%),
            radial-gradient(ellipse at 83% 78%, #23505d, transparent 53%);
        background-size: 40px 40px, 40px 40px, 100% 100%, 100% 100%;
    }

    & :deep(.el-scrollbar__view) {
        display: grid;
        min-height: 100%;
    }
}

.auth-form-card {
    width: min(100%, 440px);
    border: 1px solid #d7e8e1;
    border-radius: 20px;
    background: linear-gradient(155deg, #f1fbf6, #fff 44%);
    box-shadow: 0 24px 72px #031410a8, 0 0 0 6px #d7fff017;
    overflow-wrap: anywhere;

    & :deep(.el-card__body) { padding: clamp(22px, 5vw, 34px); }
    & :deep(.app-page-header h1) { font-size: 30px; }
    & :deep(.el-alert) { margin-bottom: 10px; }
    & :deep(.el-form) { margin-top: 22px; }
    & :deep(.el-input) { --el-input-height: 44px; }
    & :deep(.el-button + .el-button) { margin: 8px 0 0; }

    & :deep(.el-button[type='submit']) {
        width: 100%;
        min-height: 44px;
        font-weight: 600;
    }

    &__brand { margin-bottom: 20px; }

    &__footer {
        margin: 20px 0 0;
        padding-top: 16px;
        border-top: 1px solid var(--el-border-color-light);
        color: var(--el-text-color-regular);
        font-size: 13px;
        text-align: center;

        & :deep(a) { font-weight: 600; }
    }
}
</style>
