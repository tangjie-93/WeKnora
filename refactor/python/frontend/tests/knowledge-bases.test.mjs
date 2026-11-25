// Native node:test + existing TS transpilation and Vue renderer; no DOM/framework dependency.
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import test, { after, beforeEach, afterEach } from 'node:test';
import ts from 'typescript';
import { createPinia, setActivePinia } from 'pinia';
import { createRenderer, nextTick } from 'vue';
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query';

const directory = await mkdtemp(join(tmpdir(), 'weknora-kb-unit-'));
const modules = ['api/client', 'api/auth', 'api/knowledge-bases', 'stores/session', 'hooks/useSession', 'hooks/useKnowledgeBases'];
for (const name of modules) {
    const source = await readFile(new URL(`../src/${name}.ts`, import.meta.url), 'utf8');
    let output = ts.transpileModule(source, { compilerOptions: {
        target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022,
    } }).outputText;
    output = output.replace(/from ['"]([^'"]+)['"]/g, (all, specifier) => {
        const local = modules.find(candidate => specifier === `../${candidate}` ||
            specifier === `./${candidate.split('/').at(-1)}`);
        return `from '${local ? pathToFileURL(join(directory, local.replace('/', '-') + '.mjs')).href : import.meta.resolve(specifier)}'`;
    });
    await writeFile(join(directory, name.replace('/', '-') + '.mjs'), output);
}
const client = await import(pathToFileURL(join(directory, 'api-client.mjs')));
const api = await import(pathToFileURL(join(directory, 'api-knowledge-bases.mjs')));
const { useSessionStore } = await import(pathToFileURL(join(directory, 'stores-session.mjs')));
const session = await import(pathToFileURL(join(directory, 'hooks-useSession.mjs')));
const { useKnowledgeBases } = await import(pathToFileURL(join(directory, 'hooks-useKnowledgeBases.mjs')));
const originalFetch = globalThis.fetch;
let queryClient, store, pinia, application, storage;
const response = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
const settle = async () => { for (let i = 0; i < 5; i++) { await nextTick(); await new Promise(resolve => setImmediate(resolve)); } };
const account = (user = 'user-a', tenant = 1) => ({
    user: { id: user, username: 'Isolated', email: 'isolated@example.com', avatar: null, created_at: null, updated_at: null,
        tenant_id: tenant, is_active: true, can_access_all_tenants: false, is_system_admin: false, preferences: {} },
    tenant: { id: tenant, name: 'Isolated space', status: 'active', business: '', description: null, created_at: null,
        updated_at: null, deleted_at: null, retriever_engines: [], storage_quota: 1000, storage_used: 0 },
    memberships: [{ tenant_id: tenant, tenant_name: 'Isolated space', role: 'owner' }],
});
const loginResponse = () => ({ success: true, token: 'new', refresh_token: 'new-refresh',
    user: account().user, active_tenant: account().tenant, memberships: account().memberships });
