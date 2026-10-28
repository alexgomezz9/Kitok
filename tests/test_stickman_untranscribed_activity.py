import json
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from kitok.youtube_stickman_es import voice_cleaning
from kitok.youtube_stickman_es.audio_autoclean import plan_autocuts
from kitok.youtube_stickman_es.files import digest, write


SCRIPT = 'Uno dos tres cuatro cinco seis siete ocho.'


def evidence(tmp_path, script=SCRIPT, *, audible=False):
    folder = tmp_path / 'episode'
    folder.mkdir()
    (folder / 'guion_final.txt').write_text(script)
    with wave.open(str(folder / 'voz.mp3'), 'wb') as out:
        out.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
        out.writeframes((b'\x00\x20' if audible else b'\x01\x00') * 182400)
    (folder / 'voz.srt').write_text('original subtitles')
    starts = [.1, .4, .7, 1., 2.4, 2.7, 3., 3.3]
    segments = [{'text': word, 'start': start, 'end': start+.2}
                for word, start in zip(script.split(), starts)]
    asr = {'text': script, 'duration': 3.8, 'segments': segments,
           'identity': {'audio_sha256': digest(folder / 'voz.mp3'),
                        'engine': 'fixture', 'model_files': {'model.bin': 'a'*64}}}
    write(folder / 'voz.alignment.json', {'method': 'fish_provider_timestamps',
          'words': [{'word': s['text'], 'start': s['start'], 'end': s['end']} for s in segments]})
    before = {'identity': asr['identity'], 'status': 'review_required', 'differences': [],
              'alignment_sha256': digest(folder / 'voz.alignment.json'),
              'uncovered_activity': [{'start': 1.32, 'end': 2.28, 'active_seconds': .8}]}
    return folder, asr, before


def augment(folder, asr, before, *, silences=()):
    script = (folder / 'guion_final.txt').read_text()
    plan = plan_autocuts(script, asr, silences=silences)
    return voice_cleaning._activity_cuts(folder, script, asr, before, plan)


def test_exact_script_energy_gap_produces_hash_bound_distinct_cut(tmp_path):
    folder, asr, before = evidence(tmp_path)
    plan = augment(folder, asr, before)
    cut, = plan['cuts']
    assert cut['kind'] == 'untranscribed_activity'
    assert cut['recognized'] == '' and cut['asr_range'] == [4, 4]
    assert cut['left_anchor'] == ['tres', 'cuatro']
    assert cut['right_anchor'] == ['cinco', 'seis']
    assert cut['start_sample'] / 48000 >= 1.32
    assert cut['end_sample'] / 48000 <= 2.28
    assert cut['minimum_active_seconds'] >= .5
    assert plan['asr_sha256'] == digest(asr)
    assert plan['provider_alignment_sha256'] == digest(folder / 'voz.alignment.json')
    assert plan['activity_report_sha256'] == digest(before)
    assert plan['plan_sha256'] == digest({k: v for k, v in plan.items() if k != 'plan_sha256'})
    assert len(plan['matched_script_words']) == len(plan['protected_word_intervals']) == 8


@pytest.mark.parametrize('change', ['missing', 'replace', 'overlap', 'zero_duration'])
def test_differences_or_invalid_individual_word_clock_stay_blocked(tmp_path, change):
    folder, asr, before = evidence(tmp_path)
    if change == 'missing':
        del asr['segments'][2]
    elif change == 'replace':
        asr['segments'][2]['text'] = 'nueve'
    elif change == 'overlap':
        asr['segments'][2]['end'] = 1.05
    else:
        asr['segments'][2]['end'] = asr['segments'][2]['start']
    asr['text'] = ' '.join(row['text'] for row in asr['segments'])
    assert augment(folder, asr, before)['cuts'] == []


def test_provider_words_protect_speech_even_when_asr_omits_it(tmp_path):
    folder, asr, before = evidence(tmp_path)
    path = folder / 'voz.alignment.json'
    provider = json.loads(path.read_text())
    provider['words'][3]['end'] = 1.8
    path.unlink()
    write(path, provider)
    before['alignment_sha256'] = digest(path)
    assert augment(folder, asr, before)['cuts'] == []


def test_repeated_anchor_on_either_side_requires_review(tmp_path):
    folder, asr, before = evidence(tmp_path, 'Uno dos tres cuatro uno dos siete ocho.')
    assert augment(folder, asr, before)['cuts'] == []


