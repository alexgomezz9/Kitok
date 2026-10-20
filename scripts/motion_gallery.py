#!/usr/bin/env python3
"""Build short local motion proofs with existing media. Never calls a speech/stock API.

Effects are a generic gallery. Sample configs explicitly bound an existing audio
interval to <=40s; this tool cannot render a complete documentary.
"""
from pathlib import Path
import argparse
import json
import math
import re
import subprocess
from types import SimpleNamespace

from kitok.audio_library import AudioLibrary, narrative_transition
from kitok.config import Settings, PROJECT_ROOT
from kitok.editing.manifest import build_edit_manifest
from kitok.editing.motion import motion_plan, provider_sections, automatic_sfx
from kitok.editing.motion_components import CATALOG, MotionDesign
from kitok.editing.production import render_editorial_plan
from kitok.editing.quality import inspect_video, contact_sheet
from kitok.editing.storyboard import EditorialPlan, EditorialScene, EditorialAsset, frame_time, project_file, file_hash
from kitok.longform.models import TimelineClip, TimelineSlot
from kitok.media.ffprobe import probe_media
from kitok.state import write_json_atomic


def run(command):
    subprocess.run(command,check=True,capture_output=True,timeout=1200)


def review(plan, folder, settings, *, title, family, kind, credits, baseline=None):
    output=folder/'preview.mp4'
    result=render_editorial_plan(plan,root=PROJECT_ROOT,output=output,settings=settings)
    points=[min(plan.duration-.1,s.start+.5*(s.end-s.start)) for s in plan.scenes]
    report=inspect_video(output,folder/'qa.json',settings=settings,comparison=baseline,scene_boundaries=points)
    # Name exposed through the read-only gallery route.
    (folder/'qa.contact.jpg').rename(folder/'contact.jpg')
    if len(points)<4:
        contact_sheet(output,folder/'contact.jpg',points,ffmpeg=settings.ffmpeg_binary,columns=len(points),label='Review')
    report['contact_sheet']=str(folder/'contact.jpg')
    report['contact_sheet_sha256']=file_hash(folder/'contact.jpg')
    write_json_atomic(folder/'qa.json',report)
    (folder/'CREDITS.md').write_text(credits,encoding='utf-8')
    write_json_atomic(folder/'item.json',{'id':folder.name,'title':title,'family':family,'kind':kind,
                      'duration':plan.duration,'preset':next((s.motion_design.preset for s in plan.scenes if s.motion_design),'investigation'),
                      'review':'Prueba local; revisar ritmo, sincronía y relevancia. Stock ilustrativo.'})
    plan.write(folder/'plan.json')
    return result


