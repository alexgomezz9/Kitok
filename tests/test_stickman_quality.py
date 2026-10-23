"""Real acoustic probes: sustained gaps must remain visible under background music."""
import json
import math
import struct
import wave

import pytest

from kitok.config import Settings
from kitok.youtube_stickman_es.quality import inspect_audio_continuity, silence_intervals


def tone(path, *, gap=False, trailing=False):
    with wave.open(str(path), 'wb') as audio:
        audio.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b''.join(struct.pack('<h',
            0 if gap and 1 <= n/8000 < 3 or trailing and n/8000 >= 2
            else round(4000*math.sin(2*math.pi*220*n/8000))) for n in range(32000)))


def test_source_gap_is_flagged_even_when_music_masks_final_mix(tmp_path):
    settings = Settings(_env_file=None, data_root=tmp_path)
    narration, final = tmp_path/'voice.wav', tmp_path/'mix.wav'
    tone(narration, gap=True)
    tone(final)
    report = inspect_audio_continuity(final, narration, settings=settings)
    assert report['status'] == 'human_review_required'
    assert report['tracks']['final_mix']['quiet_intervals'] == []
    interval, = report['tracks']['source_narration']['quiet_intervals']
    assert abs(interval['start']-1) < .01 and abs(interval['end']-3) < .01
    assert 'intentional pauses' in report['limitation']


def test_continuous_audio_and_trailing_silence_are_distinguished(tmp_path):
    settings = Settings(_env_file=None, data_root=tmp_path)
    source = tmp_path/'voice.wav'
    tone(source)
    assert inspect_audio_continuity(source, source, settings=settings)['status'] == 'no_long_silence_detected'
    tone(source, trailing=True)
    interval, = silence_intervals(source, settings=settings)
    assert abs(interval['start']-2) < .01 and abs(interval['end']-4) < .01


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('outcome', ['passed', 'rejected', 'interrupted'])
def test_final_report_is_published_only_after_all_checks(tmp_path, monkeypatch, existing, outcome):
    """A watcher must never mistake the base measurements for a final verdict."""
    from types import SimpleNamespace
    from kitok.editing import quality as measurements
    from kitok.youtube_stickman_es import quality

    output = tmp_path / 'qa.json'
    previous = {'technical_status': 'passed', 'video_sha256': 'previous-video'}
    if existing:
        output.write_text(json.dumps(previous))

    def assert_unpublished():
        if existing:
            assert json.loads(output.read_text()) == previous
        else:
            assert not output.exists(), 'Partial measurements exposed as final QA'

    monkeypatch.setattr(measurements, 'probe_media', lambda *args: SimpleNamespace(
        video_codec='h264', audio_codec='aac', duration=1, width=1920, height=1080, fps=30))
    frames = [{'best_effort_timestamp_time': str(i / 30), 'pix_fmt': 'yuv420p'} for i in range(30)]
    monkeypatch.setattr(measurements.subprocess, 'run', lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stderr='', stdout=json.dumps({'frames': frames})))
    monkeypatch.setattr(measurements, 'measure_loudness', lambda *args:
                        {'integrated_lufs': -16, 'true_peak_dbtp': -1 if outcome == 'rejected' else -2})
    monkeypatch.setattr(measurements, 'stream_durations', lambda *args: (1, 1))
    monkeypatch.setattr(measurements, 'decoded_audio_hash', lambda *args: 'audio-digest')
    monkeypatch.setattr(measurements, 'file_hash', lambda *args: 'video-digest')
    monkeypatch.setattr(measurements, 'contact_sheet', lambda *args, **kwargs: None)

    def continuity(*args, **kwargs):
        assert_unpublished()
        if outcome == 'interrupted':
            raise RuntimeError('Continuity check interrupted')
        return {'status': 'no_long_silence_detected'}

    monkeypatch.setattr(quality, 'inspect_audio_continuity', continuity)
    plan = SimpleNamespace(duration=1, narration_duration=1, scenes=[])
    settings = Settings(_env_file=None, data_root=tmp_path)
    if outcome == 'interrupted':
        with pytest.raises(RuntimeError, match='Continuity check interrupted'):
            quality.inspect_delivery(tmp_path/'video.mp4', output, plan=plan,
                                     settings=settings, narration=tmp_path/'voice.wav')
        assert_unpublished()
    else:
        result = quality.inspect_delivery(tmp_path/'video.mp4', output, plan=plan,
                                          settings=settings, narration=tmp_path/'voice.wav')
        assert json.loads(output.read_text()) == result
        assert result['technical_status'] == outcome
        assert result['video_sha256'] == 'video-digest'
