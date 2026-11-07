import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import sequence from './sequence.json';

const $ = id => document.getElementById(id);
const canvas = $('scene');
const state = {mode:'explore', time:0, playing:false, section:false, xray:false,
  hardware:true, explode:0, press:false, part:'all'};
const info = {
  all:['模型全体','青い円盤と紫のハブを、緑の板ばね3枚でつなぎます。下の部品ボタンで、ねじ穴を単独表示できます。','台座 Ø120 mm / M3 × 7本'],
  base:['台座と中心の柱','柱の上にØ3.4の穴、横にナット用の溝があります。固定側を表す部品です。横から見るとナットを入れる入口を確認できます。','柱 Ø8.0 / 横溝 幅5.9 × 高さ2.6 mm'],
  coil:['コイル役リング','台座の円形の溝にはめるだけのプラスチックです。ねじ穴はなく、磁力もありません。','外径 Ø87 / 内径 Ø71 / 高さ9.4 mm'],
  hub:['ハブ','中心の穴で柱を通し、3つの通し穴で板ばねを固定します。「裏から」で六角ナット穴が見えます。','軸穴 Ø8.7 / ねじ穴 Ø3.4 × 3'],
  armature:['円盤（アーマチュア役）','板ばねでハブにつながる動く部品。押すと灰色の固定面に接触します。裏側の六角穴がM3ナットを受けます。','外径 Ø100 / 内径 Ø60 / 厚さ5.5 mm'],
  spring0:['板ばね（3枚使用）','両端の穴をねじと平座金で固定します。真ん中が曲がり、円盤が上下できる構造です。CGのたわみは指定した形で、力の計算ではありません。','厚さ0.8 / 幅7 / 穴 Ø3.4 × 2 mm'],
  cap:['抜け止めキャップ','柱の上に載せ、平座金とM3×25で留めます。ハブを押しつぶさず、抜けるのを防ぐ設計です。','外径 Ø13 / 厚さ2 / 穴 Ø3.4 mm'],
};
let renderer, controls, scene, camera, nodes = new Map(), dirty = true, lastStage = -1;
const up = new THREE.Vector3(0,1,0);
const axis = new THREE.Vector3(0,1,0);
let renderCount = 0;
const toView = p => new THREE.Vector3(p[0]*.1,p[2]*.1,-p[1]*.1);
const stageAt = t => sequence.stages.findLastIndex(s => s[0] <= t);
const isHardware = n => /^(screw|nut|washer)_/.test(n);
const timeText = t => `${Math.floor(t/60)}:${String(Math.floor(t%60)).padStart(2,'0')}`;
const sectionActive = () => state.mode==='assembly' ? state.time>=71&&state.time<84 : state.section;

function frameAt(t) {
  const f = Math.max(0,Math.min(sequence.frames.length-1,t*sequence.fps));
  const i = Math.floor(f), j = Math.min(i+1,sequence.frames.length-1), u=f-i;
  return {poses:sequence.frames[i].map((p,k)=>p.map((x,a)=>x+(sequence.frames[j][k][a]-x)*u)),
    press:sequence.press[i]+(sequence.press[j]-sequence.press[i])*u};
}

function explodeOffset(n) {
  if(n==='base') return [0,0,0];
  if(n==='coil') return [0,0,12];
  if(n==='nut_axle'){
    const a=sequence.manifest.slot_deg*Math.PI/180;
    return [26*Math.cos(a),26*Math.sin(a),.6];
  }
  if(n==='cap') return [0,0,74];
  if(n==='washer_axle') return [0,0,82];
  if(n==='screw_axle') return [0,0,116];
  if(n.startsWith('spring')) return [0,0,49];
  if(n.startsWith('screw')) return [0,0,70];
  if(n.startsWith('washer')) return [0,0,56];
  if(n.startsWith('nut')) return [0,0,29];
  return [0,0,40];
}

function updateModel(){
  const assembly=state.mode==='assembly';
  const sampled=frameAt(assembly?state.time:85);
  const cut=sectionActive();
  $('section').disabled=assembly;
  $('section').checked=cut;
  $('section-note').hidden=!assembly;
  const press=assembly?sampled.press:(state.press?1:0);
  for(let i=0;i<sequence.names.length;i++){
    const n=sequence.names[i], ent=sequence.manifest.render[n];
    const p=[...sampled.poses[i]];
    if(!assembly){
      p[3]=0;
      const off=explodeOffset(n);
      for(let k=0;k<3;k++)p[k]+=off[k]*state.explode;
      if(ent.group==='armature')p[2]-=sequence.manifest.delta*press;
    }
    for(const suffix of ['', '_sec']){
      const o=nodes.get(n+suffix); if(!o)continue;
      const sectionMesh=suffix==='_sec';
      o.visible=(state.part==='all'||state.part===n) && (state.hardware||!isHardware(n)) &&
        (cut?sectionMesh:!sectionMesh);
      o.position.copy(toView(p));
      o.quaternion.setFromAxisAngle(axis, sectionMesh?0:p[3]);
      if(o.morphTargetInfluences)o.morphTargetInfluences[0]=press;
      o.material.transparent=state.xray&&!isHardware(n);
      o.material.opacity=o.material.transparent?.3:1;
      o.material.depthWrite=!o.material.transparent;
    }
  }
  scene.updateMatrixWorld(true);
  dirty=true;
}

