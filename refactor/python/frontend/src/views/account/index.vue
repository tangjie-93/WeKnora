<template>
    <section class="account-page">
        <AppPageHeader eyebrow="YOUR ACCOUNT & WORKSPACE" title="账户与空间" description="你的身份与当前个人空间，来自实时验证的服务端记录。" />
        <el-skeleton v-if="query.isPending.value || query.isFetching.value" :rows="4" animated />
        <div v-else-if="query.isError.value" class="account-page__recovery"><el-alert :title="query.error.value instanceof ApiError && query.error.value.status === 403 ? '当前空间不可用' : '暂时无法读取账户'" :description="errorMessage(query.error.value)" type="error" :closable="false" show-icon /><el-button @click="query.refetch()">重试账户验证</el-button></div>
        <template v-else-if="account">
            <el-row class="account-page__grid" :gutter="12">
                <el-col :xs="24" :md="12">
                    <el-card shadow="never">
                        <template #header>
                            <div class="account-page__card-heading">
                                <span>账户资料</span>
                                <el-tag size="small" type="success">{{ account.user.is_active ? '正常' : '已停用' }}</el-tag>
                            </div>
                        </template>
                        <div class="account-page__welcome">
                            <el-avatar :size="36" aria-hidden="true">{{ account.user.username.slice(0, 1).toUpperCase() }}</el-avatar>
                            <div>
                                <h2>你好，{{ account.user.username }}</h2>
                                <el-text type="info" size="small">欢迎回到 WeKnora。</el-text>
                            </div>
                        </div>
                        <el-descriptions :column="1" size="small">
                            <el-descriptions-item label="用户名">{{ account.user.username }}</el-descriptions-item>
                            <el-descriptions-item label="邮箱">{{ account.user.email }}</el-descriptions-item>
                            <el-descriptions-item label="账户 ID"><code>{{ account.user.id }}</code></el-descriptions-item>
                            <el-descriptions-item label="创建时间">{{ formatDate(account.user.created_at) }}</el-descriptions-item>
                        </el-descriptions>
                    </el-card>
                </el-col>
                <el-col :xs="24" :md="12"><el-card shadow="never"><template #header><div class="account-page__card-heading"><span>当前个人空间</span><el-tag size="small" type="success">{{ account.tenant.status }}</el-tag></div></template><el-descriptions :column="1" size="small"><el-descriptions-item label="空间名称">{{ account.tenant.name }}</el-descriptions-item><el-descriptions-item label="空间 ID">{{ account.tenant.id }}</el-descriptions-item><el-descriptions-item label="成员角色">{{ membership?.role === 'owner' ? '所有者' : membership?.role || '无有效成员' }}</el-descriptions-item><el-descriptions-item label="创建时间">{{ formatDate(account.tenant.created_at) }}</el-descriptions-item></el-descriptions></el-card></el-col>
            </el-row>
            <el-alert class="account-page__boundary" title="已接入当前空间的空知识库创建与真实列表，待独立验证；模型未配置、向量引擎不可用，上传、检索和问答仍未开放。" type="info" :closable="false" show-icon />
            <RouterLink class="account-page__knowledge-link" to="/knowledge-bases">进入知识库</RouterLink>
            <el-collapse class="account-page__details"><el-collapse-item title="这份信息从哪里来？" name="source"><p>账户、空间和成员角色均来自 GET /api/v1/auth/me，刷新页面会重新验证。</p></el-collapse-item></el-collapse>
        </template>
    </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink } from 'vue-router';
import AppPageHeader from '../../components/layout/AppPageHeader.vue';
import { ApiError, errorMessage } from '../../api/client';
import { useCurrentAccount } from '../../hooks/useSession';
const { query, account } = useCurrentAccount();
const membership = computed(() => account.value?.memberships.find(item => item.tenant_id === account.value?.tenant.id));

/** 将服务端时间格式化为浏览器本地时间，不伪造缺失日期。 */
function formatDate(value: string | null): string {
    if (!value) return '未提供';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}
</script>

<style scoped lang="less">
.account-page {
    overflow-wrap: anywhere;

    &__recovery { display: grid; justify-items: start; gap: 12px; }
    &__knowledge-link { display: inline-block; margin-bottom: 12px; color: var(--el-color-primary); }
    &__knowledge-link:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 3px; }
    & :deep(.el-descriptions__cell) { overflow-wrap: anywhere; }
    & :deep(.el-descriptions__table) { table-layout: fixed; }

    &__welcome {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 12px;

        & .el-avatar { flex: none; }
        & h2 { margin: 0 0 2px; font-size: 14px; }
    }
    &__grid {
        row-gap: 12px;
        margin-bottom: 12px;

        & :deep(.el-card) { height: 100%; }
    }
    &__card-heading { display: flex; align-items: center; justify-content: space-between; }
    &__boundary { margin-bottom: 12px; }
    &__details p { margin: 0; color: var(--el-text-color-secondary); font-size: 13px; }
    & :deep(.el-card__header) { padding: 10px 14px; }
    & :deep(.el-card__body) { padding: 14px; }
}
</style>
