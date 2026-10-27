"""Independent ASR review before mixing; never delete or synthesize speech.

Provider TTS alignment proves text/timing consistency, not what was spoken.
This check sends only audio to ASR and compares its independently decoded words.
Differences require review: ASR itself can omit or hallucinate words.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import json
import math
import os
from pathlib import Path
import re
import subprocess
import unicodedata

from ..editing.manifest import clean_script
from .files import digest, local_file, replace_state, write


VERSION = 2

# No script/prompt is passed to the recognizer. All model files must already be
# local; this worker neither downloads weights nor uploads audio.
_LOCAL_RUNNER = r'''
import json,sys,socket
def offline(*args,**kwargs):
 raise RuntimeError('Network disabled in local ASR worker')
socket.socket.connect=offline
socket.create_connection=offline
from faster_whisper import WhisperModel
m=WhisperModel(sys.argv[1],device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
segments,info=m.transcribe(sys.argv[2],language='es',beam_size=5,word_timestamps=True,
                         condition_on_previous_text=False,vad_filter=False)
text=[]; words=[]
for segment in segments:
 text.append(segment.text)
 words.extend({'text':w.word.strip(),'start':w.start,'end':w.end} for w in segment.words or [])
print(json.dumps({'text':' '.join(text),'duration':info.duration,'segments':words},ensure_ascii=False))
'''


def tokens(text: str) -> list[str]:
    text = unicodedata.normalize('NFKD', clean_script(text).casefold())
    return re.findall(r'\w+', ''.join(c for c in text if not unicodedata.combining(c)))


def compare_transcript(script: str, result: dict) -> dict:
    """Locate differences without interpreting a recognizer's error as a cut."""
    if not isinstance(result, dict) or not isinstance(result.get('text'), str):
        raise ValueError('ASR returned no transcript; preserve response for review')
    duration = result.get('duration')
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('ASR returned no finite positive duration')
    segments = result.get('segments')
    if not isinstance(segments, list):
        raise ValueError('ASR returned no timestamp segments')
    recognized, timed, previous = [], [], 0.0
    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(segment.get('text'), str):
            raise ValueError('ASR returned an invalid timestamp segment')
        start, end = segment.get('start'), segment.get('end')
        if (isinstance(start, bool) or isinstance(end, bool)
                or not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                or not math.isfinite(start + end) or not 0 <= start <= end <= duration + .25
                or start < previous):
            raise ValueError('ASR timestamps are invalid or unordered')
        previous = start
        words = tokens(segment['text'])
        recognized.extend(words)
        timed.extend([(start, end)] * len(words))
    expected = tokens(script)
    # Use the full decoded text for fidelity: timestamp segments may be missing or
    # normalized differently. Match their tokens only to attach diagnostic times.
    heard = tokens(result['text'])
    if not expected or not heard:
        raise ValueError('Script or independently recognized speech is empty')
    timing_exact = recognized == heard
    differences = []
    for kind, i, j, a, b in SequenceMatcher(None, expected, heard, autojunk=False).get_opcodes():
        if kind == 'equal':
            continue
        row = {'kind': kind, 'script_range': [i, j], 'asr_range': [a, b],
               'expected': ' '.join(expected[i:j]), 'recognized': ' '.join(heard[a:b])}
        if timing_exact and a < b:
            row.update(start=timed[a][0], end=timed[b - 1][1])
        differences.append(row)
    return {'version': VERSION, 'status': 'review_required' if differences else 'matched',
            'expected_words': len(expected), 'recognized_words': len(heard),
            'timestamp_text_matches': timing_exact, 'differences': differences,
            'asr_is_fallible': True, 'automatic_cuts': False,
            'acoustic_sync_verified': False}


