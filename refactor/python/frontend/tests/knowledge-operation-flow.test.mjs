// Static explanation only: use node:test and the existing Vue compiler/renderer, without a DOM or backend.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { compileTemplate, parse } from 'vue/compiler-sfc';
import { createSSRApp } from 'vue';
import { renderToString } from 'vue/server-renderer';

const componentUrl = new URL('../src/views/knowledge/components/KnowledgeOperationFlow.vue', import.meta.url);
const source = await readFile(componentUrl, 'utf8');
const { descriptor, errors } = parse(source);
assert.deepEqual(errors, []);
const compiled = compileTemplate({ source: descriptor.template.content, filename: componentUrl.pathname, id: 'knowledge-flow-test' });
assert.deepEqual(compiled.errors, []);
const code = compiled.code.replaceAll('from "vue"', `from ${JSON.stringify(import.meta.resolve('vue'))}`);
const { render } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const warnings = [];
const app = createSSRApp({ render });
app.config.warnHandler = message => warnings.push(message);
const html = await renderToString(app);
const text = html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');

test('renders six ordered steps with success arrows and an adjacent recovery branch for each', () => {
    assert.deepEqual(warnings, []);
    const steps = [...html.matchAll(/<li class="knowledge-operation-flow__step">([\s\S]*?)<\/li>/g)].map(match => match[1]);
    assert.equal(steps.length, 6);
    steps.forEach((step, index) => {
        assert.match(step, new RegExp(`class="knowledge-operation-flow__number">${index + 1}<`));
        assert.match(step, /<h3>/);
        assert.match(step, /class="knowledge-operation-flow__lane"/);
        assert.match(step, /<code>/);
        assert.match(step, /<aside[^>]*aria-label=/);
        assert.equal(step.includes('knowledge-operation-flow__connector'), index < 5);
    });
    assert.equal((html.match(/aria-hidden="true">↓/g) || []).length, 5);
    for (const condition of ['有创建权限', '校验通过', '接口参数校验通过', '响应格式及用户、空间归属', '当前身份、空间与筛选仍匹配']) {
        assert.ok(text.includes(condition), condition);
    }
});

test('explains uncertain writes, pre-commit failure and committed-create refresh failure separately', () => {
    for (const message of [
        '全程保护，而非最后一步', '忽略晚到的成功、错误和清理回调',
        '不请求业务列表', '不发送创建请求', '创建请求不会自动重试',
        '先选“全部”并成功刷新列表核对', '关闭弹窗不代表服务端回滚',
        '未提交的事务回滚', '审计失败不逆转创建成功',
        '已创建，但列表刷新未成功', '只重试列表，不要再次创建',
        '其他成员创建的', '新建条目不会出现', '不冒充“空间为空”',
    ]) assert.ok(text.includes(message), message);
    assert.ok(html.indexOf('knowledge-operation-flow__guard') < html.indexOf('<ol'));
    for (const symbol of ['captureOwner()', 'owns()', 'ownsSubmission()', 'handleSubmit()',
        'createKnowledgeBase()', 'KnowledgeBaseService.create()', 'refreshOwnedList()', 'fetchKnowledgeBases()']) {
        assert.ok(text.includes(symbol), symbol);
    }
});

test('code references use native keyboard-accessible disclosure and a stateless theme-aware layout', () => {
    assert.match(html, /<details[^>]*>\s*<summary>对照代码：每一步在哪里实现？<\/summary>/);
    for (const path of ['src/hooks/useSession.ts', 'src/hooks/useKnowledgeBases.ts',
        'src/views/knowledge/components/CreateKnowledgeBaseDialog.vue', 'src/api/knowledge-bases.ts',
        'src/api/client.ts', 'app/api/routes/knowledge_bases.py', 'app/services/knowledge_bases.py',
        'app/repositories/knowledge_bases.py', 'src/views/knowledge/index.vue']) {
        assert.ok(text.includes(path), path);
    }
    assert.equal(descriptor.script, null);
    assert.equal(descriptor.scriptSetup, null);
    assert.equal(descriptor.styles.length, 1);
    assert.equal(descriptor.styles[0].scoped, true);
    assert.match(descriptor.styles[0].content, /var\(--el-/);
    assert.match(descriptor.styles[0].content, /@container \(max-width: 760px\)/);
    assert.match(descriptor.styles[0].content, /minmax\(0, 1fr\)/);
    assert.match(descriptor.styles[0].content, /overflow-wrap: anywhere/);
    assert.doesNotMatch(html, /<button|<script|<header|aria-pressed|onclick|实时运行追踪器/);
});
test('all documented code files exist', async () => {
    // Resolve independently of test execution order.
    const paths = [...descriptor.template.content.matchAll(/<code>((?:src|app)\/[^<]+)<\/code>/g)].map(match => match[1]);
    for (const path of paths) {
        const prefix = path.startsWith('app/') ? '../../backend/' : '../';
        await readFile(new URL(`${prefix}${path}`, import.meta.url), 'utf8');
    }
});

test('parent mounts the explanation only inside the existing collapse and retains real business controls', async () => {
    const page = await readFile(new URL('../src/views/knowledge/index.vue', import.meta.url), 'utf8');
    const parsed = parse(page);
    assert.deepEqual(parsed.errors, []);
    assert.match(parsed.descriptor.scriptSetup.content, /import KnowledgeOperationFlow from "\.\/components\/KnowledgeOperationFlow.vue"/);
    assert.match(page, /<el-collapse-item title="本次操作如何工作？" name="call-chain"\s*>\s*<p>以下是代码调用关系说明，不是实时运行追踪。<\/p>\s*<KnowledgeOperationFlow \/>/);
    assert.equal((page.match(/<KnowledgeOperationFlow/g) || []).length, 1);
    assert.match(page, /@click="openCreateDialog"/);
    assert.match(page, /@click="retryList"/);
    assert.match(page, /:submit="submit"/);
    assert.match(page, /container-type: inline-size/);
    assert.doesNotMatch(page, /&__explanation ol/);
});
