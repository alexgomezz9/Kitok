// Central HTTP contract. Python validates all requests; /openapi.json is authoritative.
export type Turn = { speaker: string; text: string }
export type Content = { id: string; subject: string; script: string; keywords: string[]; caption: string; content_format: 'explainer'|'dialogue'; voice_profile: string; visual_profile: string; dialogue: Turn[]|null; dialogue_preset: string|null; character_profile: string|null; platforms: string[]; publish_at: string|null; schedule_enabled: boolean; background_file?: string|null; visual_seed?: string|null; background_seed?: string|null }
export type Video = { item: Content; status: string; generation_status:string; schedule_status:'unscheduled'|'queued'|'scheduled'|'published'; publishing_status:string|null; queue_position:number|null; stage: string|null; job: { id?: string; status?: string; error?: string }; error: string|null; technical_error: string|null; preview_url: string|null; thumbnail_url: string|null; duration: number|null; scheduled_at: string|null; remote_locked: boolean; buffer: Record<string,{post_id?: string;status?:string;due_at?:string}>; warnings: string[] }
export type Format = { id:string; name:string; content_format:'explainer'|'dialogue'; voice_profile?:string; dialogue_preset?:string; character_profile?:string; speakers?:string[] }
export type Metadata = { voices:{id:string;display_name:string;provider:string;value:string}[]; visual_profiles:string[]; formats:Format[]; timezone:string; default_visual_profile:string }
export type Character = { id:string;display_name:string;side:string;scale:number;poses:{name:string;filename:string;url:string}[];warnings:string[] }
export type Background = {id:string;pool:string;filename:string;duration?:number;width?:number;height?:number;codec?:string;size?:number;compatible:boolean;error?:string}
export type Calendar = {timezone:string;items:Video[];queued:Video[];unscheduled:Video[];conflicts:{ids:string[];platforms:string[]}[];slots:{at:string;occupied_platforms:string[]}[];remote_changes_supported:boolean}
export async function api<T>(path:string, options:RequestInit={}):Promise<T> {
  let response:Response
  try { response=await fetch(`/api${path}`,{...options,headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...options.headers}}) }
  catch {throw new Error('No se puede conectar con Kitok. Comprueba que el backend está abierto en el puerto 8000.')}
  if(!response.ok){let message='No se pudo completar la operación';try{const data=await response.json();message=typeof data.detail==='string'?data.detail:message}catch{};throw new Error(message)}
  return response.json()
}
export const send = <T>(path:string,body:unknown={},method='POST')=>api<T>(path,{method,body:JSON.stringify(body)})
export const statusNames:Record<string,string>={pending:'Borrador',generating:'Generando',submitted:'Generando',generated:'Validando',ready:'Ready',failed:'Error',unscheduled:'Sin fecha',queued:'En cola',published:'Publicado',scheduled:'Programado',attention:'Revisar'}
export function localInput(iso:string,zone:string){const parts=new Intl.DateTimeFormat('sv-SE',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(iso));return parts.replace(' ','T')}
