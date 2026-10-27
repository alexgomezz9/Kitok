"""Real FFmpeg burn/audio checks, with editorial QA isolated from this fixture."""
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from kitok.config import Settings
from kitok.editing.quality import decoded_audio_hash
from kitok.media.ffprobe import probe_video_clock
from kitok.media.ffmpeg import EncoderSettings
from kitok.youtube_stickman_es import pipeline, subtitle_delivery
from kitok.youtube_stickman_es.files import digest


@pytest.fixture
def delivery(tmp_path, monkeypatch):
    folder = tmp_path / 'episode'
    folder.mkdir()
    base = folder / 'video_final.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                    'color=c=gray:s=1920x1080:r=30:d=1', '-f', 'lavfi', '-i',
                    'sine=frequency=330:sample_rate=48000:duration=1', '-c:v', 'libx264',
                    '-preset', 'ultrafast', '-threads', '2', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', str(base)], capture_output=True, check=True, timeout=60)
    (folder / 'guion_final.txt').write_text('Una prueba clara.')
    (folder / 'voz.mp3').write_bytes(b'validated narration fixture')
    (folder / 'voz.alignment.json').write_text('{}')
    (folder / 'qa.json').write_text(json.dumps({'technical_status': 'passed', 'video_sha256': digest(base)}))
    words = [{'word': word, 'start': start, 'end': end}
             for word, start, end in [('Una', .1, .3), ('prueba', .35, .6), ('clara', .65, .9)]]
    narration = {'words': words, 'duration': 1., 'script_sha256': digest(folder / 'guion_final.txt'),
                 'audio_sha256': digest(folder / 'voz.mp3'),
                 'alignment_sha256': digest(folder / 'voz.alignment.json')}
    plan = SimpleNamespace(duration=1., narration_duration=1., scenes=[])
    plan.model_dump = lambda: {'duration': 1., 'fixture': True}
    config = SimpleNamespace(voice=SimpleNamespace(model_dump=lambda: {}), fade_in=.6, fade_out=.8)
    monkeypatch.setattr(pipeline, 'current', lambda episode: (plan, config, None))

    def existing_narration(*args, **kwargs):
        assert kwargs['generate'] is False
        return narration
    monkeypatch.setattr(subtitle_delivery, 'prepare_narration', existing_narration)
    calls = []

    def fixture_qa(video, output, **kwargs):
        calls.append(video)
        return {'technical_status': 'passed', 'video_sha256': digest(video)}
    monkeypatch.setattr(subtitle_delivery, 'inspect_delivery', fixture_qa)
    monkeypatch.setattr(subtitle_delivery, 'choose_encoder',
                        lambda *args, **kwargs: EncoderSettings('libx264', 'medium'))
    settings = Settings(_env_file=None, data_root=tmp_path, ready_dir=tmp_path / 'ready')
    return tmp_path, folder, settings, narration, calls


def run(delivery, **kwargs):
    root, folder, settings, _, _ = delivery
    return subtitle_delivery.caption_video(folder, root=root, settings=settings, **kwargs)


def test_real_burn_has_exact_clock_and_identical_audio_and_reuses_complete_output(delivery):
    root, folder, _, _, calls = delivery
    before = digest(folder / 'video_final.mp4')
    result = run(delivery)
    video = root / result['video']
    assert result['technical_status'] == 'passed' and result['human_review_required']
    assert result['provider_requests'] == 0 and result['new_voice_requested'] is False
    assert probe_video_clock(video).frames == 30
    assert decoded_audio_hash(video) == decoded_audio_hash(folder / 'video_final.mp4')
    assert digest(video) != before and digest(folder / 'video_final.mp4') == before
    receipt = json.loads((root / result['receipt']).read_text())
    assert receipt['identity']['base_video_sha256'] == before
    assert receipt['identity']['ass_sha256'] == digest(root / result['subtitles'])
    assert receipt['identity']['encoder']['codec'] == 'libx264'
    assert receipt['identity']['encoder']['preset'] == 'fast'
    assert receipt['identity']['encoder']['cq'] == 20
    original = digest(video)
    assert run(delivery) == result
    assert digest(video) == original and len(calls) == 1


@pytest.mark.parametrize('change', ['rejected', 'wrong_digest'])
def test_base_qa_must_match_passed_video(delivery, change):
    _, folder, _, _, _ = delivery
    qa = {'technical_status': 'rejected' if change == 'rejected' else 'passed',
          'video_sha256': 'wrong' if change == 'wrong_digest' else digest(folder / 'video_final.mp4')}
    (folder / 'qa.json').write_text(json.dumps(qa))
    with pytest.raises(ValueError, match='passed QA'):
        run(delivery)
    assert not (folder / 'subtitles.ass').exists()
    assert not (folder / 'video_subtitulado.mp4').exists()


def test_missing_real_word_times_cannot_estimate_or_generate_voice(delivery):
    _, folder, _, narration, _ = delivery
    narration.pop('words')
    with pytest.raises(ValueError, match='existing validated word alignment'):
        run(delivery)
    assert not (folder / 'subtitles.ass').exists()


def test_changed_ass_is_preserved(delivery):
    _, folder, _, _, _ = delivery
    ass = folder / 'subtitles.ass'
    ass.write_text('operator captions')
    with pytest.raises(FileExistsError):
        run(delivery)
    assert ass.read_text() == 'operator captions'
    assert not (folder / 'video_subtitulado.mp4').exists()