function fit(view='iso'){
  const box=new THREE.Box3();
  for(const o of nodes.values()){
    if(!o.visible)continue;
    o.geometry.computeBoundingBox();
    box.union(o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld));
  }
  if(box.isEmpty())return;
  const center=box.getCenter(new THREE.Vector3());
  const dirs={iso:new THREE.Vector3(.9,.85,1.3),top:new THREE.Vector3(0,1,.0001),
    bottom:new THREE.Vector3(0,-1,.0001),side:new THREE.Vector3(1,.12,1)};
  if(sectionActive()){
    const a=108*Math.PI/180;
    dirs.iso.set(Math.cos(a),.35,-Math.sin(a));
  }
  const v=(dirs[view]||dirs.iso).normalize();
  camera.up.copy(up);
  controls.target.copy(center);
  const vfov=camera.fov*Math.PI/180;
  const right=new THREE.Vector3().crossVectors(up,v).normalize();
  const screenUp=new THREE.Vector3().crossVectors(v,right).normalize();
  let distance=.5;
  for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z]){
    const p=new THREE.Vector3(x,y,z).sub(center);
    distance=Math.max(distance,p.dot(v)+Math.abs(p.dot(right))/(Math.tan(vfov/2)*camera.aspect),
      p.dot(v)+Math.abs(p.dot(screenUp))/Math.tan(vfov/2));
  }
  camera.position.copy(center).add(v.multiplyScalar(distance*1.22));
  controls.update();dirty=true;
}

function setMode(mode){
  const changed=state.mode!==mode;
  state.mode=mode;state.playing=false;
  $('explore').setAttribute('aria-pressed',mode==='explore');
  $('assembly').setAttribute('aria-pressed',mode==='assembly');
  $('explode').disabled=mode==='assembly';
  $('press').disabled=mode==='assembly'||state.explode>0||state.part!=='all';
  $('play').textContent=mode==='assembly'?'再生':'組立を再生';
  $('scene-label').textContent=mode==='assembly'?'組立手順のCG':'完成形を観察';
  updateModel();updateCaption();if(changed)fit();
}

