<template>
    <section class="progress-page">
        <AppPageHeader
            eyebrow="开发进度"
            title="前后端开发进度"
            description="按模块展示当前实现、验证状态和明确边界；内容来自版本化开发记录，不是实时运行状态。"
        />
        <el-alert title="进度页面只展示已记录的开发事实，不读取本机状态文件，也不发起服务检测。" type="info" :closable="false" show-icon />

        <el-row class="progress-page__overview" :gutter="12">
            <el-col :xs="8" :sm="8"><el-statistic title="已完成模块" :value="completedCount" /></el-col>
            <el-col :xs="8" :sm="8"><el-statistic title="前端模块" :value="frontendItems.length" /></el-col>
            <el-col :xs="8" :sm="8"><el-statistic title="后端模块" :value="backendItems.length" /></el-col>
        </el-row>

        <el-row class="progress-page__columns" :gutter="12">
            <el-col :xs="24" :lg="12">
                <el-card shadow="never">
                    <template #header><div class="progress-page__card-title"><span>前端开发</span><el-tag type="success" size="small">{{ frontendDoneCount }}/{{ frontendItems.length }}</el-tag></div></template>
                    <el-timeline>
                        <el-timeline-item v-for="item in frontendItems" :key="item.title" :type="item.type" :hollow="item.status !== '已完成'">
                            <div class="progress-page__item"><div><strong>{{ item.title }}</strong><p>{{ item.description }}</p></div><el-tag :type="item.tagType" size="small" effect="plain">{{ item.status }}</el-tag></div>
                        </el-timeline-item>
                    </el-timeline>
                </el-card>
            </el-col>
            <el-col :xs="24" :lg="12">
                <el-card shadow="never">
                    <template #header><div class="progress-page__card-title"><span>后端开发</span><el-tag type="success" size="small">{{ backendDoneCount }}/{{ backendItems.length }}</el-tag></div></template>
                    <el-timeline>
                        <el-timeline-item v-for="item in backendItems" :key="item.title" :type="item.type" :hollow="item.status !== '已完成'">
                            <div class="progress-page__item"><div><strong>{{ item.title }}</strong><p>{{ item.description }}</p></div><el-tag :type="item.tagType" size="small" effect="plain">{{ item.status }}</el-tag></div>
                        </el-timeline-item>
                    </el-timeline>
                </el-card>
            </el-col>
        </el-row>

        <el-card class="progress-page__boundary" shadow="never">
            <template #header>当前边界与下一步</template>
            <el-descriptions :column="1" border size="small">
                <el-descriptions-item label="已实现">账户注册、登录、会话恢复、服务端退出、个人空间查看、健康检查和开发进度展示。</el-descriptions-item>
                <el-descriptions-item label="待实现">知识库 CRUD、文档上传、解析、索引、检索、问答和流式响应。</el-descriptions-item>
                <el-descriptions-item label="验证口径">状态标签代表代码和对应测试报告中的记录，不等于生产环境或实时服务状态。</el-descriptions-item>
            </el-descriptions>
        </el-card>
    </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import AppPageHeader from '../../components/layout/AppPageHeader.vue';

const frontendItems = [
    { title: 'Element Plus 统一布局', description: '固定 Header、独立内容滚动区、紧凑间距和共享布局组件。', status: '已完成', type: 'success', tagType: 'success' },
    { title: '账户与认证页面', description: '注册、登录、会话恢复、退出和个人空间信息展示。', status: '已完成', type: 'success', tagType: 'success' },
    { title: '服务检测工作台', description: '手动健康检查、请求状态、错误分类和代理诊断。', status: '已完成', type: 'success', tagType: 'success' },
    { title: '知识库业务界面', description: '知识库、文档上传、检索和问答页面。', status: '未开始', type: 'info', tagType: 'info' },
];

const backendItems = [
    { title: 'FastAPI 应用入口', description: '健康接口和统一异常处理基础。', status: '已完成', type: 'success', tagType: 'success' },
    { title: 'SQLite 连接检查', description: '独立只读数据库目标检查和初始化诊断。', status: '已完成', type: 'success', tagType: 'success' },
    { title: '账户认证服务', description: '认证迁移、账户注册、登录、令牌刷新和会话撤销。', status: '已完成', type: 'success', tagType: 'success' },
    { title: '知识库业务 API', description: '知识库 CRUD、文档处理、检索和问答接口。', status: '未开始', type: 'info', tagType: 'info' },
];

const frontendDoneCount = computed(() => frontendItems.filter(item => item.status === '已完成').length);
const backendDoneCount = computed(() => backendItems.filter(item => item.status === '已完成').length);
const completedCount = computed(() => frontendDoneCount.value + backendDoneCount.value);
</script>

<style scoped lang="less">
.progress-page {
    width: min(100%, 1040px);

    &__overview { margin: 12px 0; }
    &__overview :deep(.el-col) { padding: 12px; border: 1px solid var(--el-border-color-light); background: var(--el-bg-color); }
    &__overview :deep(.el-statistic__head) { font-size: 12px; }
    &__columns { margin-bottom: 12px; }
    &__columns :deep(.el-card__body) { padding: 14px; }
    &__card-title { display: flex; align-items: center; justify-content: space-between; }
    &__item { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
    &__item strong { color: var(--el-text-color-primary); font-size: 13px; }
    &__item p { margin: 3px 0 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.45; }
    &__boundary :deep(.el-card__body) { padding: 14px; }
    & :deep(.el-timeline) { margin: 0; padding-left: 4px; }
    & :deep(.el-timeline-item) { padding-bottom: 14px; }
    & :deep(.el-timeline-item:last-child) { padding-bottom: 0; }
}
</style>
