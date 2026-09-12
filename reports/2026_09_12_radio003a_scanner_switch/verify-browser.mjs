import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { writeFile } from 'node:fs/promises';
import { chromium } from '/home/mouse9911/gits/leo-tracker-single-rx-10m/web/node_modules/playwright/index.mjs';

const session = process.argv[2];
assert.match(session, /^scan-hop-[0-9a-f]{16}$/);
const prefix = `/var/tmp/leo-radio003a-web-${session}-v2`;
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
const report = { session, errors: [], failedResponses: [], assets: [], screenshots: [] };
page.on('pageerror', error => report.errors.push(String(error)));
page.on('response', response => {
  if (response.status() >= 400) report.failedResponses.push({ url: response.url(), status: response.status() });
});
try {
  await page.goto('http://192.168.1.142:8090/', { waitUntil: 'networkidle', timeout: 30000 });
  await page.getByRole('button', { name: 'Scanner', exact: true }).click();
  await page.getByRole('button', { name: new RegExp(session) }).click({ timeout: 30000 });
  for (const [tab, alt, artifact] of [
    [null, 'Persistent-hop capture coverage', 'coverage'],
    ['GLRT64 vs time', 'Persistent-hop GLRT64 response over time', 'glrt64-response'],
    ['CFO vs time', 'Persistent-hop CFO windows over time', 'cfo-trajectories'],
  ]) {
    if (tab) await page.getByRole('tab', { name: tab, exact: true }).click();
    const img = page.getByRole('img', { name: `${alt} for ${session}`, exact: true });
    await img.waitFor({ state: 'visible', timeout: 30000 });
    await img.evaluate(async node => { if (!node.complete) await node.decode(); });
    const shape = await img.evaluate(node => ({ width: node.naturalWidth, height: node.naturalHeight, url: node.src }));
    assert.ok(shape.width > 0 && shape.height > 0);
    assert.ok(shape.url.includes(`/${session}/${artifact}.png`));
    const response = await page.request.get(shape.url);
    assert.equal(response.status(), 200);
    const bytes = await response.body();
    assert.equal(bytes.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
    const screenshot = `${prefix}-${artifact}.png`;
    await page.screenshot({ path: screenshot, fullPage: true });
    report.screenshots.push(screenshot);
    report.assets.push({ name: artifact, ...shape, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') });
  }
  report.title = await page.title();
  report.selectedText = await page.locator('body').innerText();
  assert.ok(report.selectedText.includes('radio_pluto_003a'));
  assert.equal(report.errors.length, 0);
  assert.equal(report.failedResponses.length, 0);
  report.status = 'verified';
} catch (error) {
  report.status = 'failed';
  report.failure = String(error);
  throw error;
} finally {
  await writeFile(`${prefix}.json`, JSON.stringify(report, null, 2) + '\n');
  await browser.close();
}
