"""Raw-voice preprocessing: cut insertions, recognize again, then allow planning.

Source voice and paid receipts are immutable. A partial correction is a diagnostic
artifact, never the narration consumed by the renderer.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import subprocess
import wave

from ..editing.manifest import clean_script
from ..media.ffprobe import probe_media
from .audio_autoclean import apply_autocuts, plan_autocuts
from .files import digest, local_file, write
from .voice_fidelity import activity_outside_words, tokens, verify_voice


MODE = 'local_asr_autocut'

_WINDOW_RUNNER = r'''
import json,sys,socket
def offline(*a,**kw): raise RuntimeError('Network disabled in local ASR worker')
socket.socket.connect=offline
socket.create_connection=offline
from faster_whisper import WhisperModel
model=WhisperModel(sys.argv[1],device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
results=[]
for path in json.loads(sys.argv[2]):
 segments,info=model.transcribe(path,language='es',beam_size=5,word_timestamps=True,
                               condition_on_previous_text=False,vad_filter=False)
 text=[];words=[]
 for segment in segments:
  text.append(segment.text)
  words.extend({'text':w.word.strip(),'start':w.start,'end':w.end} for w in segment.words or [])
 results.append({'text':' '.join(text),'duration':info.duration,'segments':words})
print(json.dumps(results,ensure_ascii=False))
'''


def _window_evidence(episode: Path, source: Path, script: str, asr: dict,
                     plan: dict, settings) -> list[dict]:
    """Refine only unresolved insertion clocks, in one offline model process."""
    pending = [row for row in plan['unresolved'] if row['kind'] == 'insert']
    if not pending:
        return []
    key = digest({'source': digest(source), 'asr': digest(asr), 'runner': digest(_WINDOW_RUNNER)})
    folder = local_file(episode, '.stickman/voice-cleaning/windows/' + key, exists=False)
    folder.mkdir(parents=True, exist_ok=True)
    record = folder / 'evidence.json'
    if record.exists():
        rows = json.loads(record.read_text())
        if any(digest(local_file(episode, str(Path(row['window_audio_path']).relative_to(episode)))) != row['window_audio_sha256'] for row in rows):
            raise ValueError('Local refinement audio changed; correction blocked')
        return rows
    pcm = folder / 'source.wav'
    if not pcm.exists():
        subprocess.run([settings.ffmpeg_binary, '-nostdin', '-v', 'error', '-n', '-i', str(source),
            '-ar', '48000', '-c:a', 'pcm_s16le', str(pcm)], capture_output=True, check=True, timeout=180)
    rows = []
    segments = asr['segments']
    # The full recognizer returns individual words; never use token indices to
    # address multi-word segments or manufacture a missing intra-segment clock.
    if any(len(tokens(segment['text'])) != 1 for segment in segments):
        return []
    with wave.open(str(pcm)) as inp:
        rate = inp.getframerate()
        for index, row in enumerate(pending):
            a, b = row['asr_range']
            start = max(0, round((segments[max(0, a-4)]['start']-.25)*rate))
            end = min(inp.getnframes(), round((segments[min(len(segments)-1,b+3)]['end']+.25)*rate))
            clip = folder / f'window-{index:03d}.wav'
            if clip.exists():
                raise ValueError('Incomplete refinement preserved; inspect it before retrying')
            inp.setpos(start)
            with wave.open(str(clip), 'wb') as out:
                out.setparams(inp.getparams())
                out.writeframes(inp.readframes(end-start))
            identity = asr.get('identity', asr)
            rows.append({'source_audio_sha256': digest(source), 'source_asr_sha256': digest(asr),
                'script_range': row['script_range'], 'window_audio_path': str(clip),
                'window_audio_sha256': digest(clip), 'offset': start/rate, 'duration': (end-start)/rate,
                'engine': identity['engine'], 'model_files': identity['model_files']})
    completed = subprocess.run([str(settings.local_asr_python), '-c', _WINDOW_RUNNER,
        str(settings.local_asr_model), json.dumps([row['window_audio_path'] for row in rows])],
        capture_output=True, text=True, check=True, timeout=1800,
        env={**os.environ, 'HF_HUB_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1'})
    results = json.loads(completed.stdout)
    if not isinstance(results, list) or len(results) != len(rows):
        raise ValueError('Incomplete local refinement recognition; originals preserved')
    for row, result in zip(rows, results):
        row['result'] = result
    if digest(source) != plan['source_audio_sha256']:
        raise ValueError('Raw audio changed during local refinement')
    write(record, rows)
    pcm.unlink()
    return rows


def _silences(audio: Path, settings, duration: float) -> list[tuple[float, float]]:
    result = subprocess.run([settings.ffmpeg_binary, '-nostdin', '-hide_banner', '-i', str(audio),
        '-af', 'silencedetect=noise=-35dB:d=0.015', '-f', 'null', '-'],
        capture_output=True, text=True, check=True, timeout=300)
    intervals, start = [], None
    for kind, value in re.findall(r'silence_(start|end): ([0-9.]+)', result.stderr):
        point = min(duration, float(value))
        if kind == 'start':
            start = point
        elif start is not None:
            if point > start:
                intervals.append((start, point))
            start = None
    if start is not None and start < duration:
        intervals.append((start, duration))
    return intervals


def _word_clock(script: str, asr: dict, duration: float) -> list[dict]:
    """Use observed individual ASR times, never interpolate or copy false TTS marks."""
    text = clean_script(script)
    expected = list(re.finditer(r'\w+', text))
    actual = asr['segments']
    if len(expected) != len(actual):
        raise ValueError('Corrected ASR must contain one observed timestamp per script word')
    words, previous = [], 0.
    for match, segment in zip(expected, actual):
        start, end = float(segment['start']), float(segment['end'])
        if (tokens(match.group()) != tokens(segment['text']) or len(tokens(segment['text'])) != 1
                or not math.isfinite(start + end) or not previous <= start < end <= duration + .001):
            raise ValueError('Corrected voice needs exact, positive, nonoverlapping recognized words')
        words.append({'word': match.group(), 'start': start, 'end': end})
        previous = end
    return words


def _activity_cuts(episode: Path, script: str, asr: dict, before: dict, plan: dict) -> dict:
    """Remove only energy in uniquely anchored gaps in two observed word clocks.

    Energy is not interpreted as speech or given invented transcript tokens.
    All reported gaps must qualify: the second ASR cannot detect omitted energy.
    """
    activity = before.get('uncovered_activity', [])
    if (not activity or before.get('differences') != [] or plan['cuts'] or plan['unresolved']
            or tokens(asr['text']) != tokens(script)):
        return plan
    from .audio import _provider_segments
    try:
        words = _word_clock(script, asr, asr['duration'])
        alignment = local_file(episode, 'voz.alignment.json')
        if digest(alignment) != before.get('alignment_sha256'):
            return plan
        provider = _provider_segments(alignment, script, asr['duration'])
    except (ValueError, KeyError, TypeError, OSError):
        return plan
    expected, cuts = tokens(script), []
    margin, rate = plan['policy']['margin_seconds'], plan['sample_rate']
    for evidence in activity:
        a, b, active = (evidence.get(k) for k in ('start', 'end', 'active_seconds'))
        if (any(type(v) not in (int, float) or not math.isfinite(v) for v in (a, b, active))
                or not 0 <= a < b <= asr['duration'] or not .5 <= active <= b-a+.001):
            return plan
        candidates = []
        for i in range(2, len(words)-1):
            left, right = expected[i-2:i], expected[i:i+2]
            if any(sum(expected[k:k+2] == anchor for k in range(len(expected)-1)) != 1
                   for anchor in (left, right)):
                continue
            start, end = max(a, words[i-1]['end']+margin), min(b, words[i]['start']-margin)
            # Aggregate measured energy gives a conservative lower bound within
            # the intersection, even if all excluded time was audible.
            if end-start < .025 or active - ((b-a)-(end-start)) < .5:
                continue
            boundaries = []
            for point in (start, end):
                midpoints = [(p+q)/2 for p, q in plan['measured_silences']
                             if p <= point <= q and start <= (p+q)/2 <= end]
                boundaries.append(midpoints[0] if len(midpoints) == 1 else point)
            if (boundaries[1]-boundaries[0] >= .025
                    and active - ((b-a)-(boundaries[1]-boundaries[0])) >= .5):
                start, end = boundaries
            begin, finish = math.ceil(start*rate), math.floor(end*rate)
            if (finish-begin < round(.025*rate)
                    or active - ((b-a)-(finish-begin)/rate) < .5
                    or any(begin/rate < w['end']+margin and finish/rate > w['start']-margin
                           for w in provider)):
                continue
            candidates.append({'kind': 'untranscribed_activity', 'script_range': [i, i],
                'asr_range': [i, i], 'expected': '', 'recognized': '',
                'start_sample': begin, 'end_sample': finish,
                'left_anchor': left, 'right_anchor': right, 'activity_evidence': evidence,
                'minimum_active_seconds': active - ((b-a)-(finish-begin)/rate),
                'boundary_method': 'observed_asr_gap_provider_guards_and_measured_energy'})
        if len(candidates) != 1:
            return plan
        cuts.extend(candidates)
    cuts.sort(key=lambda row: row['start_sample'])
    if any(a['end_sample'] > b['start_sample'] for a, b in zip(cuts, cuts[1:])):
        return plan
    result = {**plan, 'cuts': cuts, 'status': 'cuts_available',
              'protected_word_intervals': [[w['start'], w['end']] for w in provider],
              'provider_alignment_sha256': digest(alignment), 'activity_report_sha256': digest(before)}
    result['plan_sha256'] = digest({k: v for k, v in result.items() if k != 'plan_sha256'})
    return result


def _cues(script: str, words: list[dict]) -> list[dict]:
    text = clean_script(script)
    spans = list(re.finditer(r'\w+', text))
    cues = []
    for start in range(0, len(words), 6):
        end = min(start + 6, len(words))
        first = 0 if start == 0 else spans[start].start()
        last = spans[end].start() if end < len(spans) else len(text)
        cues.append({'index': len(cues)+1, 'start': words[start]['start'],
                     'end': words[end-1]['end'], 'text': ' '.join(text[first:last].split())})
    return cues


def cleaned_paths(episode: Path, mode: str | None) -> tuple[Path, Path, Path]:
    """Resolve only a fully checked correction; used by plan/reuse/QA/captions."""
    original = (local_file(episode, 'voz.mp3'), local_file(episode, 'voz.srt'),
                local_file(episode, 'voz.alignment.json', exists=False))
    if mode != MODE:
        return original
    active = local_file(episode, '.stickman/voice-cleaning/active.json', exists=False)
    if not active.exists():
        return original
    data = json.loads(active.read_text())
    if (data.get('status') != 'ready' or data.get('raw_audio_sha256') != digest(original[0])
            or data.get('script_sha256') != digest(local_file(episode, 'guion_final.txt'))):
        raise ValueError('Raw voice/script changed after automatic correction; use another episode revision')
    paths = []
    if set(data.get('files', {})) != {'audio', 'srt', 'alignment', 'validation', 'asr', 'narration', 'plan', 'edit'}:
        raise ValueError('Incomplete corrected voice manifest; rendering blocked')
    for key in ('audio', 'srt', 'alignment', 'validation', 'asr', 'narration', 'plan', 'edit'):
        record = data['files'][key]
        path = local_file(episode, record['path'])
        if digest(path) != record['sha256']:
            raise ValueError('Corrected voice evidence changed; rendering blocked')
        if key in {'audio', 'srt', 'alignment'}:
            paths.append(path)
    validation = json.loads(local_file(episode, data['files']['validation']['path']).read_text())
    if validation.get('status') != 'matched' or validation['identity']['audio_sha256'] != data['files']['audio']['sha256']:
        raise ValueError('Corrected voice lacks matching independent recognition')
    return tuple(paths)


def clean_narration(episode: Path, *, settings, raw: dict, require_ready: bool = True,
                    on_stage=None) -> dict:
    """Caller holds episode lock. No speech provider or renderer is called."""
    emit = on_stage or (lambda message: None)
    script_path = local_file(episode, 'guion_final.txt')
    script = script_path.read_text(encoding='utf-8-sig')
    source = local_file(episode, 'voz.mp3')
    if digest(source) != raw['audio_sha256'] or digest(script_path) != raw['script_sha256']:
        raise ValueError('Raw narration changed before preprocessing')
    active = local_file(episode, '.stickman/voice-cleaning/active.json', exists=False)
    if active.exists():
        audio, srt, alignment = cleaned_paths(episode, MODE)
        manifest = json.loads(active.read_text())
        result = json.loads(local_file(episode, manifest['files']['narration']['path']).read_text())
        if (result.get('audio_path') != str(audio) or result.get('audio_sha256') != digest(audio)
                or result.get('srt_path') != str(srt) or result.get('srt_sha256') != digest(srt)
                or result.get('alignment_path') != str(alignment)):
            raise ValueError('Pinned corrected narration differs from its manifest')
        emit('Voz corregida existente: conservando copia y reloj verificados; sin volver a la voz cruda')
        return result
    emit('Voz cruda: reconociendo contenido antes de imágenes o montaje')
    before = verify_voice(episode, settings=settings, transcribe=True)
    asr_path = Path(before['report_path']).parent / 'asr.json'
    asr = json.loads(asr_path.read_text())
    asr['identity'] = before['identity']
    silences = _silences(source, settings, asr['duration'])
    plan = plan_autocuts(script, asr, source_audio_sha256=raw['audio_sha256'], silences=silences)
    if any(row['kind'] == 'insert' for row in plan['unresolved']):
        emit('Voz cruda: afinando ventanas ambiguas con ASR local, sin enviar el guion al reconocedor')
        windows = _window_evidence(episode, source, script, asr, plan, settings)
        plan = plan_autocuts(script, asr, source_audio_sha256=raw['audio_sha256'], silences=silences, windows=windows)
    plan = _activity_cuts(episode, script, asr, before, plan)
    if not plan['cuts']:
        if before['status'] == 'matched':
            return raw
        detail = {'status': 'review_required', 'cuts_applied': 0, 'audio_path': str(source),
                  'before_report': before['report_path'], 'unresolved': plan['unresolved']}
        if require_ready:
            raise ValueError(f'Raw voice has no safely removable insertions; planning blocked. Review {before["report_path"]}')
        return detail
    destination = local_file(episode, '.stickman/voice-cleaning/' + plan['plan_sha256'], exists=False)
    emit(f'Voz cruda: retirando {len(plan["cuts"])} añadidos en copia PCM; original conservado')
    edit = apply_autocuts(source, destination, plan, ffmpeg=settings.ffmpeg_binary)
    write(destination / 'guion_final.txt', script)
    emit('Voz corregida: segunda transcripción independiente antes de permitir montaje')
    after = verify_voice(destination, settings=settings, transcribe=True, audio_filename='audio.wav')
    if digest(source) != raw['audio_sha256'] or digest(script_path) != raw['script_sha256']:
        raise ValueError('Raw voice or script changed during automatic correction; montage blocked')
    blocked_insertions = [row for row in plan['unresolved'] if row['kind'] == 'insert']
    detail = {'status': 'review_required', 'cuts_applied': len(plan['cuts']),
              'removed_seconds': sum(b-a for a, b in edit['removed_samples'])/edit['sample_rate'],
              'audio_path': edit['audio_path'], 'before_report': before['report_path'],
              'after_report': after['report_path'], 'remaining_differences': after['differences'],
              'unresolved': plan['unresolved'], 'raw_audio_sha256': raw['audio_sha256'],
              'output_audio_sha256': edit['output_audio_sha256'], 'automatic_clean_acceptance': False}
    if after['status'] == 'matched' and not blocked_insertions:
        corrected = json.loads((Path(after['report_path']).parent / 'asr.json').read_text())
        duration = probe_media(Path(edit['audio_path']), settings.ffprobe_binary).duration
        words = _word_clock(script, corrected, duration)
        remaining_activity = activity_outside_words(Path(edit['audio_path']), words,
            ffmpeg=settings.ffmpeg_binary, duration=duration)
        detail['remaining_untranscribed_activity'] = remaining_activity
        if remaining_activity:
            write(destination / 'preprocessing.json', detail)
            if require_ready:
                raise ValueError(f'Corrected voice still contains untranscribed activity; montage blocked. Review {after["report_path"]}')
            return detail
        from .audio import format_srt, parse_srt
        srt = destination / 'clean.srt'
        write(srt, format_srt(_cues(script, words)))
        alignment = destination / 'clean.alignment.json'
        write(alignment, {'method': 'local_asr_word_timestamps_after_audio_cuts', 'words': words,
                          'audio_sha256': edit['output_audio_sha256'], 'asr_sha256': digest(Path(after['report_path']).parent/'asr.json'),
                          'plan_sha256': plan['plan_sha256'], 'acoustic_sync_verified': False})
        detail['status'] = 'ready'
        result = {**raw, 'audio_path': edit['audio_path'], 'audio_sha256': edit['output_audio_sha256'],
                  'srt_path': str(srt), 'srt_sha256': digest(srt), 'alignment_path': str(alignment),
                  'alignment_sha256': digest(alignment), 'alignment_method': 'local_asr_word_timestamps_after_audio_cuts',
                  'words': words, 'cues': parse_srt(srt.read_text()), 'duration': duration,
                  'voice_cleaning': detail}
        write(destination / 'clean_narration.json', result)
        files = {key: {'path': str(path.relative_to(episode)), 'sha256': digest(path)} for key, path in {
            'audio': Path(edit['audio_path']), 'srt': srt, 'alignment': alignment,
            'validation': Path(after['report_path']), 'asr': Path(after['report_path']).parent / 'asr.json',
            'narration': destination / 'clean_narration.json', 'plan': destination / 'plan.json',
            'edit': destination / 'receipt.json'}.items()}
        write(active, {'version': 1, 'status': 'ready', 'raw_audio_sha256': raw['audio_sha256'],
                       'script_sha256': digest(script_path), 'files': files})
        cleaned_paths(episode, MODE)
        return result
    write(destination / 'preprocessing.json', detail)
    if require_ready:
        raise ValueError(f'Raw voice: removed {len(plan["cuts"])} insertions in preserved copy, but {len(after["differences"])} differences remain; montage blocked. Review {after["report_path"]}')
    return detail
