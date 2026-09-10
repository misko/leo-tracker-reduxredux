import { chromium } from '/home/mouse9911/gits/leo-tracker-arm-presence/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';
const root = '/tmp/leo-scanner-rollout.j7UWTe';
const id = 'scan-hop-f6f9037314e87e27';
const browser = await chromium.launch({
  headless: true,
  executablePath: '/home/mouse9911/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',
  env: {...process.env, LD_LIBRARY_PATH: '/home/mouse9911/.cache/ms-playwright/ubuntu-libs/usr/lib/x86_64-linux-gnu'},
});
const page = await browser.newPage({viewport: {width: 1600, height: 1100}});
const failures = [], responses = [];
page.on('pageerror', error => failures.push(String(error)));
page.on('response', response => {
  if (response.url().includes('/scanner/adaptive-sessions')) {
    responses.push({url: response.url(), status: response.status()});
    if (response.status() >= 400) failures.push(`${response.status()} ${response.url()}`);
  }
});
try {
  await page.goto('http://127.0.0.1:8090/', {waitUntil: 'domcontentloaded'});
  await page.getByRole('button', {name: 'Scanner', exact: true}).click();
  await page.getByRole('region', {name: 'Adaptive hop history', exact: true}).waitFor();
  await page.getByRole('button', {name: new RegExp(id)}).waitFor({timeout: 420000});
  await page.getByRole('button', {name: new RegExp(id)}).click();
  await page.getByRole('heading', {name: 'Actual channel visits', exact: true}).waitFor();
  await page.getByText('Passed recording health gates', {exact: true}).waitFor();
  await page.getByRole('table', {name: 'Radio-side GLRT dwell results', exact: true}).waitFor();
  await page.screenshot({path: `${root}/production-overview-final.png`, fullPage: false});
  await page.getByRole('region', {name: 'On-radio GLRT', exact: true}).locator('header').scrollIntoViewIfNeeded();
  await page.screenshot({path: `${root}/production-glrt-final.png`, fullPage: false});
  await page.getByRole('button', {name: 'Next GLRT results', exact: true}).click();
  await page.getByRole('row').filter({hasText: /^50 ·/}).waitFor();
  if (failures.length) throw new Error(failures.join('\n'));
  fs.writeFileSync(`${root}/browser-verification-final.json`, JSON.stringify({passed: true, session_id: id, responses, failures, text: await page.locator('.adaptive-summary').innerText()}, null, 2));
  console.log('Production browser passed: live history refresh, selected capture, GLRT evidence, pagination.');
} catch (error) {
  fs.writeFileSync(`${root}/browser-failure-final.json`, JSON.stringify({error: String(error), responses, failures}, null, 2));
  throw error;
} finally {await browser.close();}
