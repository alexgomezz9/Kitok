"""Real fractional-stock seeks must not accumulate lost frames in long edits."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from kitok.editing.production import EditorialValidationError, _require_clock, render_editorial_plan
from kitok.editing.storyboard import EditorialAsset, EditorialPlan, EditorialScene, file_hash


SETTINGS = SimpleNamespace(ffmpeg_binary='ffmpeg', ffprobe_binary='ffprobe')


def _ffmpeg(*arguments):
    return subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', *map(str, arguments)],
                          check=True, capture_output=True, timeout=60)


def _clock(path):
    result = subprocess.run([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames',
        '-show_entries', 'stream=nb_read_frames,start_time,duration', '-of', 'json', str(path)],
        check=True, capture_output=True, text=True, timeout=30)
    stream = json.loads(result.stdout)['streams'][0]
    return int(stream['nb_read_frames']), float(stream['start_time']), float(stream['duration'])


def _audio_hash(path):
    return _ffmpeg('-i', path, '-map', '0:a:0', '-c:a', 'copy',
                   '-f', 'hash', '-hash', 'sha256', '-').stdout


def _fractional_stock_plan(tmp_path, *, scenes=12):
    assets = {}
    for name, rate in [('ntsc', '30000/1001'), ('film', '24000/1001')]:
        stock = tmp_path / f'{name}.mp4'
        _ffmpeg('-f', 'lavfi', '-i', f'testsrc2=size=320x180:rate={rate}:duration=8',
                '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', stock)
        assets[name] = EditorialAsset(path=stock.name, description='Synthetic stock with fractional FPS')
    audio = tmp_path / 'approved.m4a'
    _ffmpeg('-f', 'lavfi', '-i', f'sine=frequency=230:sample_rate=48000:duration={scenes}',
            '-c:a', 'aac', audio)
    return EditorialPlan(episode_id='fractional-clock', title='Fractional seek clock regression',
        audio_source=audio.name, duration=scenes, width=320, height=180, fps=30,
        audio_is_final_mix=True, assets=assets, scenes=[
            EditorialScene(id=f'scene_{index:02}', start=index, end=index+1,
                intention='Maintain exact shot boundaries', spoken_claim='Synthetic illustration',
                asset=('ntsc', 'film')[index % 2], source_start=(.679181, .916411, 6.318426)[index % 3],
                transition=('cut', 'fade')[index % 2])
            for index in range(scenes)])


def test_fractional_stock_seeks_deliver_exact_frames_and_approved_aac(tmp_path):
    """A one-frame loss per short scene used to fail only at the final mux."""
    plan = _fractional_stock_plan(tmp_path)
    source_hashes = {path: file_hash(path) for path in tmp_path.iterdir() if path.is_file()}
    output = tmp_path / 'delivery.mp4'
    result = render_editorial_plan(plan, root=tmp_path, output=output,
                                   settings=SETTINGS, encoder_name='libx264')
    workspace = tmp_path / '.editorial-work' / plan.episode_id
    for scene in plan.scenes:
        frames, start, duration = _clock(workspace / f'{scene.id}.mp4')
        assert frames == 30, scene.id
        assert start == pytest.approx(0, abs=1e-6), scene.id
        assert duration == pytest.approx(1, abs=1e-6), scene.id
    for video in (workspace / 'assembled.mp4', output):
        frames, start, duration = _clock(video)
        assert frames == 360
        assert start == pytest.approx(0, abs=1e-6)
        assert duration == pytest.approx(12, abs=1e-6)
        _ffmpeg('-xerror', '-i', video, '-f', 'null', '-')
    assert result['audio_delivery'] == 'copied-aac'
    assert _audio_hash(output) == _audio_hash(tmp_path / plan.audio_source)
    assert all(file_hash(path) == digest for path, digest in source_hashes.items())


def test_cache_with_matching_hash_but_missing_frame_is_regenerated(tmp_path):
    """The old duration tolerance accepted 29/30 cached frames and drift grew."""
    plan = _fractional_stock_plan(tmp_path, scenes=2)
    render_editorial_plan(plan, root=tmp_path, output=tmp_path / 'first.mp4',
                          settings=SETTINGS, encoder_name='libx264')
    workspace = tmp_path / '.editorial-work' / plan.episode_id
    corrupted = workspace / 'scene_00.mp4'
    _ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30', '-frames:v', '29',
            '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', corrupted)
    receipt_path = corrupted.with_suffix('.json')
    receipt = json.loads(receipt_path.read_text())
    receipt['media_sha256'] = file_hash(corrupted)
    receipt_path.write_text(json.dumps(receipt))
    assert _clock(corrupted)[0] == 29
    result = render_editorial_plan(plan, root=tmp_path, output=tmp_path / 'second.mp4',
                                   settings=SETTINGS, encoder_name='libx264')
    assert result['rendered_scenes'] == ['scene_00']
    assert result['reused_scenes'] == ['scene_01']
    assert _clock(corrupted) == pytest.approx((30, 0, 1))
    assert _clock(tmp_path / 'second.mp4') == pytest.approx((60, 0, 2))
    _ffmpeg('-xerror', '-i', tmp_path / 'second.mp4', '-f', 'null', '-')


def test_fractional_seeks_keep_last_frame_available_for_dissolve_and_wipe(tmp_path):
    """A lost final frame also prevented extracting the following transition still."""
    plan = _fractional_stock_plan(tmp_path, scenes=4)
    for scene, transition in zip(plan.scenes, ('cut', 'fade', 'dissolve', 'wipe')):
        scene.transition = transition
    output = tmp_path / 'transitions.mp4'
    render_editorial_plan(plan, root=tmp_path, output=output,
                          settings=SETTINGS, encoder_name='libx264')
    workspace = tmp_path / '.editorial-work' / plan.episode_id
    assert not list(workspace.glob('*.previous.png'))
    for scene in plan.scenes:
        assert _clock(workspace / f'{scene.id}.mp4') == pytest.approx((30, 0, 1))
    assert _clock(output) == pytest.approx((120, 0, 4))
    assert _audio_hash(output) == _audio_hash(tmp_path / plan.audio_source)
    _ffmpeg('-xerror', '-i', output, '-f', 'null', '-')


def test_clock_rejection_reports_measurements_and_preserves_failed_media(tmp_path):
    """A real short encode must leave inspectable evidence instead of a generic error."""
    failed = tmp_path / 'short-scene.part.mp4'
    diagnostics = tmp_path / 'short-scene.validation.json'
    _ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=30', '-frames:v', '29',
            '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', failed)
    original_hash = file_hash(failed)
    with pytest.raises(EditorialValidationError) as caught:
        _require_clock(failed, 30, 30, diagnostics)
    assert 'video_frames=29 expected=30' in str(caught.value)
    assert 'video_duration=0.966667s expected=1.000000s' in str(caught.value)
    report = json.loads(diagnostics.read_text())
    assert report['status'] == 'rejected'
    assert report['actual_frames'] == 29
    assert report['expected_frames'] == 30
    assert report['video_duration'] == pytest.approx(29/30, abs=1e-6)
    assert report['expected_duration'] == 1
    assert report['video_start_time'] == 0
    assert file_hash(failed) == original_hash
