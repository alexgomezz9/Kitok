import json
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from kitok.youtube_stickman_es import voice_cleaning
from kitok.youtube_stickman_es.files import digest, write
from kitok.youtube_stickman_es.models import Voice


@pytest.fixture
def episode(tmp_path):
    folder = tmp_path / 'episode'
    folder.mkdir()
    (folder / 'guion_final.txt').write_text('Uno dos tres cuatro cinco seis siete ocho.')
    with wave.open(str(folder / 'voz.mp3'), 'wb') as out:
        out.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
        out.writeframes(b'\x01\x00' * 96000)
    (folder / 'voz.srt').write_text('1\n00:00:00,000 --> 00:00:01,900\nUno dos tres cuatro cinco seis siete ocho.\n')
    write(folder / 'voz.alignment.json', {'method': 'fish_provider_timestamps', 'words': []})
    return folder


def recognized(text, duration):
    words = text.split()
    step = duration / len(words)
    return {'text': text, 'duration': duration, 'segments': [
        {'text': word, 'start': i * step, 'end': (i+.7) * step} for i, word in enumerate(words)]}


def raw_record(episode):
    return {'audio_path': str(episode / 'voz.mp3'), 'audio_sha256': digest(episode / 'voz.mp3'),
            'script_sha256': digest(episode / 'guion_final.txt'), 'duration': 2,
            'srt_sha256': digest(episode / 'voz.srt')}


def fake_recognizer(episode, monkeypatch, *, post_text=None):
    calls = []
    def verify(folder, *, settings, transcribe, audio_filename='voz.mp3'):
        calls.append((folder, audio_filename))
        initial = folder == episode
        audio = folder / audio_filename
        if initial:
            data = recognized('Uno dos ruido tres cuatro cinco seis siete ocho', 2)
        else:
            with wave.open(str(audio)) as out:
                duration = out.getnframes() / out.getframerate()
            data = recognized(post_text or 'Uno dos tres cuatro cinco seis siete ocho', duration)
        identity = {'audio_sha256': digest(audio), 'engine': 'local_fixture_asr', 'model_files': {'model.bin': 'a'*64}}
        workspace = folder / '.stickman/voice-fidelity/test'
        workspace.mkdir(parents=True, exist_ok=True)
        write(workspace / 'asr.json', data)
        report = {'identity': identity, 'report_path': str(workspace / 'report.json'),
                  'status': 'review_required' if initial or post_text else 'matched',
                  'differences': [{'kind': 'insert'}] if initial or post_text else []}
        write(workspace / 'report.json', report)
        return report
    monkeypatch.setattr(voice_cleaning, 'verify_voice', verify)
    return calls


def test_real_pcm_correction_needs_second_pass_then_exposes_checked_clock(episode, monkeypatch):
    before = {p.name: digest(p) for p in episode.iterdir()}
    calls = fake_recognizer(episode, monkeypatch)
    settings = SimpleNamespace(ffmpeg_binary='ffmpeg', ffprobe_binary='ffprobe')
    result = voice_cleaning.clean_narration(episode, settings=settings, raw=raw_record(episode))
    assert result['voice_cleaning']['cuts_applied'] == 1
    assert result['alignment_method'] == 'local_asr_word_timestamps_after_audio_cuts'
    assert calls[0] == (episode, 'voz.mp3') and calls[1][1] == 'audio.wav'
    assert len(result['words']) == 8
    assert Path(result['audio_path']).suffix == '.wav'
    assert result['audio_sha256'] != before['voz.mp3']
    paths = voice_cleaning.cleaned_paths(episode, voice_cleaning.MODE)
    assert paths[0] == Path(result['audio_path'])
    assert all(digest(episode / name) == value for name, value in before.items())
    assert voice_cleaning.clean_narration(episode, settings=settings, raw=raw_record(episode)) == result


def test_partial_edit_is_available_but_can_never_be_render_input(episode, monkeypatch):
    fake_recognizer(episode, monkeypatch, post_text='Uno dos ruido tres cuatro cinco seis siete ocho')
    settings = SimpleNamespace(ffmpeg_binary='ffmpeg', ffprobe_binary='ffprobe')
    report = voice_cleaning.clean_narration(episode, settings=settings, raw=raw_record(episode), require_ready=False)
    assert report['status'] == 'review_required' and report['cuts_applied'] == 1
    assert Path(report['audio_path']).is_file()
    assert not (episode / '.stickman/voice-cleaning/active.json').exists()
    assert voice_cleaning.cleaned_paths(episode, voice_cleaning.MODE)[0] == episode / 'voz.mp3'
    with pytest.raises(ValueError, match='montage blocked'):
        voice_cleaning.clean_narration(episode, settings=settings, raw=raw_record(episode))


