// Playwright CLI run-code --filename=<this file>. Requires owned services from
// backend/tests/auth_browser_services.py; uses real API except explicit fault injection.
async (page) => {
    const base = new URL(page.url()).origin;
    const evidence = '/Users/james/Desktop/github/WeKnora/refactor/artifacts/weknora-product-auth/04-e2e/output/playwright';
    const assert = (value, message) => { if (!value) throw new Error(message); };
    const passed = []; const errors = []; const warnings = []; const consoleErrors = []; const requests = [];
    const onError = error => errors.push(error.message);
    const onConsole = message => { if (message.type() === 'warning') warnings.push(message.text()); if (message.type() === 'error') consoleErrors.push(message.text()); };
    const onRequest = request => requests.push({ path: new URL(request.url()).pathname, method: request.method() });
    page.on('pageerror', onError); page.on('console', onConsole); page.on('request', onRequest);
    const email = 'task04-product@example.com'; const password = 'Isolated-browser-8';
    const ready = () => page.getByRole('heading', { name: '你好，Task04 Product', exact: true }).waitFor();
    const noOverflow = async () => assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'horizontal overflow');
    try {
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto(`${base}/#/register`);
        await page.screenshot({ path: `${evidence}/register-desktop.png` });
        assert(await page.getByRole('main').count() === 1, 'registration main not unique');
        await page.getByLabel('用户名', { exact: true }).fill('Task04 Product');
        await page.getByLabel('邮箱', { exact: true }).fill(email);
        await page.getByLabel('密码', { exact: true }).fill(password);
        await page.getByLabel('确认密码', { exact: true }).fill('Mismatch-8');
        await page.getByRole('button', { name: '创建账户', exact: true }).click();
        assert(await page.getByLabel('确认密码').getAttribute('aria-invalid') === 'true', 'confirmation not marked invalid');
        assert(await page.getByLabel('确认密码').getAttribute('aria-describedby') === 'confirm-error', 'confirmation error unassociated');
        assert(requests.filter(item => item.path.endsWith('/register')).length === 0, 'invalid registration submitted');
        passed.push('UI01 labeled fields, mismatched confirmation accessible, no invalid API submission');
        await page.getByLabel('确认密码').fill(password);
        await page.getByLabel('确认密码').press('Enter');
        await page.waitForURL('**/#/login');
        assert(await page.getByRole('status').innerText().then(text => text.includes('注册成功')), 'no registration success');
        assert(await page.getByLabel('密码', { exact: true }).inputValue() === '', 'password retained');
        assert(!page.url().includes(email), 'email in URL');
        passed.push('UI02 actual keyboard registration201 creates account then login, password cleared');
        await page.getByLabel('密码', { exact: true }).fill('Wrong-test-8');
        await page.getByRole('button', { name: '登录', exact: true }).click();
        await page.getByRole('alert').waitFor();
        assert((await page.getByRole('alert').innerText()).includes('邮箱或密码不正确'), 'wrong password feedback missing');
        assert(await page.getByLabel('密码', { exact: true }).getAttribute('aria-describedby') === 'login-error', 'login error unassociated');
        passed.push('UI03 real incorrect credentials401 safe visible feedback');
        await page.getByLabel('密码', { exact: true }).fill(password);
        let first = true;
        const networkFault = async route => { if (first) { first = false; await route.abort('failed'); } else await route.continue(); };
        await page.route('**/api/v1/auth/me', networkFault);
        const beforeLogin = requests.filter(item => item.path.endsWith('/login')).length;
        await page.getByLabel('密码', { exact: true }).press('Enter');
        await page.waitForURL('**/#/account');
        await page.getByRole('button', { name: '重试读取账户' }).waitFor();
        assert(await page.getByRole('heading', { name: '你好，Task04 Product' }).count() === 0, 'network error displayed identity');
        await page.getByRole('button', { name: '重试读取账户' }).click(); await ready();
        await page.unroute('**/api/v1/auth/me', networkFault);
        assert(requests.filter(item => item.path.endsWith('/login')).length === beforeLogin + 1, 'retry resubmitted password');
        passed.push('UI04 CR003 first-me network failure retry with existing session, exactly one login');
        for (const status of [500, 503, 403]) {
            const fault = route => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ success: false, error: { code: status === 403 ? 1002 : 1007, message: 'test fault', details: null } }) });
            await page.route('**/api/v1/auth/me', fault); await page.reload();
            await page.getByRole('button', { name: '重试读取账户' }).waitFor();
            assert(await page.getByRole('heading', { name: '你好，Task04 Product' }).count() === 0, 'failed me leaked cached identity');
            assert(await page.getByRole('button', { name: '退出登录' }).first().isVisible(), 'failed me has no logout');
            await page.unroute('**/api/v1/auth/me', fault);
            await page.getByRole('button', { name: '重试读取账户' }).click(); await ready();
            passed.push(`UI05-${status} CR003 reload first-me${status} retry without password login`);
        }
        const nullable = async route => {
            const response = await route.fetch(); const data = await response.json();
            for (const key of ['avatar', 'created_at', 'updated_at']) data.data.user[key] = null;
            for (const key of ['description', 'created_at', 'updated_at']) data.data.tenant[key] = null;
            await route.fulfill({ response, json: data });
        };
        await page.route('**/api/v1/auth/me', nullable); await page.reload(); await ready();
        assert(await page.getByText('未提供', { exact: true }).count() === 2, 'nullable dates not safely rendered');
        await page.unroute('**/api/v1/auth/me', nullable);
        passed.push('UI06 CR004 nullable user/tenant accepted, two absent date fallbacks');
        const originalHash = new URL(page.url()).hash;
        await page.getByRole('link', { name: '跳至主要内容' }).focus(); await page.keyboard.press('Enter');
        assert(await page.evaluate(() => document.activeElement.id) === 'product-content', 'skip link did not focus main');
        assert(new URL(page.url()).hash === originalHash, 'skip link changed business hash');
        passed.push('UI07 CR005 keyboard skip focuses main and preserves account hash');
        await page.reload(); await ready();
        assert((await page.getByRole('main').innerText()).includes("Task04 Product's Workspace"), 'not real workspace');
        const nav = page.getByRole('navigation', { name: '主导航' });
        assert(await nav.getByRole('link').count() === 2, 'extra unsupported product modules');
        await noOverflow(); await page.screenshot({ path: `${evidence}/account-desktop.png` });
        passed.push('UI08 real me account/owner/workspace, reload restoration and desktop1440 product layout');
        await page.setViewportSize({ width: 375, height: 812 }); await noOverflow();
        await page.getByRole('button', { name: '菜单', exact: true }).click();
        assert(await page.getByRole('button', { name: '菜单', exact: true }).getAttribute('aria-expanded') === 'true', 'mobile nav not opened');
        await page.keyboard.press('Escape');
        assert(await page.getByRole('button', { name: '菜单', exact: true }).evaluate(node => node === document.activeElement), 'Escape lost mobile focus');
        await page.screenshot({ path: `${evidence}/account-mobile.png` });
        passed.push('UI09 mobile375 no overflow, menu/Escape focus return');
        await page.setViewportSize({ width: 1440, height: 900 });
        for (const [old, target, heading] of [['health', 'health', '检测 Python 后端连接'], ['progress', 'progress', '开发进度']]) {
            await page.goto(`${base}/#/${old}`); await page.waitForURL(`**/#/workbench/${target}`);
            await page.getByRole('heading', { name: heading, exact: true, level: 1 }).waitFor();
            assert(await page.getByRole('main').count() === 1, 'workbench duplicated main');
        }
        await page.goto(`${base}/#/health`); await page.getByRole('button', { name: '检测后端连接', exact: true }).waitFor();
        assert((await page.getByRole('status').innerText()).includes('待检测'), 'health auto requested');
        const liveHealth = page.waitForResponse(`${base}/health`);
        await page.getByRole('button', { name: '检测后端连接', exact: true }).click();
        assert((await liveHealth).headers()['x-weknora-implementation'] === 'python-fastapi', 'health proxy not Python');
        await page.getByRole('status').filter({ hasText: '连接成功' }).waitFor();
        passed.push('UI10 auxiliary-only workbench, old hash redirects, actual health proxy');
        await page.goto(`${base}/#/account`); await ready();
        const force403 = route => route.fulfill({ status: 403, contentType: 'application/json', body: '{"success":false,"error":{"code":1002,"message":"test","details":null}}' });
        await page.route('**/api/v1/auth/me', force403); await page.reload();
        await page.getByRole('heading', { name: '当前空间不可用' }).waitFor();
        const oldToken = await page.evaluate(() => JSON.parse(sessionStorage.getItem('weknora.auth.v1')).accessToken);
        const logoutResponse = page.waitForResponse('**/api/v1/auth/logout');
        await page.getByRole('button', { name: '退出登录' }).first().click();
        assert((await logoutResponse).status() === 200, '403 logout did not reach server');
        await page.waitForURL('**/#/login'); await page.unroute('**/api/v1/auth/me', force403);
        assert((await page.request.get(`${base}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${oldToken}` } })).status() === 401, 'old token still usable');
        assert(await page.evaluate(() => sessionStorage.getItem('weknora.auth.v1')) === null, 'credentials not cleared');
        passed.push('UI11 CR003 persistent403 real logout, server rejects old token, browser credentials cleared');
        await page.goto(`${base}/#/account`); await page.waitForURL('**/#/login');
        await page.screenshot({ path: `${evidence}/login-desktop.png` });
        await page.setViewportSize({ width: 375, height: 812 }); await page.goto(`${base}/#/register`); await noOverflow();
        await page.screenshot({ path: `${evidence}/register-mobile.png` });
        await page.goto(`${base}/#/login`); await noOverflow();
        await page.getByLabel('邮箱', { exact: true }).fill(email); await page.getByLabel('密码', { exact: true }).fill(password);
        await page.getByLabel('密码', { exact: true }).press('Enter'); await ready();
        passed.push('UI12 unauthenticated route protected, mobile registration/login, actual relogin leaves session for restart');
        assert(errors.length === 0 && warnings.length === 0, 'application errors or Vue warnings');
        const unexpected = consoleErrors.filter(text => !/401|403|500|503|net::ERR_FAILED/.test(text));
        assert(unexpected.length === 0, `unexpected console errors ${unexpected}`);
        return { passed, groups: passed.length, errors, warnings, expectedConsoleErrorCount: consoleErrors.length,
            live: 'register/login/me/health/logout and old-token rejection', injected: 'first-me network/500/503/403 and nullable',
            requests: requests.reduce((counts, item) => { counts[`${item.method} ${item.path}`] = (counts[`${item.method} ${item.path}`] || 0) + 1; return counts; }, {}) };
    } finally { page.off('pageerror', onError); page.off('console', onConsole); page.off('request', onRequest); }
}
