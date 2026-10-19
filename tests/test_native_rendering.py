from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kitok.config import Settings
from kitok.longform.models import TimelineClip, TimelineSlot
from kitok.longform.timeline import build_timeline
from kitok.media.ffmpeg import (
    EncoderSettings,
    FFmpegNativeEngine,
    FFmpegProgress,
    FFmpegProgressParser,
    LoudnormMeasurement,
    RenderSpec,
    build_audio_analysis_command,
    build_audio_mux_command,
    build_chunk_command,
    choose_encoder,
    log_ffmpeg_progress,
    nvenc_available,
    parse_loudnorm_measurement,
)
from kitok.media.ffprobe import MediaInfo
from kitok.providers.pexels import PexelsProvider
from kitok.rendering.native import NativeLongformRenderer
from kitok.stock.cache import AssetCache, SearchCache
from kitok.stock.models import SelectedStock, StockAsset, StockVariant
from kitok.stock.selector import OutputGeometry, StockSelector


def asset(asset_id=1, *, duration=20, variants=None, query="casino"):
    return StockAsset(
        asset_id=asset_id,
        query=query,
        duration=duration,
        variants=tuple(variants or [StockVariant("https://cdn.invalid/video.mp4", 1920, 1080, 30)]),
    )


def test_search_cache_round_trip_and_ignores_incomplete_file(tmp_path):
    cache = SearchCache(tmp_path)
    original = [asset()]
    path = cache.store("casino lights", "landscape", 80, 1, original)

    assert cache.load("casino lights", "landscape", 80, 1) == original
    path.write_text("{incomplete", encoding="utf-8")
    assert cache.load("casino lights", "landscape", 80, 1) is None


def test_asset_cache_requires_complete_valid_video_and_matching_variant(tmp_path):
    cache = AssetCache(tmp_path)
    selection = SelectedStock(asset(), asset().variants[0])
    part = cache.part_path(1)
    part.write_bytes(b"video")
    result = cache.commit(selection, part)

    assert cache.get(1, lambda path: path.read_bytes() == b"video", selection) == result
    other = SelectedStock(asset(), StockVariant("different", 1280, 720, 30))
    assert cache.get(1, lambda _: True, other) is None
    cache.part_path(2).write_bytes(b"partial")
    assert cache.get(2, lambda _: True) is None


def test_pexels_provider_searches_once_then_uses_search_cache(tmp_path, caplog):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "videos": [{
                    "id": 123,
                    "duration": 12,
                    "url": "https://pexels.invalid/123",
                    "video_files": [
                        {"link": "https://cdn.invalid/123.mp4", "width": 1920,
                         "height": 1080, "fps": 29.97, "file_type": "video/mp4"}
                    ],
                }]
            },
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = PexelsProvider("secret", tmp_path, client=client, asset_validator=lambda _: True)
    caplog.set_level(logging.DEBUG, logger="kitok.providers.pexels")
    first = provider.search_videos("casino lights", orientation="landscape")
    second = provider.search_videos("casino lights", orientation="landscape")

    assert first == second
    assert len(calls) == 1
    assert calls[0].headers["Authorization"] == "secret"
    assert first[0].asset_id == 123
    assert first[0].variants[0].fps == pytest.approx(29.97)
    assert "search cache miss" in caplog.text
    assert "search cache hit" in caplog.text
    assert "secret" not in caplog.text


def test_pexels_provider_download_is_atomic_and_cached(tmp_path, caplog):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=b"mock-video", request=request)

    provider = PexelsProvider(
        "secret",
        tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        asset_validator=lambda path: path.read_bytes() == b"mock-video",
    )
    caplog.set_level(logging.DEBUG, logger="kitok.providers.pexels")
    choice = SelectedStock(asset(), asset().variants[0])

    first = provider.download_asset(choice)
    second = provider.download_asset(choice)

    assert first == second
    assert first.read_bytes() == b"mock-video"
    assert not first.with_suffix(".mp4.part").exists()
    assert len(calls) == 1
    assert "asset cache miss asset_id=1" in caplog.text
    assert "asset cache hit asset_id=1" in caplog.text


