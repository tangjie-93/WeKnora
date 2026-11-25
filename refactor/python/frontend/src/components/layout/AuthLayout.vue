<template>
    <el-container class="auth-layout" direction="vertical">
        <el-header v-if="!hideHeader" class="auth-layout__header" height="56px"><AppBrand /><RouterLink to="/workbench/health">服务检测</RouterLink></el-header>
        <el-main class="auth-layout__main">
            <el-scrollbar class="auth-layout__scrollbar">
                <div class="auth-layout__content"><slot /></div>
            </el-scrollbar>
        </el-main>
    </el-container>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router';
import AppBrand from './AppBrand.vue';

defineProps({ hideHeader: Boolean });
</script>

<style scoped lang="less">
.auth-layout {
    height: 100dvh;
    overflow: hidden;

    &__header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 18px;
        border-bottom: 1px solid var(--el-border-color-light);
        background: var(--el-bg-color);

        & a:not(.app-brand) {
            color: var(--el-color-primary);
            font-size: 13px;
        }
    }

    &__main {
        min-height: 0;
        padding: 0;
        overflow: hidden;
        background: var(--el-fill-color-extra-light);
    }

    &__scrollbar {
        height: 100%;
    }

    &__content {
        display: grid;
        min-height: 100%;
        padding: 18px;
        place-items: center;
    }

    @media (max-width: 767px) {
        &__header,
        &__content {
            padding-right: 12px;
            padding-left: 12px;
        }
    }
}
</style>
