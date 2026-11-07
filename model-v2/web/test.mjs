import {launchBrowser} from './browser.mjs';
import {writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const browser = await launchBrowser(['--enable-webgl','--ignore-gpu-blocklist']);
const page = await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[],requests=[],checks=[];
page.on('pageerror',e=>{errors.push(e.message);console.error('PAGE ERROR',e.message);});
page.on('console',m=>{if(['warning','error'].includes(m.type())){errors.push(m.text());console.error(m.type(),m.text());}});
page.on('request',r=>requests.push(r.url()));
const read=()=>page.evaluate(()=>window.__brakeDebug);
async function check(name,condition){assert.ok(condition,name);checks.push(name);}
try{
  await page.goto(pathToFileURL(resolve('viewer.html')).href);
  await page.waitForFunction(()=>window.__brakeDebug?.ready,{},{timeout:20000});
  let d=await read();
  await check('52 meshes loaded, 29 full meshes visible',d.meshCount===52&&d.visible.length===29);
  await check('Video defaults to muted and volume zero',d.muted&&d.volume===0);
  await check('Desktop has no horizontal page overflow',!d.horizontalOverflow);
  await page.screenshot({path:'../results/viewer-desktop.png',fullPage:true});
  await page.getByLabel('断面を見る',{exact:true}).check();
  d=await read();await check('Only the 23 pre-cut meshes are visible',d.visible.length===23&&d.visible.every(n=>n.endsWith('_sec')));
  const y=d.positions.armature[1];
  await page.getByRole('button',{name:'円盤を押す',exact:true}).click();
  d=await read();await check('Press lowers armature by 1.5 mm',Math.abs(y-d.positions.armature[1]-.15)<1e-6);
  await check('Spring morph and armature move together',d.morphs.spring0[0]===1&&d.morphs.spring0_sec[0]===1);
  await page.screenshot({path:'../results/viewer-section.png',fullPage:true});
  await page.getByRole('button',{name:'円盤を離す',exact:true}).click();
  d=await read();await check('Release restores armature',Math.abs(d.positions.armature[1]-y)<1e-6);
  await page.getByRole('button',{name:'全体に戻す',exact:true}).click();
  await page.getByLabel('分解の割合',{exact:true}).press('End');
  d=await read();await check('Explode separates hardware',Math.abs(d.positions.screw_axle[1]-15.23)<1e-5);
  await check('Cannot press an exploded assembly',await page.getByRole('button',{name:'円盤を押す',exact:true}).isDisabled());
  await page.getByRole('button',{name:'ハブ',exact:true}).click();
  d=await read();await check('Single-part mode shows the hub only',d.visible.length===1&&d.visible[0]==='hub');
  await page.getByRole('button',{name:'裏から',exact:true}).click();
  await page.screenshot({path:'../results/viewer-hub-underside.png',fullPage:true});
  await page.getByRole('button',{name:'全体に戻す',exact:true}).click();
  await page.getByLabel('プラスチックを透かす',{exact:true}).check();
  await page.getByLabel('ねじ・ナットを表示',{exact:true}).uncheck();
  d=await read();await check('Hardware visibility toggles independently',d.visible.length===8);
  await page.getByRole('button',{name:'全体に戻す',exact:true}).click();
  for(let i=0;i<12;i++){
    await page.locator(`[data-step="${i}"]`).click();
    d=await read();await check(`Step ${i} selects expected meshes`,d.state.mode==='assembly'&&d.visible.length===(i===10?23:29));
    await check(`Step ${i} section control reflects authored view`,await page.locator('#section').isDisabled()
      &&(await page.locator('#section').isChecked())===(i===10));
  }
  await page.locator('[data-step="0"]').click();
  const kitCamera=(await read()).cameraPosition;
  await page.getByRole('button',{name:'観察する',exact:true}).click();
  const exploreCamera=(await read()).cameraPosition;
  await page.getByLabel('組立の時刻',{exact:true}).press('ArrowRight');
  d=await read();
  await check('Seeking from explore within the same stage restores kit framing',
    Math.hypot(...d.cameraPosition.map((x,i)=>x-kitCamera[i]))<1e-5
    &&Math.hypot(...d.cameraPosition.map((x,i)=>x-exploreCamera[i]))>1);
  await page.getByRole('button',{name:'観察する',exact:true}).click();
  await page.locator('#section').check();
  await page.locator('[data-step="5"]').click();
  d=await read();
  await check('Tightening always shows rotating full screws, not static cut meshes',
    !d.effectiveSection&&d.visible.includes('screw_hub0')&&!d.visible.includes('screw_hub0_sec'));
  await page.locator('[data-step="5"]').click();
  await page.getByRole('button',{name:'再生',exact:true}).click();
  await page.waitForTimeout(500);
  await page.getByRole('button',{name:'一時停止',exact:true}).click();
  d=await read();await check('Playback advances and pauses',d.state.time>29&&!d.state.playing);
  await page.getByLabel('組立の時刻',{exact:true}).press('End');
  d=await read();await check('Timeline slider reaches the endpoint',d.state.time===88);
  await page.getByRole('button',{name:'全体に戻す',exact:true}).click();
  await page.setViewportSize({width:390,height:844});
  await page.waitForTimeout(250);
  d=await read();await check('Mobile has no horizontal page overflow',!d.horizontalOverflow);
  await page.screenshot({path:'../results/viewer-mobile.png',fullPage:true});
  await check('No external network requests',requests.every(u=>u.startsWith('file:')||u.startsWith('data:')||u.startsWith('blob:')));
  await check('No console warnings or errors',errors.length===0);
}finally{
  await writeFile('../results/viewer-validation.json',JSON.stringify({
    checks,errors,externalRequests:requests.filter(u=>!u.startsWith('file:')&&!u.startsWith('data:')&&!u.startsWith('blob:')).length
  },null,2));
  await browser.close();
}
console.log(`VIEWER CHECKS ${checks.length} FAILED 0`);
