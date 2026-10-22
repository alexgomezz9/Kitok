"""Provider integrity and word timing independent of the existing SRT grouping."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from kitok.youtube_stickman_es import audio


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    (tmp_path / 'voz.mp3').write_bytes(b'validated by mocked local probe')
    (tmp_path / 'guion_final.txt').write_text('Hola, mundo.\r\n\r\nTodo cambia.')
    words = [{'word': word, 'start': start, 'end': end} for word, start, end in [
        ('Hola,', .1, .8), ('mundo.', .8, 1.5), ('Todo', 2., 2.8), ('cambia.', 2.8, 3.8)]]
    monkeypatch.setattr(audio, 'probe_media', lambda *a: SimpleNamespace(audio_codec='pcm', duration=4.))
    monkeypatch.setattr(audio, 'stream_durations', lambda *a: (None, 4.))
    monkeypatch.setattr(audio, 'FishVoiceClient', lambda *a, **k: pytest.fail('no paid operation'))
    return tmp_path, words


def save(folder, words):
    path = folder / 'voz.alignment.json'
    path.write_text(json.dumps({'method': 'fish_provider_timestamps', 'words': words}))
    return path


def prepare(folder):
    return audio.prepare_narration(folder, root=folder, settings=SimpleNamespace(ffprobe_binary='ffprobe'))


def test_provider_paragraphs_are_not_srt_blocks(inputs):
    folder, words = inputs
    save(folder, words)
    result = prepare(folder)
    assert result['words'] == words
    assert audio.read_srt(folder / 'voz.srt') == result['cues']
    assert audio._tokens(' '.join(cue['text'] for cue in result['cues'])) == audio._tokens(
        (folder / 'guion_final.txt').read_text())
    assert len(result['cues']) == 2


def test_real_word_times_added_without_rewriting_accepted_srt_or_receipt(inputs):
    folder, words = inputs
    (folder / 'voz.srt').write_text('1\n00:00:00,100 --> 00:00:03,800\nHola, mundo. Todo cambia.\n')
    prepare(folder)
    receipt = folder / '.stickman/narration.json'
    before = receipt.read_bytes(), (folder / 'voz.srt').read_bytes()
    alignment = save(folder, words)
    result = prepare(folder)
    assert result['words'] == words
    assert result['alignment_sha256'] == hashlib.sha256(alignment.read_bytes()).hexdigest()
    assert (receipt.read_bytes(), (folder / 'voz.srt').read_bytes()) == before


def test_zero_length_word_preserves_real_provider_time(inputs):
    folder, words = inputs
    words[1]['end'] = words[1]['start']
    save(folder, words)
    result = prepare(folder)
    assert result['words'][1]['start'] == result['words'][1]['end'] == .8


def test_multitoken_segments_support_srt_but_do_not_fabricate_word_times(inputs):
    folder, _ = inputs
    save(folder, [{'word': 'Hola, mundo.', 'start': .1, 'end': 1.5},
                  {'word': 'Todo cambia.', 'start': 2., 'end': 3.8}])
    result = prepare(folder)
    assert 'words' not in result
    assert result['cues'][-1]['end'] == 3.8
    assert result['alignment_sha256']


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'substitute', 'negative', 'overlap',
                                   'reversed', 'nan', 'inf', 'beyond', 'empty', 'bool'])
def test_invalid_alignment_never_becomes_word_timing(inputs, change):
    folder, words = inputs
    if change == 'missing':
        words.pop()
    elif change == 'duplicate':
        words[1]['word'] = 'Hola'
    elif change == 'substitute':
        words[1]['word'] = 'otro'
    elif change == 'negative':
        words[0]['start'] = -.1
    elif change == 'overlap':
        words[1]['start'] = .7
    elif change == 'reversed':
        words[1]['end'] = .7
    elif change in {'nan', 'inf'}:
        words[1]['end'] = float(change)
    elif change == 'beyond':
        words[-1]['end'] = 4.1
    elif change == 'empty':
        words[1]['word'] = '!!!'
    else:
        words[1]['start'] = True
    save(folder, words)
    with pytest.raises(audio.StickmanAudioError, match='full-transcript Fish alignment'):
        prepare(folder)
    assert not (folder / 'voz.srt').exists()
    assert not (folder / '.stickman/narration.json').exists()


def test_pinned_provider_alignment_cannot_change(inputs):
    folder, words = inputs
    path = save(folder, words)
    prepare(folder)
    receipt = (folder / '.stickman/narration.json').read_bytes()
    path.write_text(path.read_text() + ' ')
    with pytest.raises(audio.StickmanAudioError, match='Provider alignment changed'):
        prepare(folder)
    assert (folder / '.stickman/narration.json').read_bytes() == receipt


def test_submillisecond_cue_collapse_is_not_fixed_with_invented_times(inputs):
    folder, words = inputs
    words = [{'word': 'Hola, mundo. Todo cambia.', 'start': .1001, 'end': .1002}]
    save(folder, words)
    with pytest.raises(audio.StickmanAudioError, match='full-transcript Fish alignment'):
        prepare(folder)
    assert not (folder / 'voz.srt').exists()


@pytest.mark.parametrize('final_time', [2., 2.5])
def test_terminal_zero_duration_word_joins_previous_cue_without_invented_times(inputs, final_time):
    folder, _ = inputs
    script = 'Hola. Fin'
    (folder / 'guion_final.txt').write_text(script)
    save(folder, [{'word': 'Hola.', 'start': .1, 'end': 2.},
                  {'word': 'Fin', 'start': final_time, 'end': final_time}])
    result = prepare(folder)
    assert result['cues'] == [{'index': 1, 'start': .1, 'end': final_time, 'text': script}]
    assert result['words'][-1]['start'] == result['words'][-1]['end'] == final_time
