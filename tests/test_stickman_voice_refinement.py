import copy
import json
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from kitok.config import Settings
from kitok.youtube_stickman_es.files import digest, write
from kitok.youtube_stickman_es.voice_fidelity import require_reviewed, verify_voice
from kitok.youtube_stickman_es.voice_refinement import resolve_window, window_requests


def recognized(text, duration=4):
    words = text.split()
    return {'text': text, 'duration': duration, 'segments': [
        {'text': word, 'start': i*duration/len(words), 'end': (i+.8)*duration/len(words)}
        for i, word in enumerate(words)]}


def test_clitics_need_exact_complete_context_letters_and_observed_clocks():
    script = 'Uno dos acercarse lo suficiente para tres cuatro.'
    request, = window_requests(script, recognized('Uno dos acercarselo suficiente para tres cuatro'))
    result = recognized('Uno dos acercárselo suficiente para')
    before = copy.deepcopy(result)
    resolved = resolve_window(request, result, [])
    assert resolved['resolved']
    assert resolved['method'] == 'exact_context_letters_with_different_word_boundaries'
    assert result == before  # Never split, retime or rewrite actual ASR words.
    assert not resolve_window(request, recognized('Uno dos acercarselo ajeno suficiente para'), [])['resolved']
    assert not resolve_window(request, recognized('Uno dos acercarse suficiente para'), [])['resolved']
    assert not resolve_window(request, result, [{'active_seconds': .8}])['resolved']


def test_name_requires_literal_recovery_in_second_recognition_not_a_phonetic_alias():
    request, = window_requests('Uno dos Krueger tres cuatro.', recognized('Uno dos Kruger tres cuatro'))
    assert resolve_window(request, recognized('Uno dos Krueger tres cuatro'), [])['resolved']
    assert not resolve_window(request, recognized('Uno dos Kruger tres cuatro'), [])['resolved']


def test_window_boundaries_keep_the_surrounding_sentence_complete():
    script = ('Antes pasó. Mientras tanto su madre terminó contándole la verdad. '
              'Fred Krueger no era un desconocido surgido de la imaginación. Después terminó.')
    asr = recognized(script.replace('Krueger', 'Kruger'), duration=10)
    request, = window_requests(script, asr)
    first = next(row for row in asr['segments'] if row['text'] == 'Mientras')
    assert request['offset'] <= first['start']-.2
    assert request['duration'] <= 20


def test_zero_duration_insertion_is_not_discarded_without_window_recovery():
    asr = recognized('Uno dos ruido tres cuatro')
    asr['segments'][2]['end'] = asr['segments'][2]['start']
    request, = window_requests('Uno dos tres cuatro.', asr)
    assert resolve_window(request, recognized('Uno dos tres cuatro'), [])['resolved']
    assert not resolve_window(request, recognized('Uno dos ruido tres cuatro'), [])['resolved']


def test_real_omission_stays_blocked_and_literal_recovery_resolves():
    request, = window_requests('Uno dos no volvió tres cuatro.', recognized('Uno dos tres cuatro'))
    assert not resolve_window(request, recognized('Uno dos volvió tres cuatro'), [])['resolved']
    assert resolve_window(request, recognized('Uno dos no volvió tres cuatro'), [])['resolved']


def test_repeated_or_reordered_context_does_not_resolve():
    assert window_requests('Uno dos cambia tres cuatro uno dos cambia tres cuatro.',
                           recognized('Uno dos ruido tres cuatro uno dos cambia tres cuatro')) == []
    request, = window_requests('Uno dos Krueger tres cuatro.', recognized('Uno dos Kruger tres cuatro'))
    assert not resolve_window(request, recognized('Uno dos Krueger tres cuatro Uno dos'), [])['resolved']
    assert not resolve_window(request, recognized('tres cuatro Krueger Uno dos'), [])['resolved']


@pytest.fixture
def runtime(tmp_path):
    episode = tmp_path / 'episode'
    episode.mkdir()
    with wave.open(str(episode / 'voz.mp3'), 'wb') as out:
        out.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        out.writeframes(b'\x00\x00' * 32000)
    (episode / 'guion_final.txt').write_text('Uno dos Krueger tres cuatro.')
    python = tmp_path / 'python'
    python.write_text('fixture runtime')
    model = tmp_path / 'model'
    model.mkdir()
    (model / 'model.bin').write_bytes(b'fixture model')
    return episode, python, model


def run_fixture(runtime, monkeypatch, *, window_text='Uno dos Krueger tres cuatro', transcribe=True):
    import subprocess
    original_run = subprocess.run
    episode, python, model = runtime
    calls = []
    def run(command, **kwargs):
        if command[0] in ('ffmpeg', 'ffprobe'):
            return original_run(command, **kwargs)
        calls.append(command)
        assert 'Krueger' not in ' '.join(command) and 'Kruger' not in ' '.join(command)
        assert kwargs['env']['HF_HUB_OFFLINE'] == '1'
        if command[-1] == str(episode / 'voz.mp3'):
            result = recognized('Uno dos Kruger tres cuatro')
        else:
            paths = json.loads(command[-1])
            assert len(paths) == 1
            with wave.open(paths[0]) as clip:
                duration = clip.getnframes()/clip.getframerate()
            result = [recognized(window_text, duration)]
        return SimpleNamespace(stdout=json.dumps(result))
    monkeypatch.setattr('kitok.youtube_stickman_es.voice_fidelity.subprocess.run', run)
    settings = Settings(_env_file=None)
    report = verify_voice(episode, settings=settings, local_python=python, local_model=model,
                          transcribe=transcribe)
    return report, calls, settings


