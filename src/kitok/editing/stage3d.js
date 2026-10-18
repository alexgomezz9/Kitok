// Local, deterministic Three.js reconstruction. No external media or network.
import * as THREE from '/three.module.js';

const spec = window.KITOK_SPEC;
const scene = new THREE.Scene();
scene.background = new THREE.Color('#070c10');
scene.fog = new THREE.FogExp2('#080f13', .035);
const renderer = new THREE.WebGLRenderer({antialias:true, preserveDrawingBuffer:true, powerPreference:'low-power'});
renderer.setSize(spec.width, spec.height);
renderer.setPixelRatio(1);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.35;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.append(renderer.domElement);
const camera = new THREE.PerspectiveCamera(41, spec.width/spec.height, .1, 80);
const ambient = new THREE.HemisphereLight('#9dc8d3', '#080b0d', 1.1);
scene.add(ambient);
const key = new THREE.SpotLight('#ffd8a3', 105, 35, .74, .65, 1.5);
key.position.set(-3, 9, 3); key.target.position.set(0, .8, 0);
key.castShadow=true; key.shadow.mapSize.set(1024,1024); key.shadow.bias=-.0003;
scene.add(key,key.target);
const rim = new THREE.DirectionalLight('#7daac8', 2.4); rim.position.set(4,4,-7); scene.add(rim);
const edge = new THREE.PointLight('#dd8b4b', 12, 13, 1.7); edge.position.set(-6,2,-2); scene.add(edge);

const material = (color, roughness=.6, metalness=.1) => new THREE.MeshStandardMaterial({color,roughness,metalness});
function mesh(geometry, mat, x=0,y=0,z=0) {
  const object=new THREE.Mesh(geometry,mat); object.position.set(x,y,z);
  object.castShadow=true; object.receiveShadow=true; scene.add(object); return object;
}
const floor=mesh(new THREE.PlaneGeometry(90,90),material('#121a1c',.93));
floor.rotation.x=-Math.PI/2; floor.position.y=-.7;
// Sparse architecture gives the camera parallax and a readable physical room.
for (const x of [-9,-6,6,9]) mesh(new THREE.BoxGeometry(.11,6,.12),material('#2b3439',.4,.7),x,2,-7);
mesh(new THREE.BoxGeometry(23,.07,.06),material('#8e7758',.4,.7),0,3.6,-7);
mesh(new THREE.CylinderGeometry(1.25,1.7,1.45,48),material('#12191c',.4,.45),0,0,0);
const wood=mesh(new THREE.CylinderGeometry(3.64,3.68,.27,96),material('#342419',.35,.12),0,.83,0);
wood.scale.x=1.43;
const rail = mesh(new THREE.TorusGeometry(3.33,.22,12,96),material('#111619',.52),0,1.02,0);
rail.rotation.x=Math.PI/2; rail.scale.x=1.44;

function canvasTexture(width,height,draw) {
  const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
  draw(canvas.getContext('2d'),width,height); const texture=new THREE.CanvasTexture(canvas);
  texture.colorSpace=THREE.SRGBColorSpace; texture.anisotropy=4; return texture;
}
const feltTexture=canvasTexture(512,512,(ctx,w,h)=>{
  ctx.fillStyle='#164943';ctx.fillRect(0,0,w,h);let seed=831;
  for(let i=0;i<22000;i++){seed=(seed*1664525+1013904223)>>>0;const x=seed%512;seed=(seed*1664525+1013904223)>>>0;const y=seed%512;ctx.fillStyle=i%2?'#255d52':'#123f39';ctx.fillRect(x,y,1,1);}
}); feltTexture.wrapS=feltTexture.wrapT=THREE.RepeatWrapping;feltTexture.repeat.set(4,4);
const felt=mesh(new THREE.CylinderGeometry(3.23,3.23,.07,96),new THREE.MeshStandardMaterial({map:feltTexture,roughness:.97}),0,1.01,0);felt.scale.x=1.44;
const line=mesh(new THREE.TorusGeometry(2.68,.009,4,100),material('#c2a77a',.7),0,1.055,0);
line.rotation.x=Math.PI/2;line.scale.x=1.5;

