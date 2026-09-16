import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from kitok import cli
from kitok.config import Settings
from kitok.file_manager import output_filename
from kitok.models import ContentQueue, MPTTask, ValidationResult
from kitok.regeneration import ReadyRegenerator
from kitok.state import StateStore
from kitok.video_validator import VideoValidator


def item(cid, status="ready"):
    return {
        "id": cid, "subject": f"Subject {cid}",
        "script": "A sufficiently long narration script for the item.",
        "keywords": ["test"], "caption": f"Caption {cid}",
        "publish_at": "2026-09-20T13:00:00+02:00",
    }


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr("kitok.config.PROJECT_ROOT", tmp_path)
    settings = Settings(_env_file=None, ready_dir=tmp_path / "phone")
    settings.ensure_directories()
    settings.mpt_preset_path = tmp_path / "preset.json"
    settings.mpt_preset_path.write_text('{"font_size": 81}')
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    state = StateStore(settings.state_path)

    def make(ids):
        settings.queue_path.write_text(json.dumps([item(cid) for cid in ids]))
        queue = ContentQueue.load(settings.queue_path)
        for entry in queue.items:
            state.upsert(entry.id, status="ready", attempts=2, mpt_task_id="old-task",
                         mpt_progress=99)
            name = output_filename(entry)
            for directory in (settings.generated_dir, settings.local_ready_dir, settings.ready_dir):
                (directory / name).write_bytes(b"old-" + entry.id.encode())
        return queue

    return settings, state, make


class FakeMPT:
    def __init__(self, state, *, fail_ids=()):
        self.state = state
        self.fail_ids = set(fail_ids)
        self.submitted = []
        self.downloaded = []
        self.closed = False

    def submit_video(self, item, preset):
        saved = StateStore(self.state.path).get(item.id)
        assert saved["mpt_task_id"] is None
        assert saved["mpt_progress"] is None
        self.submitted.append((item.id, dict(preset)))
        return "new-" + item.id

    def get_task(self, task_id):
        cid = task_id.removeprefix("new-")
        if cid in self.fail_ids:
            return MPTTask(task_id=task_id, state=-1, error="render failed")
        return MPTTask(task_id=task_id, state=1, videos=[cid])

    def download_artifact(self, artifact, destination):
        self.downloaded.append(artifact)
        destination.write_bytes(b"fresh-" + artifact.encode())

    def close(self):
        self.closed = True


def validator(monkeypatch):
    seen = []

    def validate(self, path):
        seen.append(path.read_bytes())
        return ValidationResult(ok=True, duration=12, width=1080, height=1920,
                                video_codec="h264", pixel_format="yuv420p", fps=30,
                                video_bitrate=4000000, audio_codec="aac", audio_profile="LC",
                                audio_bitrate=120000, audio_sample_rate=48000, audio_channels=2,
                                file_size=path.stat().st_size)

    monkeypatch.setattr("kitok.regeneration.VideoValidator.validate", validate)
    return seen


def test_all_ready_items_selected_and_current_preset_used(setup, monkeypatch, capsys):
    settings, state, make = setup
    queue = make(["one", "two", "three"])
    seen = validator(monkeypatch)
    fake = FakeMPT(state)
    monkeypatch.setattr(cli, "MPTClient", Mock(return_value=fake))

    assert cli.main(["--regenerate-all-ready"]) == 0

    assert [cid for cid, _ in fake.submitted] == ["one", "two", "three"]
    assert all(preset == {"font_size": 81} for _, preset in fake.submitted)
    assert seen == [b"fresh-one", b"fresh-two", b"fresh-three"]
    assert fake.closed
    assert "[3/3]" in capsys.readouterr().out
    for entry in queue.items:
        row = StateStore(state.path).get(entry.id)
        assert row["attempts"] == 3
        assert row["mpt_task_id"] == "new-" + entry.id
        assert row["regeneration_status"] == "succeeded"
        assert row["status"] == "ready"


def test_non_ready_items_skipped(setup, monkeypatch):
    settings, state, make = setup
    make(["ready", "pending", "failed"])
    state.upsert("pending", status="pending")
    state.upsert("failed", status="failed")
    validator(monkeypatch)
    fake = FakeMPT(state)

    summary = ReadyRegenerator(settings, ContentQueue.load(settings.queue_path), state,
                               fake, {"font_size": 81}, print_line=lambda _: None).run()

    assert (summary.regenerated, summary.failed, summary.skipped) == (1, 0, 2)
    assert [cid for cid, _ in fake.submitted] == ["ready"]
    assert state.get("pending")["attempts"] == 2
    assert state.get("failed")["attempts"] == 2


def test_publishing_metadata_blocks_regeneration(setup, monkeypatch, capsys):
    settings, state, make = setup
    make(["cloud", "buffer", "safe"])
    state.update_publishing("cloud", "cloudinary", public_id="uploaded")
    state.update_publishing("buffer", "buffer", "tiktok", status="unknown")
    validator(monkeypatch)
    fake = FakeMPT(state)
    monkeypatch.setattr(cli, "MPTClient", Mock(return_value=fake))

    assert cli.main(["--regenerate-all-ready"]) == 0

    assert [cid for cid, _ in fake.submitted] == ["safe"]
    assert state.get("cloud")["publishing"]["cloudinary"]["public_id"] == "uploaded"
    assert state.get("buffer")["publishing"]["buffer"]["tiktok"]["status"] == "unknown"
    assert state.get("cloud")["attempts"] == 2
    assert state.get("buffer")["attempts"] == 2
    output = capsys.readouterr().out
    assert "Cloudinary" in output and "Buffer" in output
    assert "skipped=2" in output