const item = (overrides = {}) => ({
    id: '11111111-1111-4111-8111-111111111111', name: '真实空知识库', description: '', type: 'document',
    tenant_id: 1, creator_id: 'user-a', is_temporary: false, deleted_at: null,
    created_at: '2026-11-24T00:00:00Z', updated_at: '2026-11-24T00:00:00Z', embedding_model_id: '', summary_model_id: '',
    chunking_config: { chunk_size: 0, chunk_overlap: 0, separators: null }, image_processing_config: { model_id: '' },
    vlm_config: { enabled: false, model_id: '', model_name: '', base_url: '', api_key: '', interface_type: '' },
    asr_config: { enabled: false, model_id: '', language: '' }, storage_provider_config: { provider: 'local' },
    storage_config: { secret_id: '', secret_key: '', region: '', bucket_name: '', app_id: '', path_prefix: '', provider: '' },
    indexing_strategy: { vector_enabled: true, keyword_enabled: true, wiki_enabled: false, graph_enabled: false },
    capabilities: { vector: true, keyword: true, wiki: false, graph: false, faq: false },
    extract_config: null, faq_config: null, question_generation_config: null, auto_tag_config: null, wiki_config: null, profile_config: null,
    knowledge_count: 0, chunk_count: 0, processing_count: 0, share_count: 0, is_processing: false, is_pinned: false, pinned_at: null,
    vector_store_source: 'unavailable', vector_store_status: 'unavailable', ...overrides,
});
const renderer = createRenderer({
    createElement: () => ({}), createText: () => ({}), createComment: () => ({}), insert() {}, remove() {},
    setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, patchProp() {},
});
function mount() {
    let hook;
    application = renderer.createApp({ setup() { hook = useKnowledgeBases(); return () => null; } });
    application.use(pinia); application.use(VueQueryPlugin, { queryClient }); application.mount({});
    return hook;
}
function install(user = 'user-a', tenant = 1) {
    store.installTokens({ accessToken: `isolated-${user}`, refreshToken: `refresh-${user}` }, store.epoch);
    queryClient.setQueryData(['auth', 'me', store.epoch], account(user, tenant));
}
beforeEach(() => {
    pinia = createPinia(); setActivePinia(pinia); storage = new Map();
    globalThis.sessionStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) };
    queryClient = new QueryClient(); store = useSessionStore();
    session.configureSessionRuntime({ queryClient, router: { replace: async () => {} } });
    install(); globalThis.fetch = async () => response({ success: true, data: [] });
});
afterEach(() => { application?.unmount(); application = undefined; queryClient.clear(); globalThis.fetch = originalFetch; });
after(async () => { delete globalThis.sessionStorage; await rm(directory, { recursive: true }); });

test('strict adapter accepts empty lists and legacy creator empty string; wire null still rejected', async () => {
    for (const creator of ['', 'user-a']) {
        globalThis.fetch = async () => response({ success: true, data: [item({ creator_id: creator })] });
        assert.equal((await api.fetchKnowledgeBases('all'))[0].creator_id, creator);
    }
    globalThis.fetch = async () => response({ success: true, data: [item({ creator_id: null })] });
    await assert.rejects(api.fetchKnowledgeBases('all'), error => error.kind === 'contract');
});
for (const [name, body] of [
    ['null-list', { success: true, data: null }], ['false-success', { success: false, data: [] }],
    ['too-many', { success: true, data: Array.from({ length: 101 }, () => item()) }],
    ...Object.entries({ id: 'not-uuid', tenant_id: 0, embedding_model_id: 'model', created_at: 'yesterday',
        knowledge_count: -1, vector_store_status: 'available', chunking_config: {}, profile_config: {} })
        .map(([key, value]) => [key, { success: true, data: [item({ [key]: value })] }]),
]) {
    test(`adapter rejects malformed ${name}, never disguises as empty`, async () => {
        globalThis.fetch = async () => response(body);
        await assert.rejects(api.fetchKnowledgeBases('all'), error => error.kind === 'contract');
    });
}
for (const status of [400, 401, 403, 500, 503]) {
    test(`business ${status} uses safe knowledge context and never retries POST`, async () => {
        let calls = 0;
        globalThis.fetch = async (_url, options) => { calls++; assert.equal(options.method, 'POST'); return response({ success: false, error: { code: 1007, message: 'private-sentinel' } }, status); };
        await assert.rejects(api.createKnowledgeBase({ name: 'test' }), error => error.status === status &&
            !/private-sentinel|用户名|邮箱重复|密码|认证库/.test(error.message));
        assert.equal(calls, 1);
    });
}

test('query ownership includes epoch/user/tenant/creator, no retries or retained previous key', async () => {
    globalThis.fetch = async () => response({ success: true, data: [item()] });
    const hook = mount(); await settle(); assert.equal(hook.items.value.length, 1);
    const key = ['knowledge-bases', store.epoch, 'user-a', 1, 'all'];
    const options = queryClient.getQueryCache().find({ queryKey: key }).options;
    assert.equal(options.retry, false); assert.equal(options.gcTime, 0);
    assert.equal(options.refetchOnWindowFocus, false); assert.equal(options.refetchOnReconnect, false);
    hook.creator.value = 'mine'; assert.deepEqual(hook.items.value, []); await settle();
    assert.ok(queryClient.getQueryCache().find({ queryKey: [...key.slice(0, -1), 'mine'] }));
});

