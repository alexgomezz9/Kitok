import json
import subprocess

import pytest

from kitok.config import Settings
from kitok.youtube_stickman_es.audio import _provider_segments, prepare_narration
from kitok.youtube_stickman_es.audio_cuts import METHOD, cut_words, repair_audio
from kitok.youtube_stickman_es.files import digest
from kitok.youtube_stickman_es.reuse import safe_revision


def test_sample_cuts_preserve_every_word_and_shift_both_endpoints():
    words = [{'word': 'Hola', 'start': .1, 'end': .5},
             {'word': 'mundo', 'start': 3, 'end': 3.5},
             {'word': 'final', 'start': 5, 'end': 5.5}]
    changed = cut_words(words, [[600, 2900], [3600, 4900]], 1000, 6)
    assert [w['word'] for w in changed] == ['Hola', 'mundo', 'final']
    assert changed[1]['start'] == pytest.approx(.7)
    assert changed[2]['end'] == pytest.approx(1.9)
    assert words[1]['start'] == 3
    with pytest.raises(ValueError, match='intersects'):
        cut_words(words, [[400, 2900]], 1000, 6)


@pytest.mark.parametrize('cuts', [[], [[2, 1]], [[1, 7000]], [[1, 100], [50, 200]], [[False, 100]]])
def test_invalid_cuts_are_rejected(cuts):
    with pytest.raises(ValueError):
        cut_words([{'word': 'hola', 'start': .1, 'end': .5}], cuts, 1000, 6)


@pytest.mark.parametrize('cuts', [[(1.1, 2.9)], [(0, .05), (1.1, 2), (2, 2.85)],
                                 [(1.1, 2), (2.001, 2.9)]])
@pytest.mark.parametrize('tempo', [1.0, .94])
def test_real_cut_new_episode_reuse_and_tamper_detection(tmp_path, cuts, tempo):
    source = tmp_path/'source'
    source.mkdir()
    script = 'Hola mundo.'
    (source/'guion_final.txt').write_text(script)
    (source/'titulo.txt').write_text('Prueba')
    (source/'configuracion.json').write_text('{}')
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=330:duration=4',
                    '-c:a', 'libmp3lame', str(source/'voz.mp3')], check=True)
    words = [{'word': 'Hola', 'start': .1, 'end': 1}, {'word': 'mundo', 'start': 3, 'end': 3.8}]
    (source/'voz.alignment.json').write_text(json.dumps({'method': 'fish_provider_timestamps', 'words': words}))
    settings = Settings(_env_file=None, data_root=tmp_path)
    before = {p.name: digest(p) for p in source.iterdir()}
    repaired = repair_audio(tmp_path, source, 'clean', cuts, settings=settings, reviewer='fixture listener', tempo=tempo)
    assert all(digest(source/name) == sha for name,sha in before.items())
    assert (repaired/'audio_original/voz.mp3').read_bytes() == (source/'voz.mp3').read_bytes()
    narration = prepare_narration(repaired, root=tmp_path, settings=settings)
    assert narration['alignment_method'] == METHOD
    removed = sum(b-a for a,b in cuts)
    assert narration['words'][1]['start'] == pytest.approx((3-removed)/tempo, abs=1/44100)
    assert narration['duration'] == pytest.approx(2.2/tempo, abs=.07)
    copy = safe_revision(tmp_path, repaired, 'test')
    assert prepare_narration(copy, root=tmp_path, settings=settings)['words'] == narration['words']
    with pytest.raises(ValueError, match='absent destination'):
        repair_audio(tmp_path, source, 'clean', [(1.1,2.9)], settings=settings, reviewer='fixture')
    path = repaired/'voz.alignment.json'
    data = json.loads(path.read_text())
    if tempo == 1:
        # Existing cut-only receipts have no tempo field.
        del data['audio_edit']['tempo']
        path.write_text(json.dumps(data))
        assert _provider_segments(path, script, narration['duration']) == narration['words']
    else:
        data['audio_edit']['tempo'] = 1
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError, match='invalid full-transcript'):
            _provider_segments(path, script, narration['duration'])
        data['audio_edit']['tempo'] = tempo
    data['words'][1]['start'] += .1
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='invalid full-transcript'):
        _provider_segments(path, script, narration['duration'])


def test_cutting_words_never_creates_destination(tmp_path):
    source = tmp_path/'source'
    source.mkdir()
    for name, text in [('guion_final.txt', 'Hola'), ('titulo.txt', 'Prueba'), ('configuracion.json','{}')]:
        (source/name).write_text(text)
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=2',
                    '-c:a', 'libmp3lame', str(source/'voz.mp3')], check=True)
    (source/'voz.alignment.json').write_text(json.dumps({'method': 'fish_provider_timestamps',
                   'words': [{'word': 'Hola', 'start': .1, 'end': 1}]}))
    with pytest.raises(ValueError, match='intersects'):
        repair_audio(tmp_path, source, 'clean', [(.5, 1.5)], settings=Settings(_env_file=None), reviewer='test')
    assert not (tmp_path/'clean').exists()


@pytest.mark.parametrize('tempo', [True, None, '0.94', float('nan'), float('inf'), .89, 1.11])
def test_invalid_tempo_is_rejected(tempo):
    with pytest.raises(ValueError, match='Tempo'):
        cut_words([{'word': 'hola', 'start': .1, 'end': .5}], [[600, 900]], 1000, 2, tempo=tempo)
