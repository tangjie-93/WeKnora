// Run: node --test tests/health-api.test.mjs (uses the existing TypeScript compiler).
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const source = await readFile(new URL('../src/api/health.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
}).outputText;
const { fetchHealth, HealthCheckError } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const headers = { 'Content-Type': 'application/json', 'X-WeKnora-Implementation': 'python-fastapi' };
const response = (body = '{"status":"ok"}', options = {}) => new Response(body, { headers, ...options });

async function withFetch(mock, body) {
    const original = globalThis.fetch;
    globalThis.fetch = mock;
    try { await body(); } finally { globalThis.fetch = original; }
}

async function rejectsKind(promise, kind, status) {
    await assert.rejects(promise, (error) => {
        assert.ok(error instanceof HealthCheckError);
        assert.equal(error.kind, kind);
        assert.equal(error.status, status);
        assert.ok(!error.message.includes('UNSAFE_SENTINEL'));
        return true;
    });
}

test('exact response, relative URL, no-store, forwarded signal', async () => {
    await withFetch(async (url, options) => {
        assert.equal(url, '/health');
        assert.equal(options.cache, 'no-store');
        assert.ok(options.signal instanceof AbortSignal);
        return response();
    }, async () => assert.deepEqual(await fetchHealth(), {
        status: 'ok', httpStatus: 200, implementation: 'python-fastapi',
    }));
});

test('case-insensitive JSON media type with charset accepted', async () => {
    await withFetch(async () => response(undefined, { headers: {
        ...headers, 'Content-Type': ' Application/JSON ; charset=utf-8',
    } }), async () => assert.equal((await fetchHealth()).status, 'ok'));
});

for (const [name, body, overrides] of [
    ['malformed JSON', '{', {}],
    ['null', 'null', {}],
    ['array', '[{"status":"ok"}]', {}],
    ['string', '"ok"', {}],
    ['number', '1', {}],
    ['empty object', '{}', {}],
    ['wrong status', '{"status":"down"}', {}],
    ['wrong status type', '{"status":true}', {}],
    ['extra field', '{"status":"ok","extra":true}', {}],
    ['envelope', '{"success":true,"data":{"status":"ok"}}', {}],
    ['HTML', '<h1>UNSAFE_SENTINEL</h1>', { headers: { ...headers, 'Content-Type': 'text/html' } }],
    ['missing content type', '{"status":"ok"}', { headers: { 'X-WeKnora-Implementation': 'python-fastapi' } }],
    ['wrong JSON media type', '{"status":"ok"}', { headers: { ...headers, 'Content-Type': 'application/problem+json' } }],
    ['missing identity', '{"status":"ok"}', { headers: { 'Content-Type': 'application/json' } }],
    ['wrong identity', '{"status":"ok"}', { headers: { ...headers, 'X-WeKnora-Implementation': 'go' } }],
]) {
    test(`protocol rejects ${name}`, async () => {
        await withFetch(async () => response(body, overrides), async () => rejectsKind(fetchHealth(), 'protocol'));
    });
}

for (const status of [201, 404, 405, 500, 503]) {
    test(`HTTP ${status} takes priority over unsafe non-JSON body`, async () => {
        await withFetch(async () => response('UNSAFE_SENTINEL', { status, headers: { 'Content-Type': 'text/html' } }),
            async () => rejectsKind(fetchHealth(), 'http', status));
    });
}

test('network rejection uses safe diagnostic', async () => {
    await withFetch(async () => { throw new TypeError('UNSAFE_SENTINEL'); },
        async () => rejectsKind(fetchHealth(), 'network'));
});

test('explicit and already-aborted cancellation preserve reason, never timeout', async () => {
    await withFetch((_url, { signal }) => new Promise((_resolve, reject) => {
        if (signal.aborted) reject(signal.reason);
        else signal.addEventListener('abort', () => reject(signal.reason), { once: true });
    }), async () => {
        for (const alreadyAborted of [false, true]) {
            const controller = new AbortController();
            const reason = new DOMException('test cancellation', 'AbortError');
            if (alreadyAborted) controller.abort(reason);
            const promise = fetchHealth(controller.signal);
            if (!alreadyAborted) controller.abort(reason);
            await assert.rejects(promise, (error) => error === reason);
        }
    });
});

test('late body completion after cancellation cannot become success', async () => {
    const controller = new AbortController();
    let release;
    await withFetch(async () => ({ status: 200, headers: new Headers(headers),
        json: () => new Promise((resolve) => { release = resolve; }),
    }), async () => {
        const promise = fetchHealth(controller.signal);
        await Promise.resolve();
        const reason = new DOMException('disposed', 'AbortError');
        controller.abort(reason);
        release({ status: 'ok' });
        await assert.rejects(promise, (error) => error === reason);
    });
});

test('real 5000ms timeout aborts hung fetch', async () => {
    await withFetch((_url, { signal }) => new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(signal.reason), { once: true });
    }), async () => {
        const start = performance.now();
        await rejectsKind(fetchHealth(), 'timeout');
        const elapsed = performance.now() - start;
        assert.ok(elapsed >= 4900 && elapsed < 6500, `timeout took ${elapsed}ms`);
        console.log(`Measured timeout: ${elapsed.toFixed(0)}ms`);
    });
});

test('timer and external abort listener cleaned on success and failure', async () => {
    const originalSet = globalThis.setTimeout;
    const originalClear = globalThis.clearTimeout;
    const pending = new Set();
    globalThis.setTimeout = (...args) => { const id = originalSet(...args); pending.add(id); return id; };
    globalThis.clearTimeout = (id) => { pending.delete(id); originalClear(id); };
    try {
        for (const failure of [false, true]) {
            const controller = new AbortController();
            let adds = 0; let removes = 0;
            const add = controller.signal.addEventListener.bind(controller.signal);
            const remove = controller.signal.removeEventListener.bind(controller.signal);
            controller.signal.addEventListener = (...args) => { adds++; return add(...args); };
            controller.signal.removeEventListener = (...args) => { removes++; return remove(...args); };
            await withFetch(async () => { if (failure) throw new TypeError('offline'); return response(); }, async () => {
                if (failure) await rejectsKind(fetchHealth(controller.signal), 'network');
                else await fetchHealth(controller.signal);
            });
            assert.equal(adds, 1); assert.equal(removes, 1); assert.equal(pending.size, 0);
        }
    } finally {
        for (const id of pending) originalClear(id);
        globalThis.setTimeout = originalSet; globalThis.clearTimeout = originalClear;
    }
});