def test_pexels_preflight_fails_before_expensive_work_when_key_and_cache_are_missing(tmp_path):
    provider = PexelsProvider("", tmp_path, client=httpx.Client(), asset_validator=lambda _: True)
    with pytest.raises(RuntimeError, match="before Native Fish synthesis"):
        provider.preflight_searches(["casino"], orientation="landscape")


def test_stock_selector_prefers_1080p_over_4k_and_avoids_repeat():
    exact = asset(1, variants=[StockVariant("exact", 1920, 1080, 30)])
    four_k = asset(2, variants=[StockVariant("4k", 3840, 2160, 30)])
    fallback = asset(3, variants=[StockVariant("720", 1280, 720, 30)])
    selector = StockSelector()

    first = selector.select_candidate(
        [four_k, fallback, exact],
        target=OutputGeometry(1920, 1080),
        minimum_duration=8,
    )
    second = selector.select_candidate(
        [exact, four_k],
        target=OutputGeometry(1920, 1080),
        minimum_duration=8,
        used_ids={1},
    )

    assert first.asset.asset_id == 1
    assert second.asset.asset_id == 2


def test_stock_selector_supports_vertical_output():
    landscape = asset(1, variants=[StockVariant("landscape", 1920, 1080, 30)])
    portrait = asset(2, variants=[StockVariant("portrait", 1080, 1920, 30)])
    selected = StockSelector().select_candidate(
        [landscape, portrait],
        target=OutputGeometry(1080, 1920),
        minimum_duration=6,
    )
    assert selected.asset.asset_id == 2


def test_timeline_covers_exact_narration_and_keeps_keyword_order():
    slots = build_timeline(72.37, ["one", "two", "three"], seed="stable")

    assert slots[0].start == 0
    assert slots[-1].end == pytest.approx(72.37)
    assert sum(slot.duration for slot in slots) == pytest.approx(72.37)
    assert [slot.query for slot in slots[:5]] == ["one", "two", "three", "one", "two"]
    assert all(5.5 <= slot.duration <= 8.5 for slot in slots)
    assert build_timeline(72.37, ["one", "two", "three"], seed="stable") == slots


def test_nvenc_detection_requires_runtime_probe_and_falls_back():
    def unavailable(command, **kwargs):
        if "-encoders" in command:
            return subprocess.CompletedProcess(command, 0, stdout=" V....D h264_nvenc", stderr="")
        raise subprocess.CalledProcessError(1, command, stderr="no GPU")

    assert nvenc_available(run=unavailable) is False
    selected = choose_encoder(requested="auto", run=unavailable)
    assert selected == EncoderSettings("libx264", "medium")


def test_nvenc_detection_selects_requested_preset():
    def available(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 0, stdout=" V....D h264_nvenc" if "-encoders" in command else "", stderr=""
        )

    assert choose_encoder(requested="auto", nvenc_preset="p7", run=available) == (
        EncoderSettings("h264_nvenc", "p7")
    )


def test_ffmpeg_progress_parser_reports_media_time_percentage_and_speed(caplog):
    parser = FFmpegProgressParser()
    assert parser.feed("out_time_us=30000000") is None
    assert parser.feed("speed=2.50x") is None
    progress = parser.feed("progress=continue")

    assert progress == FFmpegProgress(30.0, 2.5, "continue")
    assert progress.percentage(120) == pytest.approx(25)
    caplog.set_level(logging.INFO, logger="kitok.media.ffmpeg")
    log_ffmpeg_progress("chunk", progress, 120, chunk=(2, 8))
    assert "chunk 2/8 progress" in caplog.text
    assert "media=00:00:30.00/00:02:00.00" in caplog.text
    assert "percentage=25.0%" in caplog.text
    assert "speed=2.50x" in caplog.text


def test_ffmpeg_debug_logging_quotes_command_without_environment(caplog):
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    caplog.set_level(logging.DEBUG, logger="kitok.media.ffmpeg")
    engine = FFmpegNativeEngine(
        encoder=EncoderSettings("libx264", "medium"), runner=runner
    )
    engine._run(["ffmpeg", "-i", "/tmp/path with spaces.mp4", "out.mp4"], "test")

    assert "FFmpeg command stage=test" in caplog.text
    assert "'/tmp/path with spaces.mp4'" in caplog.text
    assert "Authorization" not in caplog.text