for (const change of ['logout', 'expire', 'login', 'pending', 'persistence-failure']) {
    test(`${change} clears knowledge/auth cache without clearing health`, async () => {
        queryClient.setQueryData(['knowledge-bases', 0, 'user-a', 1, 'all'], [item()]);
        queryClient.setQueryData(['health'], { status: 'ok' });
        if (change === 'logout') { await session.useSession().signOut(); }
        if (change === 'expire') store.invalidateSession();
        if (change === 'login') {
            store.invalidateSession();
            globalThis.fetch = async () => response(loginResponse());
            await session.useSession().signIn({ email: 'isolated@example.com', password: 'test-only' });
        }
        if (change === 'pending') store.beginLogout();
        if (change === 'persistence-failure') {
            store.invalidateSession();
            queryClient.setQueryData(['knowledge-bases', store.epoch, 'user-a', 1, 'all'], [item()]);
            globalThis.sessionStorage.setItem = () => { throw new Error('private-storage-fault'); };
            globalThis.fetch = async () => response(loginResponse());
            await assert.rejects(session.useSession().signIn({ email: 'isolated@example.com', password: 'test-only' }));
            assert.ok(store.pendingLogout);
        }
        assert.equal(queryClient.getQueriesData({ queryKey: ['knowledge-bases'] }).length, 0);
        assert.equal(queryClient.getQueriesData({ queryKey: ['auth'] }).length, 0);
        assert.deepEqual(queryClient.getQueryData(['health']), { status: 'ok' });
    });
}

for (const outcome of ['success', 'error']) {
    for (const change of ['identity', 'filter', 'unmount']) {
        test(`late list ${outcome} after ${change} cannot restore old results`, async () => {
            const gate = deferred(); let first = true;
            globalThis.fetch = async () => { if (first) { first = false; return gate.promise; } return response({ success: true, data: [] }); };
            const hook = mount(); await settle();
            if (change === 'identity') { store.invalidateSession(); install('user-b', 2); }
            if (change === 'filter') hook.creator.value = 'others';
            if (change === 'unmount') { application.unmount(); application = undefined; }
            if (outcome === 'success') gate.resolve(response({ success: true, data: [item()] }));
            else gate.reject(new TypeError('private-late-error'));
            await settle(); assert.deepEqual(hook.items.value, []);
        });
    }
}

for (const outcome of ['success', 'error']) {
    for (const change of ['identity', 'filter', 'unmount']) {
        test(`late create ${outcome}/finally after ${change} cannot alter new draft or lock`, async () => {
            const old = deferred(), current = deferred(); let posts = 0;
            globalThis.fetch = async (_url, options) => options.method === 'POST' ? (++posts === 1 ? old.promise : current.promise) : response({ success: true, data: [] });
            const hook = mount(); await settle(); const pending = hook.submit({ name: 'old' });
            assert.equal(hook.isSubmitting.value, true);
            if (change === 'identity') { store.invalidateSession(); install('user-b', 2); }
            if (change === 'filter') hook.creator.value = 'others';
            if (change === 'unmount') { application.unmount(); application = undefined; }
            await settle();
            let newer;
            if (change === 'identity') { newer = hook.submit({ name: 'new' }); assert.equal(hook.isSubmitting.value, true); }
            const state = [hook.submitError.value, hook.isSubmitting.value];
            if (outcome === 'success') old.resolve(response({ success: true, data: item() }));
            else old.reject(new TypeError('old-network-fault'));
            assert.equal(await pending, false); await settle();
            assert.deepEqual([hook.submitError.value, hook.isSubmitting.value], state);
            if (newer) { current.resolve(response({ success: true, data: item({ creator_id: 'user-b', tenant_id: 2 }) })); assert.equal(await newer, true); }
        });
    }
}

