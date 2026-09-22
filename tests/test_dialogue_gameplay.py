import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from kitok.config import Settings
from kitok.dialogue_audio import TimedTurn
from kitok.dialogue_subtitles import WEAK_ENDINGS, _word, dialogue_cues
from kitok.dialogue_video import BackgroundPool, BackgroundSelection, CharacterAssetRegistry, DialogueCompositor
from kitok.generation import GenerationPlan, GenerationService
from kitok.models import ContentItem
from kitok.smoke_test import SmokeSettings, run_dialogue_gameplay_smoke


def item(**changes):
    values = dict(id="demo", subject="Minecraft", script="", keywords=["minecraft"],
                  publish_at="2026-09-20T13:00:00+02:00", content_format="dialogue",
                  dialogue_preset="rick_morty_es", visual_profile="gameplay",
                  character_profile="rick_morty_es",
                  dialogue=[{"speaker": "rick_es", "text": "Morty, esto es una prueba."},
                            {"speaker": "morty_es", "text": "Rick, esto funciona."}])
    values.update(changes)
    return ContentItem.model_validate(values)


def png(path, color=(255, 0, 0, 255)):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    Image.new("RGBA", (20, 40), color).save(path.parent / "_temp.png")
    with Image.open(path.parent / "_temp.png") as figure:
        image.paste(figure, (30, 20))
    (path.parent / "_temp.png").unlink()
    image.save(path)


def test_character_registry_discovers_new_poses_validates_and_crops(tmp_path):
    folder = tmp_path / "rick"
    png(folder / "rick_angry.png")
    (folder / "broken.png").write_bytes(b"broken")
    warnings = []
    registry = CharacterAssetRegistry(tmp_path, warnings)
    assert [asset.pose for asset in registry.discover("rick")] == ["rick_angry"]
    assert "broken.png" in warnings[0]
    cropped = registry.cropped(registry.discover("rick")[0], tmp_path)
    with Image.open(cropped) as image:
        assert image.size == (20, 40)
    png(folder / "new_pose.png")
    assert {asset.pose for asset in CharacterAssetRegistry(tmp_path).discover("rick")} == {"rick_angry", "new_pose"}


def test_pose_selection_fallback_and_determinism(tmp_path):
    for name in ("rick_angry", "rick_jump", "rick_pointing"):
        png(tmp_path / "rick" / f"{name}.png")
    registry = CharacterAssetRegistry(tmp_path)
    first = registry.choose("rick", "nonexistent", "demo:0:rick_es")
    assert first == registry.choose("rick", "nonexistent", "demo:0:rick_es")
    second = registry.choose("rick", "nonexistent", "demo:1:rick_es", first.path)
    assert second.path != first.path
    assert registry.choose("rick", "angry", "demo:2:rick_es").pose == "rick_angry"


def test_pose_categories_prefer_active_and_reaction_and_exclude_disabled(tmp_path):
    names = ("rick_face_crazy", "rick_angry", "rick_pointing", "rick_jump",
             "rick_drinking", "rick_shrug", "rick_talking_hands", "brand_new_pose")
    for name in names:
        png(tmp_path / "rick" / f"{name}.png")
    registry = CharacterAssetRegistry(tmp_path)
    active = {registry.choose("rick", "talking", f"active:{index}", category="active").pose
              for index in range(30)}
    reactions = {registry.choose("rick", "surprised", f"reaction:{index}", category="reaction").pose
                 for index in range(30)}
    assert active <= {"rick_face_crazy", "rick_angry", "rick_pointing"}
    assert "brand_new_pose" not in active
    assert reactions <= {"rick_jump", "rick_drinking"}
    assert "rick_shrug" not in active | reactions
    assert "rick_talking_hands" not in active | reactions


