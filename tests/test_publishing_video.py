import json
from types import SimpleNamespace

import pytest

from kitok.video_validator import validate_for_publishing


@pytest.fixture
def media(tmp_path, monkeypatch):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"video")
    info = {"format": {"duration": "25", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
            "streams": [{"codec_type": "video", "width": 1080, "height": 1920, "avg_frame_rate": "30/1",
                         "codec_name": "h264", "pix_fmt": "yuv420p", "bit_rate": "4000000"},
                        {"codec_type": "audio", "codec_name": "aac", "profile": "LC",
                         "bit_rate": "120000", "sample_rate": "48000", "channels": 2}]}
    monkeypatch.setattr("kitok.video_validator.subprocess.run", lambda *a, **kw: SimpleNamespace(stdout=json.dumps(info)))
    return path, info


def test_valid_video(media):
    path, _ = media
    assert validate_for_publishing(path, ["tiktok", "instagram", "youtube"]) == []


@pytest.mark.parametrize("duration,platform", [("2.9", "tiktok"), ("181", "youtube"), ("NaN", "youtube"), ("bad", "tiktok")])
def test_invalid_duration(media, duration, platform):
    path, info = media
    info["format"]["duration"] = duration
    assert validate_for_publishing(path, [platform])


@pytest.mark.parametrize("fps", ["22/1", "61/1", "0/0", "invalid"])
def test_invalid_fps(media, fps):
    path, info = media
    info["streams"][0]["avg_frame_rate"] = fps
    assert validate_for_publishing(path, ["tiktok"])


def test_small_tiktok_and_non_short_dimensions(media):
    path, info = media
    info["streams"][0].update(width=300, height=600)
    assert validate_for_publishing(path, ["tiktok"])
    assert validate_for_publishing(path, ["youtube"])


def test_missing_file(tmp_path):
    assert validate_for_publishing(tmp_path / "missing.mp4", ["tiktok"])
