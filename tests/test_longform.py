import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import longform
from kitok.config import Settings
from kitok.models import MPTTask


def write_definition(root: Path, **overrides) -> Path:
    script = root / "content" / "longform" / "script.txt"
    script.parent.mkdir(parents=True)
    script.write_text(
        "A complete narration script that is long enough for ContentItem.",
        encoding="utf-8",
    )
    data = {
        "id": "test_longform_001",
        "subject": "A useful long-form test",
        "youtube_title": "A useful long-form test",
        "script_file": "content/longform/script.txt",
        "keywords": ["one", "two"],
        "voice_name": "en-US-GuyNeural",
        "voice_rate": 1.1,
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
    assert definition.voice_name == "en-US-GuyNeural"
    assert definition.video_clip_duration == 7


def test_longform_preset_overrides_base_without_modifying_file(tmp_path):
    definition = longform.load_longform_config(
        write_definition(tmp_path), project_root=tmp_path
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


def test_longform_output_path(tmp_path):
    assert longform.longform_output_path("abc_123", project_root=tmp_path) == (
        tmp_path / "outputs" / "longform" / "abc_123.mp4"
    )


def test_refuses_duplicate_saved_task_before_creating_client(tmp_path):
    definition = longform.load_longform_config(
        write_definition(tmp_path), project_root=tmp_path
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
        write_definition(tmp_path), project_root=tmp_path
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
    )

    assert output.read_bytes() == b"video"
    assert clients[0].submitted is False
    assert clients[0].closed is True
