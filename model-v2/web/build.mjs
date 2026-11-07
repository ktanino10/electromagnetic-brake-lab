import {readFile, writeFile} from 'node:fs/promises';
import {build} from 'esbuild';
const result = await build({entryPoints:['viewer.js'], bundle:true, format:'iife', minify:true, write:false,
  define:{MODEL_BASE64:JSON.stringify((await readFile('../blender/brake-model-v2.glb')).toString('base64'))},
  legalComments:'inline'});
const code = result.outputFiles[0].text.replaceAll('</script', '<\\/script');
const template = await readFile('index.html','utf8');
const html = template.replace('<!-- BUNDLE -->', () => `<script>${code}</script>`);
await writeFile('viewer.html',html);
const entry = template.replaceAll('href="../','href="./').replaceAll('src="../','src="./')
  .replace('<!-- BUNDLE -->', () => `<script>${code}</script>`);
await writeFile('../brake-viewer-v2.html',entry);
await writeFile('THIRD-PARTY-NOTICES.txt',
  'three.js is included under the MIT license.\n\n' + await readFile('node_modules/three/LICENSE','utf8'));
console.log(`Built offline viewer: ${html.length} characters`);
