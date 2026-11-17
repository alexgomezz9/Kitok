#!/usr/bin/env python3
"""Inspect a short, authorized reference locally. No production or upload."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from PIL import Image, ImageDraw

from kitok.config import PROJECT_ROOT, Settings
from kitok.media.ffprobe import probe_media
from kitok.youtube_stickman_es.voice_fidelity import _LOCAL_RUNNER


def run(command: list[str], *, timeout: int = 180, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=True, env=env)


def download_reference(url: str, output: Path, settings: Settings) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use a direct HTTPS URL that authorizes downloading the reference')
    tool = PROJECT_ROOT / 'local/tools/yt-dlp'
    if not tool.is_file():
        raise ValueError('Install the verified standalone yt-dlp in local/tools/yt-dlp')
    node = PROJECT_ROOT / '.tools/node/bin/node'
    if not node.is_file():
        node = Path(shutil.which('node') or '/nonexistent')
    if not node.is_file():
        raise ValueError('yt-dlp needs Node 22+ for its included YouTube EJS component')
    run([str(tool), '--ignore-config', '--no-playlist', '--no-continue',
         '--no-progress', '--no-cache-dir', '--socket-timeout', '15', '--retries', '1',
         '--max-filesize', '160M',
         '--js-runtimes', f'node:{node}', '--ffmpeg-location',
         shutil.which(settings.ffmpeg_binary) or settings.ffmpeg_binary,
         '-f', 'bv[height<=480][ext=mp4]+ba[ext=m4a]/b[height<=480]/b',
         '--merge-output-format', 'mp4', '-o', str(output), '--', url], timeout=300)


def find_cuts(source: Path, ffmpeg: str, start: float, duration: float, threshold: float) -> list[float]:
    result = run([ffmpeg, '-nostdin', '-hide_banner', '-ss', str(start), '-i', str(source),
                  '-t', str(duration), '-an',
                  '-vf', f"select='gt(scene,{threshold})',showinfo", '-f', 'null', '-'])
    return [round(float(value), 3) for value in re.findall(r'pts_time:([0-9.]+)', result.stderr)]


def contact_sheet(clip: Path, folder: Path, times: list[float], start: float, ffmpeg: str) -> Path:
    width, height = 288, 182
    sheet = Image.new('RGB', (width * 3, height * math.ceil(len(times) / 3)), '#151922')
    label = ImageDraw.Draw(sheet)
    for index, value in enumerate(times):
        frame = folder / 'frame.jpg'
        run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-ss', f'{value:.3f}',
             '-i', str(clip), '-frames:v', '1', '-vf',
             'scale=288:160:force_original_aspect_ratio=decrease,pad=288:160:(ow-iw)/2:(oh-ih)/2',
             '-threads', '1', str(frame)])
        x, y = index % 3 * width, index // 3 * height
        with Image.open(frame) as image:
            sheet.paste(image, (x, y))
        label.text((x + 8, y + 164), f'{start + value:06.2f} s', fill='white')
        frame.unlink()
    path = folder / 'fotogramas.jpg'
    sheet.save(path, quality=90)
    return path


def inspect(source: Path, settings: Settings, folder: Path, args) -> tuple[dict, Path | None]:
    media = probe_media(source, settings.ffprobe_binary)
    if not media.video_codec or not math.isfinite(media.duration):
        raise ValueError('Choose a local video with a measurable duration')
    duration = min(args.duration, media.duration - args.start)
    if duration < .5:
        raise ValueError('Choose a window of at least half a second inside the video')
    clip = folder / 'reference.mp4'
    run([settings.ffmpeg_binary, '-nostdin', '-v', 'error', '-ss', str(args.start), '-i',
         str(source), '-t', str(duration), '-map', '0:v:0', '-map', '0:a:0?', '-vf',
         'scale=640:-2:force_original_aspect_ratio=decrease', '-c:v', 'libx264',
         '-threads', '2', '-preset', 'veryfast', '-c:a', 'aac', str(clip)])
    actual = min(duration, probe_media(clip, settings.ffprobe_binary).duration)
    cuts = find_cuts(source, settings.ffmpeg_binary, args.start, actual, args.cut_threshold)
    times = sorted({round(actual * i / 9, 3) for i in range(9)}
                   | {min(round(t + .08, 3), round(actual * .97, 3)) for t in cuts[:3]})
    sheet = contact_sheet(clip, folder, times, args.start, settings.ffmpeg_binary) if args.sheet else None
    report = {'window_seconds': [args.start, round(args.start + actual, 3)],
              'cut_candidates_seconds': [round(args.start + t, 3) for t in cuts[:40]],
              'cut_candidates_total': len(cuts), 'cut_threshold': args.cut_threshold}
    if media.audio_codec and not args.no_asr:
        worker = _LOCAL_RUNNER.replace("language='es'", "language=None if sys.argv[3]=='auto' else sys.argv[3]")
        result = run([str(settings.local_asr_python), '-c', worker, str(settings.local_asr_model),
                      str(clip), args.language], env={**os.environ, 'HF_HUB_OFFLINE': '1',
                      'HF_HUB_DISABLE_TELEMETRY': '1'}, timeout=600)
        transcript = json.loads(result.stdout)
        report['transcript'] = transcript['text'].strip()
        report['words'] = [{**word, 'start': round(args.start + word['start'], 3),
                            'end': round(args.start + word['end'], 3)}
                           for word in transcript['segments']]
    if media.audio_codec and args.sound:
        tool = PROJECT_ROOT / 'local/tools/earshot/bin/earshot'
        models = PROJECT_ROOT / 'local/tools/earshot/models'
        if not tool.is_file() or not (models / 'hf').is_dir():
            raise ValueError('Earshot and its offline models must be present in local/tools/earshot')
        # Discard decoded audio and embeddings after inspection. Keep one model cache.
        cache = folder / 'earshot'
        cache.mkdir()
        (cache / 'hf').symlink_to(models / 'hf', target_is_directory=True)
        result = run([str(tool), 'timeline', str(clip), '--detail', 'low', '--json'],
                     env={**os.environ, 'EARSHOT_HOME': str(cache), 'EARSHOT_THREADS': '2',
                          'EARSHOT_OFFLINE': '1', 'HF_HUB_OFFLINE': '1',
                          'HF_HUB_DISABLE_TELEMETRY': '1'}, timeout=360)
        sound = json.loads(result.stdout)
        important = sorted(sound.get('events', []), key=lambda row: row.get('prominence_db', 0), reverse=True)[:8]
        report['sound_candidates'] = [
            {'time': round(args.start + row['t'], 3), 'shape': row.get('shape'),
             'tags': [tag['tag'] for tag in row.get('tags', [])[:3]]}
            for row in sorted(important, key=lambda row: row['t'])]
        report['loudness'] = sound.get('loudness')
        report['music_candidate'] = sound.get('music')
    return report, sheet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='Local video or direct HTTPS URL authorized for download')
    parser.add_argument('--start', type=float, default=0)
    parser.add_argument('--duration', type=float, default=24, help='Up to 90 seconds per editorial window')
    parser.add_argument('--language', choices=('auto', 'en', 'es'), default='auto')
    parser.add_argument('--cut-threshold', type=float, default=.15)
    parser.add_argument('--sound', action='store_true', help='Add offline Earshot audio event candidates')
    parser.add_argument('--no-asr', action='store_true')
    parser.add_argument('--sheet', type=Path, help='Optional contact sheet JPEG to inspect visually')
    args = parser.parse_args()
    if (not math.isfinite(args.start) or args.start < 0 or not .5 <= args.duration <= 90
            or not .01 <= args.cut_threshold <= 1):
        parser.error('Use a finite nonnegative start, a 0.5–90s window and a cut threshold in [0.01,1]')
    try:
        settings = Settings(_env_file=None)
        with TemporaryDirectory(prefix='kitok-reference-') as work:
            folder = Path(work)
            if '://' in args.source:
                source = folder / 'download.mp4'
                download_reference(args.source, source, settings)
            else:
                source = Path(args.source).expanduser().resolve(strict=True)
                if not source.is_file():
                    raise ValueError('Choose an existing local video')
            report, sheet = inspect(source, settings, folder, args)
            if sheet:
                with args.sheet.open('xb') as target, sheet.open('rb') as input_file:
                    shutil.copyfileobj(input_file, target)
            print(json.dumps(report, ensure_ascii=False, indent=2))
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(2, f"{error}\n{getattr(error, 'stderr', '') or ''}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
