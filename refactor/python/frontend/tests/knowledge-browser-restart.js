// Run after owned backend restart-request has been acknowledged in owned-services.json.
async (page) => {
    const errors = [], warnings = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'warning' || message.type() === 'error') warnings.push(message.text()); });
    await page.reload();
    await page.getByRole('heading', { name: '独立真实知识库 😀', exact: true }).waitFor();
    await page.getByRole('heading', { name: '响应丢失但已提交', exact: true }).waitFor();
    if (await page.getByRole('dialog').count()) throw new Error('unexpected dialog');
    const evidence = '/Users/james/Desktop/github/WeKnora/refactor/artifacts/weknora-knowledge-base-management/04-e2e/output/playwright';
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.screenshot({ path: `${evidence}/knowledge-desktop-stable.png` });
    await page.setViewportSize({ width: 375, height: 812 });
    if (!await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)) throw new Error('mobile overflow');
    await page.screenshot({ path: `${evidence}/knowledge-mobile-stable.png` });
    if (errors.length || warnings.length) throw new Error('unexpected console after restart');
    return { groups: 1, passed: 'B10 real reload after owned backend restart preserves all three confirmed records', errors, warnings };
}
