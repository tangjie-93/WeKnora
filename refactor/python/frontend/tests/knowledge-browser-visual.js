// Stable rendering evidence only: no CSS-transition screenshots or authentication secrets.
async (page) => {
    const base = new URL(page.url()).origin;
    const suffix = Date.now(), password = 'Isolated-visual-8';
    const registered = await page.request.post(`${base}/api/v1/auth/register`, { data: {
        username: `Visual ${suffix}`, email: `visual-${suffix}@example.com`, password,
    } });
    if (registered.status() !== 201) throw new Error('visual test registration');
    await page.goto(`${base}/#/login`);
    await page.getByLabel('邮箱', { exact: true }).fill(`visual-${suffix}@example.com`);
    await page.getByLabel('密码', { exact: true }).fill(password);
    await page.getByRole('button', { name: '登录', exact: true }).click(); await page.waitForURL('**/#/account');
    await page.getByRole('link', { name: '进入知识库', exact: true }).click();
    await page.getByText('当前空间还没有知识库', { exact: true }).waitFor();
    await page.getByRole('button', { name: '创建知识库', exact: true }).click();
    await page.getByLabel('名称', { exact: true }).fill('独立真实知识库 😀');
    await page.getByLabel('描述', { exact: true }).fill('真实临时 SQLite 数据；模型未配置，不开放上传或问答。');
    await page.getByRole('dialog').getByRole('button', { name: '创建知识库', exact: true }).click();
    await page.getByRole('dialog').waitFor({ state: 'hidden' });
    await page.getByText('模型未配置', { exact: true }).waitFor();
    await page.evaluate(() => document.fonts.ready);
    const path = '/Users/james/Desktop/github/WeKnora/refactor/artifacts/weknora-knowledge-base-management/04-e2e/output/playwright';
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.screenshot({ path: `${path}/knowledge-desktop-final.png`, animations: 'disabled' });
    await page.setViewportSize({ width: 375, height: 812 });
    await page.screenshot({ path: `${path}/knowledge-mobile-final.png`, animations: 'disabled' });
    if (!await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)) throw new Error('visual overflow');
    await page.getByRole('button', { name: '退出登录', exact: true }).first().click(); await page.waitForURL('**/#/login');
    return { result: 'stable screenshots captured after dialog hidden/fonts ready; supporting evidence, not extra scenario count' };
}
