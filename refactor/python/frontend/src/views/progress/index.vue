<template>
    <section class="progress-page">
        <AppPageHeader
            eyebrow="开发进度"
            title="前后端开发进度"
            description="按模块展示当前实现、验证状态和明确边界；内容来自版本化开发记录，不是实时运行状态。"
        />
        <el-alert title="当前可创建空文档知识库并查看列表。知识库详情、编辑、删除、共享，以及文档上传、检索和问答尚未开放。" type="info" :closable="false" show-icon />

        <el-row class="progress-page__columns" :gutter="12">
            <el-col :xs="24" :lg="12">
                <el-card shadow="never">
                    <template #header>前端开发</template>
                    <el-timeline>
                        <el-timeline-item v-for="item in frontendItems" :key="item.title" :type="item.type" :hollow="item.status !== '已完成'">
                            <div class="progress-page__item"><div><strong>{{ item.title }}</strong><p>{{ item.description }}</p></div><el-tag :type="item.tagType" size="small" effect="plain">{{ item.status }}</el-tag></div>
                        </el-timeline-item>
                    </el-timeline>
                </el-card>
            </el-col>
            <el-col :xs="24" :lg="12">
                <el-card shadow="never">
                    <template #header>后端开发</template>
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
                <el-descriptions-item label="已实现">账户注册、登录、会话恢复、服务端退出、个人空间查看、健康检查和开发进度展示。空知识库创建与真实列表已实现：独立测试及质量审核已通过；每个空间最多 100 个非临时、未删除知识库。</el-descriptions-item>
                <el-descriptions-item label="独立审查">定向复审 PASSED，当前 P0 / P1 / P2 均为 0；首轮 3 个 P1 及修复历史保留，不以当前通过覆盖历史发现。</el-descriptions-item>
                <el-descriptions-item label="独立测试">TASK-04 测试执行已完成且通过：后端新增 186 项、全量 406 项；前端新增 42 项、全量 83 项。浏览器业务 11 组、既有导航 5 组，共 16 组；新增已包含在全量内，浏览器组数不与 runner 测试数累加。</el-descriptions-item>
                <el-descriptions-item label="静态与构建">Ruff、Vue / TypeScript 类型检查、使用私有空 envDir 的安全构建均通过；9 个迁移资产字节检查通过。依据正式测试报告记录，本次进度同步没有重新执行验证。</el-descriptions-item>
                <el-descriptions-item label="待实现">知识库详情、编辑、删除、共享、模型管理、文档上传、解析、索引、检索、问答和流式响应，均未开始。</el-descriptions-item>
                <el-descriptions-item label="验证口径">独立测试及质量审核已通过：TASK-04 Leader 门禁 PASSED（9 项硬门禁、3 项软门禁），结论已审计；这不表示完整 CRUD 或整个知识库模块完成。模型未配置，向量引擎不可用。</el-descriptions-item>
            </el-descriptions>
        </el-card>
    </section>
</template>

<script setup lang="ts">
import AppPageHeader from '../../components/layout/AppPageHeader.vue';

const frontendItems = [
    { title: 'Element Plus 统一布局', description: '固定 Header、独立内容滚动区、紧凑间距和共享布局组件。', status: '已完成', type: 'success', tagType: 'success' },
    { title: '账户与认证页面', description: '注册、登录、会话恢复、退出和个人空间信息展示。', status: '已完成', type: 'success', tagType: 'success' },
    { title: '服务检测工作台', description: '手动健康检查、请求状态、错误分类和代理诊断。', status: '已完成', type: 'success', tagType: 'success' },
    { title: '空知识库创建与列表', description: '真实列表、名称描述创建、失败恢复和移动导航已实现；前端新增 42 / 全量 83 项通过，浏览器业务 11 + 导航 5 = 16 组通过；独立测试及质量审核已通过。', status: '已通过验证', type: 'warning', tagType: 'warning' },
    { title: '其余知识业务界面', description: '详情、编辑、删除、上传、检索和问答页面，均不属于本轮创建与列表切片。', status: '未开始', type: 'info', tagType: 'info' },
];

const backendItems = [
    { title: 'FastAPI 应用入口', description: '健康接口和统一异常处理基础。', status: '已完成', type: 'success', tagType: 'success' },
    { title: 'SQLite 连接检查', description: '独立只读数据库目标检查和初始化诊断。', status: '已完成', type: 'success', tagType: 'success' },
    { title: '账户认证服务', description: '认证迁移、账户注册、登录、令牌刷新和会话撤销。', status: '已完成', type: 'success', tagType: 'success' },
    { title: '空知识库创建与列表 API', description: 'POST/GET /api/v1/knowledge-bases 有限子集、真实空模型和最多 100 条容量；后端新增 186 / 全量 406 项通过，独立复审 PASSED（当前问题均为 0）；独立测试及质量审核已通过。', status: '已通过验证', type: 'warning', tagType: 'warning' },
    { title: '其余知识业务 API', description: '知识库详情、编辑、删除、共享、文档处理、检索和问答接口，本轮尚未开始。', status: '未开始', type: 'info', tagType: 'info' },
];
</script>

<style scoped lang="less">
.progress-page {
    overflow-wrap: anywhere;

    &__item > div { min-width: 0; }
    &__item > .el-tag { flex-shrink: 0; }
    & :deep(.el-descriptions__table) { table-layout: fixed; }

    &__columns { row-gap: 12px; margin-block: 12px; }
    &__columns :deep(.el-card__body) { padding: 14px; }
    &__item { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
    &__item strong { color: var(--el-text-color-primary); font-size: 13px; }
    &__item p { margin: 3px 0 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.45; }
    &__boundary :deep(.el-card__body) { padding: 14px; }
    & :deep(.el-timeline) { margin: 0; padding-left: 4px; }
    & :deep(.el-timeline-item) { padding-bottom: 14px; }
    & :deep(.el-timeline-item:last-child) { padding-bottom: 0; }
}
</style>