function labelTexture(text,sub='',color='#e8dcc5') {
  return canvasTexture(1024,256,(ctx,w,h)=>{
    ctx.clearRect(0,0,w,h);ctx.fillStyle=color;ctx.textAlign='center';ctx.font='bold 83px sans-serif';ctx.fillText(text,w/2,114);
    ctx.fillStyle='#a5b6b4';ctx.font='25px sans-serif';ctx.fillText(sub,w/2,178);
  });
}
function plaque(text,sub,x,z,width=2.0,color) {
  const tex=labelTexture(text,sub,color),plane=mesh(new THREE.PlaneGeometry(width,width/4),new THREE.MeshBasicMaterial({map:tex,transparent:true,depthWrite:false}),x,1.075,z);
  plane.rotation.x=-Math.PI/2;return plane;
}
plaque('PAREDES','PLAYER',-2.15,2.1,1.65);
const privateLabel=plaque('OTHER PLAYER','PRIVATE HAND',1.25,.05,1.65);
privateLabel.visible=['private','exposed','question'].includes(spec.mode);

function cardTexture(rank,suit,back=false) {
  return canvasTexture(256,356,(ctx,w,h)=>{
    ctx.fillStyle=back?'#142f48':'#f1ebdc';ctx.fillRect(0,0,w,h);
    if(back){ctx.strokeStyle='#53718b';ctx.lineWidth=3;for(let x=-h;x<w+h;x+=18){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x+h,h);ctx.stroke();}ctx.strokeStyle='#d2ba83';ctx.lineWidth=5;ctx.strokeRect(13,13,w-26,h-26);ctx.beginPath();ctx.ellipse(w/2,h/2,54,77,0,0,Math.PI*2);ctx.stroke();}
    else{ctx.fillStyle=(suit==='♥'||suit==='♦')?'#b84137':'#18212a';ctx.font='bold 65px serif';ctx.fillText(rank,21,78);ctx.font='51px serif';ctx.fillText(suit,23,133);ctx.textAlign='center';ctx.font='125px serif';ctx.fillText(suit,w/2,260);}
  });
}
function card(rank,suit,x,z,angle=0,faceDown=false) {
  const group=new THREE.Group(); group.position.set(x,1.082,z);group.rotation.y=angle;scene.add(group);
  const body=new THREE.Mesh(new THREE.BoxGeometry(.65,.018,.92),material('#e4d9bc',.7));body.castShadow=true;group.add(body);
  for(const [top,texture] of [[true,cardTexture(rank,suit)],[false,cardTexture('','',true)]]) {
    const plane=new THREE.Mesh(new THREE.PlaneGeometry(.647,.917),new THREE.MeshStandardMaterial({map:texture,roughness:.65}));
    plane.rotation.x=top?-Math.PI/2:Math.PI/2;plane.position.y=top?.010:-.010;group.add(plane);
  }
  group.rotation.z=faceDown?Math.PI:0;return group;
}
card('A','♠',-2.58,1.24,-.12);card('K','♥',-1.88,1.2,.08);
const rivals=[card('Q','♦',.87,.88,-.12,true),card('9','♠',1.57,.92,.09,true)];

