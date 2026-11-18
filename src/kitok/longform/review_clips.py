"""Export short visual excerpts worth reviewing, after a Native delivery."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from ..editing.storyboard import file_hash
from ..media.ffprobe import probe_video_clock

GROUPS = {'manuales': 'Insertos indicados por el editor',
          'kitok': 'Efectos, rótulos y fotos animadas por Kitok'}


def _selected_scenes(receipt):
    explicit = {cue.get('asset') for cue in receipt['alignment'].get('visual_cues', [])}
    for scene in receipt['scenes']:
        key = scene.get('asset')
        asset = receipt['assets'].get(key, {})
        if key and key in explicit and Path(asset['path']).suffix.lower() == '.mp4':
            yield 'manuales', scene, asset['description']
        elif (key and key in explicit) or scene.get('motion_design') or scene.get('graphic'):
            yield 'kitok', scene, scene['spoken_claim']


def _clock(seconds):
    minutes, rest = divmod(seconds, 60)
    return f'{int(minutes):02d}:{rest:05.2f}'


def export_review_clips(episode: Path, video: Path, receipt: dict, *,
                        ffmpeg: str, ffprobe: str) -> Path:
    destination = episode / 'clips_revision'
    if destination.is_symlink():
        raise ValueError('Review directory may not be a symlink')
    # Use the validated master so this also works after cleanup of scene caches.
    total_frames = receipt['video_frames']
    # Native uses an integer timeline fps. ffprobe reports duration in microseconds.
    fps = round(total_frames / float(receipt['video_stream_duration']))
    rows = {group: [] for group in GROUPS}
    for group, scene, description in _selected_scenes(receipt):
        start, end = round(scene['start'] * fps), round(scene['end'] * fps)
        if not 0 <= start < end <= total_frames:
            raise ValueError('Review scene is outside the validated timeline')
        filename = f'{start:06d}_{scene["id"]}.mp4'
        if Path(filename).name != filename or '\\' in filename:
            raise ValueError('Review clip ID contains a path')
        rows[group].append((filename, start, end, description))
    index = destination / 'INDICE.md'
    if destination.exists():
        if not index.is_symlink() and index.is_file() and _complete(destination, index, rows, receipt):
            return destination
        raise ValueError('Existing review clips differ. Preserve the directory before exporting a revision.')

    if probe_video_clock(video, ffprobe).frames != total_frames:
        raise ValueError('Editorial receipt does not match the final frame count')
    lines = ['# Planos para revisión', '',
             'Extractos visuales del MP4 final. El vídeo completo tiene la voz y la mezcla.',
             '', f'<!-- sha256 del MP4: {receipt["output_sha256"]} -->', '']
    with TemporaryDirectory(prefix='.clips-revision-', dir=episode) as temporary:
        staged = Path(temporary) / 'revision'
        staged.mkdir()
        for group, label in GROUPS.items():
            folder = staged / group
            folder.mkdir()
            lines += [f'## {label}', '']
            for filename, start, end, description in rows[group]:
                clip = folder / filename
                subprocess.run(
                    [ffmpeg, '-nostdin', '-v', 'error', '-ss', f'{start/fps:.9f}', '-i', str(video),
                     '-map', '0:v:0', '-an', '-frames:v', str(end-start), '-c:v', 'libx264',
                     '-preset', 'fast', '-crf', '17', '-threads', '2', '-movflags', '+faststart', str(clip)],
                    check=True, capture_output=True, text=True, timeout=240,
                )
                observed = probe_video_clock(clip, ffprobe)
                if observed.frames != end-start or abs(observed.start_time) > 1e-6:
                    raise ValueError(f'Review excerpt does not match the approved frame window: {filename}')
                text = ' '.join(description.split())
                relative = clip.relative_to(staged).as_posix()
                lines.append(f'- {_clock(start/fps)} a {_clock(end/fps)} '
                             f'[{text}]({relative}) <!-- {file_hash(clip)} -->')
            if not rows[group]:
                lines.append('Sin planos de este tipo.')
            lines.append('')
        (staged / 'INDICE.md').write_text('\n'.join(lines), encoding='utf-8')
        staged.rename(destination)
    return destination


def _complete(destination, index, rows, receipt):
    body = index.read_text(encoding='utf-8')
    if f'<!-- sha256 del MP4: {receipt["output_sha256"]} -->' not in body:
        return False
    for group, clips in rows.items():
        folder = destination / group
        if folder.is_symlink() or not folder.is_dir():
            return False
        for filename, *_ in clips:
            clip = folder / filename
            if (clip.is_symlink() or not clip.is_file()
                    or f'({group}/{filename}) <!-- {file_hash(clip)} -->' not in body):
                return False
    return True
