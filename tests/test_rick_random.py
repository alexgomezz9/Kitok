from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from kitok.dialogue_audio import DialogueAudio, DialogueAudioService, TimedTurn
from kitok.dialogue_video import BackgroundPool, DialogueCompositor
from kitok.generation import GenerationService
from kitok.models import ContentItem


def rick_item(**changes):
    values = {
        "id": "rick-random-test",
        "subject": "Tiburones antiguos",
        "script": ("¿Sabías que los tiburones existen desde antes que los árboles? "
                   "Los primeros tiburones aparecieron hace más de cuatrocientos millones de años."),
        "keywords": ["tiburones"],
        "publish_at": "2026-09-20T13:00:00+02:00",
        "content_format": "explainer",
        "voice_profile": "rick_es",
        "visual_profile": "random",
        "visual_seed": "stable-visual",
    }
    values.update(changes)
    return ContentItem.model_validate(values)


def png(path, color=(255, 0, 0, 255)):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (80, 120), (0, 0, 0, 0))
    body = Image.new("RGBA", (40, 80), color)
    image.paste(body, (20, 20), body)
    image.save(path)


def test_random_pool_discovers_supported_extensions_and_selects_stably(tmp_path, monkeypatch):
    folder = tmp_path / "random"
    folder.mkdir()
    durations = {}
    for name in ("a.mp4", "b.mov", "c.mkv", "d.webm"):
        (folder / name).write_bytes(b"video")
        durations[name] = 120.0
    (folder / "ignore.txt").write_text("no")
    monkeypatch.setattr("kitok.dialogue_video.media_duration",
                        lambda path, ffprobe: durations[path.name])
    pool = BackgroundPool(tmp_path)
    assert {path.suffix for path in pool.discover("random")} == {".mp4", ".mov", ".mkv", ".webm"}
    first = pool.select_segment("random", "same-id", 25.0, seed="same-seed")
    assert first == pool.select_segment("random", "same-id", 25.0, seed="same-seed")
    assert first.start_offset + first.segment_duration <= first.source_duration
    assert any(pool.select_segment("random", "same-id", 25.0, seed=f"seed-{index}") != first
               for index in range(8))


def test_missing_random_background_fails_before_fish(local_kitok, tmp_path, monkeypatch):
    settings = local_kitok[0]
    settings.background_root = tmp_path / "backgrounds"
    monkeypatch.setattr("kitok.generation.FishVoiceClient",
                        Mock(side_effect=AssertionError("Fish must not be called")))
    with pytest.raises(ValueError, match="No random background videos found in assets/backgrounds/random"):
        GenerationService(settings, {}).plan(rick_item(), tmp_path)


def test_single_speaker_plan_uses_fish_measured_audio_and_local_segment(local_kitok, tmp_path,
                                                                        monkeypatch):
    settings = local_kitok[0]
    settings.background_root = tmp_path / "backgrounds"
    folder = settings.background_root / "random"
    folder.mkdir(parents=True)
    source = folder / "local.mov"
    source.write_bytes(b"video")
    audio = DialogueAudio(tmp_path / "rick.mp3", [TimedTurn("rick_es", 0, 25.25, "texto")], 25.25)
    fish = Mock()
    monkeypatch.setattr("kitok.generation.FishVoiceClient", Mock(return_value=fish))
    generate = Mock(return_value=audio)
    monkeypatch.setattr("kitok.generation.DialogueAudioService.generate_single", generate)
    monkeypatch.setattr("kitok.dialogue_video.media_duration", lambda *args: 90.0)

    plan = GenerationService(settings, {"voice_name": "unchanged"}).plan(rick_item(), tmp_path)

    assert plan.dialogue_audio is audio
    assert plan.local_background == source
    assert plan.background_selection.source == source
    assert plan.background_selection.segment_duration == 25.25
    assert plan.background_selection.start_offset + 25.25 <= 90.0
    generate.assert_called_once()
    fish.close.assert_called_once()


def test_single_speaker_audio_uses_rick_fish_and_measured_duration(tmp_path, monkeypatch):
    item = rick_item()
    fish = Mock()
    fish.synthesize.side_effect = lambda text, reference, target: target.write_bytes(b"mp3")
    monkeypatch.setattr("kitok.dialogue_audio.media_duration", lambda *args: 12.75)
    audio = DialogueAudioService(fish).generate_single(item, tmp_path)
    assert audio.duration == 12.75
    assert audio.timeline == [TimedTurn("rick_es", 0.0, 12.75, item.script)]
    assert fish.synthesize.call_args.args[0] == item.script