def test_ffmpeg_chunk_command_uses_cover_hard_cuts_and_quality_vbr(tmp_path):
    source = tmp_path / "source.mp4"
    clip = TimelineClip(TimelineSlot(0, "casino", 0, 7.25), 1, source, 2.0)
    command, script = build_chunk_command(
        [clip],
        tmp_path / "chunk.mp4",
        tmp_path / "filters.txt",
        ffmpeg="ffmpeg",
        encoder=EncoderSettings("h264_nvenc", "p6"),
        spec=RenderSpec(),
        first_chunk=True,
        last_chunk=True,
    )

    assert "scale=1920:1080:force_original_aspect_ratio=increase" in script
    assert "crop=1920:1080,fps=30" in script
    assert "concat=n=1:v=1:a=0" in script
    assert "fade=t=in:st=0:d=0.6" in script
    assert "tpad=stop_mode=clone:stop_duration=1.25" in script
    assert "fade=t=out:st=7.250000:d=1.25" in script
    assert command[command.index("-c:v") + 1] == "h264_nvenc"
    assert command[command.index("-rc") + 1] == "vbr"
    assert command[command.index("-cq") + 1] == "18"
    assert command[command.index("-b:v") + 1] == "0"


def test_final_mux_normalizes_master_after_unchanged_music_mix(tmp_path):
    command, filters = build_audio_mux_command(
        tmp_path / "visual.mp4",
        tmp_path / "voice.mp3",
        tmp_path / "final.mp4",
        ffmpeg="ffmpeg",
        narration_duration=70,
        fade_out=1.25,
        music=tmp_path / "music.mp3",
        music_volume=0.07,
        loudness_target=-16,
        lra_target=7,
        true_peak_target=-1.5,
    )
    voice_filter = filters.split(";", 1)[0]
    assert "loudnorm" not in voice_filter
    assert "afade" not in voice_filter
    assert "volume=0.07" in filters
    assert "volume=2.5dB,pan=stereo|c0=c0|c1=c0" in voice_filter
    assert "amix=inputs=2:duration=first:dropout_transition=2:normalize=0" in filters
    assert filters.index("amix=") < filters.index("loudnorm=")
    # A 0.3 dB AAC safety margin protects the requested -1.5 dBTP ceiling
    # after lossy encoding; it does not alter the requested public target.
    assert "loudnorm=I=-16:LRA=7:TP=-1.8,aresample=48000," in filters
    assert "aformat=sample_rates=48000:channel_layouts=stereo[audio]" in filters
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-c:a") + 1] == "aac"
    assert command[command.index("-b:a") + 1] == "192k"
    assert command[command.index("-ar") + 1] == "48000"
    assert command[command.index("-ac") + 1] == "2"


def test_final_mux_without_music_still_normalizes_final_master(tmp_path):
    _, filters = build_audio_mux_command(
        tmp_path / "visual.mp4",
        tmp_path / "voice.mp3",
        tmp_path / "final.mp4",
        ffmpeg="ffmpeg",
        narration_duration=70,
        fade_out=1.25,
        music=None,
        music_volume=0.07,
        loudness_target=-16,
        lra_target=7,
        true_peak_target=-1.5,
    )
    assert "volume=2.5dB,pan=stereo|c0=c0|c1=c0" in filters
    assert filters.endswith(
        "[voice]loudnorm=I=-16:LRA=7:TP=-1.8,aresample=48000,"
        "aformat=sample_rates=48000:channel_layouts=stereo[audio]"
    )


