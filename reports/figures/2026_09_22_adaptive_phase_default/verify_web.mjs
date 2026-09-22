import { createRequire } from 'node:module';
const { chromium } = createRequire(new URL('../../../web/package.json', import.meta.url))('playwright');
import { writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
const origin = process.env.LEO_UI_URL || 'http://127.0.0.1:8090';
const session = process.argv[2] || 'scan-hop-edcaedee2508bea1';
const browser = await chromium.launch({headless:true});
try {
  const page = await browser.newPage({viewport:{width:1440,height:1080}});
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(origin, {waitUntil:'domcontentloaded'});
  await page.getByRole('button', {name:'Scanner', exact:true}).click();
  const history = page.getByRole('region', {name:'Adaptive hop history'});
  await history.getByRole('table').waitFor({timeout:90000});
  for (let i=0; i<12; i++) {
    const selected = history.getByRole('button').filter({hasText:session});
    if (await selected.count()) {await selected.click(); break;}
    const before = await history.getByRole('table').innerText();
    await history.getByRole('button',{name:'Next adaptive captures'}).click();
    await page.waitForFunction(({before}) => {
      const table=document.querySelector('[aria-label="Adaptive hop history"] table');
      return table && table.innerText!==before;
    },{before},{timeout:90000});
  }
  const section=page.getByRole('region',{name:'Broadband and pilot relative phase'});
  await section.waitFor({timeout:90000});
  const images=section.locator('img');
  await images.first().waitFor({state:'attached',timeout:180000});
  await section.scrollIntoViewIfNeeded();
  const loaded=[];
  for (let i=0;i<await images.count();i++) {
    const img=images.nth(i);
    await img.scrollIntoViewIfNeeded();
    await img.evaluate(el => el.decode());
    loaded.push(await img.evaluate(el=>({src:el.src,width:el.naturalWidth,height:el.naturalHeight,displayWidth:el.getBoundingClientRect().width,panelWidth:el.closest('section').getBoundingClientRect().width})));
  }
  if(loaded.length!==2 || loaded.some(i=>i.width===0 || i.displayWidth>i.panelWidth)) throw new Error('Expected two loaded phase PNGs');
  const response=await page.request.get(`${origin}/api/v1/scanner/adaptive-sessions/${session}/analysis/relative-phase`);
  const status=await response.json();
  const artifacts=[];
  for (const a of status.manifest.artifacts) {
    const params=new URLSearchParams({binding_sha256:status.binding_sha256,artifact_sha256:a.sha256});
    const result=await page.request.get(`${origin}/api/v1/scanner/adaptive-sessions/${session}/analysis/relative-phase/${a.name}.png?${params}`);
    const raw=await result.body();
    const hash='sha256:'+createHash('sha256').update(raw).digest('hex');
    if(result.status()!==200 || hash!==a.sha256) throw new Error('Artifact HTTP/digest check failed');
    artifacts.push({...a,http_status:result.status(),verified_sha256:hash});
  }
  await section.screenshot({path:'/tmp/adaptive-phase-browser-proof.png'});
  const result={session,checked_at:new Date().toISOString(),status,loaded,artifacts,browser_errors:errors};
  await writeFile('/tmp/adaptive-phase-browser-proof.json',JSON.stringify(result,null,2));
  console.log(JSON.stringify({session,state:status.state,supported:status.manifest.supported_visit_count,loaded,errors}));
} finally {await browser.close();}
