// Optional visual/portability check. Node 22+; pass a Chromium executable.
// Usage: node check_browser.mjs /path/to/chrome /tmp/ds13-report-qa
import {spawn} from 'node:child_process';
import {mkdtemp, mkdir, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve, dirname, join} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';

const here = dirname(fileURLToPath(import.meta.url));
const chrome = process.argv[2];
if (!chrome) throw new Error('Pass the Chromium executable as argument 1');
const out = resolve(process.argv[3] || join(tmpdir(), 'ds13-report-qa'));
await mkdir(out, {recursive:true});
const profile = await mkdtemp(join(tmpdir(), 'ds13-report-chrome-'));
const child = spawn(chrome, ['--headless', '--no-sandbox', '--disable-gpu',
  '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0',
  `--user-data-dir=${profile}`, 'about:blank'], {stdio:['ignore','ignore','pipe']});
let ws;
try {
  const url = await new Promise((resolve,reject) => {
    let stderr = '';
    const timer = setTimeout(() => reject(new Error('Chromium startup timeout')),20000);
    child.stderr.on('data', b => {
      stderr += b;
      const match = stderr.match(/DevTools listening on (ws:\/\/\S+)/);
      if (match) {clearTimeout(timer);resolve(match[1]);}
    });
    child.on('error',reject);
    child.on('exit', c => {clearTimeout(timer);reject(new Error(`Chromium exited ${c}: ${stderr}`));});
  });
  ws = new WebSocket(url);
  await new Promise((resolve,reject) => {ws.onopen=resolve;ws.onerror=reject;});
  let seq=0;
  const pending=new Map();
  const requests=[];
  ws.onmessage=event => {
    const r=JSON.parse(event.data);
    if (r.id) {const p=pending.get(r.id);pending.delete(r.id);r.error?p.reject(new Error(JSON.stringify(r.error))):p.resolve(r.result);}
    if (r.method==='Network.requestWillBeSent') requests.push(r.params.request.url);
  };
  const call=(method,params={},sessionId) => new Promise((resolve,reject) => {
    const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params,sessionId}));
  });
  const {targetId}=await call('Target.createTarget',{url:'about:blank'});
  const {sessionId}=await call('Target.attachToTarget',{targetId,flatten:true});
  const page=(method,params={})=>call(method,params,sessionId);
  const evaluate=async expression => {
    const r=await page('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
    if(r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails));
    return r.result.value;
  };
  await page('Page.enable');await page('Network.enable');
  await page('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await page('Page.navigate',{url:pathToFileURL(join(here,'report.html')).href});
  for(let i=0;i<100;i++) {
    if(await evaluate('document.readyState === "complete" && document.querySelectorAll("figure img").length === 19')) break;
    await new Promise(r=>setTimeout(r,100));
  }
  await evaluate('Promise.all([...document.images].map(i=>{i.loading="eager";return i.decode()})).then(()=>true)');
  const measurements=[];
  for(const [label,width,height] of [['desktop',1440,1000],['mobile',390,844]]) {
    await page('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:label==='mobile'});
    await evaluate('window.scrollTo({top:0,behavior:"instant"})');
    const d=await evaluate('({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,images:document.images.length,broken:[...document.images].filter(i=>!i.naturalWidth).length,title:document.title})');
    assert.equal(d.images,19);assert.equal(d.broken,0);assert.ok(d.scrollWidth<=d.width,JSON.stringify(d));
    measurements.push({label,...d});
    const shot=await page('Page.captureScreenshot',{format:'png'});
    await writeFile(join(out,`${label}.png`),Buffer.from(shot.data,'base64'));
  }
  await page('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  await evaluate('document.querySelector("#fig-top-orbits").scrollIntoView({behavior:"instant"})');
  const plot=await page('Page.captureScreenshot',{format:'png'});
  await writeFile(join(out,'orbit-panel.png'),Buffer.from(plot.data,'base64'));
  const network=requests.filter(u=>/^https?:/.test(u));
  assert.equal(network.length,0);
  await writeFile(join(out,'browser-check.json'),JSON.stringify({status:'passed',measurements,externalRequests:network},null,2));
  console.log(JSON.stringify({status:'passed',measurements,externalRequests:network,output:out},null,2));
  await call('Browser.close');
} finally {
  if(ws) ws.close();
  child.kill();
}