def test_renderer_never_uses_inactive_reaction_pool(tmp_path):
    for character, poses in {
        "rick": ("rick_angry", "rick_jump"),
        "morty": ("morty_neutral", "morty_jump"),
    }.items():
        for pose in poses:
            png(tmp_path / "characters" / character / f"{pose}.png")
    settings = SimpleNamespace(character_root=tmp_path / "characters",
                               character_reaction_probability=1.0)
    compositor = DialogueCompositor(settings)
    layers = compositor._poses(item(), [
        TimedTurn("rick_es", 0, 2, "Hola"),
        TimedTurn("morty_es", 2.14, 4, "Hola"),
    ])
    assert [(layer.speaker, layer.asset.pose) for layer in layers] == [
        ("rick_es", "rick_angry"), ("morty_es", "morty_neutral")]
    assert all(layer.active for layer in layers)


def test_pose_category_falls_back_when_optional_pool_is_missing(tmp_path, monkeypatch):
    from kitok.dialogue_video import CHARACTERS
    png(tmp_path / "future" / "only_pose.png")
    monkeypatch.setitem(CHARACTERS, "future", {
        "active_poses": ["missing"], "reaction_poses": [], "disabled_poses": []})
    registry = CharacterAssetRegistry(tmp_path)
    assert registry.choose("future", "talking", "a", category="active").pose == "only_pose"
    assert registry.choose("future", "surprised", "b", category="reaction").pose == "only_pose"


def test_gameplay_uses_dialogue_preset_for_character_mapping_by_default(tmp_path):
    png(tmp_path / "characters" / "rick" / "rick_angry.png")
    png(tmp_path / "characters" / "morty" / "morty_neutral.png")
    settings = SimpleNamespace(character_root=tmp_path / "characters")
    compositor = DialogueCompositor(settings)
    layers = compositor._poses(item(character_profile=None),
                               [TimedTurn("rick_es", 0, 1, "Hola, Morty")])
    assert {layer.asset.character for layer in layers} == {"rick"}
    assert layers[0].initial and layers[0].entry_seconds == 0
    assert compositor.metadata["character_profile"] == "rick_morty_es"


def test_gameplay_selection_discovers_extensions_is_stable_and_fits(tmp_path, monkeypatch):
    folder = tmp_path / "gameplay"
    folder.mkdir()
    lengths = {}
    for name, length in (("a.mp4", 30.0), ("b.mov", 40.0),
                         ("c.mkv", 25.0), ("d.webm", 10.0)):
        path = folder / name
        path.write_bytes(b"video")
        lengths[name] = length
    monkeypatch.setattr("kitok.dialogue_video.media_duration",
                        lambda path, ffprobe: lengths[path.name])
    pool = BackgroundPool(tmp_path)
    first = pool.select_segment("gameplay", "demo", 22.47)
    assert first == pool.select_segment("gameplay", "demo", 22.47)
    assert first.source.suffix in {".mp4", ".mov", ".mkv"}
    assert first.start_offset >= 0
    assert first.start_offset + first.segment_duration <= first.source_duration
    assert first.segment_duration == 22.47
    assert any(pool.select_segment("gameplay", "demo", 22.47, seed=str(n)) != first for n in range(5))
    (folder / "new.webm").write_bytes(b"video")
    lengths["new.webm"] = 100.0
    assert folder / "new.webm" in pool.discover("gameplay")


def test_gameplay_start_is_stable_across_small_fish_duration_changes(tmp_path, monkeypatch):
    folder = tmp_path / "gameplay"
    folder.mkdir()
    (folder / "minecraft.mp4").write_bytes(b"av1")
    monkeypatch.setattr("kitok.dialogue_video.media_duration", lambda *args: 8961.116667)
    pool = BackgroundPool(tmp_path)
    short = pool.select_segment("gameplay", "same-content", 23.47)
    slightly_longer = pool.select_segment("gameplay", "same-content", 23.81)
    assert short.source == slightly_longer.source
    assert short.start_offset == slightly_longer.start_offset
    assert short.start_offset + slightly_longer.segment_duration <= short.source_duration


