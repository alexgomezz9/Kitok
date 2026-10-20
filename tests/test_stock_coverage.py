import math
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from kitok.editing.production import render_editorial_plan, validate_stock_coverage
from kitok.editing.storyboard import EditorialPlan, EditorialScene, EditorialAsset
from kitok.longform.models import TimelineSlot
from kitok.media import ffprobe
from kitok.rendering.native import source_window_duration


def test_measured_video_duration_ignores_longer_audio_and_container(tmp_path):
    path = tmp_path / 'stock.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                    'color=c=green:s=160x90:r=25:d=7.48', '-f', 'lavfi', '-i',
                    'sine=frequency=300:duration=7.53', '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-c:a', 'aac', str(path)], check=True, capture_output=True)
    assert ffprobe.probe_media(path).duration > 7.48
    assert ffprobe.measured_video_duration(path) == pytest.approx(7.48)


@pytest.mark.parametrize('duration', [None, 0., -1., math.nan, math.inf])
def test_unknown_or_invalid_video_length_is_not_replaced_by_container(tmp_path, monkeypatch, duration):
    monkeypatch.setattr(ffprobe, 'probe_media', lambda *a: SimpleNamespace(video_codec='h264', duration=20.))
    monkeypatch.setattr(ffprobe, 'stream_durations', lambda *a: (duration, 20.))
    with pytest.raises(ffprobe.ProbeError, match='video stream duration'):
        ffprobe.measured_video_duration(tmp_path / 'fixture.mp4')


@pytest.mark.parametrize('start,end', [(0., 6.02), (.016, 6.034), (.018, 6.016), (371.428, 377.714)])
def test_source_window_covers_global_frame_rounding_and_zero_clamp(start, end):
    slot = TimelineSlot(0, 'fixture', start, end-start)
    required = source_window_duration(slot, fps=30, motion=True)
    available_video = required + 3.25
    for offset in (0., .001, 3.25):
        points = [round(start*30)/30, round((start+end)*15)/30, round(end*30)/30]
        for left, right in zip(points, points[1:]):
            assert max(0., offset+left-start) + right-left <= available_video + 1e-9
    assert source_window_duration(slot, fps=30, motion=False) == slot.duration


def test_late_bad_scene_is_rejected_before_first_render_or_workspace(tmp_path, monkeypatch):
    from kitok.editing import production
    (tmp_path / 'voice.wav').write_bytes(b'approved audio')
    (tmp_path / 'stock.mp4').write_bytes(b'approved stock')
    scenes = [EditorialScene(id=f'shot_{i:04}', start=i, end=i+1,
                            intention='Illustration', spoken_claim='Illustrative footage', asset='stock',
                            source_start=0. if i < 68 else 3.1) for i in range(69)]
    plan = EditorialPlan(episode_id='preflight', title='Late scene failure', audio_source='voice.wav',
                         duration=69, assets={'stock': EditorialAsset(path='stock.mp4', description='Fixture')},
                         scenes=scenes)
    monkeypatch.setattr(production, 'probe_media', lambda *a: SimpleNamespace(audio_codec='pcm', duration=69.))
    monkeypatch.setattr(production, 'stream_durations', lambda *a: (None, 69.))
    calls = []
    monkeypatch.setattr(production, 'measured_video_duration', lambda *a: calls.append(a[0]) or 4.)
    def forbidden(*a, **kw):
        pytest.fail('No encoder or scene may start before complete stock coverage validation')
    monkeypatch.setattr(production, 'choose_encoder', forbidden)
    monkeypatch.setattr(production, '_run', forbidden)
    output = tmp_path / 'new-output' / 'result.mp4'
    with pytest.raises(ValueError, match=r'shot_0068.*required_end=4.100000s.*video_duration=4.000000s'):
        render_editorial_plan(plan, root=tmp_path, output=output,
                              settings=SimpleNamespace(ffprobe_binary='ffprobe', ffmpeg_binary='ffmpeg'))
    assert calls == [tmp_path / 'stock.mp4']
    assert not output.parent.exists()
