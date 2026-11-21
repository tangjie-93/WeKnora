// Playwright CLI run-code --filename=<this file> before stop, while stopped, and after restart.
// Does not stop services: the operator must verify process ownership separately.
async (page) => {
    const evidenceDir = '/Users/james/Desktop/github/WeKnora/refactor/artifacts/weknora-python-vue3-rebuild/04-e2e/output/playwright';
    let backendUp = false;
    try {
        const direct = await page.request.get('http://127.0.0.1:8080/health', { timeout: 1500 });
        backendUp = direct.status() === 200 && direct.headers()['x-weknora-implementation'] === 'python-fastapi';
    } catch { /* Expected only when the verified health service is stopped. */ }
    const responsePromise = page.waitForResponse(response => response.url() === 'http://127.0.0.1:5400/health');
    await page.getByRole('button', { name: '检测后端连接' }).click();
    const response = await responsePromise;
    await page.waitForFunction(up => document.querySelector('[role="status"]')?.textContent.includes(up ? '连接成功' : '检测失败'), backendUp);
    const statusText = await page.getByRole('status').innerText();
    if (backendUp) {
        if (response.status() !== 200 || !(statusText.includes('响应 JSON') && statusText.includes('python-fastapi'))) {
            throw new Error(`restored backend not reflected in UI: ${statusText}`);
        }
    } else {
        if (response.status() === 200 || statusText.includes('响应 JSON') || !statusText.includes('失败分类：http')) {
            throw new Error(`unreachable backend presented incorrectly: ${statusText}`);
        }
        if (await page.getByRole('button', { name: '检测后端连接' }).isDisabled()) throw new Error('failure prevents retry');
    }
    await page.screenshot({ path: `${evidenceDir}/${backendUp ? 'live-restored' : 'live-stopped'}.png`, fullPage: true });
    return { backendUp, actualProxyStatus: response.status(), statusText, kind: 'real service, no route interception' };
}
