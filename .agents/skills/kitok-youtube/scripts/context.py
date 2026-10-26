"""Read-only, compact editorial context. Never imports providers or renders media."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


def within(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Path must stay inside the Kitok repository')
    return path


def read_json(path: Path):
    if path.stat().st_size > 8_000_000:
        raise ValueError(f'JSON exceeds context reader limit: {path.name}')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def context(root: Path, episode: str | None = None, scene_ids=()) -> dict:
    root = root.resolve()
    profile = within(root, 'presets/youtube_historia_stickman_es.json')
    report = {
        'repository': str(root),
        'read_only': True,
        'profile': read_json(profile),
        'guide': 'docs/youtube-editorial.md',
        'research': 'docs/youtube-editorial.md',
        'historical_research': {
            'path': 'docs/research/2026-10-22-historias/README.md',
            'scope': 'Generic historical topics, not the current horror-channel selection.'
        },
        'provider_calls': 0,
        'limitation': 'File presence is not approval, semantic quality or acoustic synchronization.'
    }
    if episode is None:
        if scene_ids:
            raise ValueError('--scene requires --episode')
        return report
    folder = within(root, episode)
    base = (root / 'content/longform').resolve()
    if folder == base or not folder.is_relative_to(base) or not folder.is_dir():
        raise ValueError('Episode must be an existing folder inside content/longform')
    names = ['guion_final.txt', 'titulo.txt', 'configuracion.json', 'voz.mp3',
             'voz.srt', 'voz.alignment.json', 'editorial/estado.json',
             'planificacion_visual/plan_visual_prevoz.json', 'plan_visual.json']
    files = {}
    for name in names:
        path = within(root, str(folder.relative_to(root) / name))
        files[name] = {'exists': path.is_file()}
        if path.is_file():
            files[name]['bytes'] = path.stat().st_size
    report['episode'] = str(folder.relative_to(root))
    report['files'] = files
    state = folder / 'editorial/estado.json'
    if state.is_file():
        report['editorial_state'] = read_json(state)
    else:
        report['editorial_state'] = None
        report['next_action'] = 'Read existing episode decisions before creating editorial/estado.json; never assume approvals.'
    alignment = folder / 'voz.alignment.json'
    if alignment.is_file():
        words = read_json(alignment).get('words', [])
        report['alignment_segments'] = len(words)
    plan_path = folder / 'planificacion_visual/plan_visual_prevoz.json'
    if plan_path.is_file():
        scenes = read_json(plan_path).get('scenes', [])
        report['editorial_scenes'] = len(scenes)
        report['missing_images'] = []
        report['images_with_stale_not_generated_flag'] = []
        identifiers = set()
        selected = []
        for scene in scenes:
            ident = scene['id']
            if ident in identifiers:
                raise ValueError(f'Duplicate editorial scene: {ident}')
            identifiers.add(ident)
            image = within(root, str(folder.relative_to(root) / scene['image_file']))
            if not image.is_file():
                report['missing_images'].append(ident)
            elif scene.get('status') == 'not_generated':
                report['images_with_stale_not_generated_flag'].append(ident)
            if ident in scene_ids:
                selected.append({k: scene.get(k) for k in ('id', 'narration', 'visual_description_en', 'scene_prompt', 'image_file', 'status')})
        unknown = set(scene_ids) - identifiers
        if unknown:
            raise ValueError(f'Unknown scene IDs: {sorted(unknown)}')
        if scene_ids:
            report['selected_scenes'] = selected
    elif scene_ids:
        raise ValueError('No original visual plan available for requested scenes')
    image_dir = within(root, str(folder.relative_to(root) / 'imagenes'))
    report['image_files'] = len(list(image_dir.glob('*.png'))) if image_dir.is_dir() else 0
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode')
    parser.add_argument('--scene', action='append', default=[], help='Return only the selected exact prompts, maximum eight scenes')
    args = parser.parse_args(argv)
    try:
        if len(args.scene) > 8 or any(not re.fullmatch(r'escena_\d{3,}', value) for value in args.scene):
            raise ValueError('Supply at most eight escena_XXX identifiers')
        report = context(Path(__file__).resolve().parents[4], args.episode, args.scene)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(2, f'Cannot read editorial context: {error}\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