const chipGroups=[];
function chips(x,z,count,color,move=false) {
  const group=new THREE.Group();group.position.set(x,0,z);scene.add(group);
  for(let i=0;i<count;i++) {
    const chip=new THREE.Mesh(new THREE.CylinderGeometry(.16,.16,.055,24),[material(color,.45,.2),material(color,.48,.1),material(color,.48,.1)]);
    chip.position.y=1.08+i*.06;chip.castShadow=true;group.add(chip);
    const ring=new THREE.Mesh(new THREE.TorusGeometry(.115,.008,4,24),material('#e6d4b0',.65));ring.rotation.x=Math.PI/2;ring.position.y=1.11+i*.06;group.add(ring);
  }
  if(move)chipGroups.push({group,x,z,action:move});return group;
}
for(const [x,z,c,n] of [[-2.8,.1,'#ab4337',12],[-2.36,.05,'#b8b59c',9],[-1.94,0,'#315776',6],[3.48,.52,'#a54134',14],[3.04,.52,'#b7b19b',10],[2.59,.48,'#315d78',7],[-.5,.65,'#a54236',5],[0,.68,'#c6bca4',7],[.47,.68,'#2e657c',4]])chips(x,z,n,c,x< -1?'loss':false);
if(spec.mode==='aggression'){
  // These stacks start beside NioNio's laptop. Paredes' stacks stay still.
  chips(-.95,-1.45,12,'#ab4337','aggression');
  chips(-.5,-1.5,8,'#b7b19b','aggression');
}
// Laptop replaces invented human likenesses. Its screen is a named account, not original UI.
const laptop=new THREE.Group();laptop.position.set(.1,1.075,-2.1);scene.add(laptop);
const base=new THREE.Mesh(new THREE.BoxGeometry(1.65,.07,.95),material('#344047',.3,.8));base.castShadow=true;laptop.add(base);
const lid=new THREE.Group();lid.position.set(0,.06,-.43);lid.rotation.x=-.12;laptop.add(lid);
const shell=new THREE.Mesh(new THREE.BoxGeometry(1.65,1.0,.06),material('#1b252d',.28,.75));shell.position.y=.5;lid.add(shell);
const screenTexture=canvasTexture(768,460,(ctx,w,h)=>{
  ctx.fillStyle='#08171e';ctx.fillRect(0,0,w,h);ctx.strokeStyle='#28616e';ctx.lineWidth=3;ctx.strokeRect(22,22,w-44,h-44);
  ctx.fillStyle='#e3b86e';ctx.textAlign='center';ctx.font='bold 85px sans-serif';ctx.fillText('NioNio',w/2,210);
  ctx.fillStyle='#8aaab2';ctx.font='25px sans-serif';ctx.fillText('ACCOUNT • RECONSTRUCTION',w/2,280);
});
const screen=new THREE.Mesh(new THREE.PlaneGeometry(1.51,.86),new THREE.MeshBasicMaterial({map:screenTexture}));screen.position.set(0,.5,.035);lid.add(screen);
const screenGlow=new THREE.PointLight('#6096bc',1.4,4);screenGlow.position.set(.1,2,-1.9);scene.add(screenGlow);
// Privileged path is a spatial animated signal, only present after reveal.
const path=new THREE.CatmullRomCurve3([new THREE.Vector3(1.2,1.3,.85),new THREE.Vector3(1.25,2.0,-.55),new THREE.Vector3(.1,1.85,-2.1)]);
const access=new THREE.Mesh(new THREE.TubeGeometry(path,40,.012,6,false),new THREE.MeshBasicMaterial({color:'#efb366',transparent:true,opacity:0}));scene.add(access);
const signal=mesh(new THREE.SphereGeometry(.055,10,8),new THREE.MeshBasicMaterial({color:'#ffcd8e'}));signal.visible=false;
let amountSprite;
if(spec.amount) {
  const tex=labelTexture(spec.amount,'',spec.mode==='loss'?'#ed9583':'#efd0a0');
  amountSprite=new THREE.Sprite(new THREE.SpriteMaterial({map:tex,transparent:true,depthWrite:false}));amountSprite.position.set(-.1,2.15,.8);amountSprite.scale.set(3.8,.95,1);scene.add(amountSprite);
}
const vignette=document.createElement('div');vignette.style.cssText='position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse at 50% 48%,transparent 30%,rgba(0,0,0,.48) 100%);';document.body.append(vignette);
const heading=document.createElement('div');heading.style.cssText=`position:absolute;top:6%;left:5%;font:600 ${Math.round(spec.height*.020)}px sans-serif;letter-spacing:.18em;color:#c8bba2;text-transform:uppercase;`;heading.textContent=spec.label||'ONLINE POKER';document.body.append(heading);
if(spec.detail||spec.mode==='aggression'){
  const detail=document.createElement('div');
  detail.style.cssText=`position:absolute;top:11%;left:5%;font:${Math.round(spec.height*.022)}px sans-serif;color:#d8cbb5;text-shadow:0 1px 5px #000;`;
  detail.textContent=spec.detail||(spec.mode==='aggression'?'NioNio pushes chips into the pot':'');document.body.append(detail);
}
const notice=document.createElement('div');notice.style.cssText=`position:absolute;bottom:3%;left:0;right:0;text-align:center;font:${Math.max(10,Math.round(spec.height*.014))}px sans-serif;letter-spacing:.1em;color:#c1cccb;text-shadow:0 1px 4px #000,0 0 10px #000;`;notice.textContent='ILLUSTRATIVE RECONSTRUCTION · NOT AN ACTUAL HAND OR ORIGINAL SOFTWARE';document.body.append(notice);
const accessCue=document.createElement('div');
accessCue.style.cssText=`position:absolute;top:11%;left:5%;font:600 ${Math.round(spec.height*.026)}px sans-serif;color:#edbc7b;text-shadow:0 1px 5px #000;display:none;`;
accessCue.textContent='VISIBLE TO NioNio';document.body.append(accessCue);
const ease=x=>{x=Math.max(0,Math.min(1,x));return x*x*(3-2*x);};
window.renderFrame=(t)=>{
  const p=t/Math.max(spec.duration,.01),reveal=spec.mode==='exposed'?ease((t-spec.reveal_at)/.65):0;
  accessCue.style.display=reveal>.95?'block':'none';
  rivals.forEach((c,i)=>{c.rotation.z=Math.PI*(1-reveal);c.position.y=1.082+Math.sin(reveal*Math.PI)*(.5+i*.1);});
  access.material.opacity=reveal*.8;signal.visible=reveal>.05;if(signal.visible)signal.position.copy(path.getPoint((t*.45)%1));
  chipGroups.forEach(({group,x,z,action},i)=>{const move=spec.mode===action?ease((t-.4-i*.07)/1.5):0;group.position.x=x+(0-x)*move*.65;group.position.z=z+(.45-z)*move;});
  if(amountSprite){amountSprite.material.opacity=ease((t-.5)/.7);amountSprite.position.y=2.05+.08*Math.sin(p*Math.PI);}
  const shot=spec.shot||(['private','exposed','question'].includes(spec.mode)?'cards':spec.mode==='opponent'?'opponent':spec.mode==='loss'?'overhead':'chips');
  if(shot==='wide'){
    camera.position.set(5.8-1.0*p,6.1-.8*p,7.2-.9*p);camera.lookAt(.1,1.0,0);
  } else if(shot==='cards'){
    camera.position.set(3.9-.6*p,4.0-.55*p,4.9-.6*p);camera.lookAt(1.05,1.04,.28);
  } else if(shot==='opponent'){
    camera.position.set(1.4-.5*p,2.7-.2*p,2.9-1.0*p);camera.lookAt(.05,1.7,-1.95);
  } else if(shot==='overhead'){
    camera.position.set(-1.1+.5*p,7.2-1.0*p,3.8-.7*p);camera.lookAt(-.6,1.0,.4);
  } else {
    camera.position.set(-4.8+1.2*p,3.8-.4*p,4.4-.8*p);camera.lookAt(-.8,1.15,.25);
  }
  renderer.render(scene,camera);
};
const gl=renderer.getContext(),debug=gl.getExtension('WEBGL_debug_renderer_info');
window.stageInfo={renderer:gl.getParameter(debug?debug.UNMASKED_RENDERER_WEBGL:gl.RENDERER),threeRevision:THREE.REVISION};
window.renderFrame(0);window.stageReady=true;
