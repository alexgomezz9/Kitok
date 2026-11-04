"""A fast camera cut is not a new illustration; legacy configuration stays stable."""
from types import SimpleNamespace

import pytest

from kitok.youtube_stickman_es.models import Config
from kitok.youtube_stickman_es.pacing import pacing_report, require_pacing


def plan(runs):
    scenes = []
    cursor = 0
    for image, seconds in runs:
        scenes.append(SimpleNamespace(image_file=image, start=cursor, end=cursor+seconds))
        cursor += seconds
    return SimpleNamespace(scenes=scenes, duration=cursor)


def test_cameras_cannot_disguise_one_long_image(tmp_path):
    timeline = plan([('same.png', 2)]*15)
    report = pacing_report(tmp_path, timeline)
    assert report['bands'][0]['image_runs'] == 1
    assert report['bands'][0]['longest_hold_seconds'] == 30
    with pytest.raises(ValueError, match='Preserve the voice'):
        require_pacing(tmp_path, timeline)


def test_renamed_identical_images_do_not_pass(tmp_path):
    for i in range(15):
        (tmp_path/f'{i}.png').write_bytes(b'identical source')
    timeline = plan([(f'{i}.png', 2) for i in range(15)])
    assert pacing_report(tmp_path, timeline)['status'] == 'passed'
    assert pacing_report(tmp_path, timeline, verify_images=True)['status'] == 'needs_review'


def test_real_distinct_sources_pass_all_bands_and_clipped_tail(tmp_path):
    timeline = plan([(f'intro{i}.png', 2) for i in range(15)]
                    + [(f'mid{i}.png', 3) for i in range(10)]
                    + [(f'body{i}.png', 4) for i in range(8)])
    for scene in timeline.scenes:
        (tmp_path/scene.image_file).write_bytes(scene.image_file.encode())
    report = require_pacing(tmp_path, timeline, verify_images=True)
    assert [b['distinct_images'] for b in report['bands']] == [15, 10, 8]
    assert [b['mean_seconds'] for b in report['bands']] == [2, 3, 4]
    assert report['images_verified']


def test_one_long_hold_fails_even_with_fast_average(tmp_path):
    timeline = plan([('long.png', 8)] + [(f'{i}.png', 1) for i in range(22)])
    assert pacing_report(tmp_path, timeline)['bands'][0]['seconds_per_distinct_image'] < 2.5
    assert pacing_report(tmp_path, timeline)['status'] == 'needs_review'


def test_band_boundary_cannot_hide_seven_second_hold(tmp_path):
    timeline = plan([(f'intro{i}.png', 2) for i in range(12)] + [('extra.png', 3),
                    ('crossing.png', 7)] + [(f'mid{i}.png', 2) for i in range(13)])
    report = pacing_report(tmp_path, timeline)
    assert report['status'] == 'needs_review'
    assert [b['longest_hold_seconds'] for b in report['bands']] == [7, 7]


def test_disabled_policy_preserves_existing_configuration_hash_input():
    assert 'pacing_policy' not in Config().model_dump()
    assert Config(pacing_policy='trazo_dynamic_v1').model_dump()['pacing_policy'] == 'trazo_dynamic_v1'


from test_stickman_pipeline import setup_episode
from test_stickman_word_pipeline import supplied


def test_prepare_blocks_slow_approved_sources_without_another_provider_call(setup_episode, monkeypatch):
    import json
    from kitok.youtube_stickman_es import audio, pipeline
    root, episode, settings = supplied(setup_episode)
    config_path = episode/'configuracion.json'
    config = json.loads(config_path.read_text())
    config['pacing_policy'] = 'trazo_dynamic_v1'
    config_path.write_text(json.dumps(config))
    monkeypatch.setattr(audio, 'FishVoiceClient', lambda *a, **k: pytest.fail('No provider'))
    with pytest.raises(ValueError, match='Distinct-image pacing'):
        pipeline.execute(root, episode, 'prepare', settings=settings, reuse_images=True)
    assert not (episode/'video_final.mp4').exists()
    assert (episode/'voz.mp3').exists()
