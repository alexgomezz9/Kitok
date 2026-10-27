import copy
import json
import math
from pathlib import Path
import subprocess
import wave

import pytest

from kitok.youtube_stickman_es.audio_autoclean import plan_autocuts, apply_autocuts
from kitok.youtube_stickman_es.files import digest


def recognition(words=None, *, duration=6, audio_sha='a'*64):
    words = words or [('Jason', .1, .5), ('llegó', .6, 1), ('bla', 1.3, 1.6),
                      ('al', 2, 2.3), ('lago', 2.4, 2.8)]
    return {'text': ' '.join(w for w, _, _ in words), 'duration': duration,
            'segments': [{'text': w, 'start': a, 'end': b} for w, a, b in words],
            'identity': {'audio_sha256': audio_sha, 'engine': 'independent-test-asr',
                         'model_files': {'model.bin': 'b'*64}}}


def test_insertion_is_planned_between_exact_script_anchors_without_inventing_word_times():
    plan = plan_autocuts('Jason llegó al lago.', recognition())
    cut, = plan['cuts']
    assert cut['recognized'] == 'bla'
    assert cut['left_anchor'] == ['jason', 'llego']
    assert cut['right_anchor'] == ['al', 'lago']
    assert cut['start_sample'] == 49920  # left script word end + 40ms
    assert cut['end_sample'] == 94080  # right script word start - 40ms
    assert len(plan['matched_script_words']) == 4
    assert plan['requires_second_pass'] and not plan['automatic_acceptance']
    assert not plan['acoustic_sync_verified']


def test_acoustic_silence_boundaries_remove_prefix_outside_asr_core():
    plan = plan_autocuts('Jason llegó al lago.', recognition(),
                        silences=[(1.04, 1.12), (1.75, 1.85)])
    cut, = plan['cuts']
    assert cut['start_sample']/48000 == pytest.approx(1.08)
    assert cut['end_sample']/48000 == pytest.approx(1.8)
    assert cut['boundary_method'] == 'measured_silence_midpoints'


def test_replacement_and_omission_remain_unresolved_without_cuts():
    for heard in [recognition([('Jason', .1, .5), ('murió', .6, 1), ('al', 2, 2.3), ('lago', 2.4, 2.8)]),
                  recognition([('Jason', .1, .5), ('al', 2, 2.3), ('lago', 2.4, 2.8)])]:
        plan = plan_autocuts('Jason llegó al lago.', heard)
        assert plan['cuts'] == []
        assert plan['unresolved'][0]['reason'] == 'replacement_or_omission_requires_review'


def test_touching_word_timestamps_and_insufficient_anchors_are_blocked():
    heard = recognition()
    heard['segments'][1]['end'] = 1.3
    assert not plan_autocuts('Jason llegó al lago.', heard)['cuts']
    plan = plan_autocuts('Jason al lago.', recognition([('Jason', .1, .5), ('bla', 1.3, 1.6),
                                                     ('al', 2, 2.3), ('lago', 2.4, 2.8)]))
    assert not plan['cuts']


def test_protected_provider_word_can_veto_otherwise_possible_cut():
    plan = plan_autocuts('Jason llegó al lago.', recognition(),
                        protected_words=[{'start': 1.5, 'end': 1.8}])
    assert not plan['cuts']
    assert plan['unresolved'][0]['reason'] == 'cut_intersects_protected_provider_word'


def test_no_special_vocabulary_or_name_denylist_is_required():
    heard = recognition()
    heard['segments'][2]['text'] = 'Monet'
    heard['text'] = 'Jason llegó Monet al lago'
    assert plan_autocuts('Jason llegó al lago.', heard)['cuts'][0]['recognized'] == 'monet'
    assert not plan_autocuts('Jason llegó Monet al lago.', heard)['cuts']


