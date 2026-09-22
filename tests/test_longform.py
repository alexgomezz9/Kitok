import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import longform
from kitok.config import Settings
from kitok.models import MPTTask


def write_definition(root: Path, **overrides) -> Path:
    script_text = overrides.pop(
        "script_text",
        "A complete narration script that is long enough for ContentItem.",
    )
    script = root / "content" / "longform" / "script.txt"
    script.parent.mkdir(parents=True)
    script.write_text(script_text, encoding="utf-8")
    data = {
        "id": "test_longform_001",
        "subject": "A useful long-form test",
        "youtube_title": "A useful long-form test",
        "script_file": "content/longform/script.txt",
        "keywords": ["one", "two"],
        "video_clip_duration": 7,
    }
    data.update(overrides)
    path = root / "content" / "longform" / "item.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_longform_config_reads_script_and_builds_content_item(tmp_path):
    path = write_definition(tmp_path)

    definition = longform.load_longform_config(path, project_root=tmp_path)

    assert definition.item.id == "test_longform_001"
    assert definition.item.script.startswith("A complete narration")
    assert definition.item.schedule_enabled is False
    assert definition.item.platforms == ["youtube"]
    assert definition.voice_name == (
        "fish_audio:e686ae649ee44f219a108aacba206c1a:Loose Thread Narrator"
    )
    assert definition.voice_rate == 0.98
    assert definition.video_clip_duration == 7
    assert definition.background_music_file == (
        tmp_path / "assets/music/loose_thread/level.mp3"
    )
    assert definition.background_music_volume == 0.07
    assert definition.audio_loudness_target == -16
    assert definition.audio_lra_target == 7
    assert definition.audio_true_peak_target == -1.5
    assert definition.music_enabled is True
    assert definition.preserve_debug_audio is False


def test_longform_config_honors_new_and_legacy_narrator_overrides(tmp_path):
    legacy = longform.load_longform_config(
        write_definition(tmp_path, voice_name="fish_audio:old:Daniel", voice_rate=1.0),
        project_root=tmp_path,
    )
    assert legacy.voice_name == "fish_audio:old:Daniel"
    assert legacy.voice_rate == 1.0

    other_root = tmp_path / "new-key"
    modern = longform.load_longform_config(
        write_definition(
            other_root,
            narrator_voice="fish_audio:new:Other Narrator",
            background_music_file="custom/music.mp3",
            background_music_volume=0.12,
            audio_loudness_target=-14,
            audio_lra_target=5,
            audio_true_peak_target=-1,
            music_enabled=False,
            preserve_debug_audio=True,
        ),
        project_root=other_root,
    )
    assert modern.voice_name == "fish_audio:new:Other Narrator"
    assert modern.background_music_file == other_root / "custom/music.mp3"
    assert modern.background_music_volume == 0.12
    assert modern.audio_loudness_target == -14
    assert modern.audio_lra_target == 5
    assert modern.audio_true_peak_target == -1
    assert modern.music_enabled is False
    assert modern.preserve_debug_audio is True


def test_longform_preset_overrides_base_without_modifying_file(tmp_path):
    definition = longform.load_longform_config(
        write_definition(tmp_path, voice_name="en-US-GuyNeural", voice_rate=1.1),
        project_root=tmp_path,
    )
    preset_path = tmp_path / "preset.json"
    base = {"video_aspect": "9:16", "subtitle_enabled": True, "kept": "yes"}
    preset_path.write_text(json.dumps(base), encoding="utf-8")

    result = longform.build_longform_preset(definition, preset_path=preset_path)

    assert result["video_aspect"] == "16:9"
    assert result["video_clip_duration"] == 7
    assert result["voice_rate"] == 1.1
    assert result["subtitle_enabled"] is False
    assert result["kept"] == "yes"
    assert json.loads(preset_path.read_text(encoding="utf-8")) == base


def test_inline_fish_directions_are_preserved_in_mpt_payload(tmp_path):
    script = (
        "[professional broadcast tone] This is a complete narration opening.\n"
        "[long pause]\n"
        "[quietly, with disbelief] And this line remains unchanged."
    )
    definition = longform.load_longform_config(
        write_definition(tmp_path, script_text=script), project_root=tmp_path
    )
    preset_path = tmp_path / "preset.json"
    preset_path.write_text("{}", encoding="utf-8")
    preset = longform.build_longform_preset(definition, preset_path=preset_path)

    from kitok.mpt_client import MPTClient
    payload = MPTClient.build_payload(definition.item, preset)

    assert definition.item.script == script
    assert payload["video_script"] == script


