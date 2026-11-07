import {launchBrowser} from './browser.mjs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const browser=await launchBrowser();
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[],requests=[],cancelledMediaRequests=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('console',m=>{if(['warning','error'].includes(m.type()))errors.push(m.text());});
page.on('requestfailed',r=>{
  const failure=r.failure()?.errorText;
  // Chromium cancels media range/preload requests on navigation or metadata completion.
  // Every video is separately required to load and play below.
  if(r.resourceType()==='media'&&failure==='net::ERR_ABORTED'){
    cancelledMediaRequests.push(new URL(r.url()).pathname.split('/').pop());
  }else{
    errors.push(`${new URL(r.url()).pathname.split('/').pop()}: ${failure}`);
  }
});
page.on('request',r=>requests.push(r.url()));
let report;
try{
  const start=performance.now();
  await page.goto(pathToFileURL(resolve('../brake-viewer-v2.html')).href);
  await page.waitForFunction(()=>window.__brakeDebug?.ready);
  const loadMs=performance.now()-start;
  await page.getByText('ねじ穴・ナット穴の拡大図（5枚）',{exact:true}).click();
  await page.locator('.gallery').scrollIntoViewIfNeeded();
  for(const img of await page.locator('.gallery img').all())await img.scrollIntoViewIfNeeded();
  await page.waitForFunction(()=>[...document.querySelectorAll('.gallery img')].every(i=>i.complete&&i.naturalWidth>0));
  await writeFile('../results/viewer-accessibility.txt',await page.locator('body').ariaSnapshot());
  await page.goto(pathToFileURL(resolve('../watch-assembly.html')).href);
  await page.waitForFunction(()=>{const v=document.querySelector('video');return v.readyState>=2&&!v.paused&&v.currentTime>0;});
  const video=await page.locator('video').evaluate(v=>({
    duration:v.duration,width:v.videoWidth,height:v.videoHeight,muted:v.muted,volume:v.volume,
    playing:!v.paused,readyState:v.readyState,currentTime:v.currentTime,
  }));
  assert.equal(video.duration,88);
  assert.equal(video.width,1280);
  assert.equal(video.height,720);
  assert.equal(video.muted,true);
  assert.equal(video.volume,0);
  assert.equal(video.playing,true);
  assert.deepEqual(errors,[]);
  assert.ok(requests.every(u=>u.startsWith('file:')||u.startsWith('data:')||u.startsWith('blob:')));
  await page.goto(pathToFileURL(resolve('../../videos/watch.html')).href);
  const allVideos=[];
  for(const player of await page.locator('video').all()){
    await player.scrollIntoViewIfNeeded();
    await player.evaluate(v=>new Promise((resolve,reject)=>{
      if(v.readyState>=2){resolve();return;}
      v.addEventListener('loadeddata',resolve,{once:true});
      v.addEventListener('error',()=>reject(new Error('Video loading failed')),{once:true});
    }));
    await player.click();
    // Controls are browser-native; Space toggles playback on the focused video.
    if(await player.evaluate(v=>v.paused))await player.press('Space');
    await page.waitForFunction(index=>{
      const v=document.querySelectorAll('video')[index];return !v.paused&&v.currentTime>0;
    },allVideos.length);
    const info=await player.evaluate(v=>({file:v.getAttribute('src'),duration:v.duration,
      width:v.videoWidth,height:v.videoHeight,muted:v.muted,volume:v.volume,playing:!v.paused}));
    assert.equal(info.muted,true);assert.equal(info.volume,0);assert.equal(info.playing,true);
    assert.ok(Math.abs(info.duration-[88,92,40][allVideos.length])<.1);
    allVideos.push(info);
    await player.press('Space');
  }
  assert.deepEqual(errors,[]);
  assert.ok(requests.every(u=>u.startsWith('file:')||u.startsWith('data:')||u.startsWith('blob:')));
  report={status:'PASS',loadMs,video,allVideos,galleryImages:5,errors,cancelledMediaRequests,externalRequests:0};
}finally{
  await writeFile('../results/media-browser-validation.json',JSON.stringify(report??{status:'FAIL',errors},null,2));
  await browser.close();
}
console.log('MEDIA BROWSER CHECKS PASS');