def test_second_pass_loudnorm_uses_measured_final_mix(tmp_path):
    measurement = LoudnormMeasurement(-16.78, 2.6, -1.74, -26.94, 0.23)
    _, filters = build_audio_mux_command(
        tmp_path / "visual.mp4",
        tmp_path / "voice.mp3",
        tmp_path / "final.mp4",
        ffmpeg="ffmpeg",
        narration_duration=70,
        fade_out=1.25,
        music=tmp_path / "music.mp3",
        music_volume=0.07,
        loudness_target=-16,
        lra_target=7,
        true_peak_target=-1.5,
        loudnorm_measurement=measurement,
    )
    assert "amix=inputs=2:duration=first:dropout_transition=2:normalize=0" in filters
    assert filters.index("amix=") < filters.index("loudnorm=")
    assert "measured_I=-16.78" in filters
    assert "measured_LRA=2.6" in filters
    assert "measured_TP=-1.74" in filters
    assert "measured_thresh=-26.94" in filters
    assert "offset=0.23:linear=true" in filters
    assert "aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo" in filters


def test_audio_analysis_uses_same_final_mix_and_parses_loudnorm_json(tmp_path):
    command, filters = build_audio_analysis_command(
        tmp_path / "visual.mp4",
        tmp_path / "voice.mp3",
        ffmpeg="ffmpeg",
        narration_duration=70,
        fade_out=1.25,
        music=tmp_path / "music.mp3",
        music_volume=0.07,
        loudness_target=-16,
        lra_target=7,
        true_peak_target=-1.5,
    )
    assert "volume=0.07" in filters
    assert "normalize=0" in filters
    assert "loudnorm=I=-16:LRA=7:TP=-1.8:print_format=json,aresample=48000" in filters
    assert command[-6:] == ["-map", "[audio]", "-vn", "-f", "null", "-"]
    parsed = parse_loudnorm_measurement(
        'noise\n{"input_i":"-16.78","input_tp":"-1.74",'
        '"input_lra":"2.60","input_thresh":"-26.94",'
        '"target_offset":"0.23"}\n'
    )
    assert parsed == LoudnormMeasurement(-16.78, 2.6, -1.74, -26.94, 0.23)


def test_longform_cli_defaults_to_native_and_preserves_explicit_mpt_recovery():
    from kitok.longform import cli as longform

    args = longform._parser().parse_args(["content.json"])
    assert args.renderer == "native"
    assert args.nvenc_preset == "p5"
    historical = longform._parser().parse_args(["content.json", "--renderer", "mpt", "--resume", "known-task"])
    assert historical.renderer == "mpt" and historical.resume == "known-task"


def test_native_renderer_isolated_flow_reuses_fish_and_preserves_tags(
    tmp_path, monkeypatch, caplog
):
    source = tmp_path / "cached.mp4"
    source.write_bytes(b"stock")
    fish_calls = []

    class Fish:
        def __init__(self, *args, **kwargs):
            pass

        def synthesize(self, text, reference_id, destination, **kwargs):
            fish_calls.append((text, reference_id, kwargs))
            destination.write_bytes(b"audio")

        def close(self):
            pass

    class Pexels:
        def search_videos(self, query, orientation):
            return [asset(10, duration=90, query=query)]

        def select_candidate(self, assets, **kwargs):
            return SelectedStock(assets[0], assets[0].variants[0])

        def download_asset(self, choice):
            return source

    class Engine:
        spec = RenderSpec()
        encoder = EncoderSettings("libx264", "medium")

        def render(self, clips, narration, narration_duration, output, workspace, **kwargs):
            assert len(clips) > 1
            assert narration_duration == 65
            assert kwargs["music"] is None
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"final")
            return MediaInfo(66.25, 1920, 1080, 30, "h264", "aac", "yuv420p", 1_000_000, 5)

    monkeypatch.setattr(
        "kitok.rendering.native.probe_media",
        lambda *args, **kwargs: MediaInfo(65 if Path(args[0]).suffix == ".mp3" else 66.25,
                                          1920, 1080, 30, "h264", "aac", "yuv420p"),
    )
    settings = Settings(_env_file=None, fish_api_key=SecretStr("fish-secret"))
    item = SimpleNamespace(
        id="native_test",
        script="[calmly] This complete narration keeps its direction tag.",
        keywords=["casino", "servers"],
    )
    definition = SimpleNamespace(
        item=item,
        voice_name="fish_audio:reference-123:Narrator",
        voice_rate=0.98,
        video_clip_duration_min=5.5,
        video_clip_duration_max=8.5,
        music_enabled=False,
        background_music_file=tmp_path / "missing-is-disabled.mp3",
        background_music_volume=0.07,
        audio_loudness_target=-16,
        audio_lra_target=7,
        audio_true_peak_target=-1.5,
    )
    destination = tmp_path / "outputs" / "longform" / "native_test.mp4"
    caplog.set_level(logging.DEBUG, logger="kitok.rendering.native")

    result = NativeLongformRenderer(
        settings,
        Pexels(),
        Engine(),
        output_path=destination,
        fish_factory=Fish,
        output=lambda _: None,
    ).render(definition)

    assert result.output.read_bytes() == b"final"
    assert result.renderer == "native"
    assert fish_calls == [(
        item.script,
        "reference-123",
        {"speed": 0.98, "temperature": 0.8, "top_p": 0.7},
    )]
    manifest = json.loads(destination.with_suffix(".native.json").read_text())
    assert manifest["content_id"] == "native_test"
    assert manifest["narration_duration"] == 65
    assert not list((destination.parent / ".native-work").glob("native_test-*"))
    assert "Native render start content_id=native_test renderer=native" in caplog.text
    assert "Fish start content_id=native_test" in caplog.text
    assert "Fish end elapsed=" in caplog.text
    assert "Narration duration=65.000s" in caplog.text
    assert "Pexels search start queries=2" in caplog.text
    assert "Pexels search end elapsed=" in caplog.text
    assert "Timeline clips=" in caplog.text
    assert "Asset download/cache start" in caplog.text
    assert "Asset download/cache end elapsed=" in caplog.text
    assert "Validation start" in caplog.text
    assert "Validation end elapsed=" in caplog.text
    assert "Native final output path=" in caplog.text
    assert "Native render complete content_id=native_test" in caplog.text
    assert "Selected Pexels asset_id=10" in caplog.text
    assert "source_offset=" in caplog.text


