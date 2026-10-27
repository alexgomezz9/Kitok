"""Conservative, transcript-bound insertion cuts on immutable raw narration.

An edit is only a candidate until independent recognition of its output succeeds.
No synthesis, network, script rewriting or provider timestamps are invented here.
"""
from __future__ import annotations

from contextlib import contextmanager
from difflib import SequenceMatcher
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import wave

from .files import digest, write
from .voice_fidelity import tokens

VERSION = 1


def _hash(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def plan_autocuts(script: str, asr: dict, *, source_audio_sha256: str | None = None,
                 protected_words: list[dict] | None = None, sample_rate: int = 48000,
                 min_anchor_words: int = 2, margin_seconds: float = .04,
                 silences: list[tuple[float, float]] | None = None,
                 windows: list[dict] | None = None) -> dict:
    """Plan only internal INSERTs between unique exact script anchors.

    Identity must come from the independent ASR receipt, not the TTS transcript.
    `protected_words` may add original provider intervals as a further guard.
    Replacements, omissions, insufficient anchors and touching timings stay open.
    """
    if (type(sample_rate) is not int or not 8000 <= sample_rate <= 96000
            or type(min_anchor_words) is not int or min_anchor_words < 2
            or not _number(margin_seconds) or not .04 <= margin_seconds <= .1):
        raise ValueError('Invalid automatic cut policy')
    if not isinstance(asr, dict):
        raise ValueError('Independent timestamped ASR is required')
    identity = asr.get('identity', asr)
    if not isinstance(identity, dict):
        raise ValueError('Invalid independent ASR identity')
    audio_sha = source_audio_sha256 or identity.get('audio_sha256')
    if (not isinstance(identity, dict) or not isinstance(audio_sha, str) or len(audio_sha) != 64
            or any(c not in '0123456789abcdef' for c in audio_sha)
            or identity.get('audio_sha256') != audio_sha
            or not isinstance(identity.get('engine'), str) or not identity['engine'].strip()
            or not isinstance(identity.get('model_files'), dict) or not identity['model_files']
            or any(not isinstance(k, str) or not isinstance(v, str) or len(v) != 64
                   or any(c not in '0123456789abcdef' for c in v)
                   for k, v in identity['model_files'].items())):
        raise ValueError('Independent ASR must identify audio, engine and model hashes')
    identity = {k: identity[k] for k in ('audio_sha256', 'engine', 'model_files')}
    duration = asr.get('duration')
    if not _number(duration) or duration <= 0 or not isinstance(asr.get('segments'), list):
        raise ValueError('Independent ASR needs duration and word timestamps')
    heard, times, previous = [], [], 0.
    for segment in asr['segments']:
        if not isinstance(segment, dict) or not isinstance(segment.get('text'), str):
            raise ValueError('Invalid independent ASR word')
        start, end = segment.get('start'), segment.get('end')
        if (not _number(start) or not _number(end) or not previous <= start <= end <= duration
                or not tokens(segment['text'])):
            raise ValueError('Invalid independent ASR timestamps')
        for token in tokens(segment['text']):
            heard.append(token)
            times.append((start, end))
        previous = start
    expected = tokens(script)
    if not isinstance(asr.get('text'), str) or not expected or not heard or heard != tokens(asr['text']):
        raise ValueError('ASR text and timestamp words must match exactly')
    protected = []
    for word in protected_words or []:
        if not isinstance(word, dict):
            raise ValueError('Invalid protected word timestamp')
        start, end = word.get('start'), word.get('end')
        if not _number(start) or not _number(end) or not 0 <= start <= end <= duration + .001:
            raise ValueError('Invalid protected word timestamp')
        protected.append([start, end])
    silence_intervals = []
    for interval in silences or []:
        if (not isinstance(interval, (list, tuple)) or len(interval) != 2
                or not all(_number(v) for v in interval) or not 0 <= interval[0] < interval[1] <= duration):
            raise ValueError('Invalid measured silence interval')
        silence_intervals.append(list(interval))
    opcodes = SequenceMatcher(None, expected, heard, autojunk=False).get_opcodes()
    cuts, unresolved, matched = [], [], []
    for index, (kind, i, j, a, b) in enumerate(opcodes):
        if kind == 'equal':
            matched.extend({'script_word_index': k, 'word': expected[k],
                            'start': times[a+k-i][0], 'end': times[a+k-i][1]}
                           for k in range(i, j))
            continue
        row = {'kind': kind, 'script_range': [i, j], 'asr_range': [a, b],
               'expected': ' '.join(expected[i:j]), 'recognized': ' '.join(heard[a:b])}
        reason = None
        if kind != 'insert':
            reason = 'replacement_or_omission_requires_review'
        elif (index == 0 or index + 1 == len(opcodes)
              or opcodes[index-1][0] != 'equal' or opcodes[index+1][0] != 'equal'
              or opcodes[index-1][2] - opcodes[index-1][1] < min_anchor_words
              or opcodes[index+1][2] - opcodes[index+1][1] < min_anchor_words):
            reason = 'insufficient_exact_context_on_both_sides'
        else:
            anchor = expected[i-min_anchor_words:i+min_anchor_words]
            if sum(expected[k:k+len(anchor)] == anchor for k in range(len(expected)-len(anchor)+1)) != 1:
                reason = 'repeated_script_context_is_ambiguous'
            else:
                left, right = times[a-1][1], times[b][0]
                first, last = times[a][0], times[b-1][1]
                # Remove the whole inter-anchor interval: a recognizer may
                # timestamp only the middle of an invented syllable. Preserve
                # at least 40ms beside actual script words; never force a fit.
                start, end = left + margin_seconds, right - margin_seconds
                left_silences = [(p+q)/2 for p, q in silence_intervals if left+margin_seconds <= (p+q)/2 <= first]
                right_silences = [(p+q)/2 for p, q in silence_intervals if last <= (p+q)/2 <= right-margin_seconds]
                acoustic_boundaries = bool(left_silences and right_silences)
                if acoustic_boundaries:
                    start, end = min(left_silences), max(right_silences)
                if (not left < start <= first < last <= end < right
                        or any(times[k][1] > times[k+1][0] for k in range(a-1, b))):
                    reason = 'no_separation_from_script_word_timestamps'
                else:
                    begin, finish = math.ceil(start*sample_rate), math.floor(end*sample_rate)
                    if finish - begin < round(.025*sample_rate):
                        reason = 'insertion_too_short_to_cut'
                    elif any(begin/sample_rate < q and finish/sample_rate > p for p, q in protected):
                        reason = 'cut_intersects_protected_provider_word'
                    else:
                        cuts.append({**row, 'start_sample': begin, 'end_sample': finish,
                                     'boundary_method': 'measured_silence_midpoints' if acoustic_boundaries else 'asr_anchor_interval_guards',
                                     'left_anchor': heard[a-min_anchor_words:a],
                                     'right_anchor': heard[b:b+min_anchor_words]})
        if reason:
            unresolved.append({**row, 'reason': reason})
    result = {'version': VERSION, 'source_audio_sha256': audio_sha,
              'script_text_sha256': digest(script), 'asr_sha256': digest(asr),
              'asr_identity': identity, 'source_duration': duration, 'sample_rate': sample_rate,
              'policy': {'min_anchor_words': min_anchor_words, 'margin_seconds': margin_seconds},
              'cuts': cuts, 'unresolved': unresolved, 'matched_script_words': matched,
              'protected_word_intervals': protected, 'measured_silences': silence_intervals, 'requires_second_pass': True,
              'status': 'cuts_available' if cuts else 'no_safe_cuts',
              'acoustic_sync_verified': False, 'automatic_acceptance': False}
    if windows:
        _refine_windows(expected, result, windows)
    result['plan_sha256'] = digest(result)
    return result



def _refine_windows(expected: list[str], plan: dict, windows: list[dict]):
    """Refine only a blocked INSERT using unique exact independent clip anchors."""
    evidence, updated = [], {w['script_word_index']: w for w in plan['matched_script_words']}
    seen = set()
    for window in windows:
        if (not isinstance(window, dict) or window.get('source_audio_sha256') != plan['source_audio_sha256']
                or window.get('source_asr_sha256') != plan['asr_sha256']
                or window.get('engine') != plan['asr_identity']['engine']
                or window.get('model_files') != plan['asr_identity']['model_files']):
            raise ValueError('ASR refinement does not match the original audio, transcript and model')
        path = Path(window.get('window_audio_path', '')).absolute()
        _safe_path(path)
        offset, duration, result = window.get('offset'), window.get('duration'), window.get('result')
        if (not path.is_file() or _hash(path) != window.get('window_audio_sha256')
                or not _number(offset) or not _number(duration)
                or not 0 <= offset < offset+duration <= plan['source_duration']+.001
                or not isinstance(result, dict) or not _number(result.get('duration'))
                or abs(result['duration']-duration) > .1 or not isinstance(result.get('segments'), list)):
            raise ValueError('Invalid or changed independent ASR refinement audio')
        ranges = window.get('script_range')
        if (not isinstance(ranges, list) or len(ranges) != 2
                or any(type(v) is not int for v in ranges)
                or not 0 <= ranges[0] == ranges[1] <= len(expected) or tuple(ranges) in seen):
            raise ValueError('Ambiguous or duplicate ASR refinement insertion')
        seen.add(tuple(ranges))
        matches = [r for r in [*plan['unresolved'], *plan['cuts']] if r['kind'] == 'insert' and r['script_range'] == ranges]
        if len(matches) != 1:
            raise ValueError('ASR refinement must identify one blocked raw insertion')
        row = matches[0]
        heard, times, previous = [], [], 0.
        for segment in result['segments']:
            if not isinstance(segment, dict):
                raise ValueError('Invalid independent ASR refinement word times')
            a, b = segment.get('start'), segment.get('end')
            if (not _number(a) or not _number(b) or not previous <= a <= b <= duration+.001
                    or not isinstance(segment.get('text'), str)):
                raise ValueError('Invalid independent ASR refinement word times')
            previous = a
            for token in tokens(segment['text']):
                heard.append(token)
                times.append((offset+a, offset+b))
        if not isinstance(result.get('text'), str) or heard != tokens(result['text']):
            raise ValueError('ASR refinement text does not match timestamp words')
        i = ranges[0]
        accepted = False
        for n in range(plan['policy']['min_anchor_words'], 9):
            if i < n or i+n > len(expected):
                break
            left, right = expected[i-n:i], expected[i:i+n]
            context = left+right
            if sum(expected[k:k+len(context)] == context for k in range(len(expected)-len(context)+1)) != 1:
                continue
            def positions(part):
                return [k for k in range(len(heard)-len(part)+1) if heard[k:k+len(part)] == part]
            ls, rs = positions(left), positions(right)
            if len(ls) != 1 or len(rs) != 1 or ls[0]+n >= rs[0]:
                continue
            a, b = ls[0]+n, rs[0]
            left_end, first, last, right_start = times[a-1][1], times[a][0], times[b-1][1], times[b][0]
            guard = plan['policy']['margin_seconds']
            start, end = left_end+guard, right_start-guard
            silence_left = [(p+q)/2 for p, q in plan['measured_silences'] if left_end+guard <= (p+q)/2 <= first]
            silence_right = [(p+q)/2 for p, q in plan['measured_silences'] if last <= (p+q)/2 <= right_start-guard]
            if silence_left and silence_right:
                start, end = min(silence_left), max(silence_right)
            begin, finish = math.ceil(start*plan['sample_rate']), math.floor(end*plan['sample_rate'])
            if (not left_end < start <= first < last <= end < right_start
                    or any(times[k][1] > times[k+1][0] for k in range(a-1, b))
                    or finish-begin < round(.025*plan['sample_rate'])
                    or any(start < q and end > p for p, q in plan['protected_word_intervals'])):
                continue
            replacement = dict(updated)
            for offset_index, index in enumerate(list(range(i-n, i))+list(range(i, i+n))):
                token_index = ls[0]+offset_index if offset_index < n else b+offset_index-n
                replacement[index] = {'script_word_index': index, 'word': expected[index],
                                      'start': times[token_index][0], 'end': times[token_index][1],
                                      'timing_source': 'independent_asr_window'}
            if any(start < w['end'] and end > w['start'] for w in replacement.values()):
                continue
            if any(c is not row and begin < c['end_sample'] and finish > c['start_sample'] for c in plan['cuts']):
                continue
            if row in plan['cuts']:
                plan['cuts'].remove(row)
            plan['cuts'].append({**row, 'recognized': ' '.join(heard[a:b]),
                                 'start_sample': begin, 'end_sample': finish,
                                 'left_anchor': left, 'right_anchor': right,
                                 'boundary_method': 'independent_asr_window_and_silence' if silence_left and silence_right else 'independent_asr_window',
                                 'window_audio_sha256': window['window_audio_sha256']})
            updated = replacement
            if row in plan['unresolved']:
                plan['unresolved'].remove(row)
            accepted = True
            break
        evidence.append({**window, 'refinement_accepted': accepted})
    plan['window_evidence'] = evidence
    plan['matched_script_words'] = [updated[k] for k in sorted(updated)]
    plan['cuts'].sort(key=lambda c: c['start_sample'])
    plan['status'] = 'cuts_available' if plan['cuts'] else 'no_safe_cuts'


def _safe_path(path: Path):
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError('Automatic audio cut paths cannot contain symlinks')


@contextmanager
def _output_lock(path: Path):
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Automatic audio cut output is already being prepared') from None
        yield
    finally:
        os.close(fd)


def _validate_plan(plan: dict):
    payload = {k: v for k, v in plan.items() if k != 'plan_sha256'}
    if plan.get('version') != VERSION or plan.get('plan_sha256') != digest(payload):
        raise ValueError('Automatic cut plan changed; preserve it for review')
    rate, previous = plan['sample_rate'], 0
    if type(rate) is not int or not 8000 <= rate <= 96000 or not plan.get('cuts'):
        raise ValueError('Automatic cut plan has no validated intervals')
    for cut in plan['cuts']:
        begin, end = cut['start_sample'], cut['end_sample']
        if (type(begin) is not int or type(end) is not int
                or not previous <= begin < end <= math.floor(plan['source_duration']*rate)
                or any(begin/rate < q and end/rate > p for p, q in plan['protected_word_intervals'])
                or any(begin/rate < w['end'] and end/rate > w['start'] for w in plan['matched_script_words'])):
            raise ValueError('Automatic cut intersects a script word or has invalid bounds')
        previous = end


def apply_autocuts(audio: Path, destination: Path, plan: dict, *, ffmpeg: str = 'ffmpeg') -> dict:
    """Write PCM + evidence to a new directory, never adopt it as clean narration.

    Repeating an identical completed operation reuses it; partial/changed outputs
    are preserved and blocked. Caller must re-recognize `audio_path` independently.
    """
    audio, destination = Path(audio).absolute(), Path(destination).absolute()
    _safe_path(audio)
    _safe_path(destination)
    _validate_plan(plan)
    if not audio.is_file() or _hash(audio) != plan['source_audio_sha256']:
        raise ValueError('Raw audio differs from the ASR-bound cut plan')
    destination.parent.mkdir(parents=True, exist_ok=True)
    receipt_path = destination / 'receipt.json'
    with _output_lock(destination.parent / ('.' + destination.name + '.lock')):
        if destination.exists():
            if not receipt_path.is_file() or receipt_path.is_symlink():
                raise ValueError('Incomplete automatic audio edit preserved; choose another destination')
            receipt = json.loads(receipt_path.read_text())
            result = destination / 'audio.wav'
            _safe_path(result)
            _safe_path(destination/'plan.json')
            if (receipt.get('version') != VERSION or receipt.get('status') != 'edited_requires_second_pass'
                    or receipt.get('requires_second_pass') is not True
                    or receipt.get('source_audio_sha256') != plan['source_audio_sha256']
                    or receipt.get('sample_rate') != plan['sample_rate']
                    or receipt.get('audio_path') != str(result)
                    or receipt.get('removed_samples') != [[c['start_sample'], c['end_sample']] for c in plan['cuts']]
                    or receipt.get('unresolved_count') != len(plan['unresolved'])
                    or receipt.get('plan_sha256') != plan['plan_sha256'] or not result.is_file()
                    or receipt.get('output_audio_sha256') != _hash(result)
                    or not (destination/'plan.json').is_file()
                    or json.loads((destination/'plan.json').read_text()) != plan):
                raise ValueError('Existing automatic audio edit differs; preserve it for review')
            with wave.open(str(result)) as stream:
                frames, rate = stream.getnframes(), stream.getframerate()
            if (receipt.get('output_frames') != frames or rate != plan['sample_rate']
                    or receipt.get('source_frames') != frames+sum(c['end_sample']-c['start_sample'] for c in plan['cuts'])):
                raise ValueError('Existing automatic audio edit sample clock changed')
            return receipt
        work = Path(tempfile.mkdtemp(prefix='.autocut-', dir=destination.parent))
        try:
            rate = plan['sample_rate']
            # Canonical PCM first makes every cut and final frame count exact,
            # independent of MP3 duration metadata or AAC padding.
            pcm = work / 'decoded.wav'
            subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-n', '-i', str(audio),
                            '-vn', '-map_metadata', '-1', '-ar', str(rate), '-c:a', 'pcm_s16le', str(pcm)],
                           check=True, capture_output=True, timeout=180)
            with wave.open(str(pcm)) as stream:
                total, channels = stream.getnframes(), stream.getnchannels()
            if abs(total/rate-plan['source_duration']) > 1:
                raise ValueError('ASR duration does not cover the decoded raw audio')
            intervals, previous = [], 0
            for cut in plan['cuts']:
                begin, end = cut['start_sample'], cut['end_sample']
                if end > total:
                    raise ValueError('Cut exceeds the actual decoded sample clock')
                if begin > previous:
                    intervals.append((previous, begin))
                previous = end
            if total > previous:
                intervals.append((previous, total))
            labels = ''.join(f'[in{i}]' for i in range(len(intervals)))
            graph = [f'[0:a]asplit={len(intervals)}' + labels]
            for index, (begin, end) in enumerate(intervals):
                trim = f'atrim=start_sample={begin}:end_sample={end},asetpts=PTS-STARTPTS'
                fade = min(.005, (end-begin)/rate/2)
                if index:
                    trim += f',afade=t=in:d={fade:.9f}'
                if index + 1 < len(intervals):
                    trim += f',afade=t=out:st={(end-begin)/rate-fade:.9f}:d={fade:.9f}'
                graph.append(f'[in{index}]{trim}[a{index}]')
            graph.append(''.join(f'[a{i}]' for i in range(len(intervals)))+
                         f'concat=n={len(intervals)}:v=0:a=1[out]')
            output = work / 'audio.wav'
            subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-n', '-i', str(pcm),
                            '-filter_complex', ';'.join(graph), '-map', '[out]',
                            '-ar', str(rate), '-c:a', 'pcm_s16le', str(output)],
                           check=True, capture_output=True, timeout=180)
            with wave.open(str(output)) as stream:
                expected = total - sum(c['end_sample']-c['start_sample'] for c in plan['cuts'])
                if stream.getnframes() != expected or stream.getframerate() != rate or stream.getnchannels() != channels:
                    raise ValueError('Edited PCM does not match the exact recorded sample cuts')
            if _hash(audio) != plan['source_audio_sha256']:
                raise ValueError('Raw audio changed during correction; no result was promoted')
            receipt = {'version': VERSION, 'status': 'edited_requires_second_pass',
                       'plan_sha256': plan['plan_sha256'], 'source_audio_sha256': plan['source_audio_sha256'],
                       'output_audio_sha256': _hash(output), 'audio_path': str(destination/'audio.wav'),
                       'sample_rate': rate, 'source_frames': total, 'output_frames': expected,
                       'removed_samples': [[c['start_sample'], c['end_sample']] for c in plan['cuts']],
                       'maximum_seam_fade_seconds': .005, 'requires_second_pass': True,
                       'unresolved_count': len(plan['unresolved']), 'acoustic_sync_verified': False}
            pcm.unlink()
            write(work / 'plan.json', plan)
            write(work / 'receipt.json', receipt)
            if destination.exists() or destination.is_symlink():
                raise FileExistsError('Automatic audio edit destination appeared; preserved')
            work.rename(destination)
            return receipt
        finally:
            if work.exists():
                shutil.rmtree(work)