@pytest.mark.parametrize('activity', [[], [{'start': 1.32, 'end': 2.28, 'active_seconds': 0}],
    [{'start': 0, 'end': 3.8, 'active_seconds': .8}],
    [{'start': 1.32, 'end': 2.28, 'active_seconds': .8},
     {'start': 0, 'end': .8, 'active_seconds': .6}]])
def test_no_energy_or_unlocated_or_unhandled_activity_cannot_be_accepted(tmp_path, activity):
    folder, asr, before = evidence(tmp_path)
    before['uncovered_activity'] = activity
    assert augment(folder, asr, before, silences=[(1.2, 2.4)])['cuts'] == []


def test_changed_provider_alignment_is_not_used(tmp_path):
    folder, asr, before = evidence(tmp_path)
    before['alignment_sha256'] = 'b'*64
    assert augment(folder, asr, before)['cuts'] == []


def test_measured_activity_helper_accepts_observed_words_without_provider_metadata(tmp_path):
    from kitok.youtube_stickman_es.voice_fidelity import activity_outside_words, uncovered_activity
    folder, asr, before = evidence(tmp_path, audible=True)
    words = voice_cleaning._word_clock(SCRIPT, asr, asr['duration'])
    activity = activity_outside_words(folder / 'voz.mp3', words, ffmpeg='ffmpeg', duration=3.8)
    assert len(activity) == 1 and activity[0]['active_seconds'] > .5
    assert activity == uncovered_activity(folder / 'voz.mp3', folder / 'voz.alignment.json',
                                           ffmpeg='ffmpeg', duration=3.8)


@pytest.mark.parametrize('second_pass_matches,residual', [(True, False), (False, False), (True, True)])
def test_real_pcm_edit_requires_full_second_asr_before_adoption(tmp_path, monkeypatch, second_pass_matches, residual):
    folder, asr, before = evidence(tmp_path, audible=residual)
    original = {path.name: digest(path) for path in folder.iterdir()}
    calls = []

    def verify(destination, *, settings, transcribe, audio_filename='voz.mp3'):
        calls.append(audio_filename)
        if destination == folder:
            result, report = asr, dict(before)
        else:
            with wave.open(str(destination / audio_filename)) as audio:
                duration = audio.getnframes() / audio.getframerate()
            words = SCRIPT.split() if second_pass_matches else SCRIPT.split()[:-1]
            step = duration / len(words)
            result = {'text': ' '.join(words), 'duration': duration, 'segments': [
                {'text': word, 'start': i*step, 'end': (i+.7)*step} for i, word in enumerate(words)]}
            if residual:
                for row, start in zip(result['segments'], [.1, .3, .5, .7, 1.9, 2.1, 2.3, 2.5]):
                    row.update(start=start, end=start+.15)
            report = {'identity': {'audio_sha256': digest(destination / audio_filename)},
                      'status': 'matched' if second_pass_matches else 'review_required',
                      'differences': [] if second_pass_matches else [{'kind': 'delete'}]}
        work = destination / '.stickman/voice-fidelity/fixture'
        write(work / 'asr.json', result)
        report['report_path'] = str(work / 'report.json')
        write(work / 'report.json', report)
        return report

    monkeypatch.setattr(voice_cleaning, 'verify_voice', verify)
    raw = {'audio_sha256': digest(folder / 'voz.mp3'),
           'script_sha256': digest(folder / 'guion_final.txt')}
    result = voice_cleaning.clean_narration(folder,
        settings=SimpleNamespace(ffmpeg_binary='ffmpeg', ffprobe_binary='ffprobe'),
        raw=raw, require_ready=False)
    assert calls == ['voz.mp3', 'audio.wav']
    assert all(digest(folder / name) == value for name, value in original.items())
    active = folder / '.stickman/voice-cleaning/active.json'
    if second_pass_matches and not residual:
        assert result['voice_cleaning']['status'] == 'ready'
        assert active.is_file() and len(result['words']) == 8
        assert voice_cleaning.cleaned_paths(folder, voice_cleaning.MODE)[0] == Path(result['audio_path'])
    else:
        assert result['status'] == 'review_required' and result['cuts_applied'] == 1
        assert not active.exists()
        assert voice_cleaning.cleaned_paths(folder, voice_cleaning.MODE)[0] == folder / 'voz.mp3'
        if residual:
            assert result['remaining_differences'] == []
            assert result['remaining_untranscribed_activity'][0]['active_seconds'] > .5