def uncovered_activity(audio: Path, alignment: Path, *, ffmpeg: str,
                       duration: float | None = None) -> list[dict]:
    """Find audible regions outside word marks; energy does not prove speech."""
    if not alignment.exists():
        return []
    data = json.loads(alignment.read_text())
    if not isinstance(data, dict) or data.get('method') not in {'fish_provider_timestamps', 'fish_provider_timestamps_after_audio_cuts'}:
        raise ValueError('Cannot audit activity against unrecognized word alignment')
    words = data.get('words')
    if not isinstance(words, list) or not words:
        raise ValueError('Cannot audit activity without word marks')
    process = subprocess.run([ffmpeg, '-hide_banner', '-nostdin', '-i', str(audio),
        '-af', 'silencedetect=noise=-40dB:d=0.15', '-f', 'null', '-'],
        capture_output=True, text=True, timeout=300, check=True)
    # Retain active intervals between measured silences, not an invented ASR.
    silence = re.findall(r'silence_(start|end): ([0-9.]+)', process.stderr)
    active, cursor = [], 0.0
    for kind, value in silence:
        point = float(value)
        if kind == 'start':
            if cursor is not None and point >= cursor:
                active.append((cursor, point))
            cursor = None
        elif kind == 'end':
            cursor = point
    if cursor is not None:
        active.append((cursor, float('inf')))
    if duration is None:
        from ..media.ffprobe import probe_media
        duration = probe_media(audio).duration
    gaps, previous = [], 0.0

    def inspect_gap(left, right):
        if right - left >= .75:
            seconds = sum(max(0., min(right, b) - max(left, a)) for a, b in active)
            if seconds >= .5:
                gaps.append({'start': left, 'end': right, 'active_seconds': round(seconds, 3),
                             'meaning': 'audible_energy_outside_word_marks_not_proof_of_speech'})

    for word in words:
        try:
            if not isinstance(word, dict) or isinstance(word.get('start'), bool) or isinstance(word.get('end'), bool):
                raise ValueError
            start, end = float(word['start']), float(word['end'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('Cannot audit invalid word marks') from None
        if not math.isfinite(start + end) or not 0 <= previous <= start <= end <= duration + .001:
            raise ValueError('Cannot audit invalid word marks')
        # Keep 120ms at either real-word boundary; never propose a cut here.
        left, right = previous + .12, start - .12
        inspect_gap(left, right)
        previous = end
    inspect_gap(previous + .12, duration)
    return gaps


def verify_voice(episode: Path, *, settings, transcribe: bool = False,
                 local_python: Path | None = None, local_model: Path | None = None,
                 imported_result: Path | None = None, audio_filename: str = 'voz.mp3') -> dict:
    """Run local CPU/int8 ASR or import a hash-bound local result, with cache.

    Caller holds the episode lock. Configuration is explicit; no provider, GPU,
    package installation, model download or synthesis is performed here.
    """
    audio = local_file(episode, audio_filename)
    script_path = local_file(episode, 'guion_final.txt')
    python_value = local_python or settings.local_asr_python
    model_value = local_model or settings.local_asr_model
    if not python_value or not model_value:
        raise ValueError('Local ASR needs LOCAL_ASR_PYTHON and LOCAL_ASR_MODEL (existing runtime and model); no automatic install')
    python, model = Path(python_value).absolute(), Path(model_value).absolute()
    if not python.is_file() or not (model / 'model.bin').is_file():
        raise ValueError('Local ASR runtime/model are unavailable; no download or external request was made')
    identity = {'version': VERSION, 'engine': 'faster-whisper-cpu-int8',
                'model_files': {name: digest(model / name) for name in
                    ['model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt', 'preprocessor_config.json'] if (model / name).is_file()},
                'runner_sha256': digest(_LOCAL_RUNNER), 'runtime': str(python),
                'audio_sha256': digest(audio),
                'script_sha256': digest(script_path)}
    key = digest(identity)
    folder = local_file(episode, f'.stickman/voice-fidelity/{key}', exists=False)
    folder.mkdir(parents=True, exist_ok=True)
    raw = local_file(episode, f'.stickman/voice-fidelity/{key}/asr.json', exists=False)
    operation = local_file(episode, str(folder.relative_to(episode) / 'operation.json'), exists=False)
    report_path = local_file(episode, str(folder.relative_to(episode) / 'report.json'), exists=False)
    if not raw.exists():
        if imported_result:
            result = json.loads(imported_result.read_text())
            if result.get('audio_sha256') != identity['audio_sha256']:
                raise ValueError('Imported local ASR must identify the exact audio SHA256')
            if (result.get('model_files') != identity['model_files']
                    or result.get('engine') != identity['engine']):
                raise ValueError('Imported local ASR must declare the matching engine and exact model file hashes')
        else:
            if not transcribe:
                raise ValueError('Independent ASR missing; run verify_stickman_voice.py --transcribe locally')
            replace_state(operation, {**identity, 'status': 'running'})
            try:
                process = subprocess.run([str(python), '-c', _LOCAL_RUNNER, str(model), str(audio)],
                    capture_output=True, text=True, timeout=1800, check=True,
                    env={**os.environ, 'HF_HUB_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1'})
                result = json.loads(process.stdout)
            except (subprocess.SubprocessError, json.JSONDecodeError):
                replace_state(operation, {**identity, 'status': 'failed'})
                raise ValueError('Local ASR failed; inputs preserved, no audio was uploaded') from None
        write(raw, result)
        replace_state(operation, {**identity, 'status': 'succeeded', 'response_sha256': digest(raw),
                                 'source': 'imported_local_asr_declaration' if imported_result else 'local_asr_worker'})
    result = json.loads(raw.read_text())
    record = json.loads(operation.read_text()) if operation.exists() else {}
    if (any(record.get(k) != v for k, v in identity.items())
            or record.get('status') != 'succeeded'
            or record.get('response_sha256') != digest(raw)):
        raise ValueError('Independent ASR evidence changed; preserve and review')
    if digest(audio) != identity['audio_sha256'] or digest(script_path) != identity['script_sha256']:
        raise ValueError('Voice or script changed during ASR verification')
    from ..media.ffprobe import probe_media
    duration = probe_media(audio, settings.ffprobe_binary).duration
    report = compare_transcript(script_path.read_text(encoding='utf-8-sig'), result)
    if abs(result['duration'] - duration) > 1:
        raise ValueError('ASR duration does not cover the narration; review the preserved response')
    alignment = local_file(episode, 'voz.alignment.json', exists=False)
    activity = uncovered_activity(audio, alignment, ffmpeg=settings.ffmpeg_binary, duration=duration)
    if activity:
        report['status'] = 'review_required'
    report.update(identity=identity, response_sha256=digest(raw),
                  report_path=str(report_path), source=record['source'],
                  uncovered_activity=activity,
                  alignment_sha256=digest(alignment) if alignment.exists() else None)
    write(report_path, report)
    return report


def require_reviewed(report: dict, episode: Path) -> None:
    if report['status'] == 'matched':
        return
    report_path = Path(report['report_path'])
    review = local_file(episode, str(report_path.parent.relative_to(episode) / 'review.json'), exists=False)
    if review.exists():
        decision = json.loads(review.read_text())
        if (decision.get('report_sha256') == digest(report_path)
                and decision.get('decision') == 'accept_asr_differences'
                and isinstance(decision.get('reviewer'), str) and decision['reviewer'].strip()
                and isinstance(decision.get('reason'), str) and decision['reason'].strip()):
            return
    raise ValueError(f'Voice fidelity needs review: {len(report["differences"])} ASR differences and {len(report.get("uncovered_activity", []))} audible gaps; review {report_path}. No cuts or new synthesis were performed')