def test_long_rick_narration_uses_deterministic_active_pose_intervals(tmp_path):
    for name in ("rick_angry", "rick_pointing", "rick_face_crazy",
                 "rick_jump", "rick_talking_hands"):
        png(tmp_path / "characters" / "rick" / f"{name}.png")
    settings = SimpleNamespace(
        character_root=tmp_path / "characters",
        single_speaker_pose_min_seconds=3.0,
        single_speaker_pose_max_seconds=6.0,
    )
    item = rick_item()
    timeline = [TimedTurn("rick_es", 0.0, 25.0, item.script)]
    first = DialogueCompositor(settings)._poses(item, timeline)
    second = DialogueCompositor(settings)._poses(item, timeline)
    summary = [(layer.asset.pose, layer.start, layer.end) for layer in first]
    assert summary == [(layer.asset.pose, layer.start, layer.end) for layer in second]
    assert len(first) >= 5
    assert len({layer.asset.pose for layer in first}) > 1
    assert all(3.0 <= layer.end - layer.start <= 6.0 for layer in first)
    assert {layer.asset.pose for layer in first} <= {
        "rick_angry", "rick_pointing", "rick_face_crazy",
    }
    assert "rick_jump" not in {layer.asset.pose for layer in first}
    assert "rick_talking_hands" not in {layer.asset.pose for layer in first}
    assert first[0].start == 0 and first[0].initial and first[0].entry_seconds == 0


def test_local_composition_removes_background_audio_and_bounds_short_subtitles(tmp_path,
                                                                               monkeypatch):
    for name in ("rick_angry", "rick_pointing"):
        png(tmp_path / "characters" / "rick" / f"{name}.png")
    source = tmp_path / "random.mp4"
    source.write_bytes(b"video-with-audio")
    audio_path = tmp_path / "rick.mp3"
    audio_path.write_bytes(b"fish-audio")
    item = rick_item()
    duration = 12.0
    audio = DialogueAudio(audio_path, [TimedTurn("rick_es", 0, duration, item.script)], duration)
    pool = BackgroundPool(tmp_path)
    selection = SimpleNamespace(source=source, source_duration=90.0, start_offset=5.0,
                                segment_duration=duration,
                                metadata=lambda: {"background_source": str(source)})
    settings = SimpleNamespace(
        ffmpeg_binary="ffmpeg", ffprobe_binary="ffprobe",
        character_root=tmp_path / "characters",
        single_speaker_pose_min_seconds=3.0, single_speaker_pose_max_seconds=6.0,
        explainer_subtitle_max_chars=24, explainer_subtitle_min_words=2,
        explainer_subtitle_max_words=4, explainer_subtitle_bottom_margin=64,
    )
    command = []

    def run(args, **kwargs):
        command.extend(args)
        Path(args[-1]).write_bytes(b"composed")

    monkeypatch.setattr("kitok.dialogue_video.subprocess.run", run)
    compositor = DialogueCompositor(settings)
    target = tmp_path / "final.mp4"
    compositor.compose(item, source, audio, target, tmp_path, selection=selection)

    maps = [command[index + 1] for index, value in enumerate(command) if value == "-map"]
    assert maps == ["[video]", "1:a:0"]
    assert "0:a" not in command
    filters = command[command.index("-filter_complex") + 1]
    assert "scale=1080:1920" in filters and "crop=1080:1920" in filters
    assert "Alignment=2,MarginV=64" in filters
    cues = compositor.metadata["subtitle_cues"]
    assert cues[0]["start"] == 0 and cues[-1]["end"] == duration
    assert all(cue["end"] <= duration for cue in cues)
    assert all(len(cue["text"].split()) <= 4 for cue in cues)


def test_pexels_explainer_still_uses_existing_mpt_plan(local_kitok, tmp_path, monkeypatch):
    settings = local_kitok[0]
    fish = Mock(side_effect=AssertionError("Pexels explainer must not call local Fish client"))
    monkeypatch.setattr("kitok.generation.FishVoiceClient", fish)
    item = rick_item(visual_profile="pexels", visual_seed=None)
    plan = GenerationService(settings, {"subtitle_enabled": True}).plan(item, tmp_path)
    assert plan.local_background is None and plan.dialogue_audio is None
    assert plan.preset["voice_name"].startswith("fish_audio:")
    fish.assert_not_called()


def test_rick_random_smoke_cli_routes_without_loading_queue(monkeypatch):
    from kitok import cli
    import kitok.smoke_test as smoke

    called = Mock(return_value=0)
    monkeypatch.setattr(smoke, "run_rick_random_smoke", called)
    monkeypatch.setattr(cli, "load_all", Mock(side_effect=AssertionError("production queue loaded")))
    assert cli.main(["--smoke-test", "rick-random"]) == 0
    called.assert_called_once()
