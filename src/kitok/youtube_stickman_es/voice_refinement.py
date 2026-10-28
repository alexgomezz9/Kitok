"""Bounded second recognition of uniquely anchored discrepancies; audio only.

Raw recognition and word clocks remain immutable. A resolution documents text
correspondence, never replacement timestamps or permission to remove audio.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import wave

from .files import digest, local_file, write
from .voice_fidelity import activity_outside_words, compare_transcript, tokens

RATE = 48000
POLICY = {'version': 2, 'min_anchor_words': 2, 'max_anchor_words': 8,
          'maximum_windows': 12, 'maximum_window_seconds': 20, 'padding_seconds': .2,
          'audio_context_words': 8, 'sentence_boundary_extension_words': 8}


def _positions(words: list[str], part: list[str]) -> list[int]:
    return [i for i in range(len(words)-len(part)+1) if words[i:i+len(part)] == part]


def window_requests(script: str, asr: dict) -> list[dict]:
    """Only discrepancies between exact, individually unique context anchors."""
    expected, heard = tokens(script), tokens(asr['text'])
    segments = asr['segments']
    if ([token for row in segments for token in tokens(row['text'])] != heard
            or any(len(tokens(row['text'])) != 1 for row in segments)):
        return []
    opcodes = SequenceMatcher(None, expected, heard, autojunk=False).get_opcodes()
    if sum(row[0] != 'equal' for row in opcodes) > POLICY['maximum_windows']:
        return []
    requests, difference_index = [], -1
    for index, (kind, i, j, a, b) in enumerate(opcodes):
        if kind == 'equal':
            continue
        difference_index += 1
        if (index == 0 or index+1 == len(opcodes)
                or opcodes[index-1][0] != 'equal' or opcodes[index+1][0] != 'equal'):
            continue
        def anchor(side):
            limit = opcodes[index-1][2]-opcodes[index-1][1] if side == 'left' else opcodes[index+1][2]-opcodes[index+1][1]
            for size in range(2, min(limit, POLICY['max_anchor_words'])+1):
                part = expected[i-size:i] if side == 'left' else expected[j:j+size]
                if len(_positions(expected, part)) == len(_positions(heard, part)) == 1:
                    return part
            return []
        left, right = anchor('left'), anchor('right')
        if not left or not right:
            continue
        first_index = max(0, a-max(len(left), POLICY['audio_context_words']))
        last_index = min(len(segments)-1, b+max(len(right), POLICY['audio_context_words'])-1)
        # Prefer complete utterances around the diagnostic anchors, rather than
        # clipping the first/last word of their surrounding sentence.
        for _ in range(POLICY['sentence_boundary_extension_words']):
            if first_index == 0 or re.search(r'[.!?]["\u00bb]*$', segments[first_index-1]['text']):
                break
            first_index -= 1
        for _ in range(POLICY['sentence_boundary_extension_words']):
            if last_index == len(segments)-1 or re.search(r'[.!?]["\u00bb]*$', segments[last_index]['text']):
                break
            last_index += 1
        while first_index > 0 and segments[first_index]['start'] == segments[first_index]['end']:
            first_index -= 1
        while last_index+1 < len(segments) and segments[last_index]['start'] == segments[last_index]['end']:
            last_index += 1
        first, last = segments[first_index], segments[last_index]
        if not first['start'] < first['end'] <= last['start'] < last['end']:
            continue
        start = max(0, math.floor((first['start']-POLICY['padding_seconds'])*RATE))
        end = math.ceil(min(asr['duration'], last['end']+POLICY['padding_seconds'])*RATE)
        if not 0 < (end-start)/RATE <= POLICY['maximum_window_seconds']:
            continue
        requests.append({'difference_index': difference_index, 'kind': kind,
            'script_range': [i-len(left), j+len(right)], 'asr_range': [a-len(left), b+len(right)],
            'left_anchor': left, 'right_anchor': right, 'expected_context': expected[i-len(left):j+len(right)],
            'source_samples': [start, end], 'offset': start/RATE, 'duration': (end-start)/RATE})
    return requests


def resolve_window(request: dict, result: dict, activity: list[dict]) -> dict:
    """Compare the whole interval between unique anchors, including every extra."""
    resolution = {'difference_index': request['difference_index'], 'resolved': False}
    try:
        checked = compare_transcript(result['text'], result)
    except (ValueError, KeyError, TypeError):
        return {**resolution, 'reason': 'invalid_window_recognition'}
    heard = tokens(result['text'])
    if (not checked['timestamp_text_matches'] or activity
            or any(len(tokens(row['text'])) != 1 for row in result['segments'])):
        return {**resolution, 'reason': 'incomplete_window_clock_or_uncovered_energy'}
    left, right = _positions(heard, request['left_anchor']), _positions(heard, request['right_anchor'])
    if len(left) != 1 or len(right) != 1 or left[0]+len(request['left_anchor']) > right[0]:
        return {**resolution, 'reason': 'ambiguous_or_missing_window_anchors'}
    start, end = left[0], right[0]+len(request['right_anchor'])
    words = result['segments'][start:end]
    if (any(not word['start'] < word['end'] for word in words)
            or any(a['end'] > b['start'] for a, b in zip(words, words[1:]))):
        return {**resolution, 'reason': 'window_context_needs_positive_observed_word_times'}
    actual, expected = heard[start:end], request['expected_context']
    if ''.join(actual) != ''.join(expected):
        return {**resolution, 'reason': 'window_context_still_differs', 'recognized_context': actual}
    return {**resolution, 'resolved': True, 'window_word_range': [start, end],
            'recognized_context': actual,
            'method': 'exact_context' if actual == expected else 'exact_context_letters_with_different_word_boundaries'}


def refine_report(episode: Path, audio: Path, script: str, asr: dict, report: dict, *,
                  settings, python: Path, model: Path, transcribe: bool) -> dict:
    """One offline model load for short clips; reuse only hash-bound evidence."""
    from .voice_cleaning import _WINDOW_RUNNER
    requests = window_requests(script, asr)
    if not requests:
        return report
    raw_path = Path(report['report_path']).parent / 'asr.json'
    if (digest(audio) != report['identity']['audio_sha256']
            or digest(raw_path) != report['response_sha256']
            or json.loads(raw_path.read_text()) != asr
            or local_file(episode, 'guion_final.txt').read_text(encoding='utf-8-sig') != script
            or digest(local_file(episode, 'guion_final.txt')) != report['identity']['script_sha256']):
        raise ValueError('Source voice, script or recognition changed before window verification')
    identity = {'policy': POLICY, 'source_identity': report['identity'],
                'source_asr_sha256': digest(raw_path), 'source_report_sha256': digest(Path(report['report_path'])),
                'runner_sha256': digest(_WINDOW_RUNNER), 'requests': requests}
    key = digest(identity)
    folder = local_file(episode, str(Path(report['report_path']).parent.relative_to(episode) / 'windows' / key), exists=False)
    evidence_path = folder / 'evidence.json'
    if not evidence_path.exists() and not transcribe:
        return report
    if evidence_path.exists():
        evidence = json.loads(evidence_path.read_text())
        if evidence.get('identity') != identity:
            raise ValueError('Window recognition identity changed; preserve and review')
    else:
        folder.mkdir(parents=True, exist_ok=True)
        write(folder / 'request.json', identity)
        clips = []
        with tempfile.TemporaryDirectory(prefix='.decode-', dir=folder) as temporary:
            from .audio_splices import _decode
            pcm = Path(temporary) / 'source.wav'
            _decode(audio, pcm, settings.ffmpeg_binary)
            with wave.open(str(pcm)) as source:
                for index, request in enumerate(requests):
                    clip = local_file(episode, str((folder / f'window-{index:02d}.wav').relative_to(episode)), exists=False)
                    a, b = request['source_samples']
                    if b > source.getnframes():
                        raise ValueError('Recognition window exceeds decoded source samples')
                    source.setpos(a)
                    samples = source.readframes(b-a)
                    if clip.exists():
                        with wave.open(str(clip)) as previous:
                            if previous.getparams() != (source.getparams()._replace(nframes=b-a)) or previous.readframes(b-a) != samples:
                                raise ValueError('Existing recognition window changed; preserve and review')
                    else:
                        with clip.open('xb') as target, wave.open(target, 'wb') as out:
                            out.setparams(source.getparams())
                            out.writeframes(samples)
                    clips.append({'request': request, 'audio_path': str(clip.relative_to(episode)),
                                  'audio_sha256': digest(clip)})
        response_path = folder / 'response.json'
        if response_path.exists():
            results = json.loads(response_path.read_text())
        else:
            if any(digest(model / name) != sha for name, sha in report['identity']['model_files'].items()):
                raise ValueError('Window ASR model differs from the original independent recognition')
            process = subprocess.run([str(python), '-c', _WINDOW_RUNNER, str(model),
                json.dumps([str(episode / row['audio_path']) for row in clips])],
                capture_output=True, text=True, check=True, timeout=1800,
                env={**os.environ, 'HF_HUB_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1'})
            results = json.loads(process.stdout)
            write(response_path, results)
        if not isinstance(results, list) or len(results) != len(clips):
            raise ValueError('Incomplete independent window recognition; originals preserved')
        for clip, result in zip(clips, results):
            if abs(result.get('duration', 0)-clip['request']['duration']) > .05:
                raise ValueError('Window ASR duration does not cover its exact audio samples')
            clip.update(result=result, result_sha256=digest(result),
                uncovered_activity=activity_outside_words(episode / clip['audio_path'], result['segments'],
                    ffmpeg=settings.ffmpeg_binary, duration=clip['request']['duration']))
        evidence = {'identity': identity, 'windows': clips}
        write(evidence_path, evidence)
    if (digest(audio) != report['identity']['audio_sha256'] or digest(raw_path) != identity['source_asr_sha256']
            or digest(local_file(episode, 'guion_final.txt')) != report['identity']['script_sha256']):
        raise ValueError('Source voice, script or recognition changed during window verification')
    if len(evidence.get('windows', [])) != len(requests):
        raise ValueError('Incomplete cached window recognition')
    if json.loads((folder / 'response.json').read_text()) != [clip['result'] for clip in evidence['windows']]:
        raise ValueError('Raw window recognition response changed; preserve and review')
    resolutions = []
    for request, clip in zip(requests, evidence['windows']):
        if (clip.get('request') != request or digest(local_file(episode, clip['audio_path'])) != clip.get('audio_sha256')
                or digest(clip['result']) != clip.get('result_sha256')):
            raise ValueError('Window recognition evidence changed; preserve and review')
        resolutions.append(resolve_window(request, clip['result'], clip['uncovered_activity']))
    resolved = {row['difference_index'] for row in resolutions if row['resolved']}
    remaining = [row for index, row in enumerate(report['differences']) if index not in resolved]
    path = Path(report['report_path']).parent / f'report.refined-{key}.json'
    refined = {**report, 'status': 'review_required' if remaining or report['uncovered_activity'] else 'matched',
               'original_report_path': report['report_path'], 'report_path': str(path),
               'remaining_differences': remaining, 'refinement': {'policy': POLICY,
                   'evidence_path': str(evidence_path), 'evidence_sha256': digest(evidence_path),
                   'resolutions': resolutions}}
    write(path, refined)
    return refined