test('synchronous duplicate submit lock, successful creation refresh failure stays distinct', async () => {
    const gate = deferred(); let posts = 0, failList = false;
    globalThis.fetch = async (_url, options) => {
        if (options.method === 'POST') { posts++; return gate.promise; }
        return response(failList ? { error: { code: 1008 } } : { success: true, data: [] }, failList ? 503 : 200);
    };
    const hook = mount(); await settle(); const pending = hook.submit({ name: 'one' });
    assert.equal(await hook.submit({ name: 'duplicate' }), false); assert.equal(posts, 1);
    failList = true; gate.resolve(response({ success: true, data: item() }));
    assert.equal(await pending, true); assert.match(hook.submitError.value, /已创建.*列表刷新未成功/);
    assert.equal(hook.isSubmitting.value, false);
});

test('uncertain POST is not resent; only successful all-list verification unlocks create', async () => {
    let posts = 0;
    globalThis.fetch = async (_url, options) => {
        if (options.method === 'POST') { posts++; throw new TypeError('lost after commit'); }
        return response({ success: true, data: [] });
    };
    const hook = mount(); await settle(); assert.equal(await hook.submit({ name: 'uncertain' }), false);
    assert.match(hook.submitError.value, /结果未确认/);
    assert.equal(await hook.submit({ name: 'again' }), false); assert.equal(posts, 1);
    hook.creator.value = 'mine'; await settle(); await hook.retryList();
    assert.equal(await hook.submit({ name: 'again' }), false); assert.equal(posts, 1);
    hook.creator.value = 'all'; await settle(); await hook.retryList();
    await hook.submit({ name: 'explicit-after-verification' }); assert.equal(posts, 2);
});

for (const reason of ['network', 'timeout', 'cancelled']) {
    test(`create ${reason} remains verification-first without retry`, async context => {
        let calls = 0;
        globalThis.fetch = async (_url, options) => {
            calls++;
            if (reason === 'network') throw new TypeError('private-network-fault');
            throw options.signal.reason || new DOMException('aborted', 'AbortError');
        };
        const controller = new AbortController();
        if (reason === 'cancelled') controller.abort();
        // Advance the existing request timeout deterministically; no real ten-second sleep.
        if (reason === 'timeout') {
            context.mock.timers.enable({ apis: ['setTimeout'] });
            globalThis.fetch = async (_url, options) => {
                calls++;
                return new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(options.signal.reason)));
            };
        }
        const pending = api.createKnowledgeBase({ name: 'test' }, controller.signal);
        if (reason === 'timeout') context.mock.timers.tick(30000);
        await assert.rejects(pending, error => error.kind === reason);
        assert.equal(calls, 1);
    });
}

test('tenant mismatch rejects list and create; pending logout disables business immediately', async () => {
    globalThis.fetch = async (_url, options) => response({ success: true,
        data: options.method === 'POST' ? item({ tenant_id: 2 }) : [item({ tenant_id: 2 })] });
    const hook = mount(); await settle();
    assert.deepEqual(hook.items.value, []); assert.equal(hook.listQuery.isError.value, true);
    assert.equal(await hook.submit({ name: 'wrong tenant' }), false); assert.match(hook.submitError.value, /未确认/);
    store.beginLogout(); assert.equal(hook.canCreate.value, false); assert.deepEqual(hook.items.value, []);
});

test('failed me disables business queries and never borrows prior identity', async () => {
    queryClient.removeQueries({ queryKey: ['auth'] }); let business = 0;
    globalThis.fetch = async url => {
        if (url.includes('knowledge-bases')) business++;
        return response({ error: { code: 1008 } }, 503);
    };
    const hook = mount(); await settle();
    assert.equal(hook.account.value, undefined); assert.equal(hook.canCreate.value, false);
    assert.deepEqual(hook.items.value, []); assert.equal(business, 0);
});
