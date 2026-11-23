<template>
    <section class="progress-page">
        <AppPageHeader eyebrow="开发进度" title="学习工作台" description="版本化静态说明，不是实时服务或工作流状态。" />
        <el-alert title="健康状态请到服务检测主动检查。" type="info" :closable="false" show-icon />
        <el-row class="progress-page__grid" :gutter="12">
            <el-col :xs="24" :md="12"><el-card shadow="never"><template #header>HTTP 健康检测</template><p>已通过独立审查和必要行为测试，仅说明 HTTP 应用响应。</p><el-tag type="success">已完成</el-tag></el-card></el-col>
            <el-col :xs="24" :md="12"><el-card shadow="never"><template #header>账户与个人空间</template><p>已实现真实注册、登录、会话恢复和服务端退出。</p><el-tag type="success">已完成</el-tag></el-card></el-col>
            <el-col :xs="24"><el-card shadow="never"><template #header>当前边界</template><p>认证使用独立 SQLite 结构子集；知识库、上传、解析、检索和问答尚未开放。</p><el-space wrap><el-tag type="warning">未开始</el-tag><RouterLink to="/workbench/health">前往服务检测</RouterLink></el-space></el-card></el-col>
        </el-row>
        <el-collapse class="progress-page__details">
            <el-collapse-item title="查看验证证据路径" name="evidence">
                <el-descriptions :column="1" border size="small">
                    <el-descriptions-item label="前端记录">docs/develop-process/frontend-changelog.md</el-descriptions-item>
                    <el-descriptions-item label="总记录">docs/develop-process/changelog.md</el-descriptions-item>
                    <el-descriptions-item label="测试报告">artifacts/weknora-product-auth/04-e2e/test-report.md</el-descriptions-item>
                </el-descriptions>
            </el-collapse-item>
        </el-collapse>
    </section>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router';
import AppPageHeader from '../../components/layout/AppPageHeader.vue';
</script>

<style scoped lang="less">
.progress-page {
    width: min(100%, 960px);

    &__grid { margin-top: 12px; }
    &__details { margin-top: 12px; }
    & :deep(.el-card__header) { padding: 10px 14px; font-weight: 600; }
    & :deep(.el-card__body) { padding: 14px; }
    & p { margin: 0 0 10px; color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.5; }
}
</style>
