#!/usr/bin/env python3
"""Create new, bounded gallery deliveries offline; preserve every original file.

This never renders an episode or synthesizes audio. It decodes existing <=60s
gallery videos, encodes uniform H.264 High/4:2:0 and copies AAC without changes.
An unfinished repair is preserved without item.json and is not listed by the UI.
Archiving old gallery items is deliberately a separate operator decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from collections import Counter


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, check=True, timeout=1200)


def inspect_delivery(path: Path, *, require_420: bool = True) -> dict:
    info = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                          '-of', 'json', str(path)]).stdout)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in info['streams'] if s['codec_type'] == 'audio')
    frames = json.loads(run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_frames', '-show_entries', 'frame=pix_fmt,width,height', '-of', 'json', str(path)]).stdout)['frames']
    formats = dict(Counter(f['pix_fmt'] for f in frames))
    geometry = {(f['width'], f['height']) for f in frames}
    headers = run(['ffmpeg', '-nostdin', '-hide_banner', '-v', 'info', '-i', str(path),
                   '-map', '0:v:0', '-c:v', 'copy', '-bsf:v', 'trace_headers',
                   '-f', 'null', '-']).stderr
    sps = {key: sorted({int(value) for value in re.findall(
        r'\b' + key + r'\s+\S+ = (\d+)', headers)})
        for key in ('profile_idc', 'chroma_format_idc', 'reserved_zero_2bits')}
    if not frames or len(geometry) != 1:
        raise ValueError('Empty video or changing frame geometry')
    if require_420 and (formats.keys() != {'yuv420p'} or video['codec_name'] != 'h264'
                        or video['profile'] not in {'High', 'Main', 'Constrained Baseline'}
                        or not sps['profile_idc'] or not set(sps['profile_idc']) <= {66, 77, 100}
                        or not (sps['chroma_format_idc'] == [1]
                                or (not sps['chroma_format_idc'] and set(sps['profile_idc']) <= {66, 77}))
                        or sps['reserved_zero_2bits'] != [0]):
        raise ValueError(f'Incompatible frame formats/profile: {formats} / {video.get("profile")}')
    if audio['codec_name'] != 'aac' or audio.get('profile') != 'LC':
        raise ValueError('Delivery must retain an AAC-LC audio stream')
    # A permissive software decoder alone does not reject profile switches.
    # Keep full decode in addition to the exhaustive pixel-format check above.
    run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(path), '-f', 'null', '-'])
    audio_hash = run(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a:0',
                      '-c:a', 'copy', '-f', 'hash', '-hash', 'sha256', '-']).stdout.strip()
    return {'sha256': sha256(path), 'duration': float(info['format']['duration']),
            'video_codec': video['codec_name'], 'profile': video['profile'],
            'level': video.get('level'), 'pixel_formats': formats,
            'h264_sps': sps,
            'frame_count': len(frames), 'geometry': list(next(iter(geometry))),
            'audio_codec': audio['codec_name'], 'audio_profile': audio['profile'],
            'audio_packet_sha256': audio_hash, 'full_decode': 'passed'}


def repair_item(root: Path, item_id: str, revision: str = 'compat1') -> dict:
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}', item_id):
        raise ValueError('Invalid gallery ID')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,17}', revision):
        raise ValueError('Invalid revision')
    parent = root.resolve() / 'outputs' / 'motion-gallery'
    source = parent / item_id
    if source.is_symlink() or not source.is_dir():
        raise ValueError('Gallery source must be a real directory')
    files = sorted(p for p in source.iterdir() if p.is_file())
    if any(p.is_symlink() for p in source.iterdir()):
        raise ValueError('Gallery source must not contain symbolic links')
    originals = {p.name: sha256(p) for p in files}
    item = json.loads((source / 'item.json').read_text())
    if (item.get('id') != item_id or item.get('kind') not in {'effect', 'sample'}
            or type(item.get('duration')) not in (int, float) or not 0 < item['duration'] <= 60):
        raise ValueError('Only existing short, active gallery items can be repaired')
    before = inspect_delivery(source / 'preview.mp4', require_420=False)
    if not 0 < before['duration'] <= 60:
        raise ValueError('Refusing to process media longer than 60 seconds')
    target = parent / f'{item_id}_{revision}'
    target.mkdir(exist_ok=False)
    video_receipts = {}
    for filename in ('preview.mp4', 'baseline.mp4'):
        original = source / filename
        if not original.is_file():
            continue
        prior = before if filename == 'preview.mp4' else inspect_delivery(original, require_420=False)
        if not 0 < prior['duration'] <= 60:
            raise ValueError('Refusing to process media longer than 60 seconds')
        output = target / filename
        # Re-encode only video. No normalization, resampling, fades or truncation
        # of the confirmed AAC mix. Profile is enforced, level is encoder-derived.
        if (filename == 'baseline.mp4' and prior['pixel_formats'].keys() == {'yuv420p'}
                and prior['profile'] in {'High', 'Main', 'Constrained Baseline'}):
            # A compatible A/B reference needs no generation loss at all.
            shutil.copyfile(original, output)
        else:
            run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-i', str(original),
                 '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'libx264', '-preset', 'medium',
                 '-crf', '18', '-profile:v', 'high', '-pix_fmt', 'yuv420p', '-threads', '2',
                 '-maxrate', '20M', '-bufsize', '40M', '-c:a', 'copy',
                 '-movflags', '+faststart', str(output)])
        after = inspect_delivery(output)
        if (abs(prior['duration'] - after['duration']) > .04
                or prior['frame_count'] != after['frame_count']
                or prior['audio_packet_sha256'] != after['audio_packet_sha256']):
            raise ValueError('Repair changed duration, frame count or approved AAC packets')
        video_receipts[filename] = {'before': prior, 'after': after}
    for name in ('contact.jpg', 'CREDITS.md'):
        if (source / name).is_file():
            shutil.copyfile(source / name, target / name)
    receipt = {'version': 1, 'operation': 'offline-h264-uniform-420-video-only',
               'source_id': item_id, 'target_id': target.name,
               'original_files_sha256': originals, 'videos': video_receipts,
               'external_requests': 0, 'speech_synthesis': False,
               'windows_decoder_verification': 'not available in this Linux environment'}
    if {p.name: sha256(p) for p in files} != originals:
        raise ValueError('An original file changed during repair')
    (target / 'repair.json').write_text(json.dumps(receipt, indent=2) + '\n')
    (target / 'qa.json').write_text(json.dumps(receipt, indent=2) + '\n')
    with (target / 'CREDITS.md').open('a') as handle:
        handle.write(f'\n\nDelivery compatibility revision from `{item_id}`; video re-encoded offline '
                     'as uniform H.264 High/4:2:0; approved AAC packets preserved exactly. '
                     'Original media retained; SHA-256 evidence in repair.json.\n')
    item.update(id=target.name, title=item['title'] + ' · compatibilidad 4:2:0',
                review='Vídeo 4:2:0 verificado en todos los fotogramas; AAC original conservado. '
                       'La reproducción en Windows requiere confirmación del operador.')
    # Publish the new gallery entry only after every video and invariant passes.
    (target / 'item.json').write_text(json.dumps(item, ensure_ascii=False, indent=2) + '\n')
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--item', action='append', required=True)
    parser.add_argument('--revision', default='compat1')
    args = parser.parse_args()
    for item_id in args.item:
        receipt = repair_item(args.root, item_id, args.revision)
        print(json.dumps({'id': receipt['target_id'], 'videos': receipt['videos']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