def effects(args, settings):
    root=PROJECT_ROOT
    revision=getattr(args,'revision',None)
    if revision and not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,23}',revision):
        raise ValueError('Revision must be a short lowercase ID')
    stock=project_file(root,str(args.stock))
    info=probe_media(stock,settings.ffprobe_binary)
    if info.duration < 4:
        raise ValueError('Gallery stock needs >=4 seconds')
    parent=root/'outputs/motion-gallery'
    parent.mkdir(parents=True,exist_ok=True)
    silence=parent/'gallery-silence.m4a'
    if not silence.exists():
        run([settings.ffmpeg_binary,'-nostdin','-v','error','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','4','-c:a','aac',str(silence)])
    defaults={
      'question':{'text':'What if the rules were never equal?','label':'THE QUESTION'},
      'kinetic':{'text':'One system. Two very different realities.','label':'PHRASE MOTION'},
      'keyword':{'text':'The boundary was supposed to protect everyone.','emphasis':'protect everyone','label':'MEANING BEFORE MOTION'},
      'amount':{'text':'$22 million','label':'An explicit quantity needs a clear context.','detail':'Demo data — not a historical claim.'},
      'identity':{'text':'Alex Morgan','label':'DEMONSTRATION / FICTIONAL NAME'},
      'date':{'text':'July 2007','label':'A CHANGE IN TIME','detail':'Date copied from the narration.'},
      'location':{'text':'Montréal, Canada','label':'DEMONSTRATION / PLACE'},
      'chapter':{'text':'The boundary','label':'CHAPTER 02','detail':'A pause before the explanation.'},
      'quote':{'text':'The software knew. The players did not.','label':'EDITORIAL DEMONSTRATION','detail':'An original line, not a sourced quotation.'},
      'document':{'text':'Access was limited to authorised accounts.','label':'DEMONSTRATION / ORIGINAL TEXT','detail':'Illustrative excerpt, not an archival document.'},
      'comparison':{'text':'Two possible outcomes','items':['Before — 10','After — 40'],'values':[10,40],'label':'ILLUSTRATIVE DATA / SAME UNIT'},
      'flow':{'text':'Where information travels','items':['Source','Permission','Account'],'symbols':['database','lock','person'],'label':'ILLUSTRATIVE SYSTEM DIAGRAM'},
    }
    for i,(effect,title,family) in enumerate(CATALOG):
        folder=parent/f'effect_{revision+"_" if revision else ""}{effect}'
        if (folder/'preview.mp4').exists():
            print(f'{folder.name}: existing; preserved',flush=True)
            continue
        folder.mkdir(exist_ok=True)
        design=MotionDesign(effect=effect,preset=['investigation','archive','signal'][i%3],**defaults.get(effect,{}))
        footage=family in {'footage','transitions'} or effect in {'identity','location'}
        scenes=[EditorialScene(id='demo',start=0,end=4,intention=title,spoken_claim='Demonstration only',
                  asset='stock' if footage else None,graphic=None if footage else 'motion',motion_design=design)]
        if family=='transitions':
            scenes=[EditorialScene(id='before',start=0,end=2,intention='Before',spoken_claim='Demonstration only',
                                  graphic='motion',motion_design=MotionDesign(effect='chapter',text='Before',preset='archive')),
                    EditorialScene(id='after',start=2,end=4,intention='After',spoken_claim='Demonstration only',
                                  asset='stock',transition=effect)]
        plan=EditorialPlan(episode_id=f'gallery_{effect}',title=title,audio_source=str(silence.relative_to(root)),
             duration=4,width=args.width,height=args.height,audio_is_final_mix=True,
             assets={'stock':EditorialAsset(path=str(stock.relative_to(root)),description='Demonstration stock',source_url=args.source_url,credit=args.credit)},scenes=scenes)
        review(plan,folder,settings,title=title,family=family,kind='effect',
               credits=f'# Credits\n\nStock is illustrative. {args.credit}\n{args.source_url}\nPexels License: https://www.pexels.com/license/\n\nMotion: original Kitok compositions; DejaVu fonts. Silent individual demonstration. Example figures and names are explicitly illustrative.\n')
        print(f'{folder.name}: rendered',flush=True)


