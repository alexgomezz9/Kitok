// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Workbench, { EditorialWorkbench } from './Workbench'
import PublishReview from './PublishReview'
import type { Metadata } from './api'

const metadata:Metadata={voices:[{id:'rick_es',display_name:'Rick ES',provider:'fish',value:'rick'},{id:'morty_es',display_name:'Morty ES',provider:'fish',value:'morty'},{id:'alvaro',display_name:'Álvaro',provider:'edge',value:'edge'}],visual_profiles:['gameplay','random','pexels'],formats:[{id:'classic',name:'Clásico',content_format:'explainer',voice_profile:'alvaro'},{id:'rick_morty_es',name:'Rick y Morty',content_format:'dialogue',dialogue_preset:'rick_morty_es',character_profile:'rick_morty_es',speakers:['rick_es','morty_es']}],timezone:'Europe/Madrid',default_visual_profile:'gameplay'}
const ok={valid:true,can_generate:true,words:40,checks:[{label:'FFmpeg',ok:true}],note:'Comprobación local.'}
let requests:{path:string;body:unknown}[]=[]
let longRows:unknown[]=[]
let props:ComponentProps<typeof Workbench>
beforeEach(()=>{
 requests=[];longRows=[];props={mode:'short',meta:metadata,onMode:vi.fn(),onCreated:vi.fn(),onError:vi.fn()}
 vi.stubGlobal('fetch',vi.fn(async(path:string,options?:RequestInit)=>{
  const body=options?.body?JSON.parse(String(options.body)):null
  requests.push({path,body})
  let value:unknown=path==='/api/longform'?longRows:path==='/api/longform-options'?{music_tracks:[{id:'long_note_two',title:'Long Note Two',author:'Kevin MacLeod',moods:['investigation'],preview_url:'/api/longform/music/long_note_two/preview'}]}:path==='/api/motion'||path==='/api/voices-library'?[]:ok
  if(path==='/api/content')value={item:{id:'new_short'}}
  if(path==='/api/longform'&&options?.method==='POST'){value={id:'lf_1',subject:'Mi documental',status:'draft',renderer:'native',stage:'Guion guardado',created_at:'2026-10-15T10:00:00Z',config_path:'/tmp/kitok/content/longform/studio/lf_1.json',script_path:'/tmp/kitok/content/longform/studio/lf_1.txt',output_path:'/tmp/kitok/outputs/longform/lf_1.mp4',script:'Un guion completo y suficientemente largo.',keywords:['city','science'],narrator_voice:'fish_audio:voice:Test',music_enabled:false,preview_url:null,download_url:null,error:null};longRows=[value]}
  return {ok:true,json:async()=>value}
 }))
})
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
function fillShort(){fireEvent.change(screen.getByLabelText('Título'),{target:{value:'Mi short'}});fireEvent.change(screen.getByLabelText('Guion completo'),{target:{value:'Una narración suficientemente larga para probar el vídeo.'}})}
function fillLong(){fireEvent.change(screen.getByLabelText('Título'),{target:{value:'Mi documental'}});fireEvent.change(screen.getByLabelText('Guion completo'),{target:{value:'Un guion completo y suficientemente largo para este documental.'}});fireEvent.change(screen.getByLabelText('Qué imágenes buscar (separadas por comas)'),{target:{value:'city, science'}})}

