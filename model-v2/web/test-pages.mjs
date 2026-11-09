import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, writeFile} from 'node:fs/promises';
import {resolve, sep, extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {launchBrowser} from './browser.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
const prefix = '/electromagnetic-brake-lab/';
const types = {'.html':'text/html; charset=utf-8', '.txt':'text/plain; charset=utf-8',
  '.png':'image/png', '.mp4':'video/mp4', '.zip':'application/zip',
  '.3mf':'application/octet-stream'};
const serverErrors = [];
const server = createServer(async (req, res) => {
  const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  const path = resolve(root, pathname.slice(prefix.length) || 'index.html');
  if (!pathname.startsWith(prefix) || !path.startsWith(root.endsWith(sep) ? root : root + sep)) {
    res.writeHead(404).end();
    return;
  }
  try {
    const data = await readFile(path);
    const range = req.headers.range?.match(/^bytes=(\d+)-(\d*)$/);
    const start = range ? Number(range[1]) : 0;
    const end = range && range[2] ? Math.min(Number(range[2]), data.length - 1) : data.length - 1;
    if (start > end || start >= data.length) {
      res.writeHead(416, {'Content-Range':`bytes */${data.length}`}).end();
      return;
    }
    const headers = {'Content-Type':types[extname(path)] ?? 'application/octet-stream',
      'Accept-Ranges':'bytes', 'Content-Length':end - start + 1};
    if (range) headers['Content-Range'] = `bytes ${start}-${end}/${data.length}`;
    res.writeHead(range ? 206 : 200, headers).end(data.subarray(start, end + 1));
  } catch (error) {
    if (error.code !== 'ENOENT') serverErrors.push(error.message);
    res.writeHead(error.code === 'ENOENT' ? 404 : 500).end();
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}${prefix}`;
let browser;
const errors = [], checks = [];
const check = (name, value) => {assert.ok(value, name); checks.push(name);};
try {
  browser = await launchBrowser(['--enable-webgl','--ignore-gpu-blocklist']);
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (['error','warning'].includes(message.type())) errors.push(message.text());
  });
  await page.goto(base);
  check('Japanese landing heading', await page.getByRole('heading', {level:1}).isVisible());
  const links = await page.locator('a[href], img[src]').evaluateAll(elements =>
    [...new Set(elements.map(element => element.href || element.src))]);
  for (const url of links.filter(url => url.startsWith(base))) {
    const response = await page.request.get(url);
    check(`Project-path resource: ${new URL(url).pathname.slice(prefix.length)}`, response.ok());
  }
  check('All internal links remain under project prefix',
    links.every(url => url.startsWith(base) || url.startsWith('https://github.com/ktanino10/electromagnetic-brake-lab')));
  for (const name of ['印刷用ZIPをダウンロード（約1.1MB）','本体の配置3MF','板ばねの配置3MF']) {
    const link = page.getByRole('link', {name, exact:true});
    const href = await link.getAttribute('href');
    const [download] = await Promise.all([page.waitForEvent('download'), link.click()]);
    assert.deepEqual(await readFile(await download.path()), await readFile(resolve(root, href)));
    check(`Downloaded bytes match: ${href}`, true);
  }
  await page.getByText('部品・裏のナット穴・締結の断面を見る（5枚）', {exact:true}).click();
  await page.locator('.gallery').scrollIntoViewIfNeeded();
  for (const image of await page.locator('.gallery img').all()) await image.scrollIntoViewIfNeeded();
  await page.waitForFunction(() => [...document.images].every(image => image.complete && image.naturalWidth > 0));
  check('Landing hero and five diagrams load', await page.locator('img').count() === 6);
  await page.screenshot({path:resolve(root,'model-v2/results/viewer-pages-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  check('Mobile landing has no horizontal overflow',
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({path:resolve(root,'model-v2/results/viewer-pages-mobile.png'),fullPage:true});
  await page.getByRole('link', {name:'3D模型を動かす',exact:true}).click();
  await page.waitForFunction(() => window.__brakeDebug?.ready);
  check('Viewer starts under project prefix', page.url() === base + 'model-v2/brake-viewer-v2.html');
  await page.getByLabel('断面を見る',{exact:true}).check();
  check('Viewer section operation', (await page.evaluate(() => window.__brakeDebug)).visible.every(name => name.endsWith('_sec')));
  await page.getByRole('button',{name:'円盤を押す',exact:true}).click();
  check('Viewer press operation', (await page.evaluate(() => window.__brakeDebug)).morphs.spring0[0] === 1);
  await page.getByRole('button',{name:'全体に戻す',exact:true}).click();
  await page.getByLabel('分解の割合',{exact:true}).press('End');
  check('Viewer explode operation', await page.getByRole('button',{name:'円盤を押す',exact:true}).isDisabled());
  check('Mobile viewer has no horizontal overflow',
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.goto(base);
  await page.getByRole('link',{name:'動画3本を見る',exact:true}).click();
  await page.waitForFunction(() => [...document.querySelectorAll('video')].every(video => video.readyState >= 2));
  const videos = await page.locator('video').evaluateAll(elements => elements.map(video => ({
    file:video.getAttribute('src'),duration:video.duration,muted:video.muted,volume:video.volume,
    width:video.videoWidth,height:video.videoHeight,
  })));
  assert.deepEqual(videos.map(video => video.duration), [88,92,40]);
  check('Three videos loaded muted with volume zero',
    videos.length === 3 && videos.every(video => video.muted && video.volume === 0 && video.width === 1280));
  for (let index = 0; index < videos.length; index++) {
    const player = page.locator('video').nth(index);
    await player.focus();
    await player.press('Space');
    await page.waitForFunction(index => {
      const video = document.querySelectorAll('video')[index];
      return !video.paused && video.currentTime > 0;
    }, index);
    await player.press('Space');
    check(`Video ${index + 1} plays over project-path HTTP`, true);
  }
  check('Mobile video page has no horizontal overflow',
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert.deepEqual(errors, []);
  assert.deepEqual(serverErrors, []);
  check('No browser console warnings/errors or server errors', true);
  await writeFile(resolve(root,'validation/pages-checks.json'), JSON.stringify({
    status:'PASS',scope:'Local project-path HTTP browser checks; not production Pages deployment',
    projectPath:prefix,checks,videos,errors,serverErrors,
    screenshots:['model-v2/results/viewer-pages-desktop.png','model-v2/results/viewer-pages-mobile.png'],
  },null,2) + '\n');
  console.log(`PAGES CHECKS ${checks.length} FAILED 0`);
} finally {
  if (browser) await browser.close();
  await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
}
