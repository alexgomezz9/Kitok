import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from kitok.models import MPTTask
from kitok.pipeline import Pipeline
from kitok.regeneration import ReadyRegenerator
from kitok.video_validator import VideoValidator, validate_for_publishing


def probe_info(bitrate=120000, sample_rate=48000):
    return {"format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "12"},
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920,
                         "avg_frame_rate": "30/1", "pix_fmt": "yuv420p", "bit_rate": "4000000"},
                        {"codec_type": "audio", "codec_name": "aac", "profile": "LC", "channels": 2,
                         "bit_rate": str(bitrate), "sample_rate": str(sample_rate)}]}


def mock_tools(monkeypatch, info, final=None):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if args[0] == "ffmpeg":
            Path(args[-1]).write_bytes(b"normalized")
            return SimpleNamespace(returncode=0)
        data = final if Path(args[-1]).name.startswith(".audio-") and final is not None else info
        return SimpleNamespace(returncode=0, stdout=json.dumps(data))
    monkeypatch.setattr("kitok.video_validator.subprocess.run", run)
    monkeypatch.setattr(VideoValidator, "ffprobe_available", lambda self: True)
    return calls


def test_compliant_media_is_not_reencoded(tmp_path, monkeypatch):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"original")
    calls = mock_tools(monkeypatch, probe_info())
    result = VideoValidator().prepare(path, ["instagram", "tiktok", "youtube"])
    assert result.ok and not result.normalized
    assert [args[0] for args in calls] == ["ffprobe"]
    assert path.read_bytes() == b"original"
    assert (result.fps, result.pixel_format, result.audio_bitrate, result.file_size) == (30, "yuv420p", 120000, 8)


@pytest.mark.parametrize("bitrate,sample_rate", [(170000, 48000), (120000, 96000)])
def test_audio_is_normalized_without_video_recompression(tmp_path, monkeypatch, bitrate, sample_rate):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"original")
    calls = mock_tools(monkeypatch, probe_info(bitrate, sample_rate), probe_info())
    result = VideoValidator().prepare(path, ["instagram"])
    assert result.ok and result.normalized
    assert [args[0] for args in calls] == ["ffprobe", "ffmpeg", "ffprobe"]
    command = calls[1]
    for flag, value in (("-c:v", "copy"), ("-c:a", "aac"), ("-profile:a", "aac_low"),
                        ("-b:a", "120k"), ("-ar", "48000"), ("-movflags", "+faststart")):
        assert command[command.index(flag) + 1] == value
    assert path.read_bytes() == b"normalized"


def test_video_defects_are_reported_without_transcoding(tmp_path, monkeypatch):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"original")
    info = probe_info(170000)
    info["streams"][0]["codec_name"] = "hevc"
    calls = mock_tools(monkeypatch, info)
    result = VideoValidator().prepare(path, ["instagram"])
    assert not result.ok
    assert not any(args[0] == "ffmpeg" for args in calls)
    assert "H.264" in "; ".join(result.errors)


def test_failed_final_validation_preserves_original(tmp_path, monkeypatch):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"original")
    mock_tools(monkeypatch, probe_info(170000), probe_info(160000))
    result = VideoValidator().prepare(path, ["instagram"])
    assert not result.ok
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("regenerate", [False, True])
@pytest.mark.parametrize("valid_final", [False, True])
def test_ready_only_after_final_validation(local_kitok, monkeypatch, regenerate, valid_final):
    settings, queue, state, video = local_kitok
    settings.ensure_directories()
    state.upsert("one", status="ready" if regenerate else "pending")
    fake = Mock()
    fake.submit_video.return_value = "new-task"
    fake.get_task.return_value = MPTTask(task_id="new-task", state=1, videos=["artifact"])
    fake.download_artifact.side_effect = lambda artifact, path: path.write_bytes(b"original")
    calls = mock_tools(monkeypatch, probe_info(170000), probe_info(120000 if valid_final else 160000))
    if regenerate:
        result = ReadyRegenerator(settings, queue, state, fake, {}).run(ids={"one"})
        assert result.regenerated == int(valid_final)
        assert result.failed == int(not valid_final)
    else:
        Pipeline(settings, queue, state, fake, {}).process(ids={"one"})
        assert state.get("one")["status"] == ("ready" if valid_final else "failed")
    assert [args[0] for args in calls] == ["ffprobe", "ffmpeg", "ffprobe"]
    if valid_final:
        assert state.get("one")["validation"]["normalized"] is True
        assert state.get("one")["validation"]["audio_bitrate"] == 120000
    else:
        assert video.read_bytes() == b"test-media"
        assert state.get("one")["last_error"]
