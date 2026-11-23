// Last small UI-only boundaries; current page must be on owned Vite and anonymous.
async (page) => {
    const base = new URL(page.url()).origin;
    const assert = (value, message) => { if (!value) throw new Error(message); };
    const passed = [];
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`${base}/#/register`);
    await page.getByLabel('用户名', { exact: true }).fill('Task04 Product');
    await page.getByLabel('邮箱', { exact: true }).fill('task04-product@example.com');
    await page.getByLabel('密码', { exact: true }).fill('Isolated-browser-8');
    await page.getByLabel('确认密码', { exact: true }).fill('Isolated-browser-8');
    await page.getByLabel('确认密码', { exact: true }).press('Enter');
    await page.getByRole('alert').filter({ hasText: '用户名或邮箱已被使用' }).waitFor();
    assert(await page.getByRole('button', { name: '创建账户', exact: true }).isEnabled(), 'duplicate registration blocked retry');
    passed.push('E01 actual duplicate400 safe UI feedback and retry remains available');
    await page.goto(`${base}/#/login`);
    await page.getByLabel('邮箱', { exact: true }).fill('task04-product@example.com');
    await page.getByLabel('密码', { exact: true }).fill('Isolated-browser-8');
    let release; let seen; let completed;
    const gate = new Promise(resolve => { release = resolve; });
    const started = new Promise(resolve => { seen = resolve; });
    const handled = new Promise(resolve => { completed = resolve; });
    const delayed = async route => { seen(); await gate; await route.continue(); completed(); };
    await page.route('**/api/v1/auth/login', delayed);
    try {
        await page.getByLabel('密码', { exact: true }).press('Enter'); await started;
        assert(await page.getByRole('button', { name: '正在验证账户…', exact: true }).isDisabled(), 'loading submit enabled');
        assert(await page.locator('form').getAttribute('aria-busy') === 'true', 'loading not accessible');
        assert(await page.getByLabel('邮箱', { exact: true }).isDisabled(), 'duplicate submit fields enabled');
    } finally { release(); await handled; await page.unroute('**/api/v1/auth/login', delayed); }
    await page.getByRole('heading', { name: '你好，Task04 Product', exact: true }).waitFor();
    passed.push('E02 controlled pending login disables duplicate submission and exposes aria-busy then real success');
    await page.goto(base); await page.waitForURL('**/#/account');
    await page.getByRole('heading', { name: '你好，Task04 Product', exact: true }).waitFor();
    const logout = page.waitForResponse('**/api/v1/auth/logout');
    await page.getByRole('button', { name: '退出登录', exact: true }).focus(); await page.keyboard.press('Enter');
    assert((await logout).status() === 200, 'keyboard logout not server success');
    await page.waitForURL('**/#/login');
    await page.waitForFunction(() => !sessionStorage.getItem('weknora.auth.v1.pending-logout'));
    assert(await page.evaluate(() => !sessionStorage.getItem('weknora.auth.v1')), 'keyboard logout retained credentials');
    passed.push('E03 valid root routes account, actual keyboard logout revokes and clears credentials');
    return { passed, groups: passed.length, controlled: 'login response delay only', real: 'duplicate registration and login/logout' };
}
