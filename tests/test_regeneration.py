import json
from unittest.mock import Mock

import pytest

from kitok.config import Settings
from kitok.file_manager import output_filename
from kitok.generation import GenerationPlan
from kitok.models import ContentItem, ContentQueue, ValidationResult
from kitok.regeneration import ReadyRegenerator
from kitok.state import StateStore
from kitok.video_validator import VideoValidator


@pytest.fixture
def setup(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, data_root=tmp_path, ready_dir=tmp_path / "delivery")
    settings.ensure_directories()
    queue = ContentQueue(items=[ContentItem(id=cid, subject=cid, script="A sufficiently long test script.",
                                            keywords=["city"]) for cid in ("one", "bad", "three")])
    settings.queue_path.write_text(json.dumps([item.model_dump(mode="json") for item in queue.items]))
    state = StateStore(settings.state_path)
    for item in queue.items:
        state.upsert(item.id, status="ready", attempts=2, mpt_task_id="historical-task")
        for folder in (settings.generated_dir, settings.local_ready_dir, settings.ready_dir):
            (folder / output_filename(item)).write_bytes(b"old-" + item.id.encode())
    client = Mock()
    client.submit_video.side_effect = AssertionError("MPT must remain unused")
    regen = ReadyRegenerator(settings, queue, state, client, {"subtitle_enabled": True}, print_line=lambda _: None)
    regen.generator.plan = Mock(return_value=GenerationPlan(dict(regen.preset)))
    regen.generator.finish = Mock(side_effect=lambda item, plan, src, dst, workspace: dst.write_bytes(b"fresh-" + item.id.encode()))
    regen.validator.prepare = Mock(return_value=ValidationResult(ok=True))
    return settings, queue, state, client, regen


def test_ready_regeneration_is_native_and_preserves_historical_ids(setup):
    settings, queue, state, client, regen = setup
    result = regen.run()
    assert result.regenerated == 3
    for item in queue.items:
        row = state.get(item.id)
        assert row["attempts"] == 3 and row["mpt_task_id"] == "historical-task"
        assert row["generation_renderer"] == "native" and row["regeneration_status"] == "succeeded"
        for folder in (settings.generated_dir, settings.local_ready_dir, settings.ready_dir):
            assert (folder / output_filename(item)).read_bytes() == b"fresh-" + item.id.encode()
    client.submit_video.assert_not_called()
    client.get_task.assert_not_called()


def test_publishing_metadata_and_non_ready_items_block_regeneration(setup):
    _, _, state, _, regen = setup
    state.update_publishing("one", "cloudinary", public_id="uploaded")
    state.update_publishing("bad", "buffer", "tiktok", status="unknown")
    state.upsert("three", status="pending")
    result = regen.run()
    assert result.skipped == 3 and result.regenerated == 0
    regen.generator.plan.assert_not_called()
    assert state.get("one")["publishing"]["cloudinary"]["public_id"] == "uploaded"


def test_dry_run_has_no_writes_or_external_calls(setup):
    settings, _, _, client, regen = setup
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in settings.data_root.rglob("*") if p.is_file()}
    result = regen.run(dry_run=True)
    after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in settings.data_root.rglob("*") if p.is_file()}
    assert before == after and result.would_regenerate == 3
    regen.generator.plan.assert_not_called()
    assert client.mock_calls == []


def test_one_render_failure_preserves_ready_media_and_continues(setup):
    settings, queue, state, _, regen = setup
    def render(item, plan, src, dst, workspace):
        if item.id == "bad":
            raise RuntimeError("synthetic render failure")
        dst.write_bytes(b"fresh-" + item.id.encode())
    regen.generator.finish.side_effect = render
    result = regen.run()
    assert (result.regenerated, result.failed) == (2, 1)
    for folder in (settings.generated_dir, settings.local_ready_dir, settings.ready_dir):
        assert (folder / output_filename(queue.by_id()["bad"])).read_bytes() == b"old-bad"
    assert state.get("bad")["status"] == "ready"
    assert state.get("bad")["regeneration_status"] == "failed"


def test_invalid_media_never_replaces_existing_outputs(setup):
    settings, queue, _, _, regen = setup
    regen.validator.prepare.side_effect = lambda path, *args: ValidationResult(ok=path.read_bytes() != b"fresh-bad", errors=["invalid video"])
    result = regen.run()
    assert (result.regenerated, result.failed) == (2, 1)
    for folder in (settings.generated_dir, settings.local_ready_dir, settings.ready_dir):
        assert (folder / output_filename(queue.by_id()["bad"])).read_bytes() == b"old-bad"


def test_selection_does_not_change_queue_or_unrelated_media_and_sidecars(setup):
    settings, _, _, _, regen = setup
    queue_before = settings.queue_path.read_bytes()
    sidecar = settings.local_ready_dir / "unrelated.json"
    sidecar.write_text("preserve")
    result = regen.run(ids={"one"})
    assert result.regenerated == 1
    assert sidecar.read_text() == "preserve" and settings.queue_path.read_bytes() == queue_before
    assert next(p for p in settings.local_ready_dir.glob("*.mp4") if "bad" in p.name).read_bytes() == b"old-bad"
    with pytest.raises(ValueError, match="Unknown"):
        regen.run(ids={"unknown"})


def test_validator_rejects_non_mp4_container(tmp_path, monkeypatch):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"some media")
    info = {"format": {"format_name": "matroska,webm", "duration": "12"},
            "streams": [{"codec_type": "video", "width": 1080, "height": 1920},
                        {"codec_type": "audio"}]}
    monkeypatch.setattr(VideoValidator, "ffprobe_available", lambda self: True)
    monkeypatch.setattr("kitok.video_validator.subprocess.run", lambda *args, **kwargs: Mock(returncode=0, stdout=json.dumps(info)))
    result = VideoValidator().validate(path)
    assert not result.ok and "file is not an MP4 container" in result.errors
