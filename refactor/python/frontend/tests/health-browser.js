// Playwright CLI: run-code --filename=<absolute path to this file>.
// Open the CLI session from the workspace root; keep both actual dev servers running.
async (page) => {
    const evidenceDir = '/Users/james/Desktop/github/WeKnora/refactor/artifacts/weknora-python-vue3-rebuild/04-e2e/output/playwright';
    const assert = (condition, message) => { if (!condition) throw new Error(message); };
    const passed = [];
    let timeoutMs;
    const errors = [];
    const warnings = [];
    const healthRequests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'warning') warnings.push(message.text()); });
    page.on('request', request => {
        if (new URL(request.url()).pathname === '/health') healthRequests.push(request);
    });
    const status = page.getByRole('status');
    const button = page.getByRole('button', { name: '检测后端连接' });
    const waitText = async text => {
        await page.waitForFunction(value => document.querySelector('[role="status"]')?.textContent.includes(value), text);
    };
    await page.goto('http://127.0.0.1:5400');
    await page.waitForTimeout(300);
    assert(healthRequests.length === 0, 'initial page made health request');
    assert((await status.innerText()).includes('待检测'), 'initial state not idle');
    assert(await status.getAttribute('aria-live') === 'polite', 'missing live region');
    passed.push('initial idle; zero automatic health requests; semantic status');

    await page.keyboard.press('Tab');
    assert(await button.evaluate(node => node === document.activeElement), 'Tab did not focus check button');
    const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === '/health');
    await page.keyboard.press('Enter');
    const response = await responsePromise;
    await waitText('连接成功');
    assert(response.url() === 'http://127.0.0.1:5400/health', 'request not same-origin');
    assert(response.request().method() === 'GET', 'method not GET');
    assert(response.status() === 200, 'real request not 200');
    assert(response.headers()['x-weknora-implementation'] === 'python-fastapi', 'wrong real implementation');
    assert(JSON.stringify(await response.json()) === '{"status":"ok"}', 'wrong actual JSON');
    assert(healthRequests.length === 1, 'keyboard triggered duplicate request');
    await page.screenshot({ path: `${evidenceDir}/success.png`, fullPage: true });
    passed.push('real keyboard Tab/Enter -> same-origin Vite -> Python 200/header/exact JSON');

    let release;
    const gate = new Promise(resolve => { release = resolve; });
    await page.route('**/health', async route => { await gate; await route.continue(); });
    await button.click();
    await waitText('请求中');
    assert(await page.getByRole('button', { name: '正在检测…' }).isDisabled(), 'checking button not disabled');
    assert(!(await status.innerText()).includes('响应 JSON'), 'checking leaked stale success');
    await page.getByRole('button', { name: '正在检测…' }).evaluate(node => { node.click(); node.click(); });
    assert(healthRequests.length === 2, 'duplicate while checking');
    release();
    await waitText('连接成功');
    await page.unroute('**/health');
    passed.push('controlled delay with real forwarding: disabled, duplicate prevention, stale success hidden');

    for (const fault of ['network', 'http', 'protocol', 'timeout']) {
        await page.route('**/health', async route => {
            if (fault === 'network') return route.abort('failed');
            if (fault === 'http') return route.fulfill({ status: 503, contentType: 'text/html', body: '<h1>UNSAFE_SENTINEL</h1>' });
            if (fault === 'protocol') return route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"ok"}' });
            // Intentionally hung network; abort after observed timeout via unrouteAll below.
        });
        const start = Date.now();
        await button.click();
        await waitText('检测失败');
        const text = await status.innerText();
        assert(text.includes(`失败分类：${fault}`), `wrong classification: ${text}`);
        assert(!text.includes('响应 JSON') && !text.includes('UNSAFE_SENTINEL'), 'unsafe body or stale success displayed');
        if (fault === 'timeout') {
            const elapsed = Date.now() - start;
            assert(elapsed >= 4900 && elapsed < 7000, `browser timeout ${elapsed}ms`);
            timeoutMs = elapsed;
        }
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        if (fault === 'http') await page.screenshot({ path: `${evidenceDir}/injected-http-failure.png`, fullPage: true });
        passed.push(`explicit browser injection ${fault}: safe failure, old success hidden, no retry`);
    }
    await button.click();
    await waitText('连接成功');
    const count = healthRequests.length;
    await page.evaluate(() => {
        window.dispatchEvent(new Event('focus'));
        window.dispatchEvent(new Event('offline'));
        window.dispatchEvent(new Event('online'));
        document.dispatchEvent(new Event('visibilitychange'));
    });
    const otherTab = await page.context().newPage();
    await otherTab.goto('about:blank');
    await otherTab.bringToFront();
    await page.context().setOffline(true);
    await page.context().setOffline(false);
    await page.bringToFront();
    await otherTab.close();
    await page.waitForTimeout(300);
    assert(healthRequests.length === count, 'focus/reconnect caused automatic refetch');
    await page.reload();
    await waitText('待检测');
    assert(healthRequests.length === count, 'reload made automatic health request');
    passed.push('real recovery; no focus/reconnect retry; reload returns idle with zero requests');

    const hookResults = await page.evaluate(async () => {
        const { createApp, h, nextTick } = await import('/node_modules/.vite/deps/vue.js');
        const { QueryClient, VueQueryPlugin } = await import('/node_modules/.vite/deps/@tanstack_vue-query.js');
        const { useHealthCheck } = await import('/src/views/health/hooks/useHealthCheck.ts');
        const originalFetch = window.fetch;
        const pending = [];
        let calls = 0;
        const check = (condition, message) => { if (!condition) throw new Error(message); };
        window.fetch = (_url, { signal }) => {
            calls++;
            // Deliberately ignore abort to model a late transport completion.
            return new Promise(resolve => pending.push({ signal, resolve }));
        };
        const successResponse = () => new Response('{"status":"ok"}', { headers: {
            'Content-Type': 'application/json', 'X-WeKnora-Implementation': 'python-fastapi',
        } });
        const client = new QueryClient();
        let hook;
        const mount = () => {
            const root = document.createElement('div'); document.body.append(root);
            const app = createApp({ setup() { hook = useHealthCheck(); return () => h('div'); } });
            app.use(VueQueryPlugin, { queryClient: client }); app.mount(root);
            return () => { app.unmount(); root.remove(); };
        };
        let unmount = mount();
        const results = [];
        try {
            await nextTick();
            check(calls === 0 && hook.state.value === 'idle', 'hook auto-fetch on mount');
            const first = hook.check();
            await Promise.all([hook.check(), hook.check()]);
            await nextTick();
            check(calls === 1 && hook.state.value === 'checking', 'hook synchronous duplicate guard');
            const old = hook;
            unmount();
            check(pending[0].signal.aborted, 'unmount did not abort network');
            await first;
            const callsBefore = calls;
            await old.check();
            check(calls === callsBefore, 'disposed hook could start new request');
            unmount = mount();
            await nextTick();
            check(hook.state.value === 'idle' && !hook.result.value && !hook.error.value, 'remount not fresh idle');
            pending[0].resolve(successResponse());
            await new Promise(resolve => setTimeout(resolve, 30));
            await nextTick();
            check(hook.state.value === 'idle' && !hook.result.value && !hook.error.value, 'old late response polluted remount');
            results.push('hook mount idle; synchronous duplicate check; unmount abort; disposed check ignored; remount/late response isolated');
            const second = hook.check();
            pending[1].resolve(successResponse());
            await second; await nextTick();
            check(hook.state.value === 'success' && hook.result.value?.status === 'ok' && hook.checkedAt.value > 0, 'remount success failed');
            const third = hook.check();
            await nextTick();
            check(hook.state.value === 'checking' && !hook.result.value && !hook.checkedAt.value, 'hook checking retained old success');
            pending[2].resolve(new Response('unsafe', { status: 500 }));
            await third; await nextTick();
            check(hook.state.value === 'failure' && !hook.result.value && hook.error.value?.kind === 'http' && hook.checkedAt.value > 0,
                'hook failure exposed stale success');
            results.push('hook actual vue-query terminal timestamps; checking/failure hide cached success');
            return results;
        } finally {
            unmount(); client.clear(); window.fetch = originalFetch;
        }
    });
    passed.push(...hookResults);
    await page.getByText('查看源码方法与请求原理', { exact: true }).click();
    assert(await page.getByText('python/backend/app/main.py · create_app() / health()', { exact: true }).isVisible(), 'explanation not usable');
    for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
        await page.setViewportSize(viewport);
        assert(await button.isVisible(), 'button not visible');
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
        assert(!overflow, `horizontal overflow at ${viewport.width}`);
    }
    await page.screenshot({ path: `${evidenceDir}/mobile.png`, fullPage: true });
    await page.setViewportSize({ width: 1280, height: 900 });
    assert(healthRequests.length === 7, `unexpected retry or automatic request count: ${healthRequests.length}`);
    assert(errors.length === 0, `uncaught application errors ${errors}`);
    assert(warnings.length === 0, `console warnings ${warnings}`);
    passed.push('learning disclosure, desktop/mobile layout without overflow, zero uncaught errors/warnings');
    return { passed, checks: passed.length, timeoutMs, applicationErrors: errors, warnings, healthRequests: healthRequests.length };
}
