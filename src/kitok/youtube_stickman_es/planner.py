"""Deterministic timings; semantic illustration direction is supplied by Codex.

There is intentionally no translation heuristic or hidden LLM client here.
"""
from __future__ import annotations

import math
import re
from array import array
from bisect import bisect_left, bisect_right
from collections import deque
from pathlib import Path

from ..editing.camera import CameraMotion
from ..editing.manifest import clean_script
from .audio import _tokens
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


def _word_inputs(script: str, words: list[dict], measured: float):
    text = clean_script(script)
    matches = list(re.finditer(r'\w+', text))
    if not isinstance(words, list) or not words or len(words) != len(matches):
        raise ValueError('Provider words must cover the full script transcript exactly')
    previous_end = 0.
    for match, word in zip(matches, words):
        try:
            start, end = float(word['start']), float(word['end'])
            valid = (not isinstance(word['start'], bool) and not isinstance(word['end'], bool)
                     and _tokens(word['word']) == [match.group().casefold()]
                     and math.isfinite(start) and math.isfinite(end)
                     and previous_end <= start <= end <= measured + .001)
        except (KeyError, TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            raise ValueError('Provider words must match the full script with finite monotonic timestamps')
        previous_end = end
    offsets = [0] + [m.start() for m in matches[1:]] + [len(text)]
    frames = [0] + [round(float(w['start'])*30) for w in words[1:]]
    return text, offsets, frames


def _allocate_boundaries(frames: list[int], natural: list[bool], *, target: float,
                         maximum: float) -> list[int]:
    """Globally feasible scene count, followed by uniform/natural real cuts.

    Reachability stores all possible counts as bits. Dynamic programming then
    chooses a path for the count closest to the target, avoiding greedy dead ends.
    The segment tree and sliding minimum keep dense transcripts bounded.
    """
    size = len(frames)
    max_frames = math.floor(maximum*30 + 1e-9)
    for start, end in zip(frames, frames[1:]):
        if end-start > max_frames:
            raise ValueError(
                'Real word boundaries cannot satisfy scene duration limits: '
                f'no word start between {start/30:.3f}s and {end/30:.3f}s '
                f'({(end-start)/30:.3f}s; maximum {maximum:g}s). '
                'Review voz.alignment.json against voz.mp3; a timestamp gap does not prove silence. '
                'Paid voice was preserved: do not delete it or regenerate to retry.')
    tree_size = 1 << (size-1).bit_length()
    tree = [0]*(2*tree_size)
    mask = (1 << 501)-1

    def put(index, value):
        index += tree_size
        tree[index] = value
        while index > 1:
            index //= 2
            tree[index] = tree[index*2] | tree[index*2+1]

    def query(left, right):
        result = 0
        left, right = left+tree_size, right+tree_size
        while left < right:
            if left & 1:
                result |= tree[left]
                left += 1
            if right & 1:
                right -= 1
                result |= tree[right]
            left //= 2
            right //= 2
        return result

    put(0, 1)
    feasible = 0
    for index in range(1, size):
        low = bisect_left(frames, frames[index]-max_frames, 0, index)
        high = bisect_right(frames, frames[index]-12, 0, index)
        feasible = (query(low, high) << 1) & mask
        put(index, feasible)
    counts = [k for k in range(1, 501) if feasible & (1 << k)]
    if not counts:
        raise ValueError('Real word boundaries cannot satisfy scene duration limits (0.4 seconds to maximum)')
    desired = max(1, round((frames[-1]-frames[0])/30/target))
    count = min(counts, key=lambda k: (abs(k-desired), k))
    previous = [math.inf]*size
    previous[0] = 0.
    parents = []
    for step in range(1, count+1):
        current = [math.inf]*size
        parent = array('i', [-1])*size
        candidates = deque()
        cursor = 0
        ideal = frames[0] + (frames[-1]-frames[0])*step/count
        for index in range(1, size):
            while cursor < index and frames[cursor] <= frames[index]-12:
                if math.isfinite(previous[cursor]):
                    while candidates and previous[candidates[-1]] > previous[cursor]:
                        candidates.pop()
                    candidates.append(cursor)
                cursor += 1
            while candidates and frames[candidates[0]] < frames[index]-max_frames:
                candidates.popleft()
            if candidates:
                predecessor = candidates[0]
                penalty = ((frames[index]-ideal)/30)**2
                if index < size-1 and not natural[index]:
                    penalty += .15
                current[index] = previous[predecessor] + penalty
                parent[index] = predecessor
        parents.append(parent)
        previous = current
    cuts = [size-1]
    for parent in reversed(parents):
        cuts.append(parent[cuts[-1]])
    return list(reversed(cuts))


def _word_scenes(script: str, narration: dict, config: Config, source_spans):
    text, offsets, frames = _word_inputs(script, narration['words'], float(narration['duration']))
    frames.append(math.ceil(float(narration['duration'])*30))
    natural = [True] + [text[offsets[i-1]:offsets[i]].rstrip().endswith(('.', '!', '?', ';', ':'))
                        for i in range(1, len(frames)-1)] + [True]
    if source_spans is None:
        cuts = _allocate_boundaries(frames, natural, target=config.target_scene_seconds,
                                    maximum=config.max_scene_seconds)
        return [(frames[a]/30, frames[b]/30, text[offsets[a]:offsets[b]].strip(), None)
                for a, b in zip(cuts, cuts[1:])]
    if not isinstance(source_spans, list) or not source_spans:
        raise ValueError('Source spans must cover the full script contiguously and exactly')
    cursor = 0
    result = []
    for span in source_spans:
        if not isinstance(span, dict):
            raise ValueError('Source spans must cover the full script contiguously and exactly')
        first, last = span.get('word_start'), span.get('word_end')
        if (type(first) is not int or type(last) is not int or first != cursor
                or not first < last <= len(frames)-1):
            raise ValueError('Source spans must cover the full script contiguously and exactly')
        seconds = (frames[last]-frames[first])/30
        if seconds < .4-1e-9:
            raise ValueError('Source span is shorter than 0.4 seconds; review its approved word boundaries')
        if seconds <= config.max_scene_seconds:
            cuts = [0, last-first]
        else:
            try:
                cuts = _allocate_boundaries(frames[first:last+1], natural[first:last+1],
                                            target=config.target_scene_seconds, maximum=config.max_scene_seconds)
            except ValueError as error:
                raise ValueError(f'Source scene {span.get("source_id", first)} '
                                 f'({span.get("image_file", "unknown image")}): {error}') from error
        for a, b in zip(cuts, cuts[1:]):
            a, b = a+first, b+first
            result.append((frames[a]/30, frames[b]/30, text[offsets[a]:offsets[b]].strip(), span))
        cursor = last
    if cursor != len(frames)-1:
        raise ValueError('Source spans must cover the full script contiguously and exactly')
    if len(result) > 500:
        raise ValueError('This illustration plan exceeds the shared 500-scene limit')
    return result


def plan_illustrations(episode: Path, *, title: str, script: str, narration: dict,
                       config: Config, directions: list[dict] | None = None,
                       source_spans: list[dict] | None = None) -> IllustrationPlan:
    cues, measured = narration.get('cues', []), float(narration['duration'])
    if not math.isfinite(measured) or not .8 <= measured <= 7200:
        raise ValueError('Narration duration must be finite and between .8 and 7200 seconds')
    # Ceil once to preserve every sample of narration; the visual tail is at most
    # one frame, not an artificial extra second or independently rounded shots.
    duration = math.ceil(measured*30)/30
    if not math.isfinite(duration) or not .8 <= duration <= 7200:
        raise ValueError('Narration duration must be finite and between .8 and 7200 seconds')
    if source_spans is not None and directions is not None:
        raise ValueError('Use approved source spans or scene directions, not both')
    word_based = narration.get('words') is not None
    if source_spans is not None and not word_based:
        raise ValueError('Approved source spans require real provider word timestamps')
    if word_based:
        allocations = _word_scenes(script, narration, config, source_spans)
    else:
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
        allocations = [(start, end, ' '.join(c['text'] for c in cues[first:last]), None)
                       for first, last, start, end in zip(indices, indices[1:], boundaries, boundaries[1:])]
    refs = reference_records(episode, config)
    scenes = []
    for number, (start, end, narration_text, source) in enumerate(allocations):
        if end-start > config.max_scene_seconds+1e-9:
            raise ValueError('Real subtitle boundaries leave an overly long scene; refine the SRT')
        ident = f's{number:04d}_{round(start*1000):09d}'
        scenes.append(Scene(id=ident, start=start, end=end,
                            narration=narration_text,
                            image_file=f'imagenes/{ident}.png', style_prompt=config.style_prompt,
                            reference_files=[r['path'] for r in refs if r['role'] != 'thumbnail'],
                            camera=CameraMotion(preset=CAMERAS[number % len(CAMERAS)]),
                            transition='cut' if number == 0 or number % 5 == 0 else 'dissolve'))
        if source is not None:
            local_file(episode, source['image_file'], exists=False)
            direction = Direction.model_validate({k: source[k] for k in ('visual_description', 'scene_prompt', 'characters', 'camera') if k in source}
                                                 | {'scene_id': ident})
            if set(direction.characters)-config.characters.keys():
                raise ValueError('Direction names an unknown character; define its consistent character sheet first')
            scenes[-1].image_file = source['image_file']
            scenes[-1].visual_description = direction.visual_description
            scenes[-1].scene_prompt = direction.scene_prompt
            scenes[-1].characters = direction.characters
            if direction.camera:
                scenes[-1].camera = direction.camera
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
                            direction_complete=directions is not None or source_spans is not None,
                            timing_method=(('local_asr_word_timestamps_after_audio_cuts'
                                            if narration.get('alignment_method') == 'local_asr_word_timestamps_after_audio_cuts'
                                            else 'fish_provider_word_timestamps_after_audio_cuts'
                                            if narration.get('alignment_method') == 'fish_provider_timestamps_after_audio_cuts'
                                            else 'fish_provider_word_timestamps_full_transcript') if word_based
                                           else narration['alignment_method']), srt_cues=cues)


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
