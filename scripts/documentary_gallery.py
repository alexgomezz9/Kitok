#!/usr/bin/env python3
"""Bounded offline proofs using the same partial-plan compiler and renderer as Native.

Use an existing final audio excerpt, a script, optional alignment and local stock
search cache. Never constructs Fish/Pexels HTTP clients or renders a full episode.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import re

from kitok.config import PROJECT_ROOT, Settings
from kitok.editing.manifest import build_edit_manifest
from kitok.editing.motion import motion_plan
from kitok.editing.production import render_editorial_plan
from kitok.editing.quality import inspect_video
from kitok.editing.storyboard import file_hash, frame_time, project_file
from kitok.longform.models import TimelineClip
from kitok.longform.timeline import build_semantic_timeline
from kitok.media.ffprobe import measured_video_duration
from kitok.native_recovery import CachedStock
from kitok.rendering.native import source_window_duration
from kitok.state import write_json_atomic
from kitok.stock.selector import OutputGeometry


def publish_item(plan, folder, settings, *, title, family, credits, collection,
                 kind='sample', effect_status='new', baseline=None):
    """Expose a candidate only after its complete decode and audio check pass."""
    output = folder / 'preview.mp4'
    result = render_editorial_plan(plan, root=PROJECT_ROOT, output=output,
                                   settings=settings, encoder_name='libx264')
    report = inspect_video(output, folder/'qa.json', settings=settings, comparison=baseline,
                           scene_boundaries=[(s.start+s.end)/2 for s in plan.scenes])
    Path(report['contact_sheet']).rename(folder/'contact.jpg')
    report['contact_sheet'] = str(folder/'contact.jpg')
    report['contact_sheet_sha256'] = file_hash(folder/'contact.jpg')
    write_json_atomic(folder/'qa.json', report)
    (folder/'CREDITS.md').write_text(credits, encoding='utf-8')
    plan.write(folder/'plan.json')
    write_json_atomic(folder/'item.json', {
        'id': folder.name, 'title': title, 'family': family, 'kind': kind,
        'duration': plan.duration, 'collection': collection, 'effect_status': effect_status,
        'review': 'Candidato local; revisar narración, movimiento y derechos. Stock ilustrativo.',
    })
    return result


def sample(config, settings, *, width=1920, height=1080):
    root = PROJECT_ROOT
    ident = config['id']
    if not isinstance(ident, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,99}', ident):
        raise ValueError('Invalid proof ID')
    duration = frame_time(float(config['duration']))
    if not 3 <= duration <= 40:
        raise ValueError('Proofs must be 3–40 seconds; never a full documentary')
    folder = root/'outputs/motion-gallery'/ident
    if folder.exists():
        raise ValueError('Proof folder exists; preserve it and choose a new ID')
    audio = project_file(root, config['audio_source'])
    script = project_file(root, config['script_file']).read_text(encoding='utf-8')
    alignment = (json.loads(project_file(root, config['alignment_file']).read_text())
                 if config.get('alignment_file') else None)
    try:
        editing = build_edit_manifest(script, duration, config['keywords'], word_alignment=alignment)
    except ValueError:
        if alignment is None:
            raise
        # Native keeps sentence estimates when its legacy manifest rejects
        # zero-length provider tokens. motion_plan independently validates the
        # complete expanded transcript before using any phrase timestamps.
        editing = build_edit_manifest(script, duration, config['keywords'])
    slots = build_semantic_timeline(editing.sections, duration, config['keywords'])
    stock = CachedStock(root/'cache/pexels', ffprobe=settings.ffprobe_binary)
    target = OutputGeometry(width, height)
    used, clips, credits = set(), [], []
    rng = random.Random(ident)
    for slot in slots:
        candidates = stock.search_videos(slot.query, orientation='landscape')
        # A bounded offline proof selects from already downloaded assets only.
        # New paid generation still uses Native's ordinary provider flow.
        candidates = [a for a in candidates if stock.asset_cache.video_path(a.asset_id).is_file()]
        selection = stock.select_candidate(candidates, target=target,
                                            minimum_duration=slot.duration, used_ids=used)
        path = stock.download_asset(selection)
        required = source_window_duration(slot, fps=30, motion=True)
        available = measured_video_duration(path, settings.ffprobe_binary) - required
        if available < -1e-6:
            raise ValueError('Cached stock is too short for the proof slot')
        clips.append(TimelineClip(slot, selection.asset.asset_id, path, rng.uniform(0, max(0, available))))
        used.add(selection.asset.asset_id)
        receipt = root/'cache/pexels-credits'/f'{selection.asset.asset_id}.json'
        record = json.loads(receipt.read_text()) if receipt.is_file() else {}
        credits.append(f"- {record.get('author', 'Creator unknown in historical cache')}: "
                       f"{record.get('source_url', selection.asset.page_url)}; "
                       'Pexels License https://www.pexels.com/license/; cropped/trimmed, illustrative.')
    folder.mkdir(parents=True)
    plan = motion_plan(clips, audio, duration, root=root, episode_id=ident,
                       editing=editing, style=config.get('preset', 'investigation'),
                       audio_is_final_mix=True, width=width, height=height,
                       word_alignment=alignment, script=script,
                       visual_plan=config.get('visual_plan', {}), visual_root=config.get('visual_root'))
    baseline_plan = motion_plan(clips, audio, duration, root=root, episode_id=ident+'_baseline',
                                editing=editing, style='basic', audio_is_final_mix=True,
                                width=width, height=height, script=script)
    baseline = folder/'baseline.mp4'
    render_editorial_plan(baseline_plan, root=root, output=baseline,
                          settings=settings, encoder_name='libx264')
    provenance = '\n'.join(credits)
    for asset in plan.assets.values():
        if asset.usage != 'illustration':
            provenance += f'\n- {asset.path}: {asset.description}. {asset.credit or "Permission/provenance unverified"}. {asset.source_url or ""}'
    return publish_item(plan, folder, settings, title=config['title'], family='documentary',
                        credits='# Credits\n\nExisting approved audio excerpt reused without normalization or new Fish.\n\n'
                                +provenance+'\n\n'+config.get('audio_credit', ''),
                        collection=config['collection'], baseline=baseline)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('--width', type=int, default=1920)
    parser.add_argument('--height', type=int, default=1080)
    args = parser.parse_args()
    result = sample(json.loads(args.config.read_text()), Settings(_env_file=None),
                    width=args.width, height=args.height)
    print(json.dumps({'frames': result['video_frames'], 'output': result['output']}))


if __name__ == '__main__':
    main()
