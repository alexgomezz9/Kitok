import hashlib
import json
import wave

import pytest

from kitok.config import Settings
from kitok.youtube_stickman_es import audio


VOICE = {'reference_id': 'es-test', 'model': None, 'speed': 1.1}
SOURCE = ' \n[calm] Hola,\tmundo.\n\n[break]  Todo cambia.\r\n '


def tone(path):
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\x00\x00' * 32000)


def alignment(path):
    path.write_text(json.dumps({'method': 'fish_provider_timestamps', 'words': [
        {'word': 'Hola,', 'start': .1, 'end': .8},
        {'word': 'mundo.', 'start': .8, 'end': 1.5},
        {'word': 'Todo', 'start': 2, 'end': 2.8},
        {'word': 'cambia.', 'start': 2.8, 'end': 3.8}]}))


@pytest.fixture
def episode(tmp_path):
    folder = tmp_path / 'episode'
    folder.mkdir()
    (folder / 'guion_final.txt').write_bytes(SOURCE.encode('utf-8'))
    return folder


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, data_root=tmp_path, fish_api_key='test-private-value')


def fake_fish(monkeypatch):
    calls = []

    class Fish:
        def __init__(self, *args, **kwargs):
            pass

        def synthesize(self, text, reference_id, destination, **kwargs):
            calls.append((text, reference_id, kwargs))
            tone(destination)
            alignment(destination.with_suffix('.alignment.json'))

        def close(self):
            pass

    monkeypatch.setattr(audio, 'FishVoiceClient', Fish)
    return calls


def prepare(folder, settings):
    return audio.prepare_narration(folder, root=folder.parent, settings=settings,
                                   voice=VOICE, generate=True)


def old_request(folder, settings):
    state = folder / '.stickman'
    state.mkdir()
    request = {'version': 1, 'script_sha256': audio._hash(folder / 'guion_final.txt'),
               'voice': {**VOICE, 'model': settings.fish_model}}
    (state / 'voice_request.json').write_text(json.dumps(request))
    return request


def test_compiler_collapses_only_whitespace_and_keeps_markers_and_words():
    text = '\t[calm]\nHola,\t  mundo.\r\n[soft whisper] Así\u00a0es. [break]\n'
    compiled = audio._tts_text(text)
    assert compiled == '[calm] Hola, mundo. [soft whisper] Así es. [break]'
    assert compiled.split() == text.split()
    assert audio._tts_text(text, 'strip_v1') == text.strip()
    with pytest.raises(audio.StickmanAudioError, match='preprocessing policy'):
        audio._tts_text(text, 'unknown')


def test_new_request_binds_actual_fish_text_and_reuses_without_a_client(episode, settings, monkeypatch):
    original = (episode / 'guion_final.txt').read_bytes()
    calls = fake_fish(monkeypatch)
    result = prepare(episode, settings)
    assert calls == [('[calm] Hola, mundo. [break] Todo cambia.', 'es-test', {'speed': 1.1})]
    path = episode / '.stickman/voice_request.json'
    request = json.loads(path.read_text())
    assert request['tts_text_policy'] == 'collapse_whitespace_v1'
    assert request['tts_text_sha256'] == hashlib.sha256(calls[0][0].encode('utf-8')).hexdigest()
    assert request['script_sha256'] == hashlib.sha256(original).hexdigest()
    assert (episode / 'guion_final.txt').read_bytes() == original
    monkeypatch.setattr(audio, 'FishVoiceClient', lambda *a, **k: pytest.fail('reuse must not construct Fish'))
    assert prepare(episode, settings) == result
    assert json.loads(path.read_text()) == request


@pytest.mark.parametrize('staged', [False, True])
def test_legacy_request_keeps_strip_only_text_and_paid_staging(episode, settings, monkeypatch, staged):
    original = old_request(episode, settings)
    if staged:
        tone(episode / '.stickman/fish-voz.mp3')
        alignment(episode / '.stickman/fish-voz.alignment.json')
    calls = fake_fish(monkeypatch)
    result = prepare(episode, settings)
    assert result['source'] == 'fish'
    assert calls == ([] if staged else [(SOURCE.replace('\r\n', '\n').strip(), 'es-test', {'speed': 1.1})])
    request = json.loads((episode / '.stickman/voice_request.json').read_text())
    assert request == {**original, 'audio_sha256': audio._hash(episode / 'voz.mp3')}


@pytest.mark.parametrize('mutation', ['hash', 'policy', 'missing_hash', 'missing_policy'])
def test_inconsistent_new_request_blocks_existing_audio_without_fish_or_mutation(episode, settings, monkeypatch, mutation):
    fake_fish(monkeypatch)
    prepare(episode, settings)
    path = episode / '.stickman/voice_request.json'
    request = json.loads(path.read_text())
    if mutation == 'hash':
        request['tts_text_sha256'] = 'b'*64
    elif mutation == 'policy':
        request['tts_text_policy'] = 'different_policy'
    else:
        del request['tts_text_sha256' if mutation == 'missing_hash' else 'tts_text_policy']
    path.write_text(json.dumps(request))
    original = {p.name: p.read_bytes() for p in episode.iterdir() if p.is_file()}
    request_bytes = path.read_bytes()
    monkeypatch.setattr(audio, 'FishVoiceClient', lambda *a, **k: pytest.fail('invalid identity cannot contact Fish'))
    with pytest.raises(audio.StickmanAudioError, match='preprocessing policy|text hash changed'):
        prepare(episode, settings)
    assert path.read_bytes() == request_bytes
    assert all((episode / name).read_bytes() == content for name, content in original.items())


def test_unbound_staged_audio_is_not_mislabelled_with_the_new_policy(episode, settings, monkeypatch):
    state = episode / '.stickman'
    state.mkdir()
    tone(state / 'fish-voz.mp3')
    original = (state / 'fish-voz.mp3').read_bytes()
    monkeypatch.setattr(audio, 'FishVoiceClient', lambda *a, **k: pytest.fail('unbound staging cannot contact Fish'))
    with pytest.raises(audio.StickmanAudioError, match='no request identity'):
        prepare(episode, settings)
    assert (state / 'fish-voz.mp3').read_bytes() == original
    assert not (state / 'voice_request.json').exists()
    assert not (episode / 'voz.mp3').exists()
