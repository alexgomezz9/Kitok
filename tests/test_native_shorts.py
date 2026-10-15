"""Real FFmpeg contracts with synthetic media; no external providers or MPT."""
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from kitok.config import Settings
from kitok.generation import GenerationService
from kitok.media.ffprobe import probe_media
from kitok.models import ContentItem


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and ffprobe required")
    clip = tmp_path / "clip.mp4"
    voice = tmp_path / "voice.mp3"
    def run(*args):
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args],
                       check=True, capture_output=True, timeout=60)
    run("-f", "lavfi", "-i", "testsrc2=size=180x320:rate=30:duration=3", "-c:v", "libx264", "-threads", "1", str(clip))
    run("-f", "lavfi", "-i", "sine=frequency=440:duration=0.6", str(voice))
    settings = Settings(_env_file=None, data_root=tmp_path, ready_dir=tmp_path / "ready",
                        native_cache_dir=tmp_path / "cache", background_root=tmp_path / "backgrounds",
                        character_root=tmp_path / "characters", dialogue_gap_ms=100)
    settings.ensure_directories()
    class Speech:
        def __init__(self, *args, **kwargs): pass
        def synthesize(self, text, ref, target, **kwargs): shutil.copyfile(voice, target)
        def close(self): pass
    class Stock:
        orientations = []
        def __init__(self, *args, **kwargs): pass
        def preflight_searches(self, queries, **kwargs): pass
        def search_videos(self, query, *, orientation):
            self.orientations.append(orientation)
            return [query]
        def select_candidate(self, assets, **kwargs):
            assert kwargs["target"].width == 1080 and kwargs["target"].height == 1920
            return SimpleNamespace(asset=SimpleNamespace(asset_id=1, duration=3))
        def download_asset(self, selected): return clip
        def close(self): pass
    monkeypatch.setattr("kitok.generation.FishVoiceClient", Speech)
    monkeypatch.setattr("kitok.generation.PexelsProvider", Stock)
    return settings, clip, Stock


@pytest.mark.parametrize("mode", ["pexels_fish", "pexels_dialogue", "local_rick", "pexels_music",
                                 "dialogue_music", "no_subtitles", "stock_cuts"])
def test_native_shorts_render_real_media(synthetic, tmp_path, mode):
    settings, clip, stock = synthetic
    row = dict(id=mode, subject="Synthetic", keywords=["city"], script="A sufficiently long synthetic narration.",
               voice_profile="rick_es")
    if mode in {"pexels_dialogue", "dialogue_music"}:
        row.update(content_format="dialogue", script="", voice_profile="alvaro", character_profile="rick_morty_es",
                   dialogue=[{"speaker": "rick_es", "text": "A synthetic first turn."},
                             {"speaker": "morty_es", "text": "A synthetic second turn."}])
        for character in ("rick", "morty"):
            folder = settings.character_root / character
            folder.mkdir(parents=True)
            Image.new("RGBA", (80, 140), (210, 20, 40, 255)).save(folder / "pose.png")
    if mode == "local_rick":
        row.update(visual_profile="random")
        folder = settings.background_root / "random"
        folder.mkdir(parents=True)
        shutil.copyfile(clip, folder / "clip.mp4")
    item = ContentItem(**row)
    preset = {"subtitle_enabled": mode != "no_subtitles"}
    if mode in {"pexels_music", "dialogue_music"}:
        preset.update(bgm_type="custom", bgm_file=str(tmp_path / "voice.mp3"), bgm_volume=0.08)
    if mode == "stock_cuts":
        # Exercise actual multi-shot concatenation rather than a single short stock clip.
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=2.4", str(tmp_path / "voice.mp3")],
                       check=True, capture_output=True, timeout=60)
    service = GenerationService(settings, preset)
    workspace = tmp_path / "work"
    plan = service.plan(item, workspace)
    result = service.finish(item, plan, None, tmp_path / "final.mp4", workspace)
    info = probe_media(result)
    assert (info.width, info.height, info.video_codec, info.audio_codec) == (1080, 1920, "h264", "aac")
    assert abs(info.duration - plan.dialogue_audio.duration) < 0.15
    assert service.last_metadata["renderer"] == "native"
    assert service.last_metadata["subtitle_cues"]
    if mode != "local_rick":
        assert stock.orientations and set(stock.orientations) == {"portrait"}
        assert plan.stock_timeline and service.last_metadata["stock_timeline"]
    else:
        assert plan.background_selection
    if mode in {"pexels_dialogue", "dialogue_music"}:
        assert service.last_metadata["character_appearances"]
    if mode in {"pexels_music", "dialogue_music"}:
        assert service.last_metadata["audio_mix"]["music_volume"] == 0.08
        assert service.last_metadata["audio_mix"]["music"]
    if mode == "stock_cuts":
        assert len(plan.stock_timeline) == 2


def test_missing_stock_credentials_fails_before_voice(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, data_root=tmp_path, native_cache_dir=tmp_path / "stock")
    voice = Mock(side_effect=AssertionError("must not synthesize"))
    monkeypatch.setattr("kitok.generation.FishVoiceClient", voice)
    item = ContentItem(id="demo", subject="Demo", script="A sufficiently long test narration.",
                       keywords=["uncached-query"], voice_profile="rick_es")
    with pytest.raises(RuntimeError, match="PEXELS_API_KEY"):
        GenerationService(settings, {}).plan(item, tmp_path / "work")
    voice.assert_not_called()
