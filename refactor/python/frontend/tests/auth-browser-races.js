// Follow auth-browser.js and owned backend restart. Sensitive values stay in memory.
async (page) => {
    const base = new URL(page.url()).origin;
    const assert = (value, message) => { if (!value) throw new Error(message); };
    const passed = []; const errors = []; const warnings = [];
    const onError = error => errors.push(error.message);
    const onConsole = message => { if (message.type() === 'warning') warnings.push(message.text()); };
    page.on('pageerror', onError); page.on('console', onConsole);
    const ready = name => page.getByRole('heading', { name: `你好，${name}`, exact: true }).waitFor();
    const current = await page.evaluate(() => JSON.parse(sessionStorage.getItem('weknora.auth.v1')));
    const login = async (email, password, name) => {
        await page.getByLabel('邮箱', { exact: true }).fill(email);
        await page.getByLabel('密码', { exact: true }).fill(password);
        await page.getByLabel('密码', { exact: true }).press('Enter'); await ready(name);
    };
    const logout = async () => {
        const response = page.waitForResponse('**/api/v1/auth/logout');
        await page.getByRole('button', { name: '退出登录' }).first().click();
        assert((await response).status() === 200, 'real logout not200');
        await page.waitForURL('**/#/login');
        await page.waitForFunction(() => !sessionStorage.getItem('weknora.auth.v1.pending-logout'));
    };
    try {
        // Supervisor has restarted the real process, retaining only its own DB and sidecar.
        assert((await page.request.get(`${base}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${current.accessToken}` } })).status() === 200, 'pre-restart token no longer valid');
        await page.reload(); await ready('Task04 Product');
        passed.push('R01 real backend process restart retains old token identity and browser reload');
        await page.evaluate(async () => {
            const client = await import('/src/api/client.ts');
            const original = window.fetch; let oldCalls = 0; let refreshes = 0;
            const old = JSON.parse(sessionStorage.getItem('weknora.auth.v1')).accessToken;
            window.fetch = (url, options) => {
                if (String(url).endsWith('/refresh')) refreshes++;
                if (String(url).endsWith('/me') && options?.headers?.Authorization === `Bearer ${old}`) {
                    oldCalls++; return Promise.resolve(new Response('{"success":false,"error":{"code":1001}}', { status: 401, headers: { 'Content-Type': 'application/json' } }));
                }
                return original(url, options);
            };
            try {
                await Promise.all([1, 2, 3].map(() => client.requestJson('/api/v1/auth/me', { authenticated: true })));
                if (oldCalls !== 3 || refreshes !== 1) throw new Error('browser refresh not single flight');
            } finally { window.fetch = original; }
        });
        passed.push('R02 browser three controlled401s cause exactly one real backend refresh and successful retries');
        // Real response intentionally withheld by signal-ignoring transport.
        await page.evaluate(async () => {
            const client = await import('/src/api/client.ts'); const original = window.fetch;
            const state = { ready: false, finished: false, rejected: false, release: null, restore: () => { window.fetch = original; } };
            window.__task04Me = state;
            window.fetch = (url, options = {}) => {
                if (!String(url).endsWith('/me')) return original(url, options);
                const { signal, ...ignoringSignal } = options;
                return new Promise((resolve, reject) => original(url, ignoringSignal).then(response => {
                    state.ready = true; state.release = () => resolve(response);
                }, reject));
            };
            client.requestJson('/api/v1/auth/me', { authenticated: true }).then(() => { state.finished = true; }, () => { state.rejected = true; state.finished = true; });
        });
        await page.waitForFunction(() => window.__task04Me.ready);
        await logout();
        await page.evaluate(() => { window.__task04Me.release(); window.__task04Me.restore(); });
        await page.waitForFunction(() => window.__task04Me.finished);
        assert(await page.evaluate(() => window.__task04Me.rejected), 'late me accepted across logout');
        passed.push('R03 real late me response ignores abort but cannot cross logout epoch');
        await login('task04-product@example.com', 'Isolated-browser-8', 'Task04 Product');
        await page.evaluate(async () => {
            const client = await import('/src/api/client.ts'); const store = (await import('/src/stores/session.ts')).useSessionStore();
            const original = window.fetch;
            const state = { ready: false, finished: false, rejected: false, access: '', refresh: '', release: null, restore: () => { window.fetch = original; } };
            window.__task04Refresh = state;
            window.fetch = (url, options = {}) => {
                if (!String(url).endsWith('/refresh')) return original(url, options);
                const { signal, ...ignoringSignal } = options;
                return new Promise((resolve, reject) => original(url, ignoringSignal).then(async response => {
                    const pair = await response.clone().json(); state.access = pair.access_token; state.refresh = pair.refresh_token;
                    state.ready = true; state.release = () => resolve(response);
                }, reject));
            };
            client.refreshSingleFlight(store.snapshot()).then(() => { state.finished = true; }, () => { state.rejected = true; state.finished = true; });
        });
        await page.waitForFunction(() => window.__task04Refresh.ready);
        await logout();
        const revoked = await page.evaluate(async () => {
            window.__task04Refresh.release(); window.__task04Refresh.restore();
            const response = await fetch('/api/v1/auth/me', { headers: { Authorization: `Bearer ${window.__task04Refresh.access}` } });
            return response.status;
        });
        await page.waitForFunction(() => window.__task04Refresh.finished);
        assert(revoked === 401 && await page.evaluate(() => window.__task04Refresh.rejected), 'late refresh survived logout');
        assert(await page.evaluate(() => sessionStorage.getItem('weknora.auth.v1')) === null, 'late refresh restored credentials');
        passed.push('R04 real committed refresh delayed past logout cannot restore browser or leave usable new token');
        await login('task04-product@example.com', 'Isolated-browser-8', 'Task04 Product');
        const offlineLogout = route => route.abort('failed');
        await page.route('**/api/v1/auth/logout', offlineLogout);
        await page.getByRole('button', { name: '退出登录' }).first().click();
        await page.getByRole('alert').filter({ hasText: '服务端撤销未确认' }).waitFor();
        assert(await page.getByLabel('邮箱', { exact: true }).isDisabled(), 'new login enabled while pending');
        await page.reload(); await page.getByRole('heading', { name: '服务端退出待确认' }).waitFor();
        assert(await page.getByLabel('邮箱', { exact: true }).isDisabled(), 'reload lost pending logout');
        await page.unroute('**/api/v1/auth/logout', offlineLogout);
        const retried = page.waitForResponse('**/api/v1/auth/logout');
        await page.getByRole('button', { name: '重试服务端退出' }).click();
        assert((await retried).status() === 200, 'pending logout not really retried');
        await page.waitForFunction(() => !sessionStorage.getItem('weknora.auth.v1.pending-logout'));
        passed.push('R05 logout injected network failure survives reload, blocks login then real retry clears pending');
        const registered = await page.request.post(`${base}/api/v1/auth/register`, { data: { username: 'Task04 Second', email: 'task04-second@example.com', password: 'Isolated-second-8' } });
        assert(registered.status() === 201, 'second isolated test identity creation failed');
        await login('task04-product@example.com', 'Isolated-browser-8', 'Task04 Product');
        await logout();
        await page.evaluate(() => {
            window.__task04OldIdentitySeen = false;
            window.__task04Observer = new MutationObserver(() => {
                if (document.body.innerText.includes('Task04 Product') || document.body.innerText.includes('task04-product@example.com')) window.__task04OldIdentitySeen = true;
            });
            window.__task04Observer.observe(document.body, { subtree: true, childList: true, characterData: true });
        });
        await login('task04-second@example.com', 'Isolated-second-8', 'Task04 Second');
        assert(!await page.evaluate(() => window.__task04OldIdentitySeen), 'old account flashed after switch');
        await page.evaluate(() => window.__task04Observer.disconnect());
        assert(!(await page.getByRole('main').innerText()).includes('Task04 Product'), 'old account left in main');
        passed.push('R06 real A logout then B login, mutation observer sees no old identity flash');
        await logout();
        await page.goto(`${base}/#/task04-missing`);
        await page.getByRole('heading', { name: '这个页面暂不存在', exact: true }).waitFor();
        assert(await page.getByRole('main').count() === 1, 'unknown route main not unique');
        await page.goto(`${base}/#/health`); await page.waitForURL('**/#/workbench/health');
        const wait = {}; wait.promise = new Promise(resolve => { wait.release = resolve; });
        let started; const seen = new Promise(resolve => { started = resolve; });
        const delay = async route => { started(); await wait.promise; await route.continue().catch(() => {}); };
        await page.route(`${base}/health`, delay);
        await page.getByRole('button', { name: '检测后端连接', exact: true }).click(); await seen;
        await page.goto(`${base}/#/progress`); await page.waitForURL('**/#/workbench/progress');
        wait.release(); await page.unroute(`${base}/health`, delay);
        await page.goto(`${base}/#/health`);
        assert((await page.getByRole('status').innerText()).includes('待检测'), 'health reentry stale');
        passed.push('R07 public unknown/legacy routes, controlled in-flight health leave/reentry stays idle');
        assert(errors.length === 0 && warnings.length === 0, 'browser errors/warnings');
        return { passed, groups: passed.length, errors, warnings, controlled: ['three401', 'signal-ignoring delay', 'logout network fault'], real: ['restart', 'refresh', 'all-session logout', 'second account switch'] };
    } finally { page.off('pageerror', onError); page.off('console', onConsole); }
}
