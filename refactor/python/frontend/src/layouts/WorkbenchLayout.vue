<template>
    <ProductLayout v-if="session.accessToken && !session.pendingLogout"><RouterView /></ProductLayout>
    <AuthLayout v-else>
        <div class="workbench-layout">
            <AppPageHeader eyebrow="辅助模块" title="工作台" description="服务检测与版本进度，不代替产品业务。" />
            <el-menu mode="horizontal" :default-active="route.path" @select="navigate">
                <el-menu-item index="/workbench/health">服务检测</el-menu-item>
                <el-menu-item index="/workbench/progress">开发进度</el-menu-item>
            </el-menu>
            <el-card class="workbench-layout__card" shadow="never"><RouterView /></el-card>
        </div>
    </AuthLayout>
</template>

<script setup lang="ts">
import { RouterView, useRoute, useRouter } from 'vue-router';
import AppPageHeader from '../components/layout/AppPageHeader.vue';
import AuthLayout from '../components/layout/AuthLayout.vue';
import ProductLayout from './ProductLayout.vue';
import { useSessionStore } from '../stores/session';

const route = useRoute();
const router = useRouter();
const session = useSessionStore();

/** 根据工作台菜单切换辅助页面。 */
async function navigate(path: string): Promise<void> {
    await router.push(path);
}
</script>

<style scoped lang="less">
.workbench-layout {
    width: min(100%, 960px);

    &__card { margin-top: 12px; }
    & :deep(.el-card__body) { padding: 18px; }
}
</style>
