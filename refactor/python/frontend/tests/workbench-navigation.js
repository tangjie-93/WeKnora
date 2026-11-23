// Existing navigation regression updated for the frozen product-first contract.
// Playwright CLI run-code --filename=<this file>; current page must use owned Vite.
async (page) => {
    const base = new URL(page.url()).origin;
    const assert = (value, message) => { if (!value) throw new Error(message); };
    const passed = []; const errors = []; const warnings = [];
    const nav = name => page.getByRole('navigation', { name: '工作台导航' }).getByRole('link', { name, exact: true });
    const status = () => page.getByRole('status');
    const button = () => page.getByRole('button', { name: '检测后端连接', exact: true });
    const idle = async () => {
        await status().filter({ hasText: '待检测' }).waitFor();
        assert(!(await status().innerText()).includes('响应 JSON'), 'stale health response retained');
    };
    const onError = error => errors.push(error.message);
    const onConsole = message => { if (message.type() === 'warning') warnings.push(message.text()); };
    page.on('pageerror', onError); page.on('console', onConsole);
    try {
        await page.goto(base); await page.waitForURL('**/#/login');
        await page.goto(`${base}/#/health`); await page.waitForURL('**/#/workbench/health'); await idle();
        assert(await page.getByRole('main').count() === 1, 'public workbench main not unique');
        await nav('服务检测').focus(); await page.keyboard.press('Tab');
        assert(await nav('开发进度').evaluate(node => node === document.activeElement && node.matches(':focus-visible')), 'navigation Tab focus missing');
        await page.keyboard.press('Enter'); await page.waitForURL('**/#/workbench/progress');
        assert(await nav('开发进度').getAttribute('aria-current') === 'page', 'wrong active item');
        await page.goBack(); await page.waitForURL('**/#/workbench/health'); await idle();
        await page.goForward(); await page.waitForURL('**/#/workbench/progress');
        const text = await page.getByRole('main').innerText();
        for (const phrase of ['版本化静态说明', '不是实时服务或工作流状态', '知识库、上传、解析、检索、问答尚未开放', '等待用户明确继续']) assert(text.includes(phrase), `missing static boundary ${phrase}`);
        passed.push('N01 product root login; legacy public health; keyboard Tab/Enter and actual history; truthful progress');
        for (const hash of ['health', 'progress', 'task04-missing']) {
            await page.setViewportSize({ width: 375, height: 812 }); await page.goto(`${base}/#/${hash}`);
            assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${hash} mobile overflow`);
            assert(await page.getByRole('main').count() === 1, 'main not unique');
        }
        passed.push('N02 auxiliary and unknown mobile375 no overflow');
        await page.goto(`${base}/#/health`); await idle();
        await button().click(); await status().filter({ hasText: '连接成功' }).waitFor();
        try {
            await page.context().setOffline(true); await button().click(); await status().filter({ hasText: '检测失败' }).waitFor();
            assert((await status().innerText()).includes('network') && !(await status().innerText()).includes('响应 JSON'), 'offline kept stale success');
        } finally { await page.context().setOffline(false); }
        await button().click(); await status().filter({ hasText: '连接成功' }).waitFor();
        passed.push('N03 actual health/offline/manual retry, no stale success');
        await nav('开发进度').click(); await nav('服务检测').click(); await idle();
        let release; let seen;
        const gate = new Promise(resolve => { release = resolve; });
        const started = new Promise(resolve => { seen = resolve; });
        const delayed = async route => { seen(); await gate; await route.continue().catch(() => {}); };
        await page.route(`${base}/health`, delayed);
        try {
            await button().click(); await started;
            const canceled = page.waitForEvent('requestfailed', { predicate: request => request.url() === `${base}/health` });
            await nav('开发进度').click();
            assert((await canceled).failure().errorText.includes('ERR_ABORTED'), 'health transport not aborted');
            await nav('服务检测').click(); await idle();
        } finally { release(); await page.unroute(`${base}/health`, delayed); }
        passed.push('N04 real navigation aborts controlled in-flight health transport, reentry idle');
        await page.evaluate(() => {
            const original = window.fetch;
            const state = { ready: false, release: null, restore: () => { window.fetch = original; } };
            window.__task04LateHealth = state;
            window.fetch = (url, options = {}) => {
                if (String(url) !== '/health') return original(url, options);
                const { signal, ...ignoringSignal } = options;
                return new Promise((resolve, reject) => original(url, ignoringSignal).then(response => {
                    state.ready = true; state.release = () => resolve(response);
                }, reject));
            };
        });
        try {
            await button().click(); await page.waitForFunction(() => window.__task04LateHealth.ready);
            await nav('开发进度').click(); await nav('服务检测').click(); await idle();
            await page.evaluate(() => window.__task04LateHealth.release()); await idle();
        } finally { await page.evaluate(() => window.__task04LateHealth.restore()); }
        passed.push('N05 real health response withheld ignoring abort cannot pollute reentry');
        assert(errors.length === 0 && warnings.length === 0, 'application errors/Vue warnings');
        return { passed, groups: passed.length, errors, warnings, controlled: 'health response delay; signal ignoring wrapper', real: 'offline/network/manual recovery/history/focus' };
    } finally { await page.context().setOffline(false); page.off('pageerror', onError); page.off('console', onConsole); }
}
