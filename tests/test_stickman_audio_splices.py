import json
import math
from pathlib import Path
import struct
import subprocess
import wave

import pytest

from kitok.youtube_stickman_es.audio_splices import apply_splices
from kitok.youtube_stickman_es.files import digest


def tone(path, seconds, *, rate=48000, frequency=220):
    with wave.open(str(path), 'wb') as target:
        target.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        target.writeframes(b''.join(struct.pack('<h', int(3000*math.sin(2*math.pi*frequency*i/rate)))
                                   for i in range(round(seconds*rate))))


@pytest.fixture
def source(tmp_path):
    path = tmp_path/'source.wav'
    tone(path, 4)
    return path


def test_real_cuts_and_replacements_share_one_pcm_clock_and_keep_sources(source, tmp_path):
    clip = tmp_path/'replacement.wav'
    tone(clip, .5, rate=22050, frequency=550)
    before = {p: digest(p) for p in [source, clip]}
    operations = [
        {'start_sample': 48000, 'end_sample': 72000, 'reason': 'independent ASR confirmed insertion'},
        {'start_sample': 96000, 'end_sample': 144000, 'replacement_path': str(clip),
         'replacement_sha256': digest(clip), 'reason': 'reviewed missing phrase', 'evidence': {'asr': 'matched'}}]
    receipt = apply_splices(source, tmp_path/'edit', operations, source_audio_sha256=digest(source))
    assert receipt['output_frames'] == 3*48000
    assert receipt['requires_second_pass'] and not receipt['acoustic_sync_verified']
    assert [row['kind'] for row in receipt['mapping']] == ['source', 'cut', 'source', 'replacement', 'source']
    assert receipt['mapping'][3]['output_samples'] == [72000, 96000]
    assert all(digest(path) == sha for path, sha in before.items())
    assert apply_splices(source, tmp_path/'edit', operations) == receipt
    with wave.open(receipt['audio_path']) as output:
        assert (output.getnframes(), output.getframerate()) == (144000, 48000)


@pytest.mark.parametrize('operations', [[], [None],
    [{'start_sample': True, 'end_sample': 100, 'reason': 'invalid'}],
    [{'start_sample': 100, 'end_sample': 99, 'reason': 'invalid'}],
    [{'start_sample': 100, 'end_sample': 200}],
    [{'start_sample': 100, 'end_sample': 200, 'reason': ' ' }],
    [{'start_sample': 0, 'end_sample': 1000000, 'reason': 'outside'}],
    [{'start_sample': 100, 'end_sample': 200, 'reason': 'first'},
     {'start_sample': 150, 'end_sample': 300, 'reason': 'overlap'}]])
def test_invalid_operation_cannot_create_a_published_output(source, tmp_path, operations):
    with pytest.raises(ValueError):
        apply_splices(source, tmp_path/'edit', operations)
    assert not (tmp_path/'edit').exists()


def test_replacement_hash_and_original_hash_are_required_and_checked(source, tmp_path):
    clip = tmp_path/'replacement.wav'
    tone(clip, .5)
    operation = {'start_sample': 100, 'end_sample': 200, 'reason': 'fixture',
                 'replacement_path': str(clip), 'replacement_sha256': 'wrong'}
    with pytest.raises(ValueError, match='Replacement audio differs'):
        apply_splices(source, tmp_path/'edit', [operation])
    with pytest.raises(ValueError, match='Original narration differs'):
        apply_splices(source, tmp_path/'edit', [{'start_sample': 100, 'end_sample': 200, 'reason': 'fixture'}],
                      source_audio_sha256='wrong')


def test_entire_cut_and_unused_hash_are_rejected(source, tmp_path):
    with pytest.raises(ValueError, match='entire narration'):
        apply_splices(source, tmp_path/'edit', [{'start_sample': 0, 'end_sample': 4*48000, 'reason': 'all'}])
    with pytest.raises(ValueError, match='unused replacement hash'):
        apply_splices(source, tmp_path/'edit', [{'start_sample': 100, 'end_sample': 200,
                      'reason': 'fixture', 'replacement_sha256': 'not used'}])


def test_existing_partial_output_and_symlinks_are_preserved(source, tmp_path):
    operations = [{'start_sample': 100, 'end_sample': 200, 'reason': 'fixture'}]
    partial = tmp_path/'edit'
    partial.mkdir()
    (partial/'operator.txt').write_text('preserve')
    with pytest.raises(ValueError, match='Incomplete'):
        apply_splices(source, partial, operations)
    linked = tmp_path/'linked'
    linked.symlink_to(partial, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        apply_splices(source, linked, operations)
    assert (partial/'operator.txt').read_text() == 'preserve'


def test_changed_output_or_receipt_is_not_reused(source, tmp_path):
    operations = [{'start_sample': 100, 'end_sample': 200, 'reason': 'fixture'}]
    destination = tmp_path/'edit'
    apply_splices(source, destination, operations)
    path = destination/'receipt.json'
    receipt = json.loads(path.read_text())
    receipt['mapping'][0]['output_samples'][1] += 1
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='differs'):
        apply_splices(source, destination, operations)


def test_a_source_change_during_encoding_blocks_promotion(source, tmp_path, monkeypatch):
    original = subprocess.run
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if '-filter_complex' in args[0]:
            source.write_bytes(b'concurrent change')
        return result
    monkeypatch.setattr('kitok.youtube_stickman_es.audio_splices.subprocess.run', changed)
    with pytest.raises(ValueError, match='changed during'):
        apply_splices(source, tmp_path/'edit', [{'start_sample': 100, 'end_sample': 200, 'reason': 'fixture'}])
    assert not (tmp_path/'edit').exists()
