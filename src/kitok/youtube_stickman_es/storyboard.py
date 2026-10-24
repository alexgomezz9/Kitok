"""Compile editorial decisions into the existing image-reuse contract, offline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Literal

from pydantic import Field, model_validator

from ..editing.camera import CameraMotion
from ..editing.manifest import clean_script
from ..media.ffprobe import probe_media, stream_durations
from .audio import _provider_segments, _tokens
from .files import digest, episode_lock, local_file, write
from .models import Config, Direction, Model
from .planner import plan_illustrations, reference_records
from .reuse import source_spans


PLAN = 'planificacion_visual/plan_visual_prevoz.json'
VISUAL_TYPES = Literal['action', 'reaction', 'object', 'map', 'date', 'quantity',
                       'question', 'comparison', 'timeline', 'diagram', 'place',
                       'silhouette', 'document']
GUARD = ('Landscape 16:9, one clear visual idea, important content inside the central 85%. '
         'Use only the specified subjects. No accidental lettering, logos or watermarks. '
         'Explicit intentional text in SCENE overrides generic no-text style rules. '
         'Illustrations and recreated documents are illustrative, never archival evidence.')


class Beat(Model):
    narration: str | None = Field(default=None, min_length=1)
    through: str | None = Field(default=None, min_length=1)
    visual_description: str = Field(min_length=20, max_length=600)
    scene_prompt: str = Field(min_length=30, max_length=4500)
    characters: list[str] = Field(default_factory=list)
    camera: CameraMotion | None = None
    visual_type: VISUAL_TYPES = 'action'
    display_text: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode='after')
    def source_choice(self):
        if (self.narration is None) == (self.through is None):
            raise ValueError('Supply exact narration OR a unique ending quote in through')
        return self


def prompt_prefix(config: Config, characters: list[str]) -> str:
    sheet = '\n'.join(f'{ident}: {config.characters[ident]}' for ident in characters)
    return f'STYLE\n{config.style_prompt}\n{GUARD}\nCHARACTERS\n{sheet or "None; do not add a protagonist."}\nSCENE\n'


def _inputs(episode: Path):
    script = local_file(episode, 'guion_final.txt')
    config = Config.model_validate_json(local_file(episode, 'configuracion.json').read_text(encoding='utf-8-sig'))
    text = clean_script(script.read_text(encoding='utf-8-sig'))
    if not _tokens(text):
        raise ValueError('The final narration script is empty')
    return script, text, config


def build(episode: Path, decisions: list[dict], *, output: str = PLAN) -> dict:
    """The model supplies meaning; offsets, identity expansion and paths are exact."""
    if output not in (PLAN, 'plan_visual.json'):
        raise ValueError('Output must use plan_visual.json or '+PLAN+' so production can discover it')
    script, text, config = _inputs(episode)
    reference_records(episode, config)
    if not isinstance(decisions, list) or not 1 <= len(decisions) <= 500:
        raise ValueError('Supply between 1 and 500 editorial beats')
    beats = [Beat.model_validate(item) for item in decisions]
    matches = list(re.finditer(r'\w+', text))
    cursor = word_cursor = 0
    scenes = []
    for number, beat in enumerate(beats, 1):
        start = cursor
        while start < len(text) and text[start].isspace():
            start += 1
        if beat.narration is not None:
            narration = beat.narration.strip()
            if not text.startswith(narration, start):
                raise ValueError(f'Beat {number}: narration must be the exact next source fragment')
            end = start+len(narration)
        else:
            quote = beat.through.strip()
            occurrences = [m.start() for m in re.finditer(re.escape(quote), text[start:])]
            if len(occurrences) != 1:
                raise ValueError(f'Beat {number}: through must occur exactly once in the remaining script; use a longer quote')
            end = start+occurrences[0]+len(quote)
            narration = text[start:end]
        indices = [i for i, m in enumerate(matches) if m.start() < end and m.end() > start]
        if (not indices or indices[0] != word_cursor or matches[indices[0]].start() < start
                or matches[indices[-1]].end() > end
                or (end < len(text) and not text[end].isspace() and text[end].isalnum())):
            raise ValueError(f'Beat {number}: source boundary must not split a word')
        last = indices[-1]+1
        # Keep punctuation attached to its own spoken fragment, including negation/questions.
        if end < len(text) and not text[end].isspace():
            raise ValueError(f'Beat {number}: include trailing punctuation in the exact quote')
        if set(beat.characters)-config.characters.keys():
            raise ValueError(f'Beat {number}: unknown character; define it in configuracion.json first')
        if len(set(beat.characters)) != len(beat.characters):
            raise ValueError(f'Beat {number}: duplicate character')
        detail = beat.scene_prompt.strip()
        if beat.display_text:
            detail += f'\nIntentional visible text ONLY: {json.dumps(beat.display_text, ensure_ascii=False)}. No other text.'
        prompt = prompt_prefix(config, beat.characters)+detail
        direction = Direction(scene_id=f'escena_{number:03d}', visual_description=beat.visual_description,
                              scene_prompt=prompt, characters=beat.characters, camera=beat.camera)
        scene = {'id': direction.scene_id, 'source_char_start': start, 'source_char_end': end,
                 'source_word_start': word_cursor, 'source_word_end': last, 'narration': narration,
                 'visual_description': direction.visual_description, 'scene_prompt': prompt,
                 'characters': beat.characters, 'image_file': f'imagenes/{direction.scene_id}.png',
                 'visual_type': beat.visual_type}
        if beat.camera:
            scene['camera'] = beat.camera.model_dump(exclude_none=True)
        if beat.display_text:
            scene['display_text'] = beat.display_text
        scenes.append(scene)
        cursor, word_cursor = end, last
    if text[cursor:].strip() or word_cursor != len(matches):
        raise ValueError('Storyboard must cover the complete script once; missing final narration')
    source_name = 'guion_final.txt' if script.read_text(encoding='utf-8') == text else 'guion_lectura_limpia.txt'
    source = local_file(episode, source_name, exists=False)
    plan = {'version': 1, 'status': 'prevoz_visual_direction', 'script_source': source_name,
            'script_sha256': digest(source) if source_name == 'guion_final.txt' else None,
            'config_sha256': digest(config.model_dump()), 'scene_count': len(scenes),
            'spoken_token_count': len(matches), 'timing': 'pending_real_alignment', 'scenes': scenes}
    target = local_file(episode, output, exists=False)
    # Never create a shadow plan that the existing reuse lookup would ignore.
    other = local_file(episode, 'plan_visual.json', exists=False)
    if other.exists() and target != other:
        raise ValueError('plan_visual.json already takes precedence; use an isolated episode copy')
    with episode_lock(episode):
        if source_name != 'guion_final.txt':
            write(source, text)
            plan['script_sha256'] = digest(source)
        write(target, plan)
    return {'plan': output, 'scenes': len(scenes), 'timing': 'pending_real_alignment',
            'next_skill': 'kitok-image-batches'}


def check(episode: Path, *, plan_path: str = PLAN, timing: bool = False,
          ffprobe: str = 'ffprobe') -> dict:
    script, _, config = _inputs(episode)
    spans = source_spans(episode, script.read_text(encoding='utf-8-sig'),
                         require_images=False, plan_path=plan_path)
    raw = json.loads(local_file(episode, plan_path).read_text(encoding='utf-8'))
    if raw.get('config_sha256') and raw['config_sha256'] != digest(config.model_dump()):
        raise ValueError('Storyboard style/characters/config changed; rebuild in another revision')
    for span in spans:
        direction = Direction.model_validate({k: v for k, v in span.items()
            if k in ('visual_description', 'scene_prompt', 'characters', 'camera')} | {'scene_id': span['source_id']})
        if set(direction.characters)-config.characters.keys():
            raise ValueError('Storyboard names an unknown character')
    result = {'scenes': len(spans), 'coverage': 'complete', 'timing': 'pending_real_alignment',
              'visual_types': sorted({s.get('visual_type', 'unspecified') for s in raw['scenes']})}
    if not timing:
        return result
    audio = local_file(episode, 'voz.mp3', exists=False)
    alignment = local_file(episode, 'voz.alignment.json', exists=False)
    if not audio.exists() or not alignment.exists():
        return result | {'reason': 'Requires existing voice and real Fish word alignment; SRT alone cannot refine these spans'}
    info = probe_media(audio, ffprobe)
    _, audio_duration = stream_durations(audio, ffprobe)
    duration = audio_duration if audio_duration is not None else info.duration
    words = _provider_segments(alignment, script.read_text(encoding='utf-8-sig'), duration)
    if not all(len(_tokens(w['word'])) == 1 for w in words):
        return result | {'reason': 'Provider segments are not word alignment; no intra-segment times invented'}
    narration = {'duration': duration, 'words': words, 'audio_sha256': digest(audio),
                 'srt_sha256': '', 'alignment_method': json.loads(alignment.read_text())['method']}
    plan = plan_illustrations(episode, title='Storyboard timing audit',
        script=script.read_text(encoding='utf-8-sig'), narration=narration, config=config, source_spans=spans)
    rows = [{'source_id': source['source_id'], 'render_id': scene.id, 'start': scene.start, 'end': scene.end,
             'image_file': scene.image_file} for scene in plan.scenes
            for source in spans if scene.image_file == source['image_file']]
    bands = []
    warnings = []
    for start, end, low, high in ((0, 30, 1.5, 2.5), (30, 60, 2.5, 4), (60, plan.duration, 4, 6)):
        shots = [s for s in plan.scenes if start <= s.start < end]
        if shots:
            average = sum(s.end-s.start for s in shots)/len(shots)
            bands.append({'from': start, 'to': end, 'shots': len(shots), 'mean_seconds': round(average, 3)})
            if not low <= average <= high:
                warnings.append(f'{start}–{end:g}s: mean {average:.2f}s outside editorial guide {low}–{high}s; review meaning/readability')
    if len(plan.scenes) != len(spans):
        warnings.append('Long source scenes split by the existing planner, reusing their image; inspect mapping')
    return result | {'timing': plan.timing_method, 'audio_sha256': digest(audio),
                     'alignment_sha256': digest(alignment), 'duration': plan.duration,
                     'acoustic_sync_verified': False, 'bands': bands, 'warnings': warnings, 'mapping': rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['context', 'build', 'check'])
    parser.add_argument('episode', type=Path)
    parser.add_argument('--decisions', type=Path, help='Compact editorial JSON list; never image generation')
    parser.add_argument('--plan', default=PLAN, help='Episode-relative plan path')
    parser.add_argument('--timing', action='store_true', help='Read-only audit of existing Fish/audio clock')
    args = parser.parse_args(argv)
    try:
        episode = args.episode.absolute()
        if episode.is_symlink() or not episode.is_dir():
            raise ValueError('Choose an existing episode directory without symlinks')
        if args.command == 'context':
            _, text, config = _inputs(episode)
            result = {'script': text, 'style_prompt': config.style_prompt, 'characters': config.characters,
                      'references': reference_records(episode, config),
                      'word_alignment_exists': local_file(episode, 'voz.alignment.json', exists=False).exists()}
        elif args.command == 'build':
            if args.decisions is None:
                parser.error('build requires --decisions')
            result = build(episode, json.loads(args.decisions.read_text(encoding='utf-8-sig')), output=args.plan)
        else:
            result = check(episode, plan_path=args.plan, timing=args.timing)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        print(json.dumps({'status': 'blocked', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
