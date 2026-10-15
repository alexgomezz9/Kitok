import { useEffect, useState, type ReactNode } from 'react'
import { api } from './api'

// A small, safe renderer for our local guide. Content is rendered as React text,
// never HTML. The same GUIA.md serves people, CLI users and future agents.
function document(markdown:string) {
 const nodes:ReactNode[]=[];let paragraph:string[]=[];let code:string[]|null=null
 const flush=()=>{if(paragraph.length){nodes.push(<p key={nodes.length}>{paragraph.join(' ')}</p>);paragraph=[]}}
 for(const line of markdown.split('\n')) {
  if(line.startsWith('```')){flush();if(code){nodes.push(<pre key={nodes.length}><code>{code.join('\n')}</code></pre>);code=null}else code=[];continue}
  if(code){code.push(line);continue}
  if(!line.trim()){flush();continue}
  const heading=/^(#{1,3}) (.*)$/.exec(line)
  if(heading){flush();nodes.push(heading[1].length<3?<h2 key={nodes.length}>{heading[2]}</h2>:<h3 key={nodes.length}>{heading[2]}</h3>);continue}
  if(/^(- |\d+\. )/.test(line)){flush();nodes.push(<p className="guide-step" key={nodes.length}>{line.replace(/^- /,'• ')}</p>);continue}
  paragraph.push(line)
 }
 flush();return nodes
}
export default function Guide(){
 const [markdown,setMarkdown]=useState(''),[error,setError]=useState('')
 useEffect(()=>{api<{markdown:string}>('/guide').then(r=>setMarkdown(r.markdown)).catch(e=>setError(e.message))},[])
 return <><div className="page-heading"><div><p className="eyebrow">TU MANUAL, SIEMPRE A MANO</p><h1>Cómo usar Kitok.</h1><p>La misma guía está en el archivo GUIA.md del proyecto.</p></div></div>{error&&<p role="alert">{error}</p>}<article className="panel guide-document">{markdown?document(markdown):!error&&<p>Cargando guía…</p>}</article></>
}