def test_existing_video_without_complete_receipt_cannot_be_overwritten(delivery):
    _, folder, _, _, _ = delivery
    output = folder / 'video_subtitulado.mp4'
    output.write_bytes(b'operator output')
    with pytest.raises(ValueError, match='Incomplete caption delivery'):
        run(delivery)
    assert output.read_bytes() == b'operator output'


def test_failed_qa_preserves_staged_video_and_original(delivery, monkeypatch):
    _, folder, _, _, _ = delivery
    before = digest(folder / 'video_final.mp4')
    monkeypatch.setattr(subtitle_delivery, 'inspect_delivery',
                        lambda *args, **kwargs: {'technical_status': 'rejected'})
    with pytest.raises(ValueError, match='QA rejected'):
        run(delivery)
    assert digest(folder / 'video_final.mp4') == before
    assert not (folder / 'video_subtitulado.mp4').exists()
    assert list((folder / '.stickman/caption-work').glob('*/video_subtitulado.mp4'))


def test_revision_selects_matching_base_and_separate_outputs(delivery):
    _, folder, _, _, _ = delivery
    (folder / 'video_final.mp4').rename(folder / 'video_final__v2.mp4')
    (folder / 'qa.json').rename(folder / 'qa__v2.json')
    result = run(delivery, revision='v2')
    assert result['video'].endswith('video_subtitulado__v2.mp4')
    assert result['subtitles'].endswith('subtitles__v2.ass')
    with pytest.raises(ValueError, match='short lowercase ID'):
        run(delivery, revision='../unsafe')


def test_runtime_selected_nvenc_uses_p5_and_existing_encoder_arguments(delivery, monkeypatch):
    _, folder, _, _, _ = delivery
    selected = []

    def nvenc(ffmpeg, **kwargs):
        selected.append((ffmpeg, kwargs))
        return EncoderSettings('h264_nvenc', kwargs['nvenc_preset'])
    monkeypatch.setattr(subtitle_delivery, 'choose_encoder', nvenc)
    original_run = subprocess.run

    def observe(command, **kwargs):
        if '-vf' in command and 'ass=' in command[command.index('-vf') + 1]:
            assert command[command.index('-c:v') + 1] == 'h264_nvenc'
            assert command[command.index('-preset') + 1] == 'p5'
            assert command[command.index('-cq') + 1] == '18'
            assert command[command.index('-multipass') + 1] == 'fullres'
            assert command[command.index('-c:a') + 1] == 'copy'
            raise RuntimeError('NVENC command inspected without requiring GPU in test')
        return original_run(command, **kwargs)
    monkeypatch.setattr(subtitle_delivery.subprocess, 'run', observe)
    with pytest.raises(RuntimeError, match='NVENC command inspected'):
        run(delivery)
    assert selected == [('ffmpeg', {'nvenc_preset': 'p5'})]
    assert not (folder / 'video_subtitulado.mp4').exists()


def test_completed_delivery_reuses_recorded_encoder_without_probing_current_gpu(delivery, monkeypatch):
    root, _, _, _, _ = delivery
    result = run(delivery)
    original = digest(root / result['video'])
    receipt_before = (root / result['receipt']).read_bytes()

    def changed_availability(*args, **kwargs):
        pytest.fail('A completed output must not probe or select a new runtime encoder')
    monkeypatch.setattr(subtitle_delivery, 'choose_encoder', changed_availability)
    assert run(delivery) == result
    assert digest(root / result['video']) == original
    assert (root / result['receipt']).read_bytes() == receipt_before


def test_interrupted_caption_qa_resumes_same_encoding_without_gpu_probe(delivery, monkeypatch):
    _, folder, _, _, calls = delivery
    original_qa = subtitle_delivery.inspect_delivery
    monkeypatch.setattr(subtitle_delivery, 'inspect_delivery',
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('interrupted during QA')))
    with pytest.raises(RuntimeError, match='interrupted during QA'):
        run(delivery)
    staged = list((folder / '.stickman/caption-work').glob('*/video_subtitulado.mp4'))
    assert len(staged) == 1
    encoded_sha = digest(staged[0])
    assert (staged[0].parent / 'encoded.json').exists()
    monkeypatch.setattr(subtitle_delivery, 'inspect_delivery', original_qa)
    monkeypatch.setattr(subtitle_delivery, 'choose_encoder',
                        lambda *a, **kw: pytest.fail('Recovering a completed encoding must not probe the GPU'))
    result = run(delivery)
    assert result['technical_status'] == 'passed'
    assert digest(folder / 'video_subtitulado.mp4') == encoded_sha
    assert len(calls) == 1
    assert list((folder / '.stickman/caption-work').glob('*/video_subtitulado.mp4')) == staged


def test_corrupt_preserved_encoding_blocks_instead_of_reencoding(delivery, monkeypatch):
    _, folder, _, _, _ = delivery
    monkeypatch.setattr(subtitle_delivery, 'inspect_delivery',
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('interrupted')))
    with pytest.raises(RuntimeError, match='interrupted'):
        run(delivery)
    staged = next((folder / '.stickman/caption-work').glob('*/video_subtitulado.mp4'))
    staged.write_bytes(b'changed preserved encoding')
    monkeypatch.setattr(subtitle_delivery, 'choose_encoder',
                        lambda *a, **kw: pytest.fail('Corruption must not trigger an encode'))
    with pytest.raises(ValueError, match='encoding changed'):
        run(delivery)
    assert staged.read_bytes() == b'changed preserved encoding'
    assert not (folder / 'video_subtitulado.mp4').exists()