def test_native_renderer_never_overwrites_without_explicit_start_over(tmp_path):
    destination = tmp_path / "exists.mp4"
    destination.write_bytes(b"production")
    renderer = NativeLongformRenderer(
        Settings(_env_file=None),
        object(),
        SimpleNamespace(),
        output_path=destination,
    )
    with pytest.raises(RuntimeError, match="already exists"):
        renderer.render(SimpleNamespace())
    assert destination.read_bytes() == b"production"


def test_native_renderer_failure_does_not_require_output_callback(tmp_path):
    class Fish:
        def __init__(self, *args, **kwargs):
            pass

        def synthesize(self, *args, **kwargs):
            raise RuntimeError("synthetic Fish failure")

        def close(self):
            pass

    item = SimpleNamespace(
        id="native_failure",
        script="[calm] A sufficiently long script for native validation.",
        keywords=["casino"],
    )
    definition = SimpleNamespace(
        item=item,
        voice_name="fish_audio:reference:Narrator",
        voice_rate=0.98,
        music_enabled=False,
        background_music_file=tmp_path / "unused.mp3",
    )
    provider = SimpleNamespace(preflight_searches=lambda *args, **kwargs: None)
    renderer = NativeLongformRenderer(
        Settings(_env_file=None),
        provider,
        SimpleNamespace(),
        output_path=tmp_path / "final.mp4",
        fish_factory=Fish,
        output=None,
    )

    with pytest.raises(RuntimeError, match="synthetic Fish failure"):
        renderer.render(definition)


def test_native_preflight_failure_happens_before_fish_and_creates_no_output(tmp_path):
    class MissingPexels:
        def preflight_searches(self, *args, **kwargs):
            raise RuntimeError("missing Pexels key")

    renderer = NativeLongformRenderer(
        Settings(_env_file=None),
        MissingPexels(),
        SimpleNamespace(),
        output_path=tmp_path / "native.mp4",
        fish_factory=lambda *args, **kwargs: pytest.fail("Fish must not be called"),
        output=lambda _: None,
    )
    definition = SimpleNamespace(
        item=SimpleNamespace(script="A complete native narration.", keywords=["casino"]),
        voice_name="fish_audio:reference:Narrator",
        music_enabled=False,
    )
    with pytest.raises(RuntimeError, match="missing Pexels key"):
        renderer.render(definition)
    assert not (tmp_path / "native.mp4").exists()
