"""Deterministic timings; semantic illustration direction is supplied by Codex.

There is intentionally no translation heuristic or hidden LLM client here.
"""
from __future__ import annotations

import math
from pathlib import Path

from ..editing.camera import CameraMotion
from .files import digest, local_file, write
from .models import Config, Direction, IllustrationPlan, Scene


CAMERAS = ('slow_push_in', 'pan_right', 'slow_pull_out', 'pan_left', 'pan_down', 'pan_up', 'static')


def reference_records(episode: Path, config: Config) -> list[dict]:
    records = []
    for ref in config.references:
        path = local_file(episode, ref.path)
        if path.stat().st_size>40*1024**2:
            raise ValueError('Style reference exceeds the 40MB bound')
        from PIL import Image
        with Image.open(path) as image:
            if image.width*image.height>40_000_000:
                raise ValueError('Style reference exceeds the 40MP bound')
            image.verify()
        records.append({**ref.model_dump(), 'sha256': digest(path)})
    return records


def plan_illustrations(episode: Path, *, title: str, script: str, narration: dict,
                       config: Config, directions: list[dict] | None = None) -> IllustrationPlan:
    cues, measured = narration['cues'], float(narration['duration'])
    # Ceil once to preserve every sample of narration; the visual tail is at most
    # one frame, not an artificial extra second or independently rounded shots.
    duration = math.ceil((measured-1e-9)*30)/30
    if not math.isfinite(duration) or not .8 <= duration <= 7200:
        raise ValueError('Narration duration must be finite and between .8 and 7200 seconds')
    count = max(1, round(duration/config.target_scene_seconds))
    if count > 500:
        raise ValueError('This illustration plan exceeds the shared 500-scene limit')
    if len(cues) < count:
        raise ValueError('SRT is too coarse for approximately one image every five seconds; supply finer real alignment')
    if any(c['end']-c['start'] > config.max_scene_seconds for c in cues):
        raise ValueError('A subtitle cue is too long; supply real phrase/word timestamps, never estimated splits')
    indices = [0]
    for cut in range(1, count):
        lower, upper = indices[-1]+1, len(cues)-(count-cut)
        target = duration*cut/count
        # Prefer a natural phrase ending only among genuinely nearby timestamps.
        choice = min(range(lower, upper+1), key=lambda i: (
            abs(cues[i]['start']-target) + (0 if cues[i-1]['text'].rstrip().endswith(('.', '!', '?', ';', ':')) else .15), i))
        indices.append(choice)
    indices.append(len(cues))
    boundaries = [0.] + [round(cues[i]['start']*30)/30 for i in indices[1:-1]] + [duration]
    refs = reference_records(episode, config)
    scenes = []
    for number, (first, last, start, end) in enumerate(zip(indices, indices[1:], boundaries, boundaries[1:])):
        if end-start > config.max_scene_seconds+1/30:
            raise ValueError('Real subtitle boundaries leave an overly long scene; refine the SRT')
        ident = f's{number:04d}_{round(start*1000):09d}'
        scenes.append(Scene(id=ident, start=start, end=end,
                            narration=' '.join(c['text'] for c in cues[first:last]),
                            image_file=f'imagenes/{ident}.png', style_prompt=config.style_prompt,
                            reference_files=[r['path'] for r in refs if r['role'] != 'thumbnail'],
                            camera=CameraMotion(preset=CAMERAS[number % len(CAMERAS)]),
                            transition='cut' if number == 0 or number % 5 == 0 else 'dissolve'))
    if directions is not None:
        parsed = [Direction.model_validate(item) for item in directions]
        by_id = {d.scene_id: d for d in parsed}
        if len(by_id) != len(parsed) or set(by_id) != {s.id for s in scenes}:
            raise ValueError('Directions must identify every planned scene exactly once; no missing or unknown IDs')
        for scene in scenes:
            direction = by_id[scene.id]
            if set(direction.characters)-config.characters.keys():
                raise ValueError('Direction names an unknown character; define its consistent character sheet first')
            scene.visual_description = direction.visual_description
            scene.scene_prompt = direction.scene_prompt
            scene.characters = direction.characters
            if direction.camera:
                scene.camera = direction.camera
    return IllustrationPlan(title=title, script_sha256=digest(local_file(episode,'guion_final.txt')),
                            audio_sha256=narration['audio_sha256'], srt_sha256=narration['srt_sha256'],
                            config_sha256=digest(config.model_dump()), duration=duration,
                            narration_duration=measured, references=refs, scenes=scenes,
                            direction_complete=directions is not None,
                            timing_method=narration['alignment_method'], srt_cues=cues)


def combined_prompt(scene: Scene, config: Config) -> str:
    if not scene.visual_description or not scene.scene_prompt:
        raise ValueError('Specific visual direction is missing; Codex must complete it before generating images')
    characters = '\n'.join(f'{name}: {config.characters[name]}' for name in scene.characters)
    return (f'STYLE PROMPT\n{scene.style_prompt}\n\nCHARACTER SHEET\n{characters or "No recurring character specified."}'
            f'\n\nSCENE PROMPT\n{scene.scene_prompt}\n\nVISUAL DESCRIPTION\n{scene.visual_description}'
            f'\n\nEXACT APPROVED SPANISH NARRATION (context only, never render as letters)\n{scene.narration}'
            '\n\nDelivery: one finished landscape 16:9 illustration. Keep important action inside '
            'the central 85% so gentle camera movement preserves it. No typography or accidental lettering. '
            'Match approved character/reference identity; do not reuse a previous scene composition.')


def write_plan(episode: Path, plan: IllustrationPlan):
    stem = 'plan_imagenes' if plan.direction_complete else 'plan_imagenes.borrador'
    write(local_file(episode, stem+'.json', exists=False), plan.model_dump())
    lines = [f'# {plan.title}', '', f'{len(plan.scenes)} ilustraciones · {plan.duration:.3f} s · 30 fps',
             f'Tiempos: {plan.timing_method}. Cortes: error máximo medio frame; cola visual menor de un frame.',
             '', 'Dirección semántica: '+('completa; revisar fidelidad visual' if plan.direction_complete else
                 'PENDIENTE. Codex debe aportar descripción concreta y prompt individual en inglés; no generar genéricos.'), '']
    for s in plan.scenes:
        lines += [f'## {s.id} · {s.start:.3f}–{s.end:.3f} s', '', s.narration, '',
                  f'Archivo: {s.image_file}', f'Cámara: {s.camera.preset}; transición: {s.transition}',
                  f'Referencias: {", ".join(s.reference_files)}', f'Personajes: {", ".join(s.characters)}',
                  '', 'STYLE PROMPT', s.style_prompt, '', 'Descripción visual',
                  s.visual_description or 'PENDIENTE', '', 'SCENE PROMPT', s.scene_prompt or 'PENDIENTE', '']
    write(local_file(episode, stem+'.md', exists=False), '\n'.join(lines)+'\n')


def direction_template(plan: IllustrationPlan) -> list[dict]:
    return [{'scene_id':s.id, 'visual_description':'', 'scene_prompt':'', 'characters':[]} for s in plan.scenes]
