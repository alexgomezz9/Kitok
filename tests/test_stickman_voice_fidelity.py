import json

import pytest
from pathlib import Path
from types import SimpleNamespace

from kitok.config import Settings
from kitok.youtube_stickman_es.files import digest, write
from kitok.youtube_stickman_es.voice_fidelity import compare_transcript, require_reviewed, verify_voice, uncovered_activity


def asr(text, *, duration=4):
    words = text.split()
    return {'text': text, 'duration': duration, 'segments': [
        {'text': word, 'start': i * duration / len(words), 'end': (i + .8) * duration / len(words)}
        for i, word in enumerate(words)]}


def test_case_punctuation_accent_and_delivery_tags_do_not_create_false_differences():
    report = compare_transcript('[whispering] Él llegó. [break] ¡Ahora!', asr('el llego ahora'))
    assert report['status'] == 'matched'
    assert report['acoustic_sync_verified'] is False


def test_optional_guard_preserves_legacy_configuration_hashes():
    from kitok.youtube_stickman_es.models import Voice, Config
    assert Voice().model_dump() == {'reference_id': None, 'model': None, 'speed': 1}
    assert Config.model_validate({'voice': {'transcript_verification': 'local_asr'}}).model_dump()['voice']['transcript_verification'] == 'local_asr'


def test_repeated_invented_speech_inside_otherwise_exact_script_is_flagged_and_timed():
    report = compare_transcript('Jason llegó al lago y desapareció.',
                                asr('Jason llegó montantani montantan al lago y desapareció'))
    assert report['status'] == 'review_required'
    difference, = report['differences']
    assert difference['kind'] == 'insert'
    assert difference['recognized'] == 'montantani montantan'
    assert difference['start'] == 1
    assert report['automatic_cuts'] is False


def test_missing_negation_blocks_even_when_other_words_match():
    report = compare_transcript('Jason no murió en el lago.', asr('Jason murió en el lago'))
    assert report['status'] == 'review_required'
    assert report['differences'][0]['expected'] == 'no'


def test_missing_or_nonmatching_asr_times_never_invent_diagnostic_timestamps():
    result = asr('Jason llegó montantani')
    result['segments'] = []
    report = compare_transcript('Jason llegó', result)
    assert report['status'] == 'review_required'
    assert report['timestamp_text_matches'] is False
    assert 'start' not in report['differences'][0]


@pytest.mark.parametrize('result', [None, {}, {'text': '', 'duration': 4, 'segments': []},
                                 {'text': 'Hola', 'duration': float('nan'), 'segments': []},
                                 {'text': 'Hola', 'duration': 4, 'segments': [{'text': 'Hola', 'start': 3, 'end': 2}]}])
def test_bad_asr_is_never_accepted(result):
    with pytest.raises(ValueError):
        compare_transcript('Hola', result)


@pytest.fixture
def episode(tmp_path):
    import wave
    folder = tmp_path / 'episode'
    folder.mkdir()
    with wave.open(str(folder / 'voz.mp3'), 'wb') as handle:
        handle.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        handle.writeframes(b'\0\0' * 32000)
    (folder / 'guion_final.txt').write_text('Jason llegó al lago.')
    return folder


@pytest.fixture
def runtime(episode):
    python = episode.parent / 'python'
    python.write_text('test fixture executable')
    model = episode.parent / 'model'
    model.mkdir()
    (model / 'model.bin').write_bytes(b'test fixture model')
    return {'local_python': python, 'local_model': model}


def test_audio_only_local_worker_cached_once_and_hash_bound_review(episode, runtime, monkeypatch):
    calls = []
    def respond(command, **kwargs):
        calls.append(command)
        assert command[-1] == str(episode / 'voz.mp3')
        assert 'Jason' not in ' '.join(command)  # Never prime ASR with the expected script.
        assert kwargs['env']['HF_HUB_OFFLINE'] == '1'
        return SimpleNamespace(stdout=json.dumps(asr('Jason llegó montantani al lago')))
    monkeypatch.setattr('kitok.youtube_stickman_es.voice_fidelity.subprocess.run', respond)
    monkeypatch.setattr('kitok.media.ffprobe.probe_media', lambda *a, **k: SimpleNamespace(duration=4))
    settings = Settings(_env_file=None)
    report = verify_voice(episode, settings=settings, transcribe=True, **runtime)
    assert verify_voice(episode, settings=settings, **runtime) == report
    assert len(calls) == 1
    with pytest.raises(ValueError, match='Voice fidelity needs review'):
        require_reviewed(report, episode)
    path = Path(report['report_path'])
    write(path.parent / 'review.json', {'decision': 'accept_asr_differences',
        'report_sha256': digest(path), 'reviewer': 'Operator', 'reason': 'Every difference listened to and accepted'})
    require_reviewed(report, episode)
    path.write_text(path.read_text() + ' ')
    with pytest.raises(ValueError, match='Voice fidelity needs review'):
        require_reviewed(report, episode)