def test_refined_match_preserves_original_difference_counts_files_and_caches_windows(runtime, monkeypatch):
    episode, python, model = runtime
    report, calls, settings = run_fixture(runtime, monkeypatch)
    original = json.loads(Path(report['original_report_path']).read_text())
    assert report['status'] == 'matched' and original['status'] == 'review_required'
    assert report['differences'] == original['differences']
    assert report['recognized_words'] == original['recognized_words']
    assert report['timestamp_text_matches'] == original['timestamp_text_matches']
    assert report['remaining_differences'] == []
    assert report['refinement']['resolutions'][0]['method'] == 'exact_context'
    raw = Path(report['report_path']).parent / 'asr.json'
    assert json.loads(raw.read_text())['text'] == 'Uno dos Kruger tres cuatro'
    hashes = digest(raw), digest(episode / 'voz.mp3'), digest(episode / 'guion_final.txt')
    assert verify_voice(episode, settings=settings, local_python=python, local_model=model) == report
    assert len(calls) == 2
    assert hashes == (digest(raw), digest(episode / 'voz.mp3'), digest(episode / 'guion_final.txt'))


@pytest.mark.parametrize('window_text', ['Uno dos Kruger tres cuatro', 'Uno dos Krueger ajeno tres cuatro'])
def test_real_window_differences_do_not_pass(runtime, monkeypatch, window_text):
    report, _, _ = run_fixture(runtime, monkeypatch, window_text=window_text)
    assert report['status'] == 'review_required' and len(report['remaining_differences']) == 1


def test_window_energy_keeps_otherwise_exact_recognition_blocked(runtime, monkeypatch):
    monkeypatch.setattr('kitok.youtube_stickman_es.voice_refinement.activity_outside_words',
                        lambda *a, **k: [{'start': 1, 'end': 2, 'active_seconds': .8}])
    report, _, _ = run_fixture(runtime, monkeypatch)
    assert report['status'] == 'review_required'
    assert report['refinement']['resolutions'][0]['reason'] == 'incomplete_window_clock_or_uncovered_energy'


@pytest.mark.parametrize('tamper', ['clip', 'result', 'identity', 'response'])
def test_cached_refinement_rejects_changed_evidence(runtime, monkeypatch, tamper):
    episode, python, model = runtime
    report, calls, settings = run_fixture(runtime, monkeypatch)
    path = Path(report['refinement']['evidence_path'])
    evidence = json.loads(path.read_text())
    if tamper == 'clip':
        with (episode / evidence['windows'][0]['audio_path']).open('ab') as out:
            out.write(b'changed')
    elif tamper == 'result':
        evidence['windows'][0]['result']['text'] = 'Invented replacement'
        path.write_text(json.dumps(evidence))
    elif tamper == 'identity':
        evidence['identity']['source_asr_sha256'] = 'b'*64
        path.write_text(json.dumps(evidence))
    else:
        (path.parent / 'response.json').write_text('[]')
    with pytest.raises(ValueError, match='changed'):
        verify_voice(episode, settings=settings, local_python=python, local_model=model)
    assert len(calls) == 2


def test_review_message_counts_only_remaining_discrepancies(runtime):
    episode, _, _ = runtime
    report = {'status': 'review_required', 'differences': [{}, {}, {}],
              'remaining_differences': [{}], 'report_path': str(episode / '.stickman/report.json')}
    with pytest.raises(ValueError, match='1 unresolved ASR differences'):
        require_reviewed(report, episode)


def test_second_verification_after_cuts_never_uses_refinement(runtime, monkeypatch):
    episode, python, model = runtime
    (episode / 'audio.wav').write_bytes((episode / 'voz.mp3').read_bytes())
    calls = []
    monkeypatch.setattr('kitok.youtube_stickman_es.voice_fidelity.subprocess.run',
        lambda command, **kwargs: calls.append(command) or SimpleNamespace(stdout=json.dumps(recognized('Uno dos Kruger tres cuatro'))))
    monkeypatch.setattr('kitok.media.ffprobe.probe_media', lambda *a, **k: SimpleNamespace(duration=4))
    report = verify_voice(episode, settings=Settings(_env_file=None), local_python=python,
                          local_model=model, transcribe=True, audio_filename='audio.wav')
    assert report['status'] == 'review_required' and 'refinement' not in report
    assert len(calls) == 1
    cached = verify_voice(episode, settings=Settings(_env_file=None), local_python=python,
                          local_model=model, transcribe=False)
    assert cached['status'] == 'review_required' and 'refinement' not in cached
    assert len(calls) == 1  # A cached full ASR does not opt into missing window recognition.
