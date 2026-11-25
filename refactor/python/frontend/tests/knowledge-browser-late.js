// Real old list response withheld ignoring cancellation; switch to a newly registered real identity.
async (page) => {
    const base = new URL(page.url()).origin;
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.getByRole('heading', { name: '独立真实知识库 😀', exact: true }).waitFor();
    await page.evaluate(() => {
        const original = window.fetch;
        const state = { ready: false, release: null, restore: () => { window.fetch = original; } };
        window.__kbLate = state;
        window.fetch = (url, options = {}) => {
            if (!String(url).startsWith('/api/v1/knowledge-bases?')) return original(url, options);
            const { signal, ...ignoringSignal } = options;
            return new Promise((resolve, reject) => original(url, ignoringSignal).then(response => {
                state.ready = true; state.release = () => resolve(response);
            }, reject));
        };
    });
    await page.getByRole('button', { name: '刷新列表', exact: true }).click();
    await page.waitForFunction(() => window.__kbLate.ready);
    await page.getByRole('button', { name: '退出登录', exact: true }).first().click();
    await page.waitForURL('**/#/login');
    await page.waitForFunction(() => !sessionStorage.getItem('weknora.auth.v1.pending-logout'));
    const suffix = Date.now(), email = `late-${suffix}@example.com`, password = 'Isolated-late-8';
    const registered = await page.request.post(`${base}/api/v1/auth/register`, { data: { username: `Late ${suffix}`, email, password } });
    if (registered.status() !== 201) throw new Error('late identity registration not201');
    await page.getByLabel('邮箱', { exact: true }).fill(email); await page.getByLabel('密码', { exact: true }).fill(password);
    await page.getByRole('button', { name: '登录', exact: true }).click(); await page.waitForURL('**/#/account');
    await page.evaluate(() => window.__kbLate.restore());
    await page.getByRole('link', { name: '进入知识库', exact: true }).click();
    await page.getByText('当前空间还没有知识库', { exact: true }).waitFor();
    await page.evaluate(() => window.__kbLate.release());
    await page.getByRole('button', { name: '刷新列表', exact: true }).click();
    await page.getByText('当前空间还没有知识库', { exact: true }).waitFor();
    if (await page.getByRole('heading', { name: '独立真实知识库 😀', exact: true }).count()) throw new Error('late list crossed users');
    await page.getByRole('button', { name: '退出登录', exact: true }).first().click(); await page.waitForURL('**/#/login');
    return { groups: 1, passed: 'B11 real signal-ignoring old list cannot cross logout, unmount, new login and new empty space' };
}