describe('guided studio',()=>{
 it('audits a failed long video before explicitly confirming reuse of paid narration',async()=>{
  longRows=[{id:'lf_failed',subject:'Paid narration',status:'failed',renderer:'native',stage:'Needs review',created_at:'2026-10-20',config_path:'/tmp/job.json',script_path:'/tmp/job.txt',output_path:'/tmp/job.mp4',script:'An existing paid narration.',keywords:['city'],narrator_voice:'fish_audio:voice:Original',music_enabled:false,error:'Original failure'}];
  const original=vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async(path,options)=>{
   if(String(path).endsWith('/recovery')){
    requests.push({path:String(path),body:options?.body?JSON.parse(String(options.body)):null});
    return {ok:true,json:async()=>({narration_sha256:'a'.repeat(64),audit_fingerprint:'b'.repeat(64),duration:654.733,note:'Sólo caché local.'})} as Response;
   }
   return original(path,options)
  });
  render(<Workbench {...props} mode="long"/>);
  fireEvent.click(await screen.findByRole('button',{name:/Paid narration/}));
  fireEvent.click(screen.getByRole('button',{name:'Revisar recuperación sin generar'}));
  await screen.findByText(/Narración confirmada: 654.733/);
  expect(requests.filter(r=>r.path.endsWith('/recovery')).map(r=>r.body)).toEqual([null]);
  fireEvent.click(screen.getByRole('button',{name:'Recuperar montaje usando esta voz · sin Fish ni red'}));
  await waitFor(()=>expect(requests.filter(r=>r.path.endsWith('/recovery'))).toHaveLength(2));
  expect(requests.filter(r=>r.path.endsWith('/recovery'))[1].body).toEqual({narration_sha256:'a'.repeat(64),audit_fingerprint:'b'.repeat(64)});
  expect(requests.some(r=>r.path.includes('/jobs'))).toBe(false);
 })
 it('offers the two modes and keeps advanced controls folded',()=>{render(<Workbench {...props}/>);fireEvent.click(screen.getByRole('button',{name:/Vídeo largo/}));expect(props.onMode).toHaveBeenCalledWith('long');expect(screen.getByText('Opciones avanzadas').closest('details')?.open).toBe(false)})
 it('checks shorts without creating content or starting a job',async()=>{render(<Workbench {...props}/>);fillShort();fireEvent.click(screen.getByRole('button',{name:'Comprobar sin generar'}));await screen.findByText('Comprobación sin generar');expect(requests.map(r=>r.path)).toEqual(['/api/content-preview']);expect(requests[0].body).toMatchObject({visual_profile:'random',voice_profile:'rick_es'});fireEvent.click(screen.getByRole('button',{name:/Guardar borrador y continuar/}));await waitFor(()=>expect(props.onCreated).toHaveBeenCalledWith('new_short'));expect(requests.some(r=>r.path.includes('/jobs'))).toBe(false)})
 it('invalidates the preview when the script changes',async()=>{render(<Workbench {...props}/>);fillShort();fireEvent.click(screen.getByRole('button',{name:'Comprobar sin generar'}));await screen.findByText('Comprobación sin generar');fireEvent.change(screen.getByLabelText('Guion completo'),{target:{value:'Un guion diferente que necesita una nueva revisión.'}});expect(screen.queryByText('Guardar borrador y continuar')).toBeNull()})
 it('shows missing prerequisites and prevents advancing',async()=>{vi.mocked(fetch).mockResolvedValue({ok:true,json:async()=>({...ok,can_generate:false,checks:[{label:'FISH_API_KEY',ok:false}]})} as Response);render(<Workbench {...props}/>);fillShort();fireEvent.click(screen.getByRole('button',{name:'Comprobar sin generar'}));await screen.findByText('Falta configurar');expect((screen.getByRole('button',{name:/Guardar borrador y continuar/}) as HTMLButtonElement).disabled).toBe(true)})
 it('stores a long-form draft before an explicit paid generation',async()=>{render(<Workbench {...props} mode="long"/>);fillLong();fireEvent.click(screen.getByRole('button',{name:'Comprobar sin generar'}));await screen.findByText('Comprobación sin generar');fireEvent.click(screen.getByRole('button',{name:'Guardar borrador'}));await screen.findByRole('button',{name:'Generar vídeo largo (usa voz y stock)'});expect(requests.some(r=>r.path.includes('/jobs'))).toBe(false);expect(requests.find(r=>r.path==='/api/longform-preview')?.body).toMatchObject({renderer:'native',music_enabled:false,keywords:['city','science']});fireEvent.click(screen.getByRole('button',{name:'Generar vídeo largo (usa voz y stock)'}));await waitFor(()=>expect(requests.some(r=>r.path==='/api/longform/lf_1/jobs')).toBe(true))})
 it('sends explicit documentary and manual music choices without starting generation',async()=>{
  render(<Workbench {...props} mode="long"/>);fillLong();
  fireEvent.change(screen.getByLabelText('Montaje'),{target:{value:'documentary'}});
  fireEvent.change(screen.getByLabelText('Música'),{target:{value:'manual'}});
  await screen.findByRole('option',{name:'Long Note Two · Kevin MacLeod'});
  fireEvent.change(screen.getByLabelText('Pista musical'),{target:{value:'long_note_two'}});
  fireEvent.change(screen.getByLabelText('Narrador'),{target:{value:'fish_audio:morty:Morty ES'}});
  fireEvent.click(screen.getByRole('button',{name:'Comprobar sin generar'}));
  await screen.findByText('Comprobación sin generar');
  expect(requests.find(r=>r.path==='/api/longform-preview')?.body).toMatchObject({mounting_style:'documentary',music_mode:'manual',music_track:'long_note_two',narrator_voice:'fish_audio:morty:Morty ES'});
  expect(requests.some(r=>r.path.includes('/jobs'))).toBe(false);
  fireEvent.change(screen.getByLabelText('Música'),{target:{value:'off'}});
  expect(screen.queryByRole('button',{name:'Guardar borrador'})).toBeNull();
 })
 it('auditions existing library samples and saves voice preferences without generation',async()=>{
  let voice={id:'licensed_narrator',reference_id:'12345678901234567890123456789012',display_name:'Licensed Narrator',languages:['en'],tags:['documentary'],selectable:true,favorite:false,assigned_channels:[] as string[],samples:[{url:'/api/voices-library/licensed_narrator/samples/0',kind:'preview'}]};
  vi.mocked(fetch).mockImplementation(async(path,options)=>{
   const body=options?.body?JSON.parse(String(options.body)):null;requests.push({path:String(path),body});
   if(String(path).endsWith('/favorite'))voice={...voice,favorite:body.enabled};
   if(String(path).endsWith('/assign'))voice={...voice,assigned_channels:[body.channel]};
   return {ok:true,json:async()=>String(path).startsWith('/api/voices-library')?[voice]:String(path)==='/api/longform'?[]:{music_tracks:[]}} as Response;
  });
  render(<Workbench {...props} mode="long"/>);
  await screen.findByLabelText('Escuchar Licensed Narrator 1');
  expect(screen.getByLabelText('Escuchar Licensed Narrator 1').getAttribute('preload')).toBe('none');
  fireEvent.click(screen.getByRole('button',{name:'Guardar favorito · Licensed Narrator'}));
  await screen.findByRole('button',{name:'Quitar favorito · Licensed Narrator'});
  fireEvent.click(screen.getByRole('button',{name:'Usar en loose_thread'}));
  await screen.findByRole('button',{name:'Asignada a loose_thread'});
  expect((screen.getByLabelText('Narrador') as HTMLSelectElement).value).toBe('fish_audio:12345678901234567890123456789012:Licensed Narrator');
  expect(requests.some(r=>r.path.includes('/jobs'))).toBe(false);
 })
 it('invalidates a completed review when a delayed assigned voice arrives',async()=>{
  const original=vi.mocked(fetch).getMockImplementation()!;
  let resolve!:(response:Response)=>void;
  vi.mocked(fetch).mockImplementation((path,options)=>String(path)==='/api/voices-library'?new Promise<Response>(r=>{resolve=r}):original(path,options));
  render(<Workbench {...props} mode="long"/>);fillLong();
  fireEvent.click(screen.getByRole('button',{name:'Comprobar sin generar'}));
  await screen.findByRole('button',{name:'Guardar borrador'});
  resolve({ok:true,json:async()=>[{id:'saved',reference_id:'12345678901234567890123456789012',display_name:'Saved voice',languages:['en'],tags:[],selectable:true,favorite:false,assigned_channels:['loose_thread'],samples:[]}]} as Response);
  await waitFor(()=>expect((screen.getByLabelText('Narrador') as HTMLSelectElement).value).toContain('Saved voice'));
  expect(screen.queryByRole('button',{name:'Guardar borrador'})).toBeNull();
 })
 it('preserves the selected narrator when saving a channel assignment fails',async()=>{
  const original=vi.mocked(fetch).getMockImplementation()!;
  const voice={id:'candidate',reference_id:'12345678901234567890123456789012',display_name:'Candidate',languages:['en'],tags:[],selectable:true,favorite:false,assigned_channels:[],samples:[]};
  vi.mocked(fetch).mockImplementation((path,options)=>{
   if(String(path)==='/api/voices-library')return Promise.resolve({ok:true,json:async()=>[voice]} as Response);
   if(String(path)==='/api/voices-library/assign')return Promise.resolve({ok:false,json:async()=>({detail:'No se guardó la asignación'})} as Response);
   return original(path,options)
  });
  render(<Workbench {...props} mode="long"/>);
  await screen.findByRole('button',{name:'Usar en loose_thread'});
  fireEvent.change(screen.getByLabelText('Narrador'),{target:{value:'fish_audio:rick:Rick ES'}});
  fireEvent.click(screen.getByRole('button',{name:'Usar en loose_thread'}));
  await screen.findByText('No se guardó la asignación');
  expect((screen.getByLabelText('Narrador') as HTMLSelectElement).value).toBe('fish_audio:rick:Rick ES');
 })
 it('keeps the default narrator label when assigning the baseline voice',async()=>{
  const original=vi.mocked(fetch).getMockImplementation()!;
  const voice={id:'baseline',reference_id:'e686ae649ee44f219a108aacba206c1a',display_name:'Loose Thread',languages:['en'],tags:[],selectable:true,favorite:false,assigned_channels:[],samples:[]};
  vi.mocked(fetch).mockImplementation((path,options)=>String(path).startsWith('/api/voices-library')?Promise.resolve({ok:true,json:async()=>[voice]} as Response):original(path,options));
  render(<Workbench {...props} mode="long"/>);
  await screen.findByRole('button',{name:'Usar en loose_thread'});
  fireEvent.change(screen.getByLabelText('Narrador'),{target:{value:'fish_audio:rick:Rick ES'}});
  fireEvent.click(screen.getByRole('button',{name:'Usar en loose_thread'}));
  await waitFor(()=>expect((screen.getByLabelText('Narrador') as HTMLSelectElement).value).toBe(''));
  expect(screen.getByRole('option',{name:'Loose Thread · narrador original (inglés)'})).toBeTruthy();
 })
 it('offers local music audition in manual and automatic modes before generation',async()=>{
  render(<Workbench {...props} mode="long"/>);
  fireEvent.change(screen.getByLabelText('Música'),{target:{value:'manual'}});
  await screen.findByRole('option',{name:'Long Note Two · Kevin MacLeod'});
  fireEvent.change(screen.getByLabelText('Pista musical'),{target:{value:'long_note_two'}});
  const player=screen.getByLabelText('Escuchar música Long Note Two');
  expect(player.getAttribute('src')).toBe('/api/longform/music/long_note_two/preview');
  expect(player.getAttribute('preload')).toBe('none');
  fireEvent.change(screen.getByLabelText('Música'),{target:{value:'auto'}});
  expect(screen.getByText('Escuchar biblioteca musical').closest('details')?.open).toBe(false);
  expect(screen.getByLabelText('Escuchar música Long Note Two')).toBeTruthy();
  expect(requests.some(r=>r.path.includes('/jobs'))).toBe(false);
 })
 it('keeps custom dialogue presets available under advanced options',async()=>{const meta={...metadata,formats:[...metadata.formats,{id:'custom_cast',name:'Mi reparto',content_format:'dialogue' as const,dialogue_preset:'custom_cast',speakers:['morty_es','rick_es']}]};render(<Workbench {...props} meta={meta}/>);fireEvent.change(screen.getByLabelText('Estilo'),{target:{value:'dialogue'}});fireEvent.change(screen.getByLabelText('Reparto del diálogo'),{target:{value:'custom_cast'}});expect((screen.getByLabelText('Personaje 1') as HTMLSelectElement).value).toBe('morty_es');fireEvent.change(screen.getByLabelText('Título'),{target:{value:'Diálogo personalizado'}});fireEvent.change(screen.getByLabelText('Texto 1'),{target:{value:'Un primer turno completo.'}});fireEvent.change(screen.getByLabelText('Texto 2'),{target:{value:'Una respuesta completa.'}});fireEvent.click(screen.getByRole('button',{name:'Comprobar sin generar'}));await screen.findByText('Comprobación sin generar');expect(requests[0].body).toMatchObject({dialogue_preset:'custom_cast',dialogue:[{speaker:'morty_es',text:'Un primer turno completo.'},{speaker:'rick_es',text:'Una respuesta completa.'}]})})
 it('discards a delayed preview if the user edits its input meanwhile',async()=>{let resolve!:(response:Response)=>void;vi.mocked(fetch).mockImplementationOnce(()=>new Promise<Response>(r=>{resolve=r}));render(<Workbench {...props}/>);fillShort();fireEvent.click(screen.getByRole('button',{name:'Comprobar sin generar'}));fireEvent.change(screen.getByLabelText('Guion completo'),{target:{value:'Otro guion completo que necesita revisión.'}});resolve({ok:true,json:async()=>ok} as Response);await waitFor(()=>expect((screen.getByRole('button',{name:'Comprobar sin generar'}) as HTMLButtonElement).disabled).toBe(false));expect(screen.queryByText('Guardar borrador y continuar')).toBeNull()})
 it('shows an actionable error when a preview fails',async()=>{vi.mocked(fetch).mockRejectedValue(new Error('offline'));render(<Workbench {...props}/>);fillShort();fireEvent.click(screen.getByRole('button',{name:'Comprobar sin generar'}));await waitFor(()=>expect(props.onError).toHaveBeenCalledWith(expect.stringContaining('backend')));expect(screen.queryByText('Guardar borrador y continuar')).toBeNull()})
 it('previews Buffer separately from confirming the actual send',async()=>{vi.mocked(fetch).mockImplementation(async(path)=>{requests.push({path:String(path),body:null});return {ok:true,json:async()=>({token:'review',summary:{posts:2,uploads:1,estimated_requests:4,occupancy:'cache',issues:[],platforms:{tiktok:1,youtube:1}},rows:[]})} as Response});const done=vi.fn();render(<PublishReview id="short_1" onDone={done}/>);fireEvent.click(screen.getByRole('button',{name:'Previsualizar envío (dry-run)'}));await screen.findByRole('button',{name:'Confirmar envío a Buffer'});expect(requests.map(r=>r.path)).toEqual(['/api/content/short_1/publish-preview']);fireEvent.click(screen.getByRole('button',{name:'Confirmar envío a Buffer'}));await waitFor(()=>expect(done).toHaveBeenCalledOnce());expect(requests[1].path).toBe('/api/publish/review/confirm')})
})


