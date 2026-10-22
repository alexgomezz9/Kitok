"""Explicitly reviewed audio cuts, with original words and media preserved."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .files import digest, episode_lock, episode_path, local_file, write
from .reuse import _snapshot_files

METHOD = 'fish_provider_timestamps_after_audio_cuts'


def cut_words(words: list[dict], cuts: list[list[int]], rate: int, duration: float) -> list[dict]:
    if type(rate) is not int or rate <= 0 or not cuts:
        raise ValueError('Audio cuts need a sample rate and explicit intervals')
    previous = 0
    for start, end in cuts:
        if (type(start) is not int or type(end) is not int
                or not previous <= start < end <= math.floor(duration*rate)):
            raise ValueError('Audio cuts must be ordered, disjoint sample intervals')
        if any(start/rate < w['end'] and end/rate > w['start'] for w in words):
            raise ValueError('An audio cut intersects a provider word; nothing was removed')
        previous = end

    def shifted(value):
        return value - sum(end-start for start, end in cuts if end/rate <= value)/rate

    return [{**w, 'start': shifted(w['start']), 'end': shifted(w['end'])} for w in words]


def verify_edited_alignment(path: Path, data: dict, script: str) -> list[dict]:
    from .audio import _provider_segments
    edit = data['audio_edit']
    source = local_file(path.parent, 'audio_original/voz.mp3')
    alignment = local_file(path.parent, 'audio_original/voz.alignment.json')
    output = local_file(path.parent, 'voz.mp3')
    if json.loads(alignment.read_text())['method'] != 'fish_provider_timestamps':
        raise ValueError('Expected original provider alignment as cut evidence')
    if (digest(source) != edit['source_audio_sha256']
            or digest(alignment) != edit['source_alignment_sha256']
            or digest(output) != edit['output_audio_sha256']):
        raise ValueError('Edited audio or original evidence changed')
    original = _provider_segments(alignment, script, edit['source_duration'])
    expected = cut_words(original, edit['removed_samples'], edit['sample_rate'], edit['source_duration'])
    if data['words'] != expected:
        raise ValueError('Edited word timestamps do not match the recorded audio cuts')
    return expected


def repair_audio(root: Path, episode: Path, destination: str, cuts: list[tuple[float, float]],
                 *, settings, reviewer: str) -> Path:
    """Create a new episode atomically. Never replace audio or reuse paid state."""
    from .audio import _provider_segments, _provider_cues, format_srt
    from ..media.ffprobe import stream_durations
    root = root.resolve()
    episode = episode_path(root, episode)
    target = local_file(root, destination, exists=False)
    if target.exists() or not reviewer.strip():
        raise ValueError('Choose an absent destination and identify the audio reviewer')
    target.parent.mkdir(parents=True, exist_ok=True)
    with episode_lock(episode):
        hashes = _snapshot_files(episode)
        audio = local_file(episode, 'voz.mp3')
        alignment = local_file(episode, 'voz.alignment.json')
        if json.loads(alignment.read_text())['method'] != 'fish_provider_timestamps':
            raise ValueError('Cut the original provider audio, not a previously edited copy')
        script = local_file(episode, 'guion_final.txt').read_text(encoding='utf-8-sig')
        duration = stream_durations(audio, settings.ffprobe_binary)[1]
        words = _provider_segments(alignment, script, duration)
        # PCM cuts are sample-exact; decode once and encode the finished MP3 once.
        rate = 44100
        if any(not math.isfinite(a) or not math.isfinite(b) for a, b in cuts):
            raise ValueError('Audio cuts need finite start and end times')
        removed = [[round(a*rate), round(b*rate)] for a, b in cuts]
        shifted = cut_words(words, removed, rate, duration)
        temporary = Path(tempfile.mkdtemp(prefix='.audio-repair-', dir=target.parent))
        try:
            for name in hashes:
                archive = 'audio_original/'+name if name in {'voz.mp3', 'voz.alignment.json', 'voz.srt'} else name
                dest = temporary/archive
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local_file(episode, name), dest)
                if digest(dest) != hashes[name]:
                    raise ValueError('Source changed during repair')
            intervals = []
            cursor = 0
            for start, end in removed:
                intervals.append((cursor, start))
                cursor = end
            intervals.append((cursor, None))
            intervals = [(a, b) for a, b in intervals if b is None or b > a]
            graph = []
            for index, (start, end) in enumerate(intervals):
                trim = f'atrim=start_sample={start}' + (f':end_sample={end}' if end is not None else '')
                fade = min(.005, (end-start)/rate/2) if end is not None else .005
                fades = f',afade=t=in:d={fade:.9f}' if index or start else ''
                if end is not None:
                    fades += f',afade=t=out:st={(end-start)/rate-fade:.9f}:d={fade:.9f}'
                graph.append(f'[0:a]aresample={rate},{trim},asetpts=PTS-STARTPTS{fades}[a{index}]')
            graph.append(''.join(f'[a{i}]' for i in range(len(intervals)))+
                         f'concat=n={len(intervals)}:v=0:a=1[out]')
            subprocess.run([settings.ffmpeg_binary, '-nostdin', '-v', 'error', '-n', '-i', str(audio),
                            '-filter_complex', ';'.join(graph), '-map', '[out]', '-c:a', 'libmp3lame',
                            '-b:a', '192k', str(temporary/'voz.mp3')], check=True, timeout=120,
                           capture_output=True)
            data = {'method': METHOD, 'precision': 'derived_from_provider_sample_cuts',
                    'confidence': None, 'words': shifted, 'audio_edit': {
                        'source_audio_sha256': digest(audio), 'source_alignment_sha256': digest(alignment),
                        'output_audio_sha256': digest(temporary/'voz.mp3'), 'source_duration': duration,
                        'sample_rate': rate, 'removed_samples': removed, 'reviewer': reviewer,
                        'maximum_seam_fade_seconds': .005,
                        'reason': 'Operator confirmed non-speech synthesis artifacts in these gaps'}}
            write(temporary/'voz.alignment.json', data)
            edited_duration = stream_durations(temporary/'voz.mp3', settings.ffprobe_binary)[1]
            expected = duration-sum(b-a for a,b in removed)/rate
            if abs(edited_duration-expected) > .06:
                raise ValueError('Repaired duration differs from the recorded cuts')
            write(temporary/'voz.srt', format_srt(_provider_cues(temporary/'voz.alignment.json', script, edited_duration)))
            write(temporary/'audio_repair_source.json', {'source_episode': str(episode.relative_to(root)),
                  'source_files': hashes, 'audio_edit': data['audio_edit']})
            if any(digest(local_file(episode, name)) != sha for name, sha in hashes.items()):
                raise ValueError('Source inputs changed during repair')
            if target.exists():
                raise FileExistsError('Destination appeared during repair')
            os.rename(temporary, target)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return target
