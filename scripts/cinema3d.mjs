#!/usr/bin/env node
/** Deterministic offline 3D frames -> FFmpeg. Only loopback modules are served. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createRequire} from 'node:module';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const require=createRequire(path.join(root,'frontend/package.json'));
if(!process.env.PLAYWRIGHT_BROWSERS_PATH){
  try{await fs.access(path.join(root,'.tools/browsers'));process.env.PLAYWRIGHT_BROWSERS_PATH=path.join(root,'.tools/browsers');}
  catch{/* Use Playwright's existing default installation if no project cache exists. */}
}
const {chromium}=require('playwright');
const args=process.argv.slice(2),options={};
for(let i=0;i<args.length;i+=2){if(!args[i].startsWith('--')||!args[i+1])throw Error('Expected --key value');options[args[i].slice(2)]=args[i+1];}
if(!options.spec||!options.output)throw Error('--spec JSON_PATH --output MP4_PATH required');
if((await fs.lstat(options.spec)).isSymbolicLink())throw Error('Unsupported symlink specification');
const raw=JSON.parse(await fs.readFile(options.spec,'utf8'));
const spec={...raw,width:Number(options.width||raw.width||1280),height:Number(options.height||raw.height||720),fps:Number(options.fps||raw.fps||30),duration:Number(options.duration||raw.duration||4),reveal_at:Number(raw.reveal_at??1)};
for(const key of ['width','height','fps'])if(!Number.isInteger(spec[key]))throw Error('Geometry and FPS must be integers');
if(spec.width<320||spec.width>1920||spec.height<180||spec.height>1080||spec.width%2||spec.height%2||spec.fps<24||spec.fps>60||!Number.isFinite(spec.duration)||spec.duration<.4||spec.duration>30||!Number.isFinite(spec.reveal_at)||spec.reveal_at<0||spec.reveal_at>30)throw Error('Unsupported render bounds');
if(raw.shot!==undefined&&!['wide','opponent','cards','chips','overhead'].includes(raw.shot))throw Error('Unsupported camera shot');
if(!['opponent','aggression','loss','private','exposed','question'].includes(spec.mode))throw Error('Unsupported 3D mode');
for(const [key,max]of [['label',70],['amount',30],['detail',100]])if(spec[key]!==undefined&&(typeof spec[key]!=='string'||spec[key].length>max))throw Error(`Invalid ${key}`);
const output=path.resolve(options.output);
if(!output.toLowerCase().endsWith('.mp4'))throw Error('Unsupported output extension: expected .mp4');
const pending=output.replace(/\.mp4$/i,'')+'.stage3d.part.mp4';
const previewPaths=options.previews?['before','after'].map(name=>path.resolve(`${options.previews}_${name}.jpg`)):[];
const writePaths=[output,pending,...previewPaths];
if(new Set(writePaths).size!==writePaths.length)throw Error('Unsupported overlapping output paths');
// lstat also rejects dangling symlinks. Existing files are never clobbered.
for(const candidate of writePaths){
  try{await fs.lstat(candidate);throw Error(`Refusing to overwrite existing file: ${candidate}`);}
  catch(error){if(error.code!=='ENOENT')throw error;}
}
await fs.mkdir(path.dirname(output),{recursive:true});
for(const preview of previewPaths)await fs.mkdir(path.dirname(preview),{recursive:true});
const started=performance.now();
const html=`<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;overflow:hidden;background:#070c10}canvas{display:block}</style></head><body><script>window.KITOK_SPEC=${JSON.stringify(spec).replaceAll('<','\\u003c')}</script><script type="module" src="/stage3d.js"></script></body></html>`;
const routes=new Map([['/',null],['/stage3d.js',path.join(root,'src/kitok/editing/stage3d.js')],['/three.module.js',path.join(root,'frontend/node_modules/three/build/three.module.js')],['/three.core.js',path.join(root,'frontend/node_modules/three/build/three.core.js')]]);
const server=createServer(async(req,res)=>{try{const target=routes.get(req.url);if(target===undefined){res.writeHead(404).end();return;}res.setHeader('Content-Type',target?'text/javascript':'text/html');res.end(target?await fs.readFile(target):html);}catch{res.writeHead(500).end();}});
let browser,encoder;let stderr='',ownsPending=false;
try {
  const reservation=await fs.open(pending,'wx',0o600);await reservation.close();ownsPending=true;
  server.listen(0,'127.0.0.1');await once(server,'listening');
  browser=await chromium.launch({headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--disable-dev-shm-usage']});
  const page=await browser.newPage({viewport:{width:spec.width,height:spec.height},deviceScaleFactor:1});
  page.on('pageerror',error=>process.stderr.write(`stage: ${error.message}\n`));
  await page.route('**/*',route=>{const url=new URL(route.request().url());return url.hostname==='127.0.0.1'?route.continue():route.abort();});
  await page.goto(`http://127.0.0.1:${server.address().port}/`);await page.waitForFunction(()=>window.stageReady,{},{timeout:30000});
  const info=await page.evaluate(()=>window.stageInfo);
  encoder=spawn(options.ffmpeg||'ffmpeg',['-nostdin','-v','error','-y','-f','image2pipe','-vcodec','mjpeg','-framerate',String(spec.fps),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','18','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',pending],{stdio:['pipe','ignore','pipe']});
  encoder.stderr.on('data',data=>{stderr=(stderr+data.toString()).slice(-3000);});
  // Attach completion before frames so early FFmpeg errors cannot hang a stream.
  const completed=once(encoder,'close');encoder.stdin.on('error',()=>{});
  const frames=Math.round(spec.duration*spec.fps);
  for(let index=0;index<frames;index++){
    await page.evaluate(t=>window.renderFrame(t),index/spec.fps);
    const image=await page.screenshot({type:'jpeg',quality:94,timeout:30000});
    if(encoder.exitCode!==null)throw Error(`FFmpeg exited early: ${stderr}`);
    if(!encoder.stdin.write(image))await Promise.race([once(encoder.stdin,'drain'),completed.then(()=>{throw Error(`FFmpeg exited during frame write: ${stderr}`);})]);
    if(options.previews&&[0,Math.min(frames-1,Math.round((spec.reveal_at+1.6)*spec.fps))].includes(index))await fs.writeFile(previewPaths[index===0?0:1],image,{flag:'wx'});
  }
  encoder.stdin.end();const [code]=await completed;if(code!==0)throw Error(`FFmpeg failed: ${stderr}`);
  // link publishes exclusively, so a file created during rendering survives too.
  await fs.link(pending,output);await fs.unlink(pending);ownsPending=false;
  console.log(JSON.stringify({output,frames,...spec,...info,elapsed_seconds:(performance.now()-started)/1000,node_peak_rss_mib:process.resourceUsage().maxRSS/1024,provider_requests:0}));
} catch(error){encoder?.kill('SIGKILL');if(ownsPending)await fs.rm(pending,{force:true});throw error;}
finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