def test_longform_changes_do_not_mutate_short_form_defaults(tmp_path):
    preset_path = Path(__file__).resolve().parents[1] / "presets" / "mpt_default.json"
    before = preset_path.read_bytes()
    definition = longform.load_longform_config(
        write_definition(tmp_path), project_root=tmp_path
    )
    longform.build_longform_preset(definition, preset_path=preset_path)

    settings = Settings(_env_file=None)
    assert settings.dialogue_gap_ms == 140
    assert settings.dialogue_subtitle_min_words == 2
    assert settings.dialogue_subtitle_max_words == 5
    assert preset_path.read_bytes() == before


def test_longform_output_path(tmp_path):
    assert longform.longform_output_path("abc_123", project_root=tmp_path) == (
        tmp_path / "outputs" / "longform" / "abc_123.mp4"
    )


def test_refuses_duplicate_saved_task_before_creating_client(tmp_path):
    definition = longform.load_longform_config(
        write_definition(tmp_path, music_enabled=False), project_root=tmp_path
    )
    task_path = longform.longform_task_path(definition.item.id, project_root=tmp_path)
    task_path.parent.mkdir(parents=True)
    task_path.write_text(
        json.dumps({"task_id": "existing-task", "content_id": definition.item.id}),
        encoding="utf-8",
    )

    def unexpected_client(*args, **kwargs):
        raise AssertionError("client must not be created for a duplicate submission")

    with pytest.raises(longform.LongformError, match="--resume existing-task"):
        longform.run_longform(
            definition,
            {},
            settings=Settings(_env_file=None),
            project_root=tmp_path,
            client_factory=unexpected_client,
        )


def test_resume_polls_and_downloads_without_submitting(tmp_path):
    definition = longform.load_longform_config(
        write_definition(tmp_path, music_enabled=False), project_root=tmp_path
    )

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.closed = False
            self.submitted = False

        def submit_video(self, item, preset):
            self.submitted = True
            raise AssertionError("resume must not submit")

        def get_task(self, task_id):
            return MPTTask(
                task_id=task_id,
                state=longform.TASK_STATE_COMPLETE,
                progress=100,
                videos=["/video.mp4"],
            )

        def download_artifact(self, artifact, destination):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"video")

        def close(self):
            self.closed = True

    clients = []

    def factory(*args, **kwargs):
        client = FakeClient(*args, **kwargs)
        clients.append(client)
        return client

    output = longform.run_longform(
        definition,
        {},
        settings=Settings(_env_file=None),
        project_root=tmp_path,
        resume_task_id="resume-me",
        client_factory=factory,
        audio_processor=lambda source, definition, settings: source,
    )

    assert output.read_bytes() == b"video"
    assert clients[0].submitted is False
    assert clients[0].closed is True


def test_audio_postprocess_normalizes_narration_and_mixes_music(tmp_path, monkeypatch):
    music = tmp_path / "music.mp3"
    music.write_bytes(b"music")
    definition = longform.load_longform_config(
        write_definition(
            tmp_path,
            background_music_file=str(music),
            background_music_volume=0.07,
        ),
        project_root=tmp_path,
    )
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"raw-mpt-video")
    commands = []

    monkeypatch.setattr(longform, "media_duration", lambda *args: 20.0)

    def run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"processed-video")

    monkeypatch.setattr(longform.subprocess, "run", run)
    result = longform.postprocess_longform_audio(
        source, definition, settings=Settings(_env_file=None)
    )

    assert result == source
    assert source.read_bytes() == b"processed-video"
    command = commands[0]
    filters = command[command.index("-filter_complex") + 1]
    assert "loudnorm=I=-16:LRA=7:TP=-1.5" in filters
    assert "apad=whole_dur=20" in filters
    assert "atrim=duration=20" in filters
    assert "volume=0.07" in filters
    assert "amix=inputs=2:duration=first:dropout_transition=2:normalize=0" in filters
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-b:a") + 1] == "192k"
    assert command[command.index("-stream_loop") + 1] == "-1"


