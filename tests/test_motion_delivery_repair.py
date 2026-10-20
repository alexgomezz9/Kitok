"""Offline repair preserves originals and AAC, and never replaces an old ID."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


spec = importlib.util.spec_from_file_location('motion_delivery_repair',
    Path(__file__).resolve().parents[1] / 'scripts' / 'repair_motion_delivery.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def test_repair_rejects_444_then_preserves_source_and_aac(tmp_path):
    source = tmp_path / 'outputs' / 'motion-gallery' / 'bad'
    source.mkdir(parents=True)
    video = source / 'preview.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
        'color=c=blue:s=320x180:r=30:d=1', '-f', 'lavfi', '-i',
        'sine=frequency=230:duration=1', '-c:v', 'libx264', '-pix_fmt', 'yuv444p',
        '-threads', '1', '-c:a', 'aac', str(video)], check=True, timeout=30)
    baseline = source / 'baseline.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video), '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p', '-threads', '1', '-c:a', 'copy', str(baseline)],
        check=True, timeout=30)
    (source / 'item.json').write_text(json.dumps(dict(id='bad', kind='effect',
        title='Illustrative transition', family='transitions', duration=1)))
    original = {p.name: p.read_bytes() for p in source.iterdir()}
    with pytest.raises(ValueError, match='Incompatible frame formats'):
        repair.inspect_delivery(video)
    receipt = repair.repair_item(tmp_path, 'bad')
    after = receipt['videos']['preview.mp4']['after']
    assert after['pixel_formats'] == {'yuv420p': 30}
    assert after['profile'] == 'High'
    assert after['audio_packet_sha256'] == receipt['videos']['preview.mp4']['before']['audio_packet_sha256']
    assert {p.name: p.read_bytes() for p in source.iterdir()} == original
    assert (source.parent / 'bad_compat1' / 'item.json').is_file()
    assert (source.parent / 'bad_compat1' / 'baseline.mp4').read_bytes() == original['baseline.mp4']
    with pytest.raises(FileExistsError):
        repair.repair_item(tmp_path, 'bad')


def test_repair_refuses_long_item_before_video_processing(tmp_path):
    source = tmp_path / 'outputs' / 'motion-gallery' / 'episode'
    source.mkdir(parents=True)
    (source / 'item.json').write_text(json.dumps(dict(id='episode', kind='sample',
        title='Not a short proof', family='sample', duration=652)))
    with pytest.raises(ValueError, match='short, active'):
        repair.repair_item(tmp_path, 'episode')
    assert not (source.parent / 'episode_compat1').exists()