def test_dry_run_lists_candidates_without_any_writes(setup, monkeypatch, capsys):
    settings, state, make = setup
    make(["one", "two", "pending"])
    state.upsert("pending", status="pending")
    before = {path.relative_to(settings.queue_path.parent): (path.read_bytes(), path.stat().st_mtime_ns)
              for path in settings.queue_path.parent.rglob("*") if path.is_file()}
    monkeypatch.setattr(cli, "MPTClient", Mock(side_effect=AssertionError("MPT constructed")))
    monkeypatch.setattr(cli, "configure_logging", Mock(side_effect=AssertionError("logging configured")))
    monkeypatch.setattr(Settings, "ensure_directories", Mock(side_effect=AssertionError("mkdir called")))

    assert cli.main(["--regenerate-all-ready", "--dry-run"]) == 0

    after = {path.relative_to(settings.queue_path.parent): (path.read_bytes(), path.stat().st_mtime_ns)
             for path in settings.queue_path.parent.rglob("*") if path.is_file()}
    assert after == before
    output = capsys.readouterr().out
    assert "WOULD REGENERATE one" in output
    assert "WOULD REGENERATE two" in output
    assert "SKIP pending" in output
    assert "would_regenerate=2" in output


def test_one_failure_does_not_stop_remaining_items(setup, monkeypatch, capsys):
    settings, state, make = setup
    queue = make(["one", "bad", "three"])
    validator(monkeypatch)
    fake = FakeMPT(state, fail_ids={"bad"})
    monkeypatch.setattr(cli, "MPTClient", Mock(return_value=fake))

    assert cli.main(["--regenerate-all-ready"]) == 1

    assert [cid for cid, _ in fake.submitted] == ["one", "bad", "three"]
    failed = StateStore(state.path).get("bad")
    assert "render failed" in failed["last_error"]
    assert failed["regeneration_status"] == "failed"
    assert failed["status"] == "ready"
    assert failed["attempts"] == 3
    name = output_filename(queue.by_id()["bad"])
    assert (settings.generated_dir / name).read_bytes() == b"old-bad"
    assert "regenerated=2 failed=1 skipped=0" in capsys.readouterr().out


def test_only_selected_files_are_replaced_after_validation(setup, monkeypatch):
    settings, state, make = setup
    queue = make(["one", "protected", "pending"])
    state.update_publishing("protected", "cloudinary", public_id="uploaded")
    state.upsert("pending", status="pending")
    sentinels = []
    for directory in (settings.generated_dir, settings.local_ready_dir, settings.ready_dir):
        sentinel = directory / "unrelated.mp4"
        sentinel.write_bytes(b"untouched")
        sidecar = directory / output_filename(queue.by_id()["one"]).replace(".mp4", ".json")
        sidecar.write_text("existing metadata")
        sentinels.extend([sentinel, sidecar])
    seen = validator(monkeypatch)
    fake = FakeMPT(state)

    summary = ReadyRegenerator(settings, queue, state, fake, {}, print_line=lambda _: None).run()

    assert (summary.regenerated, summary.failed, summary.skipped) == (1, 0, 2)
    assert seen == [b"fresh-one"]
    for directory in (settings.generated_dir, settings.local_ready_dir, settings.ready_dir):
        assert (directory / output_filename(queue.by_id()["one"])).read_bytes() == b"fresh-one"
        assert (directory / output_filename(queue.by_id()["protected"])).read_bytes() == b"old-protected"
        assert (directory / output_filename(queue.by_id()["pending"])).read_bytes() == b"old-pending"
    assert all(path.read_bytes() in (b"untouched", b"existing metadata") for path in sentinels)
    assert settings.queue_path.read_text() == json.dumps([item(cid) for cid in ("one", "protected", "pending")])


def test_invalid_download_does_not_replace_existing_files(setup, monkeypatch):
    settings, state, make = setup
    queue = make(["bad", "good"])
    fake = FakeMPT(state)

    def validate(self, path):
        if path.read_bytes() == b"fresh-bad":
            return ValidationResult(ok=False, errors=["invalid video stream"])
        return ValidationResult(ok=True, duration=12, width=1080, height=1920,
                                video_codec="h264", pixel_format="yuv420p", fps=30,
                                video_bitrate=4000000, audio_codec="aac", audio_profile="LC",
                                audio_bitrate=120000, audio_sample_rate=48000, audio_channels=2,
                                file_size=path.stat().st_size)

    monkeypatch.setattr("kitok.regeneration.VideoValidator.validate", validate)
    summary = ReadyRegenerator(settings, queue, state, fake, {}, print_line=lambda _: None).run()

    assert (summary.regenerated, summary.failed, summary.skipped) == (1, 1, 0)
    for directory in (settings.generated_dir, settings.local_ready_dir, settings.ready_dir):
        assert (directory / output_filename(queue.by_id()["bad"])).read_bytes() == b"old-bad"
        assert (directory / output_filename(queue.by_id()["good"])).read_bytes() == b"fresh-good"
    assert "invalid video stream" in state.get("bad")["last_error"]


def test_validator_rejects_non_mp4_container(tmp_path, monkeypatch):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"some media")
    info = {"format": {"format_name": "matroska,webm", "duration": "12"},
            "streams": [{"codec_type": "video", "width": 1080, "height": 1920},
                        {"codec_type": "audio"}]}
    monkeypatch.setattr(VideoValidator, "ffprobe_available", lambda self: True)
    monkeypatch.setattr("kitok.video_validator.subprocess.run",
                        lambda *args, **kwargs: Mock(returncode=0, stdout=json.dumps(info)))

    result = VideoValidator().validate(path)

    assert not result.ok
    assert "file is not an MP4 container" in result.errors
