// Existing node:test + TypeScript transpilation, no additional framework/dependencies.
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import test, { after, beforeEach } from 'node:test';
import ts from 'typescript';
import { createPinia, setActivePinia } from 'pinia';
import { QueryClient } from '@tanstack/vue-query';

const directory = await mkdtemp(join(tmpdir(), 'weknora-auth-unit-'));
const modules = ['api/client', 'api/auth', 'stores/session', 'hooks/useSession'];
for (const name of modules) {
    const source = await readFile(new URL(`../src/${name}.ts`, import.meta.url), 'utf8');
    let output = ts.transpileModule(source, { compilerOptions: {
        target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022,
    } }).outputText;
    output = output.replace(/from ['"]([^'"]+)['"]/g, (all, specifier) => {
        const local = { './client': 'api/client', '../api/client': 'api/client', '../api/auth': 'api/auth', '../stores/session': 'stores/session' }[specifier];
        return `from '${local ? pathToFileURL(join(directory, local.replace('/', '-') + '.mjs')).href : import.meta.resolve(specifier)}'`;
    });
    await writeFile(join(directory, name.replace('/', '-') + '.mjs'), output);
}
const client = await import(pathToFileURL(join(directory, 'api-client.mjs')));
const auth = await import(pathToFileURL(join(directory, 'api-auth.mjs')));
const { useSessionStore } = await import(pathToFileURL(join(directory, 'stores-session.mjs')));
const hooks = await import(pathToFileURL(join(directory, 'hooks-useSession.mjs')));
const originalFetch = globalThis.fetch;
after(async () => { globalThis.fetch = originalFetch; delete globalThis.sessionStorage; await rm(directory, { recursive: true }); });
const response = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
let storage;
beforeEach(() => {
    setActivePinia(createPinia());
    storage = new Map();
    globalThis.sessionStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) };
    globalThis.fetch = originalFetch;
});
function adapter() {
    let current = { accessToken: 'access-old', refreshToken: 'refresh-old', epoch: 1, signal: new AbortController().signal };
    let refreshes = 0; let expires = 0;
    const access = {
        snapshot: () => current,
        install: (tokens, epoch) => { if (!current || current.epoch !== epoch) return false; current = { ...current, ...tokens }; return true; },
        refresh: async () => { refreshes++; return { accessToken: 'access-new', refreshToken: 'refresh-new' }; },
        expire: epoch => { if (current?.epoch === epoch) { current = null; expires++; } },
    };
    client.configureSessionAccess(access);
    return { access, get current() { return current; }, set current(value) { current = value; }, get refreshes() { return refreshes; }, get expires() { return expires; } };
}

test('concurrent protected 401s share one refresh; each GET retried once', async () => {
    const state = adapter(); const gate = deferred(); let refreshes = 0; let requests = 0;
    state.access.refresh = async () => { refreshes++; await gate.promise; return { accessToken: 'access-new', refreshToken: 'refresh-new' }; };
    globalThis.fetch = async (_url, options) => { requests++; return response({}, options.headers.Authorization === 'Bearer access-old' ? 401 : 200); };
    const pending = [1, 2, 3].map(() => client.requestJson('/api/v1/auth/me', { authenticated: true }));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(refreshes, 1); gate.resolve(); await Promise.all(pending);
    assert.equal(requests, 6); assert.equal(state.current.refreshToken, 'refresh-new');
});

test('old delayed 401 reuses rotated access token without another refresh', async () => {
    const state = adapter(); const late = deferred(); let calls = 0;
    globalThis.fetch = async (_url, options) => {
        calls++;
        if (calls === 1) { await late.promise; return response({}, 401); }
        return response({}, options.headers.Authorization === 'Bearer access-old' ? 401 : 200);
    };
    const old = client.requestJson('/api/v1/auth/me', { authenticated: true });
    await client.requestJson('/api/v1/auth/me', { authenticated: true });
    late.resolve(); await old;
    assert.equal(state.refreshes, 1); assert.equal(calls, 4);
});

test('second protected 401 expires once and cannot loop', async () => {
    const state = adapter(); let calls = 0;
    globalThis.fetch = async () => { calls++; return response({}, 401); };
    await assert.rejects(client.requestJson('/api/v1/auth/me', { authenticated: true }), error => error.status === 401);
    assert.equal(calls, 2); assert.equal(state.refreshes, 1); assert.equal(state.expires, 1);
});

test('POST and public credential failures never trigger refresh', async () => {
    const state = adapter();
    globalThis.fetch = async () => response({}, 401);
    for (const options of [{ method: 'POST', authenticated: true }, { method: 'POST' }]) {
        await assert.rejects(client.requestJson('/api/v1/auth/login', options));
    }
    assert.equal(state.refreshes, 0);
});

test('late me response cannot cross identity epoch even if transport ignores abort', async () => {
    const state = adapter(); const gate = deferred();
    globalThis.fetch = async () => { await gate.promise; return response({ identity: 'old-test-user' }); };
    const pending = client.requestJson('/api/v1/auth/me', { authenticated: true });
    state.current = { ...state.current, epoch: 2, accessToken: 'other-user' }; gate.resolve();
    await assert.rejects(pending, error => error.kind === 'cancelled');
    assert.equal(state.current.accessToken, 'other-user');
});