def sample(args, settings):
    root=PROJECT_ROOT
    config=json.loads(args.config.read_text())
    ident=config['id']
    if not isinstance(ident,str) or not __import__('re').fullmatch(r'[a-z0-9][a-z0-9_-]{0,99}',ident):
        raise ValueError('Invalid sample ID')
    offset,duration=float(config['offset']),frame_time(float(config['duration']))
    if not all(math.isfinite(v) for v in (offset,duration)) or not 0<=offset or not 3<=duration<=40:
        raise ValueError('A sample must be a finite 3–40 second interval')
    folder=root/'outputs/motion-gallery'/ident
    if (folder/'preview.mp4').exists():
        raise ValueError('Sample exists: choose a new revision ID')
    folder.mkdir(parents=True,exist_ok=True)
    narration=project_file(root,config['narration'])
    alignment=json.loads(project_file(root,config['alignment']).read_text()) if config.get('alignment') else None
    script=project_file(root,config['script']).read_text()
    full=build_edit_manifest(script,probe_media(narration,settings.ffprobe_binary).duration,config['keywords'])
    full_sections=provider_sections(full.sections,alignment,full.duration) or full.sections
    # Include only complete sentences inside the excerpt. Partial edge sentences
    # remain audible stock, never become a misleading typographic fragment.
    sections=[SimpleNamespace(section=s.section,keywords=s.keywords,audio_start=s.audio_start-offset,audio_end=s.audio_end-offset)
              for s in full_sections if offset<=s.audio_start and s.audio_end<=offset+duration]
    edit=SimpleNamespace(sections=sections,alignment={'method':'provider-phrase-anchors' if alignment else 'estimated-sentence'})
    local_alignment={'words':[dict(w,start=max(0,w['start']-offset),end=max(0,w['end']-offset))
                     for w in alignment['words'] if sections and w['start']>=sections[0].audio_start+offset-.001 and w['end']<=sections[-1].audio_end+offset+.001]} if alignment else None
    library=AudioLibrary(root/'presets/music_sources.json',root/'cache/audio-library')
    mixed=folder/'mix.m4a'
    try:
        excerpt=' '.join(s.section for s in sections)
        channel=config.get('channel','loose_thread')
        selection=library.select_narrative(ident,excerpt,channel=channel)
        transition=narrative_transition(excerpt,duration,channel=channel,
                    sections=[{'text':s.section,'start':s.audio_start,'end':s.audio_end} for s in sections] if alignment else None)
        events=config.get('sfx_events',automatic_sfx(edit,duration,word_alignment=local_alignment))
        receipt=library.mix(ident,narration,mixed,duration=duration,offset=offset,sfx_events=events,transition_at=transition['transition_at'])
        write_json_atomic(folder/'music-direction.json',transition)
    finally:
        library.close()
    # Reuse the source editor's stock, with offsets clipped to this excerpt.
    original=json.loads(project_file(root,config['timeline_manifest']).read_text())
    ranges=[]
    for item in original['timeline']:
        a=max(offset,item['timeline_start']);b=min(offset+duration,item['timeline_start']+item['duration'])
        if b>a:
            ranges.append((frame_time(a-offset),frame_time(b-offset),item,a-item['timeline_start']))
    # Merge tiny edge fragments into their neighbour; select enough source footage
    # explicitly and let the renderer reject an insufficient original shot.
    if ranges and ranges[0][1] < .4 and len(ranges)>1:
        ranges.pop(0);a,b,it,shift=ranges[0];ranges[0]=(0,b,it,max(0,shift-a))
    if ranges and duration-ranges[-1][0]<.4 and len(ranges)>1:
        ranges.pop();a,b,it,shift=ranges[-1];ranges[-1]=(a,duration,it,shift)
    clips=[TimelineClip(TimelineSlot(i,item['query'],a,b-a),item['asset_id'],project_file(root,item['cache_path']),item['source_start']+shift)
           for i,(a,b,item,shift) in enumerate(ranges)]
    plan=motion_plan(clips,mixed,duration,root=root,episode_id=ident,editing=edit,style=config.get('preset','investigation'),
                     audio_is_final_mix=True,width=args.width,height=args.height,word_alignment=local_alignment)
    for asset in plan.assets.values():
        ident_match=__import__('re').search(r'/(\d+)/?$',asset.source_url or '')
        evidence=root/'cache/pexels-credits'/f'{ident_match[1]}.json' if ident_match else None
        if evidence and evidence.is_file():
            attribution=json.loads(evidence.read_text())
            asset.credit=f"{attribution['author']} · Pexels"
            asset.source_url=attribution['source_url']
    baseline=folder/'baseline.mp4'
    baseline_source=project_file(root,config['baseline'])
    run([settings.ffmpeg_binary,'-nostdin','-v','error','-ss',str(offset),'-i',str(baseline_source),'-i',str(mixed),
         '-map','0:v:0','-map','1:a:0','-t',str(duration),'-vf',f'scale={args.width}:{args.height}',
         '-c:v','libx264','-preset','fast','-crf','20','-threads','2','-c:a','copy','-movflags','+faststart',str(baseline)])
    credits='# Credits\n\nOriginal narration reused, no new Fish request.\nStock is illustrative, not footage of the case. Pexels License: https://www.pexels.com/license/\n'
    for clip in {c.asset_id:c for c in clips}.values():
        evidence=root/'cache/pexels-credits'/f'{clip.asset_id}.json'
        source=json.loads(evidence.read_text()) if evidence.is_file() else {}
        if source.get('id')==clip.asset_id and source.get('author'):
            credits+=f"\n- {source['author']}: {source['source_url']} — {source.get('author_url','')} (cropped/trimmed).\n"
        else:
            credits+=f'\n- Stock: https://www.pexels.com/video/{clip.asset_id}/ (creator unknown in historic cache; cropped/trimmed).\n'
    credits+='\n'+ '\n\n'.join(selection['credits'])+'\n\nMusic trimmed, crossfaded and ducked under the narration. Content ID: unknown.\n'
    credits+='\nBaseline reuses previous editor images with this exact new mix for a visual comparison. The previous original remains unchanged.\n'
    review(plan,folder,settings,title=config['title'],family=config.get('family','documentary'),kind='sample',credits=credits,baseline=baseline)
    print(json.dumps({'sample':ident,'duration':duration,'decisions':plan.alignment['motion_decisions'],'mix':receipt['measured']},ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--width',type=int,default=1920)
    parser.add_argument('--height',type=int,default=1080)
    sub=parser.add_subparsers(dest='command',required=True)
    e=sub.add_parser('effects');e.add_argument('--stock',type=Path,required=True);e.add_argument('--source-url',required=True);e.add_argument('--credit',required=True)
    e.add_argument('--revision',help='New revision ID; preserves all earlier gallery files')
    s=sub.add_parser('sample');s.add_argument('config',type=Path)
    args=parser.parse_args()
    settings=Settings(_env_file=None)
    effects(args,settings) if args.command=='effects' else sample(args,settings)

if __name__=='__main__': main()
