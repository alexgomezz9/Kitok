"""Editorial queue changes stay local, atomic and safe around published content."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from kitok.control_panel import ControlPanel
from kitok.dashboard import _next_slot
from kitok.models import ContentQueue
from kitok.publisher import Publisher, post_content
from kitok.publish_plan import generate_publish_plan
from kitok.queue_editor import (add_item, delete_item, edit_item, queue_digest,
                                reorder_item, set_editorial_status, suggested_id)


def _times(settings):
    return {item.id: item.publish_at for item in ContentQueue.load(settings.queue_path).items}


def test_reorder_swaps_publish_at_and_preserves_other_fields(local_kitok):
    settings, queue, state, _ = local_kitok
    before = _times(settings)
    original = queue.by_id()
    moved, neighbor = reorder_item(settings.queue_path, state, "two", -1,
                                    expected_revision=queue_digest(settings.queue_path))
    after = _times(settings)
    assert moved.id == "two" and neighbor.id == "one"
    assert after == {"one": before["two"], "two": before["one"]}
    assert ContentQueue.load(settings.queue_path).items[0].id == "two"
    assert ContentQueue.load(settings.queue_path).by_id()["one"].script == original["one"].script
    assert state.get("one")["attempts"] == 1


def test_edit_unpublished_fields_and_youtube_title(local_kitok):
    settings, queue, state, _ = local_kitok
    other = queue.by_id()["two"]
    changed = edit_item(settings.queue_path, state, "one",
                        {"subject": "New topic", "caption": "New caption", "youtube_title": "A YouTube title"},
                        expected_revision=queue_digest(settings.queue_path))
    assert changed.youtube_title == "A YouTube title"
    assert ContentQueue.load(settings.queue_path).by_id()["two"] == other
    assert post_content(changed, "youtube", "")["metadata"]["youtube"]["title"] == "A YouTube title"
    assert state.get("one")["status"] == "ready"
    with pytest.raises(ValueError, match="before generation"):
        edit_item(settings.queue_path, state, "one", {"script": "A different sufficiently long narration."},
                  expected_revision=queue_digest(settings.queue_path))


def test_pending_script_and_terms_can_be_edited(local_kitok):
    settings, _, state, _ = local_kitok
    state.upsert("one", status="pending", attempts=0)
    changed = edit_item(settings.queue_path, state, "one",
                        {"script": "A different sufficiently long narration.", "keywords": ["moon", "night"]},
                        expected_revision=queue_digest(settings.queue_path))
    assert changed.keywords == ["moon", "night"]


def test_publishing_metadata_blocks_edit_move_skip_and_delete(local_kitok):
    settings, _, state, _ = local_kitok
    state.update_publishing("one", "buffer", "tiktok", post_id="post-1", status="scheduled")
    revision = queue_digest(settings.queue_path)
    before = settings.queue_path.read_bytes()
    with pytest.raises(ValueError, match="metadata"):
        edit_item(settings.queue_path, state, "one", {"caption": "Changed"}, expected_revision=revision)
    with pytest.raises(ValueError, match="metadata"):
        reorder_item(settings.queue_path, state, "two", -1, expected_revision=revision)
    with pytest.raises(ValueError, match="metadata"):
        set_editorial_status(settings.queue_path, state, "one", "skipped", expected_revision=revision)
    with pytest.raises(ValueError, match="metadata"):
        delete_item(settings.queue_path, state, "one", expected_revision=revision)
    assert settings.queue_path.read_bytes() == before


def test_skip_archive_restore_affect_plan_but_preserve_media_and_history(local_kitok):
    settings, _, state, video = local_kitok
    set_editorial_status(settings.queue_path, state, "one", "skipped",
                         expected_revision=queue_digest(settings.queue_path))
    queue = ContentQueue.load(settings.queue_path)
    assert queue.by_id()["one"].editorial_status == "skipped"
    assert not [row for row in Publisher(settings, queue, state).plan().rows if row["id"] == "one"]
    _, plan_path = generate_publish_plan(queue, state.all(), settings.queue_path.parent / "handoff")
    assert "one" not in {row["id"] for row in json.loads(plan_path.read_text())}
    assert video.exists() and state.get("one")["attempts"] == 1
    set_editorial_status(settings.queue_path, state, "one", "archived",
                         expected_revision=queue_digest(settings.queue_path))
    assert "one" not in [row["ID"] for row in ControlPanel(settings).view()["rows"]]
    assert "one" in [row["ID"] for row in ControlPanel(settings).view(include_archived=True)["rows"]]
    set_editorial_status(settings.queue_path, state, "one", "active",
                         expected_revision=queue_digest(settings.queue_path))
    assert ContentQueue.load(settings.queue_path).by_id()["one"].editorial_status == "active"


def test_add_is_unique_validated_sorted_and_does_not_generate(local_kitok):
    settings, queue, state, _ = local_kitok
    assert suggested_id("¿Por qué la Luna?", {"por_que_la_luna"}) == "por_que_la_luna_2"
    earlier = min(item.publish_at for item in queue.items) - timedelta(hours=1)
    values = {"id": "third", "subject": "New topic", "script": "A sufficiently long new narration.",
              "caption": "New", "keywords": ["moon"], "publish_at": earlier.isoformat(),
              "youtube_title": "Moon short"}
    action = ControlPanel(settings).prepare_action("add", changes=values)
    with pytest.raises(ValueError, match="confirmation"):
        ControlPanel(settings).execute(action)
    assert "third" not in ContentQueue.load(settings.queue_path).by_id()
    result = ControlPanel(settings).execute(action, confirmed=True)
    assert result == {"added": "third"}
    assert ContentQueue.load(settings.queue_path).items[0].id == "third"
    assert not state.get("third")
    with pytest.raises(ValueError, match="already exists"):
        add_item(settings.queue_path, state, values, expected_revision=queue_digest(settings.queue_path))
    with pytest.raises(ValueError):
        add_item(settings.queue_path, state, {**values, "id": "another", "publish_at": "2026-01-01T13:00:00"},
                 expected_revision=queue_digest(settings.queue_path))
    with pytest.raises(ValueError, match="caption"):
        add_item(settings.queue_path, state, {**values, "id": "another", "caption": "",
                                              "publish_at": (earlier + timedelta(days=10)).isoformat()},
                 expected_revision=queue_digest(settings.queue_path))


def test_add_form_suggests_next_unoccupied_normal_slot(local_kitok):
    settings, queue, _, _ = local_kitok
    first = _next_slot(settings.timezone)
    second = _next_slot(settings.timezone, {first, *(item.publish_at for item in queue.items)})
    assert second > first
    assert second.hour in {13, 19, 22}
    assert second not in {item.publish_at for item in queue.items}


def test_delete_preserves_files_history_and_blocks_id_reuse(local_kitok):
    settings, _, state, video = local_kitok
    panel = ControlPanel(settings)
    action = panel.prepare_action("delete", "one")
    with pytest.raises(ValueError, match="confirmation"):
        panel.execute(action)
    assert panel.execute(action, confirmed=True) == {"deleted_from_queue": "one"}
    assert "one" not in ContentQueue.load(settings.queue_path).by_id()
    assert video.exists() and state.get("one")["attempts"] == 1
    values = {"id": "one", "subject": "New", "script": "A long enough new script for validation.",
              "caption": "New caption", "keywords": ["new"],
              "publish_at": (datetime.now(timezone.utc) + timedelta(days=8)).isoformat()}
    with pytest.raises(ValueError, match="saved history"):
        add_item(settings.queue_path, state, values, expected_revision=queue_digest(settings.queue_path))


def test_archive_preserves_scheduled_post_and_prevents_new_plan_rows(local_kitok):
    settings, _, state, _ = local_kitok
    state.update_publishing("one", "buffer", "tiktok", post_id="p-1", status="scheduled")
    set_editorial_status(settings.queue_path, state, "one", "archived",
                         expected_revision=queue_digest(settings.queue_path))
    assert state.get("one")["publishing"]["buffer"]["tiktok"]["post_id"] == "p-1"
    assert not [row for row in Publisher(settings, ContentQueue.load(settings.queue_path), state).plan().rows
                if row["id"] == "one"]


def test_dashboard_calendar_render_is_read_only(local_kitok, monkeypatch):
    settings, _, state, _ = local_kitok
    monkeypatch.setattr("kitok.control_panel.Settings", lambda: settings)
    refresh = Mock(side_effect=AssertionError("unexpected Buffer request"))
    monkeypatch.setattr(ControlPanel, "refresh_buffer", refresh)
    before = settings.queue_path.read_bytes(), state.path.read_bytes()
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "dashboard.py", default_timeout=20).run()
    app.sidebar.radio[0].set_value("Calendar / Queue").run()
    assert not app.exception
    assert (settings.queue_path.read_bytes(), state.path.read_bytes()) == before
    refresh.assert_not_called()


def test_calendar_edit_opens_selected_content_without_writing(local_kitok, monkeypatch):
    settings, _, state, _ = local_kitok
    monkeypatch.setattr("kitok.control_panel.Settings", lambda: settings)
    before = settings.queue_path.read_bytes(), state.path.read_bytes()
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "dashboard.py", default_timeout=20).run()
    app.sidebar.radio[0].set_value("Calendar / Queue").run()
    app.button(key="edit-two").click().run()
    assert not app.exception
    assert app.sidebar.radio[0].value == "Content"
    assert app.selectbox[0].value == "two"
    assert (settings.queue_path.read_bytes(), state.path.read_bytes()) == before


def test_editorial_confirmation_consumed_once(local_kitok, monkeypatch):
    settings, _, _, _ = local_kitok
    monkeypatch.setattr("kitok.control_panel.Settings", lambda: settings)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "dashboard.py", default_timeout=20).run()
    app.sidebar.radio[0].set_value("Content").run()
    next(button for button in app.button if button.label == "Skip").click().run()
    assert not app.exception
    assert app.button(key="confirm-action")
    app.button(key="confirm-action").click().run()
    assert not app.exception
    assert ContentQueue.load(settings.queue_path).by_id()["one"].editorial_status == "skipped"
    app.run()
    assert ContentQueue.load(settings.queue_path).by_id()["one"].editorial_status == "skipped"


def test_add_form_waits_for_confirmation_and_never_generates(local_kitok, monkeypatch):
    settings, _, state, _ = local_kitok
    monkeypatch.setattr("kitok.control_panel.Settings", lambda: settings)
    mpt = Mock(side_effect=AssertionError("MPT must not run when adding content"))
    monkeypatch.setattr("kitok.control_panel.MPTClient", mpt)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "dashboard.py", default_timeout=20).run()
    app.sidebar.radio[0].set_value("Calendar / Queue").run()
    next(widget for widget in app.text_input if widget.label == "Topic / title *").set_value("Why does the Moon glow?")
    next(widget for widget in app.text_input if widget.label == "Pexels / video terms *").set_value("moon, night")
    next(widget for widget in app.text_area if widget.label == "Script *").set_value("A sufficiently long narration about the Moon.")
    next(widget for widget in app.text_area if widget.label == "Caption *").set_value("Moon facts")
    next(button for button in app.button if button.label == "Review new content").click().run()
    assert not app.exception
    assert len(ContentQueue.load(settings.queue_path).items) == 2
    app.button(key="confirm-action").click().run()
    assert not app.exception
    added = [item for item in ContentQueue.load(settings.queue_path).items if item.id not in {"one", "two"}]
    assert len(added) == 1 and added[0].keywords == ["moon", "night"]
    assert not state.get(added[0].id)
    mpt.assert_not_called()


def test_delete_requires_typed_id_and_does_not_repeat(local_kitok, monkeypatch):
    settings, _, state, video = local_kitok
    monkeypatch.setattr("kitok.control_panel.Settings", lambda: settings)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "dashboard.py", default_timeout=20).run()
    app.sidebar.radio[0].set_value("Content").run()
    next(button for button in app.button if button.label == "Delete from queue").click().run()
    assert app.button(key="confirm-action").disabled
    app.text_input(key="delete-proof").set_value("one").run()
    assert not app.button(key="confirm-action").disabled
    app.button(key="confirm-action").click().run()
    assert not app.exception
    assert "one" not in ContentQueue.load(settings.queue_path).by_id()
    assert video.exists() and state.get("one")["status"] == "ready"
    app.run()
    assert "one" not in ContentQueue.load(settings.queue_path).by_id()
