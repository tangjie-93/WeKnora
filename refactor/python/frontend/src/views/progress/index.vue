<template>
    <section class="space-y-6">
        <header class="space-y-3">
            <h1 class="text-2xl font-semibold">开发进度</h1>
            <p>版本化静态说明，不是实时服务或工作流状态；健康状态请到服务检测主动检查。</p>
            <RouterLink class="progress-page__link" to="/health">前往服务检测</RouterLink>
        </header>
        <section class="space-y-2" aria-labelledby="health-slice-title">
            <h2 id="health-slice-title" class="text-lg font-semibold">上一子项：HTTP 健康检测</h2>
            <p>已通过独立审查和必需行为测试；仅说明 HTTP 应用响应，不代表数据库或模型可用。</p>
            <p>历史证据：<code>artifacts/weknora-python-vue3-rebuild/04-e2e/test-report.md</code></p>
        </section>
        <section class="space-y-2" aria-labelledby="navigation-slice-title">
            <h2 id="navigation-slice-title" class="text-lg font-semibold">历史增量：导航与静态进度</h2>
            <p>历史范围为共享外壳、服务检测与开发进度两页。历史验收结论以对应任务正式审查和测试记录为准，页面不跟踪执行状态。</p>
            <ul class="list-disc space-y-2 pl-5">
                <li>实现记录：<code>artifacts/weknora-learning-workbench/03-code/change-report.md</code></li>
                <li>独立审查定位：<code>artifacts/weknora-learning-workbench/03-code/code-review-report.md</code></li>
                <li>独立测试定位：<code>artifacts/weknora-learning-workbench/04-e2e/test-report.md</code></li>
            </ul>
            <p>以上为文档定位，不表示报告已生成或验收已通过。请在仓库中打开，不是网页下载链接。</p>
        </section>
        <section class="space-y-2" aria-labelledby="scope-title">
            <h2 id="scope-title" class="text-lg font-semibold">边界与变更记录</h2>
            <p>本轮仅实现 S2.2 显式本地 SQLite 连接检查子项，待独立审查；TASK-04 独立测试 not-run。</p>
            <p>业务数据、schema/迁移、ORM 未实现；整个 S2 未验收，整个 S1 未全量验收。上传、解析、检索、问答未开始。</p>
            <p>前端仅同步静态文字；后端新增独立 CLI，不改现有 HTTP 健康接口，不新增数据库 API 或页面连接功能。</p>
            <p>在仓库中打开前端记录：<code>docs/develop-process/frontend-changelog.md</code></p>
            <p>在仓库中打开总记录：<code>docs/develop-process/changelog.md</code></p>
            <p>每轮只实现一个需求，完成验证与讲解后暂停，等待用户明确继续；不自动进入下一功能。</p>
        </section>
    </section>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router';
</script>

<style scoped>
.progress-page__link {
    text-decoration: underline;
    text-underline-offset: 0.25em;

    &:focus-visible {
        outline: 2px solid currentColor;
        outline-offset: 4px;
    }
}
</style>