def test_repeated_context_does_not_guess_which_occurrence_is_correct():
    data = recognition([('Jason', .1, .4), ('llegó', .5, .8), ('bla', 1, 1.2),
                        ('al', 1.4, 1.6), ('lago', 1.7, 2), ('Jason', 2.2, 2.5),
                        ('llegó', 2.6, 2.9), ('al', 3.2, 3.5), ('lago', 3.6, 4)])
    plan = plan_autocuts('Jason llegó al lago. Jason llegó al lago.', data)
    assert not plan['cuts']
    assert plan['unresolved'][0]['reason'] == 'repeated_script_context_is_ambiguous'


@pytest.mark.parametrize('mutate', [
    lambda d: d.update(identity=[]),
    lambda d: d['identity'].update(audio_sha256='wrong'),
    lambda d: d['identity'].pop('model_files'),
    lambda d: d.update(duration=float('nan')),
    lambda d: d.update(text='different'),
    lambda d: d['segments'][1].update(start=-1),
    lambda d: d['segments'][1].update(end=float('inf')),
])
def test_malformed_or_unbound_recognition_never_creates_plan(mutate):
    data = recognition()
    mutate(data)
    with pytest.raises(ValueError):
        plan_autocuts('Jason llegó al lago.', data)


def make_audio(path):
    # A real PCM fixture whose frame counts are exact and quickly verifiable.
    import struct
    with wave.open(str(path), 'wb') as target:
        target.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
        target.writeframes(b''.join(struct.pack('<h', int(3000*math.sin(2*math.pi*330*i/48000)))
                                   for i in range(6*48000)))