def test_gameplay_plan_uses_actual_audio_length_and_skips_mpt(local_kitok, tmp_path, monkeypatch):
    settings = local_kitok[0]
    settings.background_root = tmp_path / "backgrounds"
    folder = settings.background_root / "gameplay"
    folder.mkdir(parents=True)
    (folder / "av1.mp4").write_bytes(b"video")
    fish = Mock()
    monkeypatch.setattr("kitok.generation.FishVoiceClient", Mock(return_value=fish))
    audio = SimpleNamespace(path=tmp_path / "dialogue.m4a", duration=9.0, timeline=[])
    monkeypatch.setattr("kitok.generation.DialogueAudioService.generate", lambda *args: audio)
    monkeypatch.setattr("kitok.dialogue_audio.media_duration", lambda *args: 9.37)
    monkeypatch.setattr("kitok.dialogue_video.media_duration", lambda *args: 120.0)
    plan = GenerationService(settings, {}).plan(item(), tmp_path)
    assert plan.background_selection.segment_duration == 9.37
    assert plan.local_background == folder / "av1.mp4"
    assert plan.background_selection.start_offset + 9.37 <= 120.0
    fish.close.assert_called_once()


def test_gameplay_compose_seeks_before_input_and_maps_only_dialogue_audio(tmp_path, monkeypatch):
    settings = SimpleNamespace(ffmpeg_binary="ffmpeg", ffprobe_binary="ffprobe",
                               character_root=tmp_path / "characters")
    source = tmp_path / "av1.mp4"
    source.write_bytes(b"video")
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"audio")
    dialogue = SimpleNamespace(path=audio, duration=9.0,
                               timeline=[TimedTurn("rick_es", 0, 8, "Morty, esto es una prueba.")])
    selection = BackgroundSelection(source, 9000.0, 3500.0, 9.37)
    command = []
    def run(args, **kwargs):
        command.extend(args)
        Path(args[-1]).write_bytes(b"video")
    monkeypatch.setattr("kitok.dialogue_video.subprocess.run", run)
    compositor = DialogueCompositor(settings)
    compositor.compose(item(character_profile=None), source, dialogue, tmp_path / "final.mp4", tmp_path,
                       selection=selection)
    assert command.index("-ss") < command.index("-i")
    assert command[command.index("-ss") + 1] == "3500.000"
    assert "-stream_loop" not in command
    assert command[command.index("-t") + 1] == "9.370"
    maps = [command[i + 1] for i, value in enumerate(command) if value == "-map"]
    assert maps == ["[video]", "1:a:0"]


def test_dialogue_subtitle_environment_settings_control_chunks_and_style(tmp_path, monkeypatch):
    values = {
        "CHARACTER_BOTTOM_MARGIN": "270",
        "DIALOGUE_SUBTITLE_BOTTOM_MARGIN": "180",
        "DIALOGUE_SUBTITLE_FONT_SIZE": "15",
        "DIALOGUE_SUBTITLE_OUTLINE": "2",
        "DIALOGUE_SUBTITLE_BOLD": "true",
        "DIALOGUE_SUBTITLE_MIN_WORDS": "2",
        "DIALOGUE_SUBTITLE_MAX_WORDS": "3",
    }
    for name in values:
        monkeypatch.delenv(name, raising=False)
    defaults = Settings(_env_file=None)
    assert defaults.dialogue_subtitle_font_size == 13
    assert defaults.dialogue_subtitle_outline == 1.0
    assert defaults.dialogue_subtitle_bold is False
    assert defaults.dialogue_subtitle_min_words == 2
    assert defaults.dialogue_subtitle_max_words == 5
    with pytest.raises(ValueError, match="Dialogue subtitle minimum words"):
        Settings(_env_file=None, dialogue_subtitle_min_words=4,
                 dialogue_subtitle_max_words=3)

    for name, value in values.items():
        monkeypatch.setenv(name, value)
    settings = Settings(
        _env_file=None,
        character_root=tmp_path / "characters",
        ffmpeg_binary="ffmpeg",
        ffprobe_binary="ffprobe",
    )
    assert settings.character_bottom_margin == 270
    assert settings.dialogue_subtitle_bottom_margin == 180
    assert settings.dialogue_subtitle_font_size == 15
    assert settings.dialogue_subtitle_outline == 2.0
    assert settings.dialogue_subtitle_bold is True
    assert settings.dialogue_subtitle_min_words == 2
    assert settings.dialogue_subtitle_max_words == 3

    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"audio")
    dialogue = SimpleNamespace(
        path=audio,
        duration=6.0,
        timeline=[TimedTurn("rick_es", 0, 6, "Uno dos tres cuatro cinco seis")],
    )
    command = []

    def run(args, **kwargs):
        command.extend(args)
        Path(args[-1]).write_bytes(b"video")

    monkeypatch.setattr("kitok.dialogue_video.subprocess.run", run)
    compositor = DialogueCompositor(settings)
    compositor.compose(
        item(character_profile=None), source, dialogue, tmp_path / "final.mp4", tmp_path,
        selection=BackgroundSelection(source, 10.0, 0.0, 6.0),
    )
    filters = command[command.index("-filter_complex") + 1]
    assert ("force_style='FontSize=15,Bold=1,Alignment=2,MarginV=180,Outline=2'"
            in filters)
    assert all(2 <= len(cue["text"].split()) <= 3
               for cue in compositor.metadata["subtitle_cues"])