test('late refresh cannot install or expire a newer session', async () => {
    const state = adapter(); const gate = deferred();
    state.access.refresh = async () => { await gate.promise; return { accessToken: 'late-access', refreshToken: 'late-refresh' }; };
    const pending = client.refreshSingleFlight(state.current);
    state.current = { ...state.current, epoch: 2, accessToken: 'other-user' }; gate.resolve();
    await assert.rejects(pending, error => error.kind === 'cancelled');
    assert.equal(state.current.accessToken, 'other-user'); assert.equal(state.expires, 0);
});

for (const status of [403, 500, 503]) {
    test(`infrastructure/permission ${status} retains credentials and never mislabels password`, async () => {
        const state = adapter(); globalThis.fetch = async () => response({ error: { code: 1007, message: 'unsafe-test-sentinel' } }, status);
        await assert.rejects(client.requestJson('/api/v1/auth/me', { authenticated: true }), error => error.status === status && !error.message.includes('unsafe-test-sentinel'));
        assert.ok(state.current); assert.equal(state.refreshes, 0); assert.equal(state.expires, 0);
    });
}

test('network errors and explicit cancellation safely classified', async () => {
    adapter(); globalThis.fetch = async () => { throw new TypeError('unsafe-test-sentinel'); };
    await assert.rejects(client.requestJson('/api/v1/auth/me', { authenticated: true }), error => error.kind === 'network' && !error.message.includes('sentinel'));
    const controller = new AbortController(); controller.abort();
    globalThis.fetch = async (_url, options) => { throw options.signal.reason; };
    await assert.rejects(client.requestJson('/api/v1/auth/me', { authenticated: true, signal: controller.signal }), error => error.kind === 'cancelled');
});

test('refresh wire DTO uses refreshToken and extracts access_token; logout explicit bearer', async () => {
    let calls = 0;
    globalThis.fetch = async (url, options) => {
        calls++;
        assert.equal(options.cache, 'no-store'); assert.equal(options.credentials, 'omit');
        if (url.endsWith('/refresh')) {
            assert.equal(options.body, JSON.stringify({ refreshToken: 'test-refresh' }));
            return response({ success: true, access_token: 'new-access', refresh_token: 'new-refresh' });
        }
        assert.equal(url, '/api/v1/auth/logout'); assert.equal(options.headers.Authorization, 'Bearer test-refresh');
        assert.equal(options.body, undefined); return response({ success: true, message: 'Logout successful' });
    };
    assert.deepEqual(await auth.refreshSession('test-refresh', new AbortController().signal), { accessToken: 'new-access', refreshToken: 'new-refresh' });
    await auth.logoutAccount('test-refresh'); assert.equal(calls, 2);
});

test('store token-only persistence, epoch cancellation and pending logout restoration', () => {
    const store = useSessionStore();
    assert.ok(store.installTokens({ accessToken: 'test-access', refreshToken: 'test-refresh' }, 0));
    const old = store.snapshot(); store.beginLogout();
    assert.ok(old.signal.aborted); assert.equal(store.snapshot(), null); assert.equal(store.accessToken, '');
    assert.equal(storage.has('weknora.auth.v1'), false); assert.equal(storage.get('weknora.auth.v1.pending-logout'), 'test-refresh');
    assert.equal(store.installTokens({ accessToken: 'late', refreshToken: 'late' }, old.epoch), false);
    setActivePinia(createPinia()); const restored = useSessionStore(); restored.restoreCredentials();
    assert.equal(restored.status, 'terminating'); assert.equal(restored.snapshot(), null);
    restored.completeLogout(); assert.equal(storage.size, 0); assert.equal(restored.status, 'anonymous');
    assert.ok(!('user' in store.$state) && !('tenant' in store.$state));
});

test('malformed persisted credentials rejected; valid restored only as unverified', () => {
    storage.set('weknora.auth.v1', JSON.stringify({ accessToken: 'x'.repeat(4097), refreshToken: 'test' }));
    const store = useSessionStore(); store.restoreCredentials(); assert.equal(store.snapshot(), null);
    assert.equal(storage.size, 0);
    storage.set('weknora.auth.v1', JSON.stringify({ accessToken: 'test-access', refreshToken: 'test-refresh' }));
    store.restoreCredentials(); assert.equal(store.status, 'restoring');
});

test('logout network failure clears auth queries not health; retry is real and unlocks login', async () => {
    const store = useSessionStore(); store.installTokens({ accessToken: 'test-access', refreshToken: 'test-refresh' }, 0);
    const queryClient = new QueryClient(); queryClient.setQueryData(['auth', 'me', 0], { username: 'old-test-user' });
    queryClient.setQueryData(['health'], { status: 'ok' });
    const navigation = []; hooks.configureSessionRuntime({ queryClient, router: { replace: async path => navigation.push(path) } });
    let attempts = 0; globalThis.fetch = async () => { attempts++; throw new TypeError('test offline'); };
    const actions = hooks.useSession(); await actions.signOut();
    assert.equal(store.snapshot(), null); assert.equal(queryClient.getQueryData(['auth', 'me', 0]), undefined);
    assert.deepEqual(queryClient.getQueryData(['health']), { status: 'ok' });
    assert.ok(actions.logoutError.value.includes('服务端撤销未确认'));
    await assert.rejects(actions.signIn({ email: 'isolated@example.com', password: 'test-only-8' }));
    globalThis.fetch = async () => { attempts++; return response({ success: true, message: 'Logout successful' }); };
    await actions.retryPendingLogout(); assert.equal(attempts, 2); assert.equal(store.pendingLogout, '');
    assert.equal(storage.size, 0); assert.equal(navigation.at(-1), '/login'); queryClient.clear();
});