def test_failed_local_worker_preserves_inputs_and_no_upload(episode, runtime, monkeypatch):
    import subprocess
    before = {p.name: digest(p) for p in episode.iterdir()}
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired('local-worker', 1800)
    monkeypatch.setattr('kitok.youtube_stickman_es.voice_fidelity.subprocess.run', fail)
    with pytest.raises(ValueError, match='no audio was uploaded'):
        verify_voice(episode, settings=Settings(_env_file=None), transcribe=True, **runtime)
    assert all(digest(episode / name) == value for name, value in before.items())


def test_no_opt_in_never_runs_asr(episode, runtime):
    with pytest.raises(ValueError, match='--transcribe locally'):
        verify_voice(episode, settings=Settings(_env_file=None), **runtime)


def test_truncated_recognition_is_rejected_even_if_text_matches(episode, runtime):
    result = episode.parent / 'asr.json'
    write(result, {**asr('Jason llegó al lago', duration=1), 'audio_sha256': digest(episode / 'voz.mp3'),
                  'engine': 'faster-whisper-cpu-int8', 'model_files': {'model.bin': digest(runtime['local_model'] / 'model.bin')}})
    with pytest.raises(ValueError, match='does not cover'):
        verify_voice(episode, settings=Settings(_env_file=None), imported_result=result, **runtime)


def test_imported_asr_cannot_be_reused_for_other_audio(episode, runtime):
    result = episode.parent / 'asr.json'
    write(result, {**asr('Jason llegó al lago'), 'audio_sha256': 'wrong'})
    with pytest.raises(ValueError, match='exact audio SHA256'):
        verify_voice(episode, settings=Settings(_env_file=None), imported_result=result, **runtime)


def test_imported_asr_cannot_claim_other_model_and_lose_its_provenance(episode, runtime):
    result = episode.parent / 'asr.json'
    write(result, {**asr('Jason llegó al lago'), 'audio_sha256': digest(episode / 'voz.mp3'),
                  'engine': 'unrelated-model', 'model_files': {}})
    with pytest.raises(ValueError, match='matching engine'):
        verify_voice(episode, settings=Settings(_env_file=None), imported_result=result, **runtime)


def test_narration_guard_blocks_before_planning_without_resynthesis(episode, monkeypatch):
    from kitok.youtube_stickman_es.audio import prepare_narration
    script = (episode / 'guion_final.txt').read_text()
    (episode / 'voz.srt').write_text('1\n00:00:00,000 --> 00:00:04,000\n'+script+'\n')
    before = digest(episode / 'voz.mp3')
    report = {'status': 'review_required', 'differences': [{'recognized': 'montantani'}],
              'report_path': str(episode / '.stickman/report.json')}
    monkeypatch.setattr('kitok.youtube_stickman_es.voice_fidelity.verify_voice', lambda *a, **k: report)
    with pytest.raises(ValueError, match='Voice fidelity needs review'):
        prepare_narration(episode, root=episode.parent, settings=Settings(_env_file=None),
                          voice={'transcript_verification': 'local_asr'})
    assert digest(episode / 'voz.mp3') == before
    assert not (episode / 'plan_imagenes.json').exists()


def test_uncovered_energy_distinguishes_audible_gap_from_silence(episode, monkeypatch):
    alignment = episode / 'voz.alignment.json'
    write(alignment, {'method': 'fish_provider_timestamps', 'words': [
        {'start': 0, 'end': 1, 'word': 'Jason'}, {'start': 3, 'end': 4, 'word': 'lago'}]})
    monkeypatch.setattr('kitok.youtube_stickman_es.voice_fidelity.subprocess.run', lambda *a, **k:
        SimpleNamespace(stderr='silence_start: 1.1\nsilence_end: 2.9'))
    assert uncovered_activity(episode / 'voz.mp3', alignment, ffmpeg='ffmpeg', duration=4) == []
    monkeypatch.setattr('kitok.youtube_stickman_es.voice_fidelity.subprocess.run', lambda *a, **k:
        SimpleNamespace(stderr=''))
    gap, = uncovered_activity(episode / 'voz.mp3', alignment, ffmpeg='ffmpeg', duration=4)
    assert gap['start'] == 1.12 and gap['end'] == 2.88
    assert gap['meaning'] == 'audible_energy_outside_word_marks_not_proof_of_speech'


def test_activity_accepts_same_one_millisecond_provider_tail_tolerance(episode, monkeypatch):
    alignment = episode / 'voz.alignment.json'
    write(alignment, {'method': 'fish_provider_timestamps', 'words': [
        {'start': 0, 'end': 4.0005, 'word': 'Hola'}]})
    monkeypatch.setattr('kitok.youtube_stickman_es.voice_fidelity.subprocess.run', lambda *a, **k:
        SimpleNamespace(stderr=''))
    assert uncovered_activity(episode / 'voz.mp3', alignment, ffmpeg='ffmpeg', duration=4) == []
