"""Pipeline-specific acceptance over Kitok's existing audiovisual measurements."""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
import subprocess

from ..editing.quality import inspect_video
from .files import digest, replace_state


QA_VERSION = 2


def silence_intervals(path: Path, *, settings) -> list[dict]:
    """Find sustained quiet audio, including tails; a pause is not proof of a defect."""
    result = subprocess.run(
        [settings.ffmpeg_binary, '-nostdin', '-hide_banner', '-threads', '2',
         '-i', str(path), '-map', '0:a:0', '-vn', '-af',
         'silencedetect=noise=-45dB:d=1.5', '-f', 'null', '-'],
        capture_output=True, text=True, check=True, timeout=600,
    )
    intervals = []
    start = None
    for kind, value in re.findall(r'silence_(start|end):\s*([\d.eE+-]+)', result.stderr):
        if kind == 'start':
            start = float(value)
        elif start is not None:
            end = float(value)
            if not math.isfinite(start) or not math.isfinite(end) or end < start:
                raise ValueError('Invalid silence detector interval')
            intervals.append({'start': start, 'end': end, 'duration': end-start})
            start = None
    if start is not None:
        raise ValueError('Silence detector did not close its final interval')
    return intervals


def inspect_audio_continuity(video: Path, narration: Path, *, settings) -> dict:
    # Analyze the dry voice too: background music can mask a missing voice segment.
    tracks = {name: {'sha256': digest(path), 'quiet_intervals': silence_intervals(path, settings=settings)}
              for name, path in [('source_narration', narration), ('final_mix', video)]}
    return {'method': 'FFmpeg silencedetect', 'threshold_db': -45, 'minimum_seconds': 1.5,
            'tracks': tracks,
            'status': 'human_review_required' if any(t['quiet_intervals'] for t in tracks.values())
                      else 'no_long_silence_detected',
            'limitation': 'Quiet intervals may be intentional pauses. Short dropouts and spoken synchronization require listening.'}


def inspect_delivery(video: Path, output: Path, *, plan, settings, narration: Path,
                     fade_in=.6, fade_out=.8) -> dict:
    report = inspect_video(video, output, settings=settings,
                           scene_boundaries=[(s.start+s.end)/2 for s in plan.scenes])
    raw = subprocess.run([settings.ffprobe_binary,'-v','error','-select_streams','v:0',
                          '-show_entries','frame=best_effort_timestamp_time,pix_fmt','-of','json',str(video)],
                         capture_output=True,text=True,check=True,timeout=600)
    frames = json.loads(raw.stdout)['frames']
    expected = round(plan.duration*30)
    failures = []
    if len(frames) != expected:
        failures.append('Decoded frame count differs from narration clock')
    maximum_error = 0.
    for index, frame in enumerate(frames):
        error = abs(float(frame['best_effort_timestamp_time'])-index/30)
        maximum_error = max(maximum_error,error)
        if frame.get('pix_fmt') != 'yuv420p' or not math.isfinite(error) or error > 1e-5:
            failures.append(f'Frame {index} has incompatible pixel format or timing')
            break
    if report['geometry'] != [1920,1080] or abs(report['fps']-30) > 1e-6:
        failures.append('Delivery must be 1920x1080 at 30 fps')
    if report['audio_stream_duration'] is None or abs(report['audio_stream_duration']-plan.narration_duration) > .08:
        failures.append('Audio duration differs from complete source narration')
    loudness = report['loudness']
    integrated, peak = loudness.get('integrated_lufs'), loudness.get('true_peak_dbtp')
    if integrated is None or not math.isfinite(integrated) or abs(integrated+16)>1:
        failures.append('Integrated audio loudness is outside -16 LUFS +/-1')
    if peak is None or not math.isfinite(peak) or peak > -1.5:
        failures.append('Audio true peak exceeds -1.5 dBTP or is not measurable')
    unexpected = [item for item in report['black_intervals']
                  if not (item['start'] <= .05 and item['end'] <= fade_in+.15)
                  and not (item['start'] >= plan.duration-fade_out-.15 and item['end'] >= plan.duration-.15)]
    if unexpected:
        failures.append('Unexpected interior black interval; inspect the preserved frames')
    continuity = inspect_audio_continuity(video, narration, settings=settings)
    report.update(qa_version=QA_VERSION, audio_continuity=continuity,
                  decoded_frames=len(frames),expected_frames=expected,max_pts_error=maximum_error,
                  unexpected_black_intervals=unexpected,failures=failures,
                  technical_status='passed' if not failures else 'rejected',
                  human_review_required=['acoustic synchronization of supplied SRT', 'all illustration meanings',
                                         'character/style consistency and deformations', 'unwanted generated lettering',
                                         'music listening and pacing', 'quiet intervals and possible audio dropouts',
                                         'thumbnail legibility', 'reference rights'])
    replace_state(output,report)
    return report