def test_chunked_subtitles_are_short_punctuation_aware_and_bounded():
    timeline = [TimedTurn("rick_es", 0, 3.2,
                          "Dos bombean sangre hacia las branquias, y el tercero manda sangre al resto del cuerpo."),
                TimedTurn("morty_es", 3.34, 4.5, "¿Tres? Qué locura.")]
    cues = dialogue_cues(timeline, max_chars=26)
    assert "".join(cue.text for cue in cues) == "".join(turn.text for turn in timeline)
    assert all(2 <= len(cue.text.split()) <= 5 for cue in cues)
    assert any(cue.text.strip().endswith("branquias,") for cue in cues)
    assert all(a.end <= b.start for a, b in zip(cues, cues[1:]))
    assert cues[0].start == 0 and cues[-1].end == 4.5
    assert all(cue.end <= (3.2 if cue.start < 3.2 else 4.5) for cue in cues)
    assert any(abs(cue.end - cue.start - (cues[1].end - cues[1].start)) > 0.01 for cue in cues[2:])


@pytest.mark.parametrize("text, expected", [
    ("Morty, hay una rana que puede congelarse",
     ["Morty, hay una rana", "que puede congelarse"]),
    ("Morty, los pulpos tienen tres corazones",
     ["Morty, los pulpos tienen", "tres corazones"]),
    ("Morty, en Venus llueve ácido sulfúrico",
     ["Morty, en Venus llueve", "ácido sulfúrico"]),
    ("Los pulpos tienen tres corazones",
     ["Los pulpos tienen", "tres corazones"]),
])
def test_semantic_subtitle_chunks_avoid_weak_or_incomplete_endings(text, expected):
    turn = TimedTurn("rick_es", 1.25, 5.75, text)
    cues = dialogue_cues([turn])
    assert [cue.text.strip() for cue in cues] == expected
    assert "".join(cue.text for cue in cues) == text
    assert all(_word(cue.text.split()[-1]) not in WEAK_ENDINGS for cue in cues[:-1])
    assert all(2 <= len(cue.text.split()) <= 5 for cue in cues)
    assert all(a.end <= b.start for a, b in zip(cues, cues[1:]))
    assert cues[0].start == turn.start and cues[-1].end == turn.end
    assert all(turn.start <= cue.start < cue.end <= turn.end for cue in cues)


def test_gameplay_smoke_preflight_does_not_touch_production_state(tmp_path):
    settings = SmokeSettings(smoke_root=tmp_path / "isolated", fish_api_key="",
                             background_root=tmp_path / "backgrounds")
    messages = []
    assert run_dialogue_gameplay_smoke(settings=settings, output=messages.append) == 2
    assert not settings.state_path.exists()
    assert any("FISH_API_KEY" in message for message in messages)


def test_gameplay_smoke_cli_routes_before_production_queue_load(monkeypatch):
    from kitok import cli
    import kitok.smoke_test as smoke
    called = Mock(return_value=0)
    monkeypatch.setattr(smoke, "run_dialogue_gameplay_smoke", called)
    monkeypatch.setattr(cli, "load_all", Mock(side_effect=AssertionError("production queue loaded")))
    assert cli.main(["--smoke-test", "dialogue-gameplay"]) == 0
    called.assert_called_once()
