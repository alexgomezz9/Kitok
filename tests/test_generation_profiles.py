import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from PIL import Image

import httpx
import pytest
from pydantic import ValidationError

from kitok.dialogue_audio import DialogueAudioService, TimedTurn
from kitok.dialogue_video import BackgroundPool, DialogueCompositor, write_subtitles
from kitok.fish_voice import FishVoiceClient, FishVoiceError
from kitok.generation import GenerationService
from kitok.models import ContentItem, ContentQueue
from kitok.mpt_client import MPTClient
from kitok.profiles import VOICES


def row(**changes):
    value = {"id": "demo", "subject": "Octopus", "script": "A sufficiently long narration script.",
             "keywords": ["octopus"], "caption": "Octopus fact",
             "publish_at": "2026-09-20T13:00:00+02:00"}
    value.update(changes)
    return value


def dialogue_row(**changes):
    return row(content_format="dialogue", script="", dialogue=[
        {"speaker": "rick_es", "text": "Los pulpos tienen tres corazones."},
        {"speaker": "morty_es", "text": "¿Tres? Qué locura."}], **changes)


def test_old_queue_defaults_and_dialogue_script(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text(json.dumps([row()]))
    item = ContentQueue.load(path).items[0]
    assert (item.content_format, item.voice_profile, item.visual_profile) == ("explainer", "alvaro", "pexels")
    assert item.effective_script == item.script
    dialogue = ContentItem.model_validate(dialogue_row())
    assert dialogue.effective_script == "Los pulpos tienen tres corazones.\n¿Tres? Qué locura."


@pytest.mark.parametrize("profile,expected", [
    ("alvaro", "es-ES-AlvaroNeural"),
    ("rick_es", "fish_audio:f75ae6efbe9945c19be01e233e045d0e:Rick ES"),
    ("morty_es", "fish_audio:5d4a03fbc6d94f9897d5f3969fd9a765:Morty ES"),
])
def test_voice_resolution_and_immutable_preset(profile, expected, tmp_path, local_kitok):
    settings = local_kitok[0]
    preset = {"voice_name": "es-ES-AlvaroNeural", "subtitle_enabled": True}
    item = ContentItem.model_validate(row(voice_profile=profile))
    plan = GenerationService(settings, preset).plan(item, tmp_path)
    assert plan.preset["voice_name"] == expected
    assert preset["voice_name"] == "es-ES-AlvaroNeural"


@pytest.mark.parametrize("changes", [
    {"voice_profile": "unknown"}, {"visual_profile": "unknown"},
    {"content_format": "unknown"}, {"content_format": "dialogue", "script": "", "dialogue": []},
    {"content_format": "dialogue", "script": "", "dialogue": [
        {"speaker": "rick_es", "text": "Yes"}, {"speaker": "unknown", "text": "No"}]},
])
def test_bad_generation_values_rejected(changes):
    with pytest.raises(ValidationError):
        ContentItem.model_validate(row(**changes))


def test_mpt_payload_uses_derived_dialogue_script_without_mutating_preset():
    captured = {}
    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"data": {"task_id": "task"}})
    client = MPTClient("http://mpt.invalid")
    client.client.close()
    client.client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://mpt.invalid")
    preset = {"voice_name": "no-voice", "subtitle_enabled": False}
    assert client.submit_video(ContentItem.model_validate(dialogue_row()), preset) == "task"
    assert captured["video_script"].startswith("Los pulpos")
    assert captured["voice_name"] == "no-voice"
    assert preset == {"voice_name": "no-voice", "subtitle_enabled": False}
    client.close()


def test_fish_request_model_reference_atomic_output_and_retries(tmp_path, monkeypatch):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(429 if len(seen) == 1 else 200,
                              content=b"ID3audio", headers={"content-type": "audio/mpeg"})
    monkeypatch.setattr("kitok.fish_voice.time.sleep", lambda _: None)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        fish = FishVoiceClient("private-token", "s2.1-pro-free", client=http)
        target = tmp_path / "turn.mp3"
        fish.synthesize("Hola", VOICES["rick_es"].value, target)
    assert len(seen) == 2 and target.read_bytes() == b"ID3audio"
    assert not (tmp_path / "turn.mp3.part").exists()
    assert json.loads(seen[0].content) == {"text": "Hola", "reference_id": VOICES["rick_es"].value,
                                           "format": "mp3"}
    assert seen[0].headers["model"] == "s2.1-pro-free"
    assert seen[0].headers["authorization"] == "Bearer private-token"


def test_fish_errors_never_include_key_or_corrupt_destination(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401, text="private-token"))) as http:
        target = tmp_path / "turn.mp3"
        target.write_bytes(b"original")
        with pytest.raises(FishVoiceError) as error:
            FishVoiceClient("private-token", client=http).synthesize("Hola", "ref", target)
    assert "private-token" not in str(error.value)
    assert target.read_bytes() == b"original"


