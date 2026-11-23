<template>
    <section class="health-panel" aria-label="健康检查">
        <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="请求">GET /health</el-descriptions-item>
            <el-descriptions-item label="策略">手动检查，最长等待 5 秒，无自动重试</el-descriptions-item>
        </el-descriptions>
        <div class="health-panel__actions">
            <el-button type="primary" :loading="state === 'checking'" @click="onCheckClick">
                {{ state === 'checking' ? '正在检测…' : '检测后端连接' }}
            </el-button>
            <el-tag :type="state === 'success' ? 'success' : state === 'failure' ? 'danger' : 'info'" effect="plain">
                {{ stateLabels[state] }}
            </el-tag>
        </div>
        <el-alert v-if="state === 'success' && result" title="连接成功（仅 HTTP 存活）" type="success" :closable="false" show-icon>
            <template #default>
                HTTP {{ result.httpStatus }}；Python 标记：<code>{{ result.implementation }}</code>；响应：<code>{{ JSON.stringify({ status: result.status }) }}</code>
            </template>
        </el-alert>
        <el-alert v-if="state === 'failure' && error" :title="`检测失败：${error.kind}`" :description="error.message" type="error" :closable="false" show-icon />
        <el-text v-if="checkedAt" size="small" type="info">最近检测：{{ new Date(checkedAt).toLocaleString() }}</el-text>
        <el-collapse>
            <el-collapse-item title="查看源码方法与请求原理" name="source">
                <ol class="health-panel__source">
                    <li><code>HealthPanel.vue</code> 接收按钮事件并触发检测。</li>
                    <li><code>useHealthCheck()</code> 管理请求状态、并发和取消。</li>
                    <li><code>fetchHealth()</code> 校验 HTTP、JSON 与 Python 标记。</li>
                    <li><code>vite.config.ts</code> 负责开发期代理。</li>
                    <li><code>app.main:health()</code> 返回健康响应。</li>
                </ol>
            </el-collapse-item>
        </el-collapse>
    </section>
</template>

<script setup lang="ts">
import { useHealthCheck } from '../hooks/useHealthCheck';

const { state, result, error, checkedAt, check } = useHealthCheck();
const stateLabels = { idle: '待检测', checking: '请求中', success: '连接成功', failure: '检测失败' };

/** 将真实按钮操作交给手动查询，成功或失败由请求状态展示。 */
async function onCheckClick(): Promise<void> {
    await check();
}
</script>

<style scoped lang="less">
.health-panel {
    display: grid;
    gap: 12px;

    &__actions { display: flex; align-items: center; gap: 10px; }
    &__source { display: grid; gap: 6px; margin: 0; padding-left: 20px; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.5; }
    & :deep(.el-alert__content) { line-height: 1.5; }
}
</style>
