"""Immutable episode snapshots and narrative-bound reuse of provided illustrations."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from PIL import Image

from ..editing.manifest import clean_script
from .files import digest, episode_path, local_file, write


_PLAN_PATHS = ('plan_visual.json', 'planificacion_visual/plan_visual_prevoz.json')
_WORD = re.compile(r'\w+', re.UNICODE)


def _plan(episode: Path):
    for name in _PLAN_PATHS:
        candidate = local_file(episode, name, exists=False)
        if candidate.exists():
            data = json.loads(candidate.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not isinstance(data.get('scenes'), list) or not data['scenes']:
                raise ValueError('Provided visual plan must contain scenes')
            return candidate, data
    raise ValueError('Image reuse requires plan_visual.json with narrative source spans')


def source_spans(episode: Path, script: str) -> list[dict]:
    """Validate original narrative ownership before changing any timing or scene IDs.

    source_char_start/end address the exact source text, and word_end is exclusive.
    The original plan's estimated times and word counts are deliberately unused.
    """
    _, plan = _plan(episode)
    source = local_file(episode, plan.get('script_source', 'guion_lectura_limpia.txt'))
    if plan.get('script_sha256') != digest(source):
        raise ValueError('Provided visual plan script hash changed or is missing')
    text = source.read_text(encoding='utf-8')
    words = list(_WORD.finditer(text))
    final_words = _WORD.findall(clean_script(script))
    if [w.group().casefold() for w in words] != [w.casefold() for w in final_words]:
        raise ValueError('Provided visual plan does not match the complete narration transcript')
    result = []
    previous_char = previous_word = 0
    ids = set()
    for scene in plan['scenes']:
        if not isinstance(scene, dict):
            raise ValueError('Invalid provided visual scene')
        start, end = scene.get('source_char_start'), scene.get('source_char_end')
        if (type(start) is not int or type(end) is not int or
                not previous_char <= start < end <= len(text)):
            raise ValueError('Provided visual source spans overlap or are invalid')
        if text[previous_char:start].strip():
            raise ValueError('Provided visual source spans leave a narrative gap')
        narration = scene.get('narration')
        if not isinstance(narration, str) or text[start:end].strip() != narration.strip():
            raise ValueError('Provided visual narration does not match its source span')
        indices = [i for i, word in enumerate(words) if word.start() < end and word.end() > start]
        if not indices or indices != list(range(previous_word, indices[-1] + 1)):
            raise ValueError('Provided visual word spans must cover narration once in order')
        if words[indices[0]].start() < start or words[indices[-1]].end() > end:
            raise ValueError('Provided visual span splits a word')
        image_value = scene.get('image_file')
        if not isinstance(image_value, str):
            raise ValueError('Provided visual scene requires an image_file')
        image = local_file(episode, image_value)
        with Image.open(image) as loaded:
            loaded.verify()
        if scene.get('image_sha256') is not None and scene['image_sha256'] != digest(image):
            raise ValueError('Provided image hash changed')
        description = scene.get('visual_description', scene.get('visual_description_en'))
        prompt = scene.get('scene_prompt')
        if not isinstance(description, str) or not description.strip() or not isinstance(prompt, str) or not prompt.strip():
            raise ValueError('Provided visual scene needs its original description and prompt')
        source_id = scene.get('id')
        if not isinstance(source_id, str) or not source_id or source_id in ids:
            raise ValueError('Provided visual scenes require unique source IDs')
        ids.add(source_id)
        characters = scene.get('characters', [])
        if not isinstance(characters, list) or any(not isinstance(c, str) for c in characters):
            raise ValueError('Invalid provided scene characters')
        result.append({'word_start': previous_word, 'word_end': indices[-1] + 1,
                       'image_file': image_value, 'visual_description': description,
                       'scene_prompt': prompt, 'characters': characters, 'source_id': source_id})
        previous_char, previous_word = end, indices[-1] + 1
    if text[previous_char:].strip() or previous_word != len(words):
        raise ValueError('Provided visual plan does not cover the complete narration')
    return result


def _snapshot_files(episode: Path) -> dict[str, str]:
    """Only operator inputs; generated plans, renders and paid state stay outside."""
    paths = set()
    for name in ('configuracion.json', 'guion_final.txt', 'titulo.txt'):
        paths.add(local_file(episode, name).relative_to(episode).as_posix())
    for name in ('voz.mp3', 'voz.alignment.json', 'voz.srt', 'guion_lectura_limpia.txt',
                 *_PLAN_PATHS, 'planificacion_visual/aprobacion_estilo_operador.json'):
        candidate = local_file(episode, name, exists=False)
        if candidate.exists():
            if not candidate.is_file():
                raise ValueError('Snapshot inputs must be regular files')
            paths.add(name)
    config = json.loads(local_file(episode, 'configuracion.json').read_text(encoding='utf-8-sig'))
    for reference in config.get('references', []):
        paths.add(local_file(episode, reference['path']).relative_to(episode).as_posix())
    for plan_name in _PLAN_PATHS:
        plan_file = local_file(episode, plan_name, exists=False)
        if not plan_file.exists():
            continue
        plan = json.loads(plan_file.read_text(encoding='utf-8'))
        paths.add(local_file(episode, plan.get('script_source', 'guion_lectura_limpia.txt')).relative_to(episode).as_posix())
        for scene in plan.get('scenes', []):
            paths.add(local_file(episode, scene['image_file']).relative_to(episode).as_posix())
    return {name: digest(local_file(episode, name)) for name in sorted(paths)}


def safe_revision(root: Path, episode: Path, name: str) -> Path:
    """Copy immutable inputs atomically, under the caller's original episode lock.

    A resumed revision must match both its original inputs and its own pinned copy.
    Originals are never linked, modified or replaced. Runtime outputs are excluded.
    """
    episode = episode_path(root, episode)
    if not isinstance(name, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', name) is None:
        raise ValueError('Revision must be a simple identifier of at most 64 characters')
    folder = episode / 'revisiones'
    if folder.is_symlink():
        raise ValueError('Revision folders cannot be symlinks')
    folder.mkdir(exist_ok=True)
    target = folder / name
    if target.is_symlink():
        raise ValueError('Revision cannot be a symlink')
    hashes = _snapshot_files(episode)
    receipt = {'version': 1, 'source_episode': episode.relative_to(root.resolve()).as_posix(),
               'files': hashes}
    if target.exists():
        episode_path(root, target)
        manifest = local_file(target, 'revision_source.json')
        if json.loads(manifest.read_text(encoding='utf-8')) != receipt:
            raise ValueError('Revision source inputs changed; choose another revision')
        if any(digest(local_file(target, path)) != value for path, value in hashes.items()):
            raise ValueError('Revision snapshot changed; preserve it and choose another revision')
        return target
    temporary = Path(tempfile.mkdtemp(prefix=f'.{name}-', dir=folder))
    try:
        for path, expected in hashes.items():
            destination = temporary / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_file(episode, path), destination)
            if digest(destination) != expected:
                raise ValueError('Source input changed while creating revision')
        write(temporary / 'revision_source.json', receipt)
        if target.exists() or target.is_symlink():
            raise FileExistsError('Revision appeared while creating its snapshot')
        os.rename(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return target