def test_real_pcm_cut_preserves_source_and_is_exact_idempotent_and_hash_bound(tmp_path):
    audio = tmp_path/'source.wav'
    make_audio(audio)
    sha = digest(audio)
    plan = plan_autocuts('Jason llegó al lago.', recognition(audio_sha=sha))
    receipt = apply_autocuts(audio, tmp_path/'edited', plan)
    assert digest(audio) == sha
    assert receipt['status'] == 'edited_requires_second_pass'
    assert receipt['maximum_seam_fade_seconds'] == .005
    with wave.open(receipt['audio_path']) as stream:
        assert stream.getnframes() == 6*48000 - (94080-49920)
    assert apply_autocuts(audio, tmp_path/'edited', plan) == receipt
    Path(receipt['audio_path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='differs'):
        apply_autocuts(audio, tmp_path/'edited', plan)


def test_mutated_plan_or_input_never_replaces_source_or_existing_output(tmp_path):
    audio = tmp_path/'source.wav'
    make_audio(audio)
    original = digest(audio)
    plan = plan_autocuts('Jason llegó al lago.', recognition(audio_sha=original))
    corrupt = copy.deepcopy(plan)
    corrupt['cuts'][0]['start_sample'] = 0
    with pytest.raises(ValueError, match='plan changed'):
        apply_autocuts(audio, tmp_path/'edited', corrupt)
    assert not (tmp_path/'edited').exists()
    audio.write_bytes(b'changed')
    with pytest.raises(ValueError, match='Raw audio differs'):
        apply_autocuts(audio, tmp_path/'edited', plan)
    audio.write_bytes(b'not the initial source')
    (tmp_path/'edited').mkdir()
    (tmp_path/'edited'/'operator.txt').write_text('preserve')
    with pytest.raises(ValueError):
        apply_autocuts(audio, tmp_path/'edited', plan)
    assert (tmp_path/'edited'/'operator.txt').read_text() == 'preserve'


def test_partial_output_and_symlinks_are_not_adopted(tmp_path):
    audio = tmp_path/'source.wav'
    make_audio(audio)
    plan = plan_autocuts('Jason llegó al lago.', recognition(audio_sha=digest(audio)))
    (tmp_path/'partial').mkdir()
    with pytest.raises(ValueError, match='Incomplete'):
        apply_autocuts(audio, tmp_path/'partial', plan)
    (tmp_path/'linked').symlink_to(tmp_path/'partial', target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        apply_autocuts(audio, tmp_path/'linked', plan)


def test_destination_race_preserves_other_writer_and_blocks_promotion(tmp_path, monkeypatch):
    audio = tmp_path/'source.wav'
    make_audio(audio)
    plan = plan_autocuts('Jason llegó al lago.', recognition(audio_sha=digest(audio)))
    destination = tmp_path/'edited'
    real_run = subprocess.run
    def concurrent(*args, **kwargs):
        result = real_run(*args, **kwargs)
        if '-filter_complex' in args[0]:
            destination.mkdir()
            (destination/'other.txt').write_text('preserve concurrent work')
        return result
    monkeypatch.setattr('kitok.youtube_stickman_es.audio_autoclean.subprocess.run', concurrent)
    with pytest.raises(FileExistsError, match='appeared'):
        apply_autocuts(audio, destination, plan)
    assert (destination/'other.txt').read_text() == 'preserve concurrent work'


def test_source_race_blocks_promotion_and_missing_second_pass_never_claims_clean(tmp_path, monkeypatch):
    audio = tmp_path/'source.wav'
    make_audio(audio)
    plan = plan_autocuts('Jason llegó al lago.', recognition(audio_sha=digest(audio)))
    real_run = subprocess.run
    def concurrent(*args, **kwargs):
        result = real_run(*args, **kwargs)
        if '-filter_complex' in args[0]:
            audio.write_bytes(b'changed by another writer')
        return result
    monkeypatch.setattr('kitok.youtube_stickman_es.audio_autoclean.subprocess.run', concurrent)
    with pytest.raises(ValueError, match='changed during'):
        apply_autocuts(audio, tmp_path/'edited', plan)
    assert not (tmp_path/'edited').exists()


def refinement(tmp_path, raw, *, i=2):
    clip = tmp_path/'window.wav'
    clip.write_bytes(b'bounded independent ASR clip fixture')
    return {'script_range': [i, i], 'source_audio_sha256': raw['identity']['audio_sha256'],
            'source_asr_sha256': digest(raw), 'window_audio_path': str(clip),
            'window_audio_sha256': digest(clip), 'offset': 0, 'duration': 6,
            'engine': raw['identity']['engine'], 'model_files': raw['identity']['model_files'],
            'result': {k: v for k, v in recognition().items() if k != 'identity'}}


def test_independent_window_can_resolve_a_touching_full_record_without_rewriting_it(tmp_path):
    raw = recognition()
    raw['segments'][1]['end'] = 1.3
    original = copy.deepcopy(raw)
    assert not plan_autocuts('Jason llegó al lago.', raw)['cuts']
    plan = plan_autocuts('Jason llegó al lago.', raw, windows=[refinement(tmp_path, raw)])
    assert len(plan['cuts']) == 1
    assert plan['cuts'][0]['boundary_method'] == 'independent_asr_window'
    assert not plan['unresolved']
    assert plan['window_evidence'][0]['refinement_accepted'] is True
    assert plan['matched_script_words'][1]['end'] == 1
    assert raw == original


@pytest.mark.parametrize('field,value', [('source_audio_sha256', 'wrong'), ('source_asr_sha256', 'wrong'),
                                       ('engine', 'wrong'), ('window_audio_sha256', 'wrong')])
def test_refinements_cannot_be_reused_for_other_evidence(tmp_path, field, value):
    raw = recognition()
    raw['segments'][1]['end'] = 1.3
    data = refinement(tmp_path, raw)
    data[field] = value
    with pytest.raises(ValueError):
        plan_autocuts('Jason llegó al lago.', raw, windows=[data])


def test_window_without_exact_anchor_does_not_force_a_cut(tmp_path):
    raw = recognition()
    raw['segments'][1]['end'] = 1.3
    data = refinement(tmp_path, raw)
    data['result']['segments'][1]['text'] = 'murió'
    data['result']['text'] = 'Jason murió bla al lago'
    plan = plan_autocuts('Jason llegó al lago.', raw, windows=[data])
    assert not plan['cuts']
    assert plan['window_evidence'][0]['refinement_accepted'] is False


def test_changed_receipt_status_is_not_reused_as_a_clean_audio(tmp_path):
    audio = tmp_path/'source.wav'
    make_audio(audio)
    plan = plan_autocuts('Jason llegó al lago.', recognition(audio_sha=digest(audio)))
    output = tmp_path/'edited'
    apply_autocuts(audio, output, plan)
    receipt = json.loads((output/'receipt.json').read_text())
    receipt['status'] = 'clean'
    (output/'receipt.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='differs'):
        apply_autocuts(audio, output, plan)


def test_window_can_extend_an_existing_candidate_to_remove_remaining_syllable(tmp_path):
    raw = recognition()
    data = refinement(tmp_path, raw)
    data['result']['segments'][1]['end'] = .9
    data['result']['segments'][3]['start'] = 2.1
    data['result']['segments'][2]['start'] = 1.15
    data['result']['segments'][2]['end'] = 1.8
    original = plan_autocuts('Jason llegó al lago.', raw)['cuts'][0]
    updated = plan_autocuts('Jason llegó al lago.', raw, windows=[data])['cuts'][0]
    assert updated['start_sample'] < original['start_sample']
    assert updated['end_sample'] > original['end_sample']


def test_duplicate_refinements_do_not_choose_between_conflicting_windows(tmp_path):
    raw = recognition()
    data = refinement(tmp_path, raw)
    with pytest.raises(ValueError, match='duplicate'):
        plan_autocuts('Jason llegó al lago.', raw, windows=[data, data])


def test_model_identity_requires_hashes_instead_of_unbound_labels():
    raw = recognition()
    raw['identity']['model_files']['model.bin'] = 'not-a-model-hash'
    with pytest.raises(ValueError, match='model hashes'):
        plan_autocuts('Jason llegó al lago.', raw)


@pytest.mark.parametrize('bad_range', [[True, True], [2.0, 2.0], [2, 3], [['bad'], ['bad']]])
def test_malformed_refinement_ranges_are_rejected(tmp_path, bad_range):
    raw = recognition()
    data = refinement(tmp_path, raw)
    data['script_range'] = bad_range
    with pytest.raises(ValueError, match='Ambiguous or duplicate'):
        plan_autocuts('Jason llegó al lago.', raw, windows=[data])



def test_automatic_cut_keeps_full_anchor_guard_and_removes_syllables_outside_asr_core():
    plan = plan_autocuts('Jason llegó al lago.', recognition())
    cut, = plan['cuts']
    # Invented speech may already begin at1.1s, though ASR only marks1.3s.
    assert cut['start_sample']/48000 <= 1.1
    assert cut['end_sample']/48000 >= 1.9
    assert cut['start_sample']/48000 >= 1 + .04
    assert cut['end_sample']/48000 <= 2 - .04


def test_insufficient_guard_never_forces_a_two_millisecond_gap():
    raw = recognition()
    raw['segments'][1]['end'] = 1.29  # Only10ms before recognized insertion.
    plan = plan_autocuts('Jason llegó al lago.', raw)
    assert not plan['cuts']
    assert plan['unresolved'][0]['reason'] == 'no_separation_from_script_word_timestamps'



def test_silence_boundaries_near_anchors_keep_no_unmatched_prefix_or_suffix():
    plan = plan_autocuts('Jason llegó al lago.', recognition(), silences=[
        (1.04, 1.12), (1.15, 1.2), (1.75, 1.85), (1.88, 1.92)])
    cut, = plan['cuts']
    assert cut['start_sample']/48000 == pytest.approx(1.08)
    assert cut['end_sample']/48000 == pytest.approx(1.9)



@pytest.mark.parametrize('field,value', [('removed_samples', []), ('sample_rate', 8000),
                                       ('output_frames', 1), ('audio_path', '/other/audio.wav')])
def test_reuse_checks_timing_receipt_not_only_the_audio_hash(tmp_path, field, value):
    audio = tmp_path/'source.wav'
    make_audio(audio)
    plan = plan_autocuts('Jason llegó al lago.', recognition(audio_sha=digest(audio)))
    output = tmp_path/'edited'
    apply_autocuts(audio, output, plan)
    receipt = json.loads((output/'receipt.json').read_text())
    receipt[field] = value
    (output/'receipt.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        apply_autocuts(audio, output, plan)