describe('local editorial comparison',()=>{
 const row={id:'sample_ab',title:'Saved edit',status:'ready',stage:'Plan guardado',error:null,duration:76,scene_count:12,files:{'A_current.mp4':'/api/editorial/sample_ab/files/A_current.mp4','B_improved.mp4':'/api/editorial/sample_ab/files/B_improved.mp4'},stats:{duration:76,geometry:[1920,1080],fps:30,full_decode:'passed',comparison:{audio_identical:true},black_intervals:[]}}
 it('reads existing A/B without starting a render and starts only on explicit action',async()=>{
  vi.mocked(fetch).mockImplementation(async(path,options)=>{requests.push({path:String(path),body:null});return {ok:true,json:async()=>String(path)==='/api/motion'?[]:options?.method==='POST'?row:[row]} as Response})
  render(<EditorialWorkbench onError={vi.fn()}/>);
  await screen.findByText('Saved edit',{selector:'h2'});
  expect(screen.getByLabelText('Vídeo A').getAttribute('src')).toContain('/files/A_current.mp4');
  expect(screen.getByLabelText('Vídeo B').getAttribute('src')).toContain('/files/B_improved.mp4');
  expect(requests.map(r=>r.path).sort()).toEqual(['/api/editorial','/api/motion']);
  expect(screen.getByText(/Audio A\/B: idéntico/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Renderizar plan guardado · reutiliza audio'}));
  await waitFor(()=>expect(requests.some(r=>r.path==='/api/editorial/sample_ab/jobs')).toBe(true));
 })
 it('shows existing motion previews and downloads without any job request',async()=>{
  vi.mocked(fetch).mockImplementation(async(path)=>{
   requests.push({path:String(path),body:null});
   return {ok:true,json:async()=>String(path)==='/api/motion'?[{id:'generic',title:'Documental de muestra',family:'investigation',duration:18,kind:'sample',files:{'preview.mp4':'/api/motion/generic/files/preview.mp4','CREDITS.md':'/api/motion/generic/files/CREDITS.md'}}]:[]} as Response
  });
  vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});
  vi.spyOn(HTMLMediaElement.prototype,'load').mockImplementation(()=>{});
  render(<EditorialWorkbench onError={vi.fn()}/>);
  await screen.findByRole('button',{name:'Reproducir muestra · Documental de muestra'});
  expect(screen.queryByLabelText('Muestra Documental de muestra')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Reproducir muestra · Documental de muestra'}));
  expect(screen.getByLabelText('Muestra Documental de muestra')).toBeTruthy();
  expect(screen.getByRole('link',{name:'Descargar muestra'}).getAttribute('href')).toBe('/api/motion/generic/files/preview.mp4');
  expect(requests.every(r=>!r.path.includes('/jobs'))).toBe(true);
 })
 it('loads a single gallery player on demand and exposes download after decode failure',async()=>{
  const items=['one','two'].map(id=>({id,title:id,family:'investigation',duration:4,kind:id==='two'?'sample':'effect',files:{'preview.mp4':`/api/motion/${id}/files/preview.mp4`,'baseline.mp4':`/api/motion/${id}/files/baseline.mp4`,'contact.jpg':`/api/motion/${id}/files/contact.jpg`}}));
  vi.mocked(fetch).mockImplementation(async(path)=>({ok:true,json:async()=>String(path)==='/api/motion'?items:[]}) as Response);
  const pause=vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});
  const load=vi.spyOn(HTMLMediaElement.prototype,'load').mockImplementation(()=>{});
  const {container}=render(<EditorialWorkbench onError={vi.fn()}/>);
  await screen.findByRole('button',{name:'Reproducir muestra · one'});
  expect(container.querySelectorAll('video')).toHaveLength(0);
  expect(screen.getAllByRole('button',{name:/Reproducir muestra ·/})[0].getAttribute('aria-label')).toBe('Reproducir muestra · two');
  fireEvent.click(screen.getByRole('button',{name:'Reproducir muestra · one'}));
  const first=screen.getByLabelText('Muestra one');
  expect(first.hasAttribute('poster')).toBe(false);
  Object.defineProperty(first,'error',{value:{code:3}});fireEvent.error(first);
  expect(screen.getByRole('alert').textContent).toContain('no pudo decodificar');
  expect(screen.getByRole('link',{name:'Descargar este MP4'}).getAttribute('href')).toContain('/one/files/preview.mp4');
  fireEvent.click(screen.getByRole('button',{name:'Reproducir muestra · one'}));
  expect(screen.getByLabelText('Muestra one')).not.toBe(first);
  expect(first.getAttribute('src')).toBeNull();
  expect(pause).toHaveBeenCalled();expect(load).toHaveBeenCalled();
  expect(screen.queryByRole('alert')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Reproducir referencia · two'}));
  expect(container.querySelectorAll('video')).toHaveLength(1);
  expect(screen.queryByLabelText('Muestra one')).toBeNull();
  expect(screen.getByLabelText('Referencia two').getAttribute('src')).toContain('/two/files/baseline.mp4');
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.getByAltText('Fotogramas estáticos de revisión de one').getAttribute('src')).toContain('/one/files/contact.jpg');
 });
 it('disables a second render while the shared worker is busy',async()=>{
  vi.mocked(fetch).mockImplementation(async(path)=>({ok:true,json:async()=>String(path)==='/api/motion'?[]:[{...row,status:'running'}]}) as Response);
  render(<EditorialWorkbench onError={vi.fn()}/>);
  expect((await screen.findByRole('button',{name:'Montaje en curso…'}) as HTMLButtonElement).disabled).toBe(true);
 })
 it('loads the promoted B revision after completion even when the run id is unchanged',async()=>{
  let poll:(()=>void)|undefined;
  const schedule=globalThis.setInterval;
  vi.spyOn(globalThis,'setInterval').mockImplementation((callback,delay,...args)=>{
   if(delay===3000)poll=callback as ()=>void;
   return schedule(callback,delay,...args)
  });
  let current={...row,status:'running',run_id:'same-run',media_revision:'previous-video'};
  vi.mocked(fetch).mockImplementation(async(path)=>({ok:true,json:async()=>String(path)==='/api/motion'?[]:[current]}) as Response);
  try{
   render(<EditorialWorkbench onError={vi.fn()}/>);
   await screen.findByText('Saved edit',{selector:'h2'});
   expect(screen.getByLabelText('Vídeo B').getAttribute('src')).toContain('previous-video');
   current={...current,status:'succeeded',media_revision:'promoted-video'};
   poll?.();
   await waitFor(()=>expect(screen.getByLabelText('Vídeo B').getAttribute('src')).toContain('promoted-video'));
  }finally{vi.mocked(globalThis.setInterval).mockRestore()}
 })
 it('offers Fish for stock shorts and no MPT selector for new long videos',()=>{
  const rendered=render(<Workbench {...props}/>);
  fireEvent.change(screen.getByLabelText('Estilo'),{target:{value:'classic'}});
  expect(screen.queryByRole('option',{name:'Álvaro'})).toBeNull();
  expect((screen.getByLabelText('Voz de la narración') as HTMLSelectElement).value).toBe('rick_es');
  rendered.rerender(<Workbench {...props} mode="long"/>);
  expect(screen.queryByLabelText('Motor')).toBeNull();
  expect(screen.queryByRole('option',{name:/MoneyPrinterTurbo/})).toBeNull();
 })
})