def test_audio_extends_music_through_video_end_after_shorter_narration(
    tmp_path, monkeypatch
):
    video_duration = 20.7
    narration_duration = 17.8
    music = tmp_path / "music.mp3"
    music.write_bytes(b"music")
    definition = longform.load_longform_config(
        write_definition(tmp_path, background_music_file=str(music)),
        project_root=tmp_path,
    )
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"raw-mpt-video")
    commands = []
    monkeypatch.setattr(longform, "media_duration", lambda *args: video_duration)

    def run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"processed-video")

    monkeypatch.setattr(longform.subprocess, "run", run)
    longform.postprocess_longform_audio(
        source, definition, settings=Settings(_env_file=None)
    )

    command = commands[0]
    filters = command[command.index("-filter_complex") + 1]
    output_duration = float(command[command.index("-t") + 1])
    assert narration_duration < video_duration
    assert "apad=whole_dur=20.7,atrim=duration=20.7[voice]" in filters
    assert "afade=t=out:st=19.2:d=1.5,atrim=duration=20.7[music]" in filters
    assert "normalize=0,atrim=duration=20.7[audio]" in filters
    assert output_duration == pytest.approx(video_duration)
    assert command[command.index("-c:v") + 1] == "copy"


def test_debug_mode_preserves_raw_normalized_and_final_mix_audio(
    tmp_path, monkeypatch
):
    music = tmp_path / "music.mp3"
    music.write_bytes(b"music")
    definition = longform.load_longform_config(
        write_definition(
            tmp_path,
            background_music_file=str(music),
            preserve_debug_audio=True,
        ),
        project_root=tmp_path,
    )
    source = tmp_path / "outputs" / "longform" / "test_longform_001.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"raw-mpt-video")
    commands = []
    monkeypatch.setattr(longform, "media_duration", lambda *args: 20.7)

    def run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"mock-audio-or-video")

    monkeypatch.setattr(longform.subprocess, "run", run)
    longform.postprocess_longform_audio(
        source, definition, settings=Settings(_env_file=None)
    )

    debug_dir = source.parent / "debug"
    expected = [
        debug_dir / "test_longform_001_01_raw.mp3",
        debug_dir / "test_longform_001_02_normalized.mp3",
        debug_dir / "test_longform_001_03_final_mix.mp3",
    ]
    assert all(path.read_bytes() == b"mock-audio-or-video" for path in expected)
    assert len(commands) == 4
    raw_command, normalized_command, mix_command, final_command = commands
    assert "-af" not in raw_command
    assert normalized_command[normalized_command.index("-af") + 1] == (
        "loudnorm=I=-16:LRA=7:TP=-1.5"
    )
    assert "-filter_complex" in mix_command
    assert final_command[final_command.index("-i") + 1] == mix_command[-1]
    assert "-af" not in final_command


def test_missing_music_fails_cleanly_before_creating_client(tmp_path):
    definition = longform.load_longform_config(
        write_definition(tmp_path), project_root=tmp_path
    )
    with pytest.raises(longform.LongformError, match="music is enabled.*does not exist"):
        longform.run_longform(
            definition,
            {},
            settings=Settings(_env_file=None),
            project_root=tmp_path,
            client_factory=lambda *args, **kwargs: pytest.fail("client was created"),
        )


def test_failed_audio_postprocess_preserves_raw_mpt_video(tmp_path, monkeypatch):
    music = tmp_path / "music.mp3"
    music.write_bytes(b"music")
    definition = longform.load_longform_config(
        write_definition(tmp_path, background_music_file=str(music)),
        project_root=tmp_path,
    )
    source = tmp_path / "raw.mp4"
    source.write_bytes(b"successful-raw-mpt-render")
    monkeypatch.setattr(longform, "media_duration", lambda *args: 20.0)
    monkeypatch.setattr(
        longform.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, args[0], stderr="mock ffmpeg failure")
        ),
    )

    with pytest.raises(longform.LongformError, match="during FFmpeg mix"):
        longform.postprocess_longform_audio(
            source, definition, settings=Settings(_env_file=None)
        )

    assert source.read_bytes() == b"successful-raw-mpt-render"
    assert not source.with_name(f".{source.name}.postprocess.tmp{source.suffix}").exists()
