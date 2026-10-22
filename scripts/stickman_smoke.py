#!/usr/bin/env python3
"""Technical Kitok smoke proof, never a channel-style sample or ImageGen claim.

Three diagnostic drawings + synthetic non-speech audio exercise the pipeline.
Optionally reuses one verified cached licensed track in an isolated cache copy.
No Fish, ImageGen, Pexels, posting, external request or original-state mutation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw

from kitok.config import PROJECT_ROOT, Settings
from kitok.youtube_stickman_es.audio import format_srt
from kitok.youtube_stickman_es.files import digest, write
from kitok.youtube_stickman_es.models import Config
from kitok.youtube_stickman_es.pipeline import execute


def diagnostic_image(path: Path, index: int):
    image = Image.new('RGB',(1600,900),'#faf9f3')
    draw = ImageDraw.Draw(image)
    ink, accent = '#1a2532',('#d77b40','#478b9b','#77964d')[index % 3]
    x,y = 600+index*80,300
    draw.ellipse((x-50,y-90,x+50,y+10),outline=ink,width=9)
    draw.line((x,y+10,x,y+225),fill=ink,width=10)
    draw.line((x,y+85,x-110,y+150),fill=ink,width=9)
    draw.line((x,y+85,x+110,y+60-index*40),fill=ink,width=9)
    draw.line((x,y+225,x-95,y+390),fill=ink,width=9)
    draw.line((x,y+225,x+90,y+385),fill=ink,width=9)
    draw.ellipse((x-24,y-48,x-17,y-41),fill=ink)
    draw.ellipse((x+17,y-48,x+24,y-41),fill=ink)
    draw.arc((x-20,y-38,x+20,y-8),0,180,fill=ink,width=5)
    draw.rounded_rectangle((1050,270,1350,570),radius=20,outline=accent,width=15)
    draw.line((1090,420,1155,485,1310,330),fill=accent,width=15)
    path.parent.mkdir(parents=True,exist_ok=True)
    image.save(path)


def run(folder: Path, *, music: bool = False):
    if folder.exists():
        raise ValueError('Preserve an existing proof; choose another folder')
    execute(PROJECT_ROOT,folder,'init')
    lines = ['Esta es la primera señal de diagnóstico.',
             'Esta es la segunda señal de diagnóstico.',
             'Esta es la tercera señal de diagnóstico.']
    (folder/'titulo.txt').write_text('Verificación técnica · sin voz ni estilo final\n')
    (folder/'guion_final.txt').write_text(' '.join(lines)+'\n')
    # MP3 is real but deliberately contains a tone, not fabricated narrated words.
    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i',
                    'sine=frequency=220:sample_rate=48000:duration=15','-af','volume=0.2',
                    '-c:a','libmp3lame','-b:a','192k',str(folder/'voz.mp3')],check=True,timeout=60)
    (folder/'voz.srt').write_text(format_srt([
        {'index':i+1,'start':i*5+.1,'end':(i+1)*5-.15,'text':line} for i,line in enumerate(lines)]))
    diagnostic_image(folder/'referencias/diagnostic.png',0)
    config = Config(references=[{'path':'referencias/diagnostic.png','role':'interior',
                      'notes':'Technical code-native fixture, NOT a channel reference or approved final style.'}])
    data = config.model_dump()
    data['music'] = {'mode':'manual','track_id':'deliberate_thought','channel':'documentary'} if music else {'mode':'off'}
    data['sfx_events'] = [{'time':5.,'kind':'soft_tick'},{'time':10.,'kind':'air_swish'}] if music else []
    (folder/'configuracion.json').write_text(Config.model_validate(data).model_dump_json(indent=2))
    runtime = folder/'runtime'
    if music:
        source = PROJECT_ROOT/'cache/audio-library/deliberate_thought'
        if not source.is_dir():
            raise ValueError('Licensed cached track required; no download is attempted')
        shutil.copytree(source,runtime/'cache/audio-library/deliberate_thought')
    settings = Settings(_env_file=None,data_root=runtime,ready_dir=runtime/'outputs/ready',fish_api_key='')
    draft = execute(PROJECT_ROOT,folder,'prepare',settings=settings)
    assert draft['status']=='visual_direction_required'
    template = json.loads((folder/'direcciones_plantilla.json').read_text())
    for i,row in enumerate(template):
        row.update(visual_description=f'Technical stick figure indicating diagnostic check {i+1}, not a final illustration.',
                   scene_prompt=f'For technical testing only, a clean original stick figure points at check shape {i+1}. '
                                 'Light background, different pose and accent. This is not an approved production scene.')
    (folder/'direccion_visual.json').write_text(json.dumps(template,ensure_ascii=False,indent=2))
    prepared = execute(PROJECT_ROOT,folder,'prepare',settings=settings)
    identifiers = prepared['images']['sample_ids']
    for i,ident in enumerate(identifiers):
        request = execute(PROJECT_ROOT,folder,'request',settings=settings,image_id=ident)
        source = folder/f'diagnostico_{i}.png'
        diagnostic_image(source,i)
        execute(PROJECT_ROOT,folder,'import-image',settings=settings,image_id=ident,source=source,
                attempt_id=request['attempt_id'],reviewed=True,source_kind='technical_fixture')
    execute(PROJECT_ROOT,folder,'approve-style',settings=settings,
            reviewer='technical fixture only; NOT operator approval of channel style')
    for i,key in enumerate(('A','B','C')):
        ident = 'thumb_'+key
        request = execute(PROJECT_ROOT,folder,'request',settings=settings,image_id=ident)
        source = folder/f'diagnostico_miniatura_{key}.png'
        diagnostic_image(source,i+3)
        execute(PROJECT_ROOT,folder,'import-image',settings=settings,image_id=ident,source=source,
                attempt_id=request['attempt_id'],reviewed=True,source_kind='technical_fixture')
    before = {str(p.relative_to(folder)):digest(p) for p in (folder/'imagenes').glob('*.png')}
    report = execute(PROJECT_ROOT,folder,'produce',settings=settings)
    assert report['technical_status']=='passed'
    assert report['packaging']['thumbnails_ready']
    resumed = execute(PROJECT_ROOT,folder,'resume',settings=settings)
    assert resumed['video']==report['video']
    rerender = execute(PROJECT_ROOT,folder,'render',settings=settings,revision='rerender')
    assert len(rerender['render']['reused_scenes'])==len(identifiers)
    assert before=={str(p.relative_to(folder)):digest(p) for p in (folder/'imagenes').glob('*.png')}
    proof = {'purpose':'Technical only, NOT editorial/visual style acceptance. Audio is a synthetic non-speech tone.',
             'imagegen_calls':0,'fish_calls':0,'illustrations':len(identifiers),
             'thumbnails':3,'video':report['video'],'rerender':rerender['video'],
             'cached_scenes_reused':len(rerender['render']['reused_scenes']),
             'images_unchanged':before,'licensed_music_and_sfx':music,
             'qa':report['qa'],'channel_style_approved':False}
    write(folder/'technical-proof.json',proof)
    print(json.dumps(proof,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    parser.add_argument('--music',action='store_true',help='Copy and reuse a locally verified licensed track')
    args=parser.parse_args()
    folder=args.folder if args.folder.is_absolute() else PROJECT_ROOT/args.folder
    run(folder,music=args.music)