describe('episode photographs and a new montage',()=>{
 it('adds a minimal image anchor and invalidates a prior review without generating',async()=>{
  const original=vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation((path,options)=>String(path)==='/api/longform/episodes'?Promise.resolve({ok:true,json:async()=>[{id:'3_ultimatebet',images:[{asset:'real_images/case.png',filename:'case.png'}]}]} as Response):original(path,options));
  render(<Workbench {...props} mode="long"/>);fillLong();
  fireEvent.click(screen.getByText('Fotografías y documentos del caso · opcional'));
  await screen.findByRole('option',{name:'3_ultimatebet'});
  fireEvent.change(screen.getByLabelText('Carpeta del episodio'),{target:{value:'3_ultimatebet'}});
  fireEvent.click(screen.getByRole('button',{name:'Comprobar sin generar'}));
  await screen.findByRole('button',{name:'Guardar borrador'});
  fireEvent.change(screen.getByLabelText('Fotografía del caso'),{target:{value:'real_images/case.png'}});
  fireEvent.change(screen.getByLabelText('Mostrar al decir esta frase exacta'),{target:{value:'guion completo'}});
  fireEvent.click(screen.getByRole('button',{name:'Añadir imagen en esta frase'}));
  expect(screen.queryByRole('button',{name:'Guardar borrador'})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Comprobar sin generar'}));
  await screen.findByRole('button',{name:'Guardar borrador'});
  expect(requests.filter(r=>r.path==='/api/longform-preview').at(-1)?.body).toMatchObject({episode_id:'3_ultimatebet',visual_plan:{visual_cues:[{asset:'real_images/case.png',anchor:{phrase:'guion completo'}}]}});
  expect(requests.some(r=>r.path.includes('/jobs'))).toBe(false);
 });
 it('rejects malformed visual JSON locally before any preview or job request',async()=>{
  render(<Workbench {...props} mode="long"/>);fillLong();
  fireEvent.change(screen.getByLabelText('Plan visual JSON'),{target:{value:'{broken'}});
  fireEvent.click(screen.getByRole('button',{name:'Comprobar sin generar'}));
  await waitFor(()=>expect(props.onError).toHaveBeenCalledWith('El JSON visual no es válido. Revísalo antes de comprobar.'));
  expect(requests.some(r=>r.path==='/api/longform-preview'||r.path.includes('/jobs'))).toBe(false);
 });
 it('saves a distinct montage then audits and explicitly starts original narration reuse',async()=>{
  const source={config_path:'/tmp/original.json',script_path:'/tmp/original.txt',output_path:'/tmp/original.mp4',id:'lf_original',subject:'Original documentary',status:'succeeded',renderer:'native',stage:'Complete',created_at:'2026-10-20',script:'An original narration that must stay identical.',keywords:['city'],narrator_voice:'fish_audio:voice:Original',music_enabled:false,error:null};
  longRows=[source];
  const original=vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async(path,options)=>{
   if(String(path)==='/api/longform'&&options?.method==='POST'){
    const body=JSON.parse(String(options.body));requests.push({path:String(path),body});const row={...source,...body,id:'lf_new',status:'draft'};longRows=[row,source];return {ok:true,json:async()=>row} as Response;
   }
   if(String(path).includes('/remount')){requests.push({path:String(path),body:options?.body?JSON.parse(String(options.body)):null});return {ok:true,json:async()=>({narration_sha256:'a'.repeat(64),audit_fingerprint:'b'.repeat(64),duration:12,note:'Sólo caché local.'})} as Response}
   return original(path,options)
  });
  render(<Workbench {...props} mode="long"/>);
  await screen.findByRole('option',{name:/Reutilizar voz: Original documentary/});
  fireEvent.change(screen.getByLabelText('Narración para este montaje'),{target:{value:'lf_original'}});
  expect((screen.getByLabelText('Guion completo') as HTMLTextAreaElement).readOnly).toBe(true);
  expect((screen.getByLabelText('Narrador') as HTMLSelectElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:'Comprobar sin generar'}));
  await screen.findByRole('button',{name:'Guardar borrador'});
  fireEvent.click(screen.getByRole('button',{name:'Guardar borrador'}));
  fireEvent.click(await screen.findByRole('button',{name:'Revisar voz original sin generar'}));
  await screen.findByText(/Narración confirmada: 12.000/);
  expect(requests.filter(r=>r.path.includes('/remount'))).toHaveLength(1);
  expect(requests.find(r=>r.path==='/api/longform'&&r.body)?.body).toMatchObject({source_narration_id:'lf_original',script:source.script,narrator_voice:source.narrator_voice});
  fireEvent.click(screen.getByRole('button',{name:'Iniciar nuevo montaje · sin Fish ni red'}));
  await waitFor(()=>expect(requests.filter(r=>r.path.includes('/remount'))).toHaveLength(2));
  expect(requests.filter(r=>r.path.includes('/remount'))[1].body).toEqual({source_id:'lf_original',narration_sha256:'a'.repeat(64),audit_fingerprint:'b'.repeat(64)});
  expect(requests.some(r=>r.path.includes('/jobs'))).toBe(false);
 });
});
