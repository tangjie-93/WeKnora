// Playwright CLI: run-code --filename=<absolute path to this file>.
// Requires existing Vite :5400 and Python :8080; never stops either service.
// Evidence is task-local; controlled cancellation/late transport is NOT live-backend proof.
async (page) => {
    const base = 'http://127.0.0.1:5400';
    const evidence = '/Users/james/Desktop/github/WeKnora/refactor/artifacts/weknora-learning-workbench/04-e2e/output/playwright';
    const assert = (condition, message) => { if (!condition) throw new Error(message); };
    const passed = [];
    const pageErrors = [];
    const warnings = [];
    const consoleErrors = [];
    const requests = [];
    const canceled = [];
    const lateResults = [];
    const onError = error => pageErrors.push(error.message);
    const onConsole = message => {
        if (message.type() === 'warning') warnings.push(message.text());
        if (message.type() === 'error') consoleErrors.push(message.text());
    };
    const onRequest = request => requests.push({ url: request.url(), type: request.resourceType() });
    page.on('pageerror', onError);
    page.on('console', onConsole);
    page.on('request', onRequest);
    const healthCount = () => requests.filter(request => new URL(request.url).pathname === '/health').length;
    const nav = name => page.getByRole('navigation', { name: '工作台导航' }).getByRole('link', { name, exact: true });
    const status = page.getByRole('status');
    const button = () => page.getByRole('button', { name: '检测后端连接', exact: true });
    const waitText = text => page.waitForFunction(value => document.querySelector('[role="status"]')?.textContent.includes(value), text);
    const routeState = async (hash, heading, active) => {
        await page.waitForURL(`${base}/#${hash}`);
        await page.getByRole('heading', { name: heading, exact: true, level: 1 }).waitFor();
        assert(await page.getByRole('main').count() === 1, `${hash}: main is not unique`);
        assert(await page.getByRole('heading', { level: 1 }).count() === 1, `${hash}: h1 is not unique`);
        for (const name of ['服务检测', '开发进度']) {
            assert(await nav(name).getAttribute('aria-current') === (name === active ? 'page' : null), `${hash}: wrong aria-current for ${name}`);
        }
    };
    const idle = async () => {
        await waitText('待检测');
        assert(!(await status.innerText()).includes('响应 JSON'), 're-entry displayed stale JSON');
    };
    try {
        await page.setViewportSize({ width: 1280, height: 900 });
        await page.goto(base);
        await routeState('/health', '检测 Python 后端连接', '服务检测');
        await idle();
        assert(healthCount() === 0, 'root entry automatically requested health');
        passed.push('N01 root redirect; unique main/h1; exact active health; idle/no request');

        await page.keyboard.press('Tab');
        assert(await nav('服务检测').evaluate(node => node === document.activeElement && node.matches(':focus-visible') && getComputedStyle(node).outlineStyle !== 'none'), 'health navigation lacks visible Tab focus');
        await page.keyboard.press('Enter');
        await routeState('/health', '检测 Python 后端连接', '服务检测');
        await page.keyboard.press('Tab');
        assert(await nav('开发进度').evaluate(node => node === document.activeElement && node.matches(':focus-visible') && getComputedStyle(node).outlineStyle !== 'none'), 'progress navigation lacks visible Tab focus');
        await page.keyboard.press('Enter');
        await routeState('/progress', '开发进度', '开发进度');
        await page.keyboard.press('Shift+Tab');
        await page.keyboard.press('Enter');
        await routeState('/health', '检测 Python 后端连接', '服务检测');
        passed.push('N02 actual Tab/Enter activates both navigation links; visible focus');

        await page.goto(`${base}/#/progress`);
        await routeState('/progress', '开发进度', '开发进度');
        await page.reload();
        await routeState('/progress', '开发进度', '开发进度');
        await nav('服务检测').click();
        await routeState('/health', '检测 Python 后端连接', '服务检测');
        await page.goBack();
        await routeState('/progress', '开发进度', '开发进度');
        await page.goForward();
        await routeState('/health', '检测 Python 后端连接', '服务检测');
        passed.push('N03 direct hash, refresh, actual history back/forward');

        const beforeProgress = requests.length;
        await nav('开发进度').click();
        await routeState('/progress', '开发进度', '开发进度');
        const text = await page.getByRole('main').innerText();
        for (const phrase of ['版本化静态说明', '不是实时服务或工作流状态', '上一子项', '仅说明 HTTP 应用响应', '不代表数据库或模型可用', '验收结论以本任务正式审查和测试记录为准', '不表示报告已生成或验收已通过', '数据库、上传、解析、检索、问答未开始', '整个 S1 未全量验收', '本轮无后端行为变化', '暂停', '等待用户明确继续', '03-code/code-review-report.md']) {
            assert(text.includes(phrase), `missing static fact: ${phrase}`);
        }
        assert(!/\d+\s*%|所有测试通过|假trace/.test(text), 'progress invents overall completion');
        const links = await page.getByRole('main').getByRole('link').evaluateAll(nodes => nodes.map(node => node.getAttribute('href')));
        assert(links.length === 1 && links[0] === '#/health', `unexpected document/download link: ${links}`);
        await page.waitForTimeout(150);
        assert(!requests.slice(beforeProgress).some(request => ['fetch', 'xhr'].includes(request.type) || /\/api(?:\/|$)|\/health$|workflow-state|artifacts\//.test(new URL(request.url).pathname)), 'progress fetched API/state/evidence');
        assert(healthCount() === 0, 'navigation triggered health requests');
        await page.screenshot({ path: `${evidence}/navigation-progress-desktop.png`, fullPage: true });
        passed.push('N04 truthful static scope/history/evidence; no API/state fetch or fake download');

        await page.evaluate(() => { location.hash = '/task04-missing'; });
        await routeState('/task04-missing', '未找到页面', null);
        await page.getByRole('link', { name: '返回服务检测', exact: true }).click();
        await routeState('/health', '检测 Python 后端连接', '服务检测');
        await idle();
        passed.push('N05 unknown hash retained, no active nav, explicit recovery to idle health');

        const widths = [];
        await page.setViewportSize({ width: 375, height: 812 });
        for (const [hash, heading, active] of [['/health', '检测 Python 后端连接', '服务检测'], ['/progress', '开发进度', '开发进度'], ['/task04-missing', '未找到页面', null]]) {
            await page.evaluate(hash => { location.hash = hash; }, hash);
            await routeState(hash, heading, active);
            const width = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
            assert(width.scroll <= width.width, `${hash}: mobile horizontal overflow ${JSON.stringify(width)}`);
            widths.push({ hash, ...width });
            await page.screenshot({ path: `${evidence}/navigation-${hash.slice(1)}-375.png`, fullPage: true });
        }
        await page.setViewportSize({ width: 1280, height: 900 });
        await nav('服务检测').click();
        await idle();
        passed.push({ name: 'N06 three routes at 375px; landmarks/current item; no horizontal overflow', widths });

        const initialCount = healthCount();
        const other = await page.context().newPage();
        try {
            await other.goto('about:blank');
            await other.bringToFront();
            await page.context().setOffline(true);
            await page.context().setOffline(false);
            await page.bringToFront();
        } finally { await other.close(); }
        await page.waitForTimeout(200);
        assert(healthCount() === initialCount, 'focus/reconnect initiated health request');
        await idle();
        passed.push('N07 actual tab focus and browser offline/online reconnect do not auto-request');

        const direct = await page.request.get('http://127.0.0.1:8080/health');
        assert(direct.status() === 200 && direct.headers()['x-weknora-implementation'] === 'python-fastapi', 'actual Python backend unavailable');
        const responsePromise = page.waitForResponse(`${base}/health`);
        await button().click();
        const live = await responsePromise;
        await waitText('连接成功');
        assert(live.status() === 200 && live.request().method() === 'GET' && live.headers()['x-weknora-implementation'] === 'python-fastapi', 'live proxy contract mismatch');
        assert(JSON.stringify(await live.json()) === '{"status":"ok"}', 'unexpected live backend JSON');
        const afterSuccess = healthCount();
        try {
            await page.context().setOffline(true);
            await button().click();
            await waitText('检测失败');
            const failedText = await status.innerText();
            assert(failedText.includes('失败分类：network') && !failedText.includes('响应 JSON'), 'real offline failure retained success');
            assert(!await button().isDisabled(), 'real failure blocked retry');
            await page.screenshot({ path: `${evidence}/navigation-real-offline.png`, fullPage: true });
        } finally { await page.context().setOffline(false); }
        await page.waitForTimeout(150);
        assert(healthCount() === afterSuccess + 1, 'reconnect retried automatically');
        const recoveryPromise = page.waitForResponse(`${base}/health`);
        await button().click();
        const recovery = await recoveryPromise;
        await waitText('连接成功');
        assert(recovery.status() === 200 && recovery.headers()['x-weknora-implementation'] === 'python-fastapi', 'real recovery not Python 200');
        await page.screenshot({ path: `${evidence}/navigation-real-recovery.png`, fullPage: true });
        await nav('开发进度').click();
        await nav('服务检测').click();
        await idle();
        passed.push('N08 live 5400->8080 success; actual browser offline failure; manual live recovery; successful state resets on re-entry');

        for (const target of ['/progress', '/task04-missing']) {
            let release;
            const gate = new Promise(resolve => { release = resolve; });
            let started;
            const seen = new Promise(resolve => { started = resolve; });
            const handler = async route => { started(); await gate; await route.continue().catch(() => {}); };
            await page.route(`${base}/health`, handler);
            try {
                await button().click();
                await seen;
                await waitText('请求中');
                const failed = page.waitForEvent('requestfailed', { predicate: request => request.url() === `${base}/health`, timeout: 3000 });
                await page.evaluate(hash => { location.hash = hash; }, target);
                await routeState(target, target === '/progress' ? '开发进度' : '未找到页面', target === '/progress' ? '开发进度' : null);
                await nav('服务检测').click();
                await idle();
                const aborted = await failed;
                assert(aborted.failure()?.errorText.includes('ERR_ABORTED'), `not canceled on ${target}: ${aborted.failure()?.errorText}`);
                canceled.push({ target, failure: aborted.failure()?.errorText });
                passed.push(`${target === '/progress' ? 'N09' : 'N10'} controlled in-flight route exit aborts transport; immediate re-entry idle`);
            } finally {
                release();
                await page.unroute(`${base}/health`, handler);
            }
        }

        for (const target of ['/progress', '/task04-missing']) {
            await page.evaluate(() => {
                const original = window.fetch;
                const state = { started: 0, aborted: 0, resolved: 0, ready: false, release: null, restore: () => { window.fetch = original; } };
                window.__task04Late = state;
                window.fetch = (url, options = {}) => {
                    if (new URL(String(url), location.href).pathname !== '/health') return original(url, options);
                    state.started++;
                    options.signal?.addEventListener('abort', () => { state.aborted++; }, { once: true });
                    const { signal, ...ignoringSignal } = options;
                    return new Promise((resolve, reject) => {
                        // Fetch a real response, but intentionally withhold it and ignore abort.
                        original(url, ignoringSignal).then(response => {
                            state.ready = true;
                            state.release = () => { state.resolved++; resolve(response); };
                        }, reject);
                    });
                };
            });
            try {
                await button().click();
                await waitText('请求中');
                await page.waitForFunction(() => window.__task04Late.ready);
                await page.evaluate(hash => { location.hash = hash; }, target);
                await routeState(target, target === '/progress' ? '开发进度' : '未找到页面', target === '/progress' ? '开发进度' : null);
                await nav('服务检测').click();
                await idle();
                const beforeRelease = healthCount();
                await page.evaluate(() => window.__task04Late.release());
                await page.waitForTimeout(100);
                await idle();
                const stats = await page.evaluate(() => ({ started: window.__task04Late.started, aborted: window.__task04Late.aborted, resolved: window.__task04Late.resolved }));
                assert(stats.started === 1 && stats.aborted === 1 && stats.resolved === 1, `late scenario invalid: ${JSON.stringify(stats)}`);
                assert(healthCount() === beforeRelease, 'late completion caused extra request');
                lateResults.push({ target, ...stats });
                passed.push(`${target === '/progress' ? 'N11' : 'N12'} explicit signal-ignoring late response injection cannot pollute rapid re-entry`);
            } finally { await page.evaluate(() => { window.__task04Late.restore(); delete window.__task04Late; }); }
        }
        await page.reload();
        await idle();
        assert(pageErrors.length === 0, `application errors: ${pageErrors}`);
        assert(warnings.length === 0, `console warnings: ${warnings}`);
        const unexplained = consoleErrors.filter(text => !/net::ERR_INTERNET_DISCONNECTED|net::ERR_ABORTED|404 \(Not Found\)/.test(text));
        assert(unexplained.length === 0, `unexplained console errors: ${unexplained}`);
        passed.push('N13 zero application errors/Vue warnings; expected offline/favicon diagnostics separated; final reload idle');
        return { passed, groups: passed.length, canceled, lateResults, healthRequests: healthCount(), pageErrors, warnings, consoleErrors, finishedAt: new Date().toISOString(), entrypoint: page.url() };
    } finally {
        await page.context().setOffline(false);
        page.off('pageerror', onError);
        page.off('console', onConsole);
        page.off('request', onRequest);
    }
}
