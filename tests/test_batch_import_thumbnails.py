import json
import subprocess
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from kitok.batch_import import parse_batch, validate_batch
from kitok.control_panel import ControlPanel
from kitok.models import ContentQueue
from kitok.queue_editor import add_batch, queue_digest
from kitok.thumbnails import ThumbnailService


def _rows(queue):
    base = queue.items[-1].publish_at + timedelta(days=3)
    return [{"id": f"new_{i}", "topic": f"New topic {i}",
             "script": "A sufficiently long script for a video.", "caption": "An interesting caption",
             "video_terms": ["sky"], "publish_at": (base + timedelta(hours=i)).isoformat()}
            for i in (1, 2)]


def test_thumbnail_cache_refreshes_only_when_video_changes(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"original mp4 bytes")
    original = video.read_bytes()
    calls = []

    def extract(command, **kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"jpeg frame")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("kitok.thumbnails.subprocess.run", extract)
    service = ThumbnailService(tmp_path / "thumbnails")
    image = service.get("one", video)
    assert image and image.read_bytes() == b"jpeg frame"
    assert service.get("one", video) == image
    assert len(calls) == 1 and "1.5" in calls[0]
    assert video.read_bytes() == original
    video.write_bytes(original + b" changed")
    assert service.get("one", video) == image
    assert len(calls) == 2
    assert video.read_bytes() == original + b" changed"


@pytest.mark.parametrize("failure", [FileNotFoundError("ffmpeg missing"), subprocess.CompletedProcess([], 1)])
def test_thumbnail_extraction_failure_is_non_fatal(tmp_path, monkeypatch, failure):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    def fail(*args, **kwargs):
        if isinstance(failure, Exception):
            raise failure
        return failure
    monkeypatch.setattr("kitok.thumbnails.subprocess.run", fail)
    assert ThumbnailService(tmp_path / "thumbnails").get("one", video) is None
    assert video.read_bytes() == b"video"


def test_valid_batch_import_is_single_queue_change(local_kitok):
    settings, queue, state, _ = local_kitok
    rows = _rows(queue)
    items, errors = validate_batch(rows, queue, state)
    assert len(items) == 2 and not errors
    before_state = state.path.read_bytes()
    imported = add_batch(settings.queue_path, state, rows, expected_revision=queue_digest(settings.queue_path))
    assert [item.id for item in imported] == ["new_1", "new_2"]
    assert len(ContentQueue.load(settings.queue_path).items) == len(queue.items) + 2
    assert state.path.read_bytes() == before_state
    assert not state.get("new_1") and not state.get("new_2")


def test_batch_rejects_bad_json_duplicate_ids_and_collisions(local_kitok):
    settings, queue, state, _ = local_kitok
    with pytest.raises(ValueError, match="Malformed JSON"):
        parse_batch("[{oops")
    rows = _rows(queue)
    rows[1]["id"] = rows[0]["id"]
    assert any("duplicate ID" in problem for problem in validate_batch(rows, queue, state)[1])
    rows = _rows(queue)
    rows[1]["publish_at"] = queue.items[0].publish_at.isoformat()
    assert any("occupied scheduling slot" in problem for problem in validate_batch(rows, queue, state)[1])
    rows[1]["caption"] = ""
    before = settings.queue_path.read_bytes()
    with pytest.raises(ValueError, match="Batch import rejected"):
        add_batch(settings.queue_path, state, rows, expected_revision=queue_digest(settings.queue_path))
    assert settings.queue_path.read_bytes() == before


def test_batch_preview_never_writes_and_confirmation_imports(local_kitok, monkeypatch):
    settings, queue, state, _ = local_kitok
    monkeypatch.setattr("kitok.control_panel.Settings", lambda: settings)
    monkeypatch.setattr("kitok.dashboard.ThumbnailService.get", lambda *args: None)
    remote = Mock(side_effect=AssertionError("Unexpected remote request"))
    monkeypatch.setattr(ControlPanel, "refresh_buffer", remote)
    before = settings.queue_path.read_bytes(), state.path.read_bytes()
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "dashboard.py", default_timeout=20).run()
    app.sidebar.radio[0].set_value("Content").run()
    assert next(area for area in app.text_area if area.label == "Batch JSON")
    next(area for area in app.text_area if area.label == "Batch JSON").set_value(json.dumps(_rows(queue))).run()
    next(button for button in app.button if button.label == "Validate batch").click().run()
    assert not app.exception
    assert (settings.queue_path.read_bytes(), state.path.read_bytes()) == before
    next(button for button in app.button if button.label == "Import 2 contents").click().run()
    assert not app.exception
    assert len(ContentQueue.load(settings.queue_path).items) == 4
    remote.assert_not_called()
