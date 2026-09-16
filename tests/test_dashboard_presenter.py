"""Daily dashboard decisions must be local, clear and conservative."""
from pathlib import Path
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from kitok.control_panel import ControlPanel
from kitok.dashboard_presenter import content_status, recommendations, status_label
from kitok.service_cache import buffer_cache


DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard.py"


def _snapshot(settings, posts):
    channels = {name: {"id": name, "service": name}
                for name in ("tiktok", "instagram", "youtube")}
    buffer_cache(settings).put("snapshot", {"organization_id": "org", "channels": channels,
                                            "posts": posts, "refreshed_at": "2026-01-01T00:00:00Z"})


def test_recommendations_prioritize_issues_and_hide_fill_for_scheduled_queue(local_kitok):
    settings, queue, state, _ = local_kitok
    settings.buffer_max_scheduled_per_channel = 2
    for item in queue.items:
        for name in item.platforms:
            state.update_publishing(item.id, "buffer", name, post_id=f"{item.id}-{name}", status="scheduled")
    _snapshot(settings, [{"id": f"{item.id}-{name}", "channelId": name, "status": "scheduled",
                          "dueAt": item.publish_at.isoformat()}
                         for item in queue.items for name in item.platforms])
    panel = ControlPanel(settings)
    data = panel.view()
    advice = recommendations(data, queue, state, settings)
    assert advice[0].kind == "none"
    assert all(item.action != "Fill schedule" for item in advice)
    data["issues"] = [{"Content ID": "one", "Platform": "instagram",
                       "What happened": "publishing failed"}]
    assert recommendations(data, queue, state, settings)[0].action == "Review issues"


def test_status_presentation_uses_one_vocabulary(local_kitok):
    _, queue, state, _ = local_kitok
    assert status_label("pending") == "Draft"
    assert status_label("sending") == "Scheduled"
    assert status_label("sent") == "Published"
    assert status_label("unknown") == "Needs attention"
    assert status_label("unexpected internal state") == "Needs attention"
    item = queue.by_id()["one"]
    assert content_status(item, state.get("one")) == "Ready"
    assert content_status(item, state.get("one"), {"Attention": "Instagram error"}) == "Needs attention"


def test_home_contextual_actions_and_help(local_kitok, monkeypatch):
    settings, _, state, _ = local_kitok
    monkeypatch.setattr("kitok.control_panel.Settings", lambda: settings)
    refresh = Mock(side_effect=AssertionError("unexpected Buffer request"))
    monkeypatch.setattr(ControlPanel, "refresh_buffer", refresh)
    _snapshot(settings, [])
    before = settings.queue_path.read_bytes(), state.path.read_bytes(), settings.cache_path.read_bytes()
    app = AppTest.from_file(DASHBOARD, default_timeout=20).run()
    assert not app.exception
    fill = next(button for button in app.button if button.label == "Fill schedule")
    assert "ready videos" in fill.help.lower()
    preview = app.button(key="preview-all")
    assert "nothing is uploaded" in preview.help.lower()
    assert [page for page in app.sidebar.radio[0].options] == ["Home", "Content", "Calendar", "Attention"]
    assert all(not expander.proto.expanded for expander in app.get("expander") if "Advanced" in expander.label)
    assert (settings.queue_path.read_bytes(), state.path.read_bytes(), settings.cache_path.read_bytes()) == before
    refresh.assert_not_called()


def test_scheduled_queue_has_no_primary_fill_button(local_kitok, monkeypatch):
    settings, queue, state, _ = local_kitok
    monkeypatch.setattr("kitok.control_panel.Settings", lambda: settings)
    settings.buffer_max_scheduled_per_channel = 2
    for item in queue.items:
        for name in item.platforms:
            state.update_publishing(item.id, "buffer", name, post_id=f"{item.id}-{name}", status="scheduled")
    _snapshot(settings, [{"id": f"{item.id}-{name}", "channelId": name, "status": "scheduled",
                          "dueAt": item.publish_at.isoformat()}
                         for item in queue.items for name in item.platforms])
    app = AppTest.from_file(DASHBOARD, default_timeout=20).run()
    assert not app.exception
    assert not [button for button in app.button if button.label == "Fill schedule"]


def test_home_promotes_attention_over_scheduling(local_kitok, monkeypatch):
    settings, _, state, _ = local_kitok
    monkeypatch.setattr("kitok.control_panel.Settings", lambda: settings)
    _snapshot(settings, [])
    state.upsert("one", last_error="Instagram publishing failed")
    app = AppTest.from_file(DASHBOARD, default_timeout=20).run()
    assert not app.exception
    assert any(button.label == "Review issues" for button in app.button)
    assert not any(button.label == "Fill schedule" for button in app.button)


def test_fill_confirmation_describes_platform_counts(local_kitok, monkeypatch):
    settings, _, _, _ = local_kitok
    monkeypatch.setattr("kitok.control_panel.Settings", lambda: settings)
    _snapshot(settings, [])
    app = AppTest.from_file(DASHBOARD, default_timeout=20).run()
    next(button for button in app.button if button.label == "Fill schedule").click().run()
    assert not app.exception
    assert any("You're about to schedule" in block.value for block in app.markdown)
    assert any("TikTok +" in block.value for block in app.caption)
    assert app.button(key="confirm-action")