def test_tampered_corrected_audio_and_raw_are_rejected(episode, monkeypatch):
    fake_recognizer(episode, monkeypatch)
    settings = SimpleNamespace(ffmpeg_binary='ffmpeg', ffprobe_binary='ffprobe')
    result = voice_cleaning.clean_narration(episode, settings=settings, raw=raw_record(episode))
    Path(result['audio_path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='evidence changed'):
        voice_cleaning.cleaned_paths(episode, voice_cleaning.MODE)
    (episode / 'voz.mp3').write_bytes(b'changed raw')
    with pytest.raises(ValueError, match='Raw voice/script changed'):
        voice_cleaning.cleaned_paths(episode, voice_cleaning.MODE)


def test_cleaning_happens_before_legacy_narration_planning(episode, monkeypatch):
    from kitok.youtube_stickman_es import audio
    monkeypatch.setattr(audio, '_read_record', lambda *a: (_ for _ in ()).throw(ValueError('raw validation stopped')))
    with pytest.raises(ValueError, match='raw validation stopped'):
        audio.prepare_narration(episode, root=episode.parent, settings=SimpleNamespace(),
                                voice={'transcript_verification': voice_cleaning.MODE})
    assert not (episode / 'plan_imagenes.json').exists()


def test_off_still_serializes_exact_legacy_fields_and_new_mode_is_explicit():
    assert Voice().model_dump() == {'reference_id': None, 'model': None, 'speed': 1.0}
    assert Voice(transcript_verification=voice_cleaning.MODE).model_dump()['transcript_verification'] == voice_cleaning.MODE


def test_new_stickman_episode_enables_preprocessing_without_changing_legacy(tmp_path):
    from kitok.youtube_stickman_es.pipeline import initialize
    initialize(tmp_path, Path('episode'))
    config = json.loads((tmp_path / 'episode/configuracion.json').read_text())
    assert config['voice']['transcript_verification'] == voice_cleaning.MODE
    assert Voice().transcript_verification == 'off'


def test_ready_correction_never_reverts_to_raw_after_model_change(episode, monkeypatch):
    fake_recognizer(episode, monkeypatch)
    settings = SimpleNamespace(ffmpeg_binary='ffmpeg', ffprobe_binary='ffprobe')
    expected = voice_cleaning.clean_narration(episode, settings=settings, raw=raw_record(episode))
    def forbid_replanning(*args, **kwargs):
        raise AssertionError('A pinned checked correction must not be replaced by a new raw ASR result')
    monkeypatch.setattr(voice_cleaning, 'verify_voice', forbid_replanning)
    actual = voice_cleaning.clean_narration(episode, settings=settings, raw=raw_record(episode))
    assert actual == expected
    assert Path(actual['audio_path']) == voice_cleaning.cleaned_paths(episode, voice_cleaning.MODE)[0]


@pytest.mark.parametrize('review_state', ['valid', 'missing', 'changed', 'uncovered_activity'])
def test_no_cut_review_keeps_explicit_provenance_and_cannot_accept_activity(episode, monkeypatch, review_state):
    workspace = episode / '.stickman/voice-fidelity/review-case'
    workspace.mkdir(parents=True)
    data = recognized('Uno dos tres cuatro cinco seis siete ocho', 2)
    write(workspace / 'asr.json', data)
    report = {'status': 'review_required', 'report_path': str(workspace / 'report.json'),
              'identity': {'audio_sha256': digest(episode / 'voz.mp3'),
                           'engine': 'local_fixture_asr', 'model_files': {'model.bin': 'a'*64}},
              'differences': [{'kind': 'replace', 'expected': 'nombre', 'recognized': 'grafia'}],
              'uncovered_activity': [{'start': .5, 'end': 1.5}] if review_state == 'uncovered_activity' else []}
    write(workspace / 'report.json', report)
    if review_state != 'missing':
        write(workspace / 'review.json', {'decision': 'accept_asr_differences',
            'report_sha256': 'changed' if review_state == 'changed' else digest(workspace / 'report.json'),
            'reviewer': 'documentary ASR review', 'reason': 'Independent short recognition corroborates spelling'})
    monkeypatch.setattr(voice_cleaning, 'verify_voice', lambda *a, **kw: report)
    monkeypatch.setattr(voice_cleaning, '_silences', lambda *a: [])
    monkeypatch.setattr(voice_cleaning, '_activity_cuts', lambda episode, script, asr, before, plan: plan)
    settings = SimpleNamespace(ffmpeg_binary='ffmpeg', ffprobe_binary='ffprobe')
    if review_state != 'valid':
        with pytest.raises(ValueError):
            voice_cleaning.clean_narration(episode, settings=settings, raw=raw_record(episode))
    else:
        raw = raw_record(episode)
        result = voice_cleaning.clean_narration(episode, settings=settings, raw=raw)
        assert result['audio_sha256'] == raw['audio_sha256']
        assert result['voice_fidelity']['status'] == 'reviewed_asr_differences'
        assert result['voice_fidelity']['review_sha256'] == digest(workspace / 'review.json')
        assert not (episode / '.stickman/voice-cleaning/active.json').exists()


def test_refined_match_cannot_cut_disproven_insertions_from_original_asr(episode, monkeypatch):
    monkeypatch.setattr(voice_cleaning, 'verify_voice', lambda *a, **kw: {
        'status': 'matched', 'differences': [{'kind': 'insert'}], 'remaining_differences': [],
        'refinement': {'resolutions': [{'resolved': True}]}})
    def forbidden(*a, **kw):
        raise AssertionError('Already verified text must not enter the cut planner')
    monkeypatch.setattr(voice_cleaning, 'plan_autocuts', forbidden)
    monkeypatch.setattr(voice_cleaning, '_silences', forbidden)
    raw = raw_record(episode)
    assert voice_cleaning.clean_narration(episode, settings=SimpleNamespace(), raw=raw) == raw


def test_partial_refinement_cannot_cut_a_disproven_insertion(episode, monkeypatch):
    report = {'status': 'review_required', 'report_path': str(episode / 'report.json'),
              'differences': [{'kind': 'insert'}, {'kind': 'replace'}],
              'remaining_differences': [{'kind': 'replace'}],
              'refinement': {'resolutions': [{'difference_index': 0, 'resolved': True}]}}
    monkeypatch.setattr(voice_cleaning, 'verify_voice', lambda *a, **kw: report)
    raw = raw_record(episode)
    result = voice_cleaning.clean_narration(episode, settings=SimpleNamespace(), raw=raw, require_ready=False)
    assert result['status'] == 'review_required' and result['cuts_applied'] == 0
    with pytest.raises(ValueError, match='Partial recognition refinement'):
        voice_cleaning.clean_narration(episode, settings=SimpleNamespace(), raw=raw)