function selectPart(n){
  state.part=n;
  if(n!=='all'){setMode('explore');state.explode=0;state.press=false;state.section=false;
    $('explode').value=0;$('explode-value').value='0%';$('section').checked=false;
    $('press').setAttribute('aria-pressed','false');$('press').textContent='円盤を押す';}
  document.querySelectorAll('[data-part]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.part===n));
  const d=info[n];$('part-title').textContent=d[0];$('detail').textContent=d[1];$('part-size').textContent=d[2];
  $('press').disabled=state.mode==='assembly'||state.explode>0||n!=='all';
  updateModel();fit();
}

function updateCaption(){
  const i=stageAt(state.time),s=sequence.stages[i];
  $('time').value=`${timeText(state.time)} / 1:28`;
  $('timeline').value=state.time;
  $('step-title').textContent=`${s[1]}  ${s[2]}`;
  if(lastStage!==i){
    $('caption').textContent=s[3];
    document.querySelectorAll('[data-step]').forEach(b=>b.classList.toggle('active',Number(b.dataset.step)===i));
    lastStage=i;
    if(state.mode==='assembly')fit();
  }
}

function showError(error){
  console.error(error);
  $('loading').hidden=false;$('loading').className='error';
  $('loading').textContent=`3D表示を開始できませんでした。Chrome / EdgeなどWebGL対応ブラウザで開いてください。詳細: ${error.message}`;
}

async function init(){
  renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:false});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));
  renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.toneMapping=THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure=.95;
  scene=new THREE.Scene();scene.background=new THREE.Color('#e4edf3');
  camera=new THREE.PerspectiveCamera(36,1,.02,2000);
  controls=new OrbitControls(camera,canvas);controls.enableDamping=false;controls.minDistance=.5;controls.maxDistance=200;
  controls.addEventListener('change',()=>dirty=true);
  scene.add(new THREE.HemisphereLight(0xffffff,0x8c9aaa,1.5));
  for(const [pos,power] of [[[8,18,14],2],[[-15,8,2],.8],[[0,10,-16],1],[[0,-12,4],1.3]]){
    const light=new THREE.DirectionalLight(0xffffff,power);light.position.set(...pos);scene.add(light);
  }
  const bytes=Uint8Array.from(atob(MODEL_BASE64),c=>c.charCodeAt(0));
  const gltf=await new GLTFLoader().parseAsync(bytes.buffer,'');
  gltf.scene.traverse(o=>{
    if(!o.isMesh)return;
    o.material=o.material.clone();o.material.side=THREE.DoubleSide;
    nodes.set(o.name,o);
  });
  if(nodes.size!==52)throw new Error(`部品データの数が一致しません: ${nodes.size}/52`);
  scene.add(gltf.scene);
  const resize=()=>{const r=canvas.parentElement.getBoundingClientRect();
    renderer.setSize(r.width,r.height,false);camera.aspect=r.width/r.height;camera.updateProjectionMatrix();dirty=true;};
  new ResizeObserver(resize).observe(canvas.parentElement);resize();
  for(let i=0;i<sequence.stages.length;i++){
    const s=sequence.stages[i],b=document.createElement('button');
    b.textContent=s[1];b.title=s[2];b.dataset.step=i;b.setAttribute('aria-label',`${s[1]} ${s[2]}`);
    b.addEventListener('click',()=>{state.time=s[0];state.part='all';selectPart('all');setMode('assembly');fit();});
    $('steps').append(b);
  }
  document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>fit(b.dataset.view)));
  document.querySelectorAll('[data-part]').forEach(b=>b.addEventListener('click',()=>selectPart(b.dataset.part)));
  $('explore').addEventListener('click',()=>{setMode('explore');fit();});
  $('assembly').addEventListener('click',()=>{selectPart('all');setMode('assembly');fit();});
  $('play').addEventListener('click',()=>{
    if(state.mode!=='assembly'){selectPart('all');setMode('assembly');fit();}
    if(state.time>=sequence.duration)state.time=0;
    state.playing=!state.playing;$('play').textContent=state.playing?'一時停止':'再生';
  });
  $('timeline').addEventListener('input',()=>{
    state.time=Number($('timeline').value);
    if(state.part!=='all')selectPart('all');
    setMode('assembly');updateModel();updateCaption();
  });
  $('explode').addEventListener('input',()=>{
    state.explode=Number($('explode').value)/100;state.press=false;
    $('explode-value').value=`${Math.round(state.explode*100)}%`;
    $('press').setAttribute('aria-pressed','false');$('press').textContent='円盤を押す';
    $('press').disabled=state.explode>0||state.part!=='all';updateModel();fit();
  });
  for(const key of ['section','xray','hardware'])$(key).addEventListener('change',()=>{
    state[key]=$(key).checked;updateModel();if(key==='section')fit();
  });
  $('press').addEventListener('click',()=>{
    state.press=!state.press;$('press').setAttribute('aria-pressed',state.press);
    $('press').textContent=state.press?'円盤を離す':'円盤を押す';updateModel();
  });
  $('reset').addEventListener('click',()=>{
    state.section=false;state.xray=false;state.hardware=true;state.explode=0;state.press=false;
    $('section').checked=false;$('xray').checked=false;$('hardware').checked=true;$('explode').value=0;
    $('explode-value').value='0%';$('press').setAttribute('aria-pressed','false');$('press').textContent='円盤を押す';
    selectPart('all');setMode('explore');fit();
  });
  canvas.addEventListener('keydown',e=>{
    if(e.key==='Home'){fit();e.preventDefault();}
  });
  const video=$('video');video.muted=true;video.volume=0;
  $('video-panel').addEventListener('toggle',()=>{if(!$('video-panel').open)video.pause();});
  updateModel();fit();$('loading').hidden=true;
  Object.defineProperty(window,'__brakeDebug',{get:()=>({
    ready:true,state:{...state},meshCount:nodes.size,visible:[...nodes.values()].filter(o=>o.visible).map(o=>o.name),
    positions:Object.fromEntries([...nodes].map(([n,o])=>[n,o.position.toArray()])),
    morphs:Object.fromEntries([...nodes].filter(([,o])=>o.morphTargetInfluences).map(([n,o])=>[n,[...o.morphTargetInfluences]])),
    renderCount,triangles:renderer.info.render.triangles,muted:video.muted,volume:video.volume,
    effectiveSection:sectionActive(),cameraPosition:camera.position.toArray(),cameraTarget:controls.target.toArray(),
    horizontalOverflow:document.documentElement.scrollWidth>window.innerWidth,
  })});
  let prev=performance.now();
  function loop(now){
    const dt=Math.min(.1,(now-prev)/1000);prev=now;
    if(state.playing){
      state.time=Math.min(sequence.duration,state.time+dt);updateModel();updateCaption();
      if(state.time>=sequence.duration){state.playing=false;$('play').textContent='再生';}
    }
    if(dirty){renderer.render(scene,camera);renderCount++;dirty=false;}
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
}
init().catch(showError);