def test_fish_rejects_non_audio_success_without_replacing_file(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not audio"))) as http:
        target = tmp_path / "turn.mp3"
        target.write_bytes(b"original")
        with pytest.raises(FishVoiceError, match="no valid audio"):
            FishVoiceClient("private-token", client=http).synthesize("Hola", "ref", target)
    assert target.read_bytes() == b"original"


def test_audio_timeline_gap_order_concat_and_subtitles(tmp_path, monkeypatch):
    item = ContentItem.model_validate(dialogue_row())
    fish = Mock()
    fish.synthesize.side_effect = lambda text, reference_id, destination: destination.write_bytes(b"mp3")
    durations = iter([2.93, 2.63])
    monkeypatch.setattr("kitok.dialogue_audio.media_duration", lambda *args: next(durations))
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"m4a")
    monkeypatch.setattr("kitok.dialogue_audio.subprocess.run", run)
    audio = DialogueAudioService(fish, gap_ms=150).generate(item, tmp_path)
    assert [(t.speaker, t.start, t.end) for t in audio.timeline] == [
        ("rick_es", 0, 2.93), ("morty_es", 3.08, 5.71)]
    assert "atrim=duration=0.150" in commands[0][commands[0].index("-filter_complex") + 1]
    assert "concat=n=3" in commands[0][commands[0].index("-filter_complex") + 1]
    subtitle = write_subtitles(audio.timeline, tmp_path / "dialogue.srt").read_text()
    assert "00:00:03,080 --> 00:00:05,710" in subtitle
    assert "¿Tres? Qué locura." in subtitle


def test_background_pool_deterministic_and_empty(tmp_path):
    pool = BackgroundPool(tmp_path)
    with pytest.raises(ValueError, match="No MP4 gameplay clips"):
        pool.choose("minecraft", "demo")
    folder = tmp_path / "minecraft"
    folder.mkdir()
    for name in ("a.mp4", "b.mp4"):
        (folder / name).write_bytes(b"clip")
    assert pool.choose("minecraft", "demo") == pool.choose("minecraft", "demo")


def test_empty_local_pool_fails_before_fish(local_kitok, tmp_path, monkeypatch):
    settings = local_kitok[0]
    settings.background_root = tmp_path / "backgrounds"
    monkeypatch.setattr("kitok.generation.FishVoiceClient", Mock(side_effect=AssertionError("Fish called")))
    with pytest.raises(ValueError, match="No MP4 gameplay clips"):
        GenerationService(settings, {}).plan(ContentItem.model_validate(dialogue_row(visual_profile="minecraft")), tmp_path)


def test_pexels_dialogue_plan_requests_silent_mpt_visual(local_kitok, tmp_path, monkeypatch):
    settings = local_kitok[0]
    fish = Mock()
    fish_factory = Mock(return_value=fish)
    monkeypatch.setattr("kitok.generation.FishVoiceClient", fish_factory)
    monkeypatch.setattr("kitok.generation.DialogueAudioService.generate", lambda *args: SimpleNamespace())
    preset = {"voice_name": "es-ES-AlvaroNeural", "subtitle_enabled": True, "font_size": 100}
    plan = GenerationService(settings, preset).plan(ContentItem.model_validate(dialogue_row()), tmp_path)
    assert plan.preset == {"voice_name": "no-voice", "subtitle_enabled": False,
                           "font_size": 100, "video_script": "octopus"}
    assert preset["voice_name"] == "es-ES-AlvaroNeural"
    fish.close.assert_called_once()
    assert fish_factory.call_args.kwargs["timeout"] == settings.fish_tts_timeout_seconds


def test_compositor_uses_timeline_for_poses_and_exact_duration(tmp_path, monkeypatch, caplog):
    settings = SimpleNamespace(ffmpeg_binary="ffmpeg", ffprobe_binary="ffprobe",
                               character_root=tmp_path / "characters")
    item = ContentItem.model_validate(dialogue_row(character_profile="rick_morty_es"))
    timeline = [TimedTurn("rick_es", 0, 1, "Rick"), TimedTurn("morty_es", 1.15, 2.15, "Morty")]
    compositor = DialogueCompositor(settings)
    assert compositor._poses(item, timeline) == []
    assert "No character PNG" in caplog.text
    assert len(compositor.warnings) == 2
    for folder in ("rick", "morty"):
        directory = settings.character_root / folder
        directory.mkdir(parents=True)
        Image.new("RGBA", (40, 60), (255, 0, 0, 180)).save(directory / "pose_01.png")
    compositor = DialogueCompositor(settings)
    poses = compositor._poses(item, timeline)
    assert [(layer.asset.path.name, layer.side, layer.active) for layer in poses] == [
        ("pose_01.png", "left", True), ("pose_01.png", "right", True)]
    assert poses[0].start == 0 and poses[0].initial
    assert poses[1].entry_seconds > 0 and poses[0].exit_seconds > 0
    monkeypatch.setattr("kitok.dialogue_video.media_duration", lambda *args: 1.0)
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"video")
    monkeypatch.setattr("kitok.dialogue_video.subprocess.run", run)
    dialogue = SimpleNamespace(path=tmp_path / "audio.m4a", timeline=timeline, duration=2.15)
    destination = tmp_path / "final.mp4"
    compositor.compose(item, tmp_path / "source.mp4", dialogue, destination, tmp_path)
    command = commands[0]
    assert command[command.index("-t") + 1] == "2.150"
    assert command[command.index("-stream_loop") + 1] == "-1"
    filters = command[command.index("-filter_complex") + 1]
    assert "gte(t,0.000)" in filters
    assert "format=rgba,scale=" in filters
    assert "overlay=x='if(" in filters
    assert "MarginV=48" in filters
    assert "gte(t,1.150)" in filters
    assert destination.read_bytes() == b"video"
