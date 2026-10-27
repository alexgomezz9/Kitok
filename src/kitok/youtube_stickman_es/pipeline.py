"""Reproducible episode interface; Kitok remains the only audiovisual renderer."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

from ..config import Settings
from ..editing.manifest import clean_script
from ..editing.production import render_editorial_plan
from ..editing.storyboard import EditorialAsset, EditorialPlan, EditorialScene
from .audio import prepare_narration, prepare_mix
from .files import digest, episode_lock, episode_path, local_file, replace_state, write
from .images import ImageBatch
from .models import Config, IllustrationPlan
from .packaging import prepare_packaging, compose_thumbnail
from .planner import direction_template, plan_illustrations, reference_records, write_plan
from .quality import QA_VERSION, inspect_delivery
from .reuse import source_spans, safe_revision


def inputs(episode: Path):
    config = Config.model_validate_json(local_file(episode,'configuracion.json').read_text(encoding='utf-8-sig'))
    title = local_file(episode,'titulo.txt').read_text(encoding='utf-8-sig').strip()
    script = local_file(episode,'guion_final.txt').read_text(encoding='utf-8-sig')
    if not title or len(title)>150 or '\n' in title or '\r' in title:
        raise ValueError('titulo.txt must contain the approved title on one line, maximum 150 characters')
    if not clean_script(script).strip():
        raise ValueError('Provide the final script; Kitok does not write or rewrite it')
    reference_records(episode,config)
    return config,title,script


def initialize(root: Path, value: Path) -> dict:
    relative = value.relative_to(root) if value.is_absolute() else value
    folder = local_file(root,str(relative),exists=False)
    if folder.resolve() == root.resolve():
        raise ValueError('Choose an episode folder, not the workspace root')
    folder.mkdir(parents=True,exist_ok=True)
    folder = episode_path(root,folder)
    for name in ('referencias','imagenes','miniaturas'):
        local_file(folder,name,exists=False).mkdir(exist_ok=True)
    config = Config()
    config.voice.transcript_verification = 'local_asr_autocut'
    write(local_file(folder,'configuracion.json',exists=False),config.model_dump())
    from .workspace import index_episode
    index_episode(folder)
    return {'episode':str(folder.relative_to(root)),'status':'inputs_required',
            'required':['guion_final.txt','titulo.txt','referencias/ with interior-frame role in configuracion.json'],
            'optional':['voz.mp3','voz.srt','direccion_visual.json'],
            'note':'No script, final illustration or paid voice was generated.'}


def _prepare(episode: Path, root: Path, settings, *, generate_voice=False, reuse_images=False, on_stage=None):
    emit = on_stage or (lambda message: None)
    emit('Entradas: comprobando guion, configuración y referencias')
    config,title,script = inputs(episode)
    _style_guide(episode,config)
    narration = prepare_narration(episode,root=root,settings=settings,
                                  voice=config.voice.model_dump(),generate=generate_voice, on_stage=on_stage)
    direction_path = local_file(episode,'direccion_visual.json',exists=False)
    reuse_images = reuse_images or local_file(episode,'.stickman/provided_images.json',exists=False).exists()
    spans = source_spans(episode,script) if reuse_images else None
    directions = json.loads(direction_path.read_text()) if direction_path.exists() and spans is None else None
    emit('Alineación: calculando cortes sobre los tiempos reales de la voz')
    plan = plan_illustrations(episode,title=title,script=script,narration=narration,config=config,
                              directions=directions,source_spans=spans)
    emit(f'Plan listo: {len(plan.scenes)} planos · {plan.duration:.1f} s de vídeo')
    if narration.get('words') is not None:
        timing_file = '.stickman/word_timing'+('' if plan.direction_complete else '.borrador')+'.json'
        write(local_file(episode,timing_file,exists=False),{
            'version':1,'alignment_sha256':narration['alignment_sha256'],
            'audio_sha256':narration['audio_sha256'],'script_sha256':narration['script_sha256'],
            'plan_sha256':digest(plan.model_dump())})
    write_plan(episode,plan)
    if not plan.direction_complete:
        write(local_file(episode,'direcciones_plantilla.json',exists=False),direction_template(plan))
        return plan,config,narration,{'status':'visual_direction_required','planned_scenes':len(plan.scenes),
                                    'next':'Codex fills direccion_visual.json using each exact narrated span; no generic images.'}
    emit('Preparando descripción, capítulos y conceptos de miniaturas')
    packaging = prepare_packaging(episode,title=title,script=clean_script(script),
                                  scenes=[s.model_dump() for s in plan.scenes],duration=plan.duration,
                                  references=plan.references,chapters=config.chapters,sources=config.sources,
                                  description=config.description,thumbnail_text=config.thumbnail_text)
    batch = ImageBatch(episode,plan,config)
    if reuse_images:
        emit('Imágenes: verificando y asociando los recursos existentes; sin generar imágenes')
        batch.adopt_provided()
    image_status = batch.status()
    if image_status['resolution_warnings']:
        emit(f'Aviso: {len(image_status["resolution_warnings"])} fuentes pequeñas; se escalan al montar, sin recuperar detalle')
    emit(f'Imágenes comprobadas: {image_status["completed"]} completadas')
    ready = image_status['render_images_ready'] and (image_status['style_approved'] or image_status['assembly_authorized'])
    return plan,config,narration,{'status':'ready_to_render' if ready else 'images_required',
                                'images':image_status,'packaging':packaging}


def current(episode: Path):
    config,title,script = inputs(episode)
    from .voice_cleaning import cleaned_paths
    voice_path, srt_path, alignment_path = cleaned_paths(episode, config.voice.transcript_verification)
    plan = IllustrationPlan.model_validate_json(local_file(episode,'plan_imagenes.json').read_text())
    if (plan.title != title or plan.script_sha256 != digest(local_file(episode,'guion_final.txt'))
            or plan.audio_sha256 != digest(voice_path)
            or plan.srt_sha256 != digest(srt_path)):
        raise ValueError('Planned script, approved title, voice or SRT changed; use another episode revision')
    if plan.timing_method in {'fish_provider_word_timestamps_full_transcript',
                              'fish_provider_word_timestamps_after_audio_cuts',
                              'local_asr_word_timestamps_after_audio_cuts'}:
        record = json.loads(local_file(episode,'.stickman/word_timing.json').read_text())
        if (record.get('alignment_sha256') != digest(alignment_path)
                or record.get('plan_sha256') != digest(plan.model_dump())
                or record.get('audio_sha256') != plan.audio_sha256
                or record.get('script_sha256') != plan.script_sha256):
            raise ValueError('Word timing evidence changed; use another episode revision')
    return plan,config,ImageBatch(episode,plan,config)


def _render(episode: Path, root: Path, settings, *, revision: str | None = None, on_stage=None):
    emit = on_stage or (lambda message: None)
    emit('Montaje: validando plan e imágenes antes de renderizar')
    if revision is not None and not re.fullmatch('[a-z0-9][a-z0-9_-]{0,39}',revision):
        raise ValueError('Render revision must be a short lowercase ID')
    plan,config,batch = current(episode)
    if not batch.approval() and not batch.provided_authorization():
        raise ValueError('Approve the style sample before rendering the episode')
    status = batch.status()
    if not status['render_images_ready']:
        raise ValueError('Every planned illustration must exist, decode and have visual review before rendering')
    narration = prepare_narration(episode,root=root,settings=settings,voice=config.voice.model_dump(),on_stage=on_stage)
    if (narration['audio_sha256'] != plan.audio_sha256 or narration['srt_sha256'] != plan.srt_sha256
            or abs(narration['duration']-plan.narration_duration) > .001):
        raise ValueError('Prepared narration differs from the planned voice clock; replan in a new revision before mixing')
    emit('Audio: preparando mezcla local de voz, música y efectos configurados')
    mix = prepare_mix(episode,narration,root=root,settings=settings,
                      music=config.music.model_dump(),sfx_events=config.sfx_events)
    source_audio = Path(mix['audio_path'])
    assets = {s.id:EditorialAsset(path=str(local_file(episode,s.image_file).relative_to(root)),
                                 description=s.visual_description,credit='Original generated illustration; reference rights require review.',
                                 sha256=digest(local_file(episode,s.image_file))) for s in plan.scenes}
    timeline = EditorialPlan(episode_id='stickman_'+batch.key[:24],channel_id='youtube_stickman_es',title=plan.title,
                              audio_source=str(source_audio.relative_to(root)),audio_is_final_mix=mix['audio_is_final_mix'],
                              duration=plan.duration,fade_in=config.fade_in,fade_out=config.fade_out,
                              transition_duration=config.transition_duration,assets=assets,
                              scenes=[EditorialScene(id=s.id,start=s.start,end=s.end,asset=s.id,
                                         intention=s.visual_description,spoken_claim=s.narration,
                                         camera=s.camera,transition=s.transition,image_fit='cover') for s in plan.scenes],
                              alignment={'method':plan.timing_method,'audio_sha256':mix['audio_sha256'],
                                         'srt_sha256':plan.srt_sha256,'plan_sha256':batch.plan_key,'batch_sha256':batch.key})
    suffix = '__'+revision if revision else ''
    output = local_file(episode,'video_final'+suffix+'.mp4',exists=False)
    qa_path = local_file(episode,'qa'+suffix+'.json',exists=False)
    request = {'plan_sha256':batch.plan_key,'batch_sha256':batch.key,'mix_sha256':mix['audio_sha256'],
               'editorial_plan_sha256':digest(timeline.model_dump()),'output':str(output.relative_to(root))}
    request_path = local_file(episode,'.stickman/render'+suffix+'.json',exists=False)
    write(request_path,request)
    if output.exists():
        receipt = local_file(episode,output.stem+'.editorial.json')
        old = json.loads(receipt.read_text())
        if (old.get('output_sha256') != digest(output)
                or old.get('alignment',{}).get('plan_sha256') != batch.plan_key
                or old.get('alignment',{}).get('batch_sha256') != batch.key
                or old.get('audio_source_sha256') != mix['audio_sha256']
                or old.get('assets') != {key:asset.model_dump() for key,asset in assets.items()}):
            raise ValueError('Existing render receipt differs; preserve it and choose --revision')
        emit('Vídeo existente: recibo e identidad comprobados; se reutiliza')
        result = old
    else:
        timeline.write(local_file(episode,'montaje'+suffix+'.json',exists=False))
        result = render_editorial_plan(timeline,root=root,output=output,settings=settings, on_stage=on_stage)
    emit('Calidad: comprobando MP4, fotogramas, sonoridad y continuidad de audio')
    if qa_path.exists():
        qa = json.loads(qa_path.read_text())
        if qa.get('video_sha256') != digest(output):
            raise ValueError('QA no longer matches the MP4')
    if not qa_path.exists() or qa.get('qa_version') != QA_VERSION:
        qa = inspect_delivery(output,qa_path,plan=plan,settings=settings,
                              narration=Path(narration['audio_path']),
                              fade_in=config.fade_in,fade_out=config.fade_out)
    credits = '# Créditos\n\nGuion y título aportados por el operador.\n\n'+'\n\n'.join(mix.get('credits',[]))
    credits += '\n\nIlustraciones generadas: revisar referencias, derechos y consistencia antes de publicar.\n'
    write(local_file(episode,'CREDITS.md',exists=False),credits)
    emit('Entrega: preparando créditos, informe y miniaturas disponibles')
    packaging = _finish_packaging(episode,plan,config)
    report = {'pipeline':'youtube_stickman_es','technical_status':qa['technical_status'],
              'production_status':'human_review_required' if packaging['thumbnails_ready'] else 'thumbnail_images_required',
              'video':str(output.relative_to(root)),'render':result,'qa':str(qa_path.relative_to(root)),
              'image_batch':batch.status(),'packaging':packaging,'new_voice_requested':False,
              'human_review_required':qa['human_review_required'],'publishing_automated':False}
    replace_state(local_file(episode,'informe_produccion'+suffix+'.json',exists=False),report)
    if qa['technical_status'] != 'passed':
        raise ValueError('Technical QA rejected the preserved MP4; inspect qa.json before another revision')
    return report


def _finish_packaging(episode: Path, plan, config):
    concepts = json.loads(local_file(episode,'miniaturas/conceptos.json').read_text())['concepts']
    thumb_state={row['id']:row for row in ImageBatch(episode,plan,config).status()['jobs'] if row['kind']=='thumbnail'}
    for concept in concepts:
        background = local_file(episode,concept['background_file'],exists=False)
        target = local_file(episode,concept['output_file'],exists=False)
        row=thumb_state['thumb_'+concept['id']]
        if row['valid'] and row['reviewed']:
            _compose_versioned(episode,concept,background,target)
    result=prepare_packaging(episode,title=plan.title,script=clean_script(local_file(episode,'guion_final.txt').read_text()),
                              scenes=[s.model_dump() for s in plan.scenes],duration=plan.duration,
                              references=plan.references,chapters=config.chapters,sources=config.sources,
                              description=config.description,thumbnail_text=config.thumbnail_text)
    result['thumbnails_ready']=result['thumbnails_ready'] and all(row['valid'] and row['reviewed'] for row in thumb_state.values())
    if not result['thumbnails_ready']:
        result['status']='thumbnail_images_required'
    return result


def _compose_versioned(episode, concept, background, target):
    receipt=local_file(episode,'.stickman/thumbnail_'+concept['id']+'.json',exists=False)
    identity=digest({'background':digest(background),'text':concept['text']})
    previous=json.loads(receipt.read_text()) if receipt.exists() else None
    if previous and previous['status']=='planned' and previous['identity']!=identity:
        raise ValueError('Interrupted thumbnail composition has different inputs; preserve and review it')
    if previous and previous['status']=='complete' and target.exists():
        if digest(target)!=previous['output_sha256']:
            raise ValueError('Previously composed thumbnail changed outside Kitok; it was preserved')
        if previous['identity']!=identity:
            archive=local_file(episode,f'.stickman/thumbnail-history/{target.stem}-{previous["output_sha256"]}.png',exists=False)
            archive.parent.mkdir(parents=True,exist_ok=True)
            if not archive.exists():os.link(target,archive)
            if digest(archive)!=previous['output_sha256'] or digest(target)!=previous['output_sha256']:
                raise ValueError('Thumbnail changed during archival; preserved for review')
            target.unlink()
    replace_state(receipt,{'version':1,'status':'planned','identity':identity})
    # Re-entering after a crash accepts only byte-identical completed output.
    compose_thumbnail(background,target,text=concept['text'])
    replace_state(receipt,{'version':1,'status':'complete','identity':identity,'output_sha256':digest(target)})


def _style_guide(episode, config):
    refs = reference_records(episode,config)
    lines = ['# Guía de estilo declarada', '', config.style_prompt, '',
             'Esta guía registra la dirección aportada. Kitok no deduce un estilo al abrir archivos.',
             'Codex debe inspeccionar fotogramas interiores y completar la ficha antes de producir.',
             'Las miniaturas se usan sólo para las miniaturas; el estilo necesita aprobación de muestra.', '',
             '## Referencias', '']
    for ref in refs:
        lines.append(f'- {ref["role"]}: {ref["path"]} · {ref["notes"]} · SHA256 {ref["sha256"]}')
    write(local_file(episode,'guia_estilo.md',exists=False),'\n'.join(lines)+'\n')
    write(local_file(episode,'personajes.json',exists=False),config.characters)


def execute(root: Path, episode: Path, command: str, *, settings=None, on_stage=None, **options) -> dict:
    """One lock spans preparation/mixing/render; no background provider scheduler."""
    root = root.resolve()
    settings = settings or Settings()
    if command == 'init':
        return initialize(root,episode)
    folder = episode_path(root,episode)
    if options.get('revision') and command == 'status':
        name = options['revision']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',name):
            raise ValueError('Revision must be a simple identifier of at most 64 characters')
        return execute(root,episode_path(root,folder/'revisiones'/name),command,settings=settings,on_stage=on_stage)
    if options.get('revision') and command in {'prepare','produce','resume'}:
        with episode_lock(folder):
            revised = safe_revision(root,folder,options['revision'])
        # The revision has its own production lock; provider opt-in never carries
        # into recovery of already supplied audio.
        return execute(root,revised,command,settings=settings,on_stage=on_stage,
                       **{**options,'revision':None,'generate_voice':False})
    if command == 'status':
        missing=[name for name in ('configuracion.json','guion_final.txt','titulo.txt')
                 if not local_file(folder,name,exists=False).is_file()]
        if missing:
            return {'pipeline':'youtube_stickman_es','status':'inputs_required','missing':missing}
        if not local_file(folder,'plan_imagenes.json',exists=False).is_file():
            draft=local_file(folder,'plan_imagenes.borrador.json',exists=False)
            return {'pipeline':'youtube_stickman_es','status':'visual_direction_required' if draft.exists() else 'preparation_required'}
        plan,config,batch = current(folder)
        return {'pipeline':'youtube_stickman_es','images':batch.status(),
                'video_exists':local_file(folder,'video_final.mp4',exists=False).is_file(),
                'human_review_required':True}
    with episode_lock(folder):
        def finish(report):
            if options.get('subtitles'):
                from .subtitle_delivery import caption_video
                report['subtitled'] = caption_video(folder, root=root, settings=settings,
                    on_stage=on_stage, revision=options.get('revision'))
            from .workspace import index_episode
            index_episode(folder)
            return report
        if command == 'subtitles':
            from .subtitle_delivery import caption_video
            return caption_video(folder, root=root, settings=settings, on_stage=on_stage,
                                 revision=options.get('revision'))
        if command in {'prepare','produce','resume'}:
            plan,config,narration,result = _prepare(folder,root,settings,generate_voice=options.get('generate_voice',False),
                                                   reuse_images=options.get('reuse_images',False), on_stage=on_stage)
            if command == 'prepare' or not plan.direction_complete:
                return result
            if not (result['images']['style_approved'] or result['images']['assembly_authorized']) or not result['images']['render_images_ready']:
                return result
            return finish(_render(folder,root,settings,revision=options.get('revision'), on_stage=on_stage))
        if command == 'render':
            return finish(_render(folder,root,settings,revision=options.get('revision'), on_stage=on_stage))
        plan,config,batch = current(folder)
        if command == 'request-next':
            status=batch.status()
            eligible=[row for row in status['jobs'] if row['eligible']]
            if not eligible:
                return {'status':'style_approval_or_attempt_review_required' if not status['style_approved'] else
                        'no_pending_requests','images':status}
            return batch.claim(eligible[0]['id'])
        if command == 'request':
            return batch.claim(options['image_id'])
        if command == 'import-image':
            return batch.import_image(options['image_id'],Path(options['source']),
                         attempt_id=options['attempt_id'],reviewed=options.get('reviewed',False),
                         reported_cost=options.get('reported_cost'),source_kind=options.get('source_kind','provided'))
        if command == 'approve-style':
            return batch.approve_style(reviewer=options['reviewer'])
        if command == 'review-image':
            return batch.review(options['image_id'],reviewer=options['reviewer'])
        if command == 'retry':
            batch.retry(options['image_id'],reason=options['reason'])
        elif command == 'reject':
            batch.reject(options['image_id'],reason=options['reason'])
        elif command == 'unknown':
            batch.mark_unknown(options['image_id'],attempt_id=options['attempt_id'],reason=options['reason'])
        elif command == 'package':
            return _finish_packaging(folder,plan,config)
        else:
            raise ValueError('Unknown pipeline command')
        return batch.status()
