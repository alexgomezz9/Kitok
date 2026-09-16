from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from kitok.control_panel import ControlPanel
from kitok.publisher import Publisher
from kitok.queue_editor import edit_item, queue_digest
from kitok.state import StateStore


def test_dashboard_pages_and_reruns_never_request_or_write(local_kitok, monkeypatch):
    settings, _, state, _ = local_kitok
    monkeypatch.setattr("kitok.control_panel.Settings", lambda: settings)
    refresh = Mock(side_effect=AssertionError("unrequested refresh"))
    monkeypatch.setattr(ControlPanel, "refresh_buffer", refresh)
    before = state.path.read_bytes()
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "dashboard.py", default_timeout=10).run()
    assert not app.exception
    for page in ["Upcoming Content", "Content Detail", "Buffer", "Attention", "Settings", "Overview"]:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception
    refresh.assert_not_called()
    assert state.path.read_bytes() == before
    assert not settings.cache_path.exists()


def test_dashboard_requires_confirmation_and_does_not_repeat(local_kitok, monkeypatch):
    settings, _, state, _ = local_kitok
    monkeypatch.setattr("kitok.control_panel.Settings", lambda: settings)
    execute = Mock(return_value={"created": 6})
    monkeypatch.setattr(ControlPanel, "execute", execute)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "dashboard.py", default_timeout=10).run()
    next(button for button in app.button if button.label == "Fill Buffer").click().run()
    assert not app.exception
    execute.assert_not_called()
    assert app.button(key="confirm-action")
    app.button(key="confirm-action").click().run()
    assert not app.exception
    execute.assert_called_once()
    assert execute.call_args.kwargs["confirmed"] is True
    app.run()
    assert execute.call_count == 1


def test_disabled_publishing_keeps_preview_available(local_kitok, monkeypatch):
    settings, _, _, _ = local_kitok
    settings.publish_enabled = False
    monkeypatch.setattr("kitok.control_panel.Settings", lambda: settings)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "dashboard.py", default_timeout=10).run()
    assert next(button for button in app.button if button.label == "Fill Buffer").disabled
    assert not next(button for button in app.button if button.label == "Preview publishing plan").disabled


def test_explicit_refresh_and_cancel_do_not_repeat_actions(local_kitok, monkeypatch):
    settings, _, _, _ = local_kitok
    monkeypatch.setattr("kitok.control_panel.Settings", lambda: settings)
    refresh = Mock(return_value={})
    execute = Mock()
    monkeypatch.setattr(ControlPanel, "refresh_buffer", refresh)
    monkeypatch.setattr(ControlPanel, "execute", execute)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "dashboard.py", default_timeout=10).run()
    next(button for button in app.button if button.label == "Refresh Buffer").click().run()
    refresh.assert_called_once()
    app.run()
    refresh.assert_called_once()
    next(button for button in app.button if button.label == "Fill Buffer").click().run()
    app.button(key="cancel-action").click().run()
    execute.assert_not_called()
    assert not app.exception


def test_selected_regeneration_reuses_regenerator(local_kitok, monkeypatch):
    from kitok.regeneration import RegenerationSummary
    settings, _, _, _ = local_kitok
    preset = settings.queue_path.parent / "preset.json"
    preset.write_text('{"font_size": 81}')
    settings.mpt_preset_path = preset
    panel = ControlPanel(settings)
    action = panel.prepare_action("regenerate", "one")
    client = Mock()
    regenerate = Mock()
    regenerate.return_value.run.return_value = RegenerationSummary(regenerated=1)
    monkeypatch.setattr("kitok.control_panel.MPTClient", Mock(return_value=client))
    monkeypatch.setattr("kitok.control_panel.ReadyRegenerator", regenerate)
    assert panel.execute(action, confirmed=True)["regenerated"] == 1
    regenerate.return_value.run.assert_called_once_with(ids={"one"})
    assert regenerate.call_args.args[4] == {"font_size": 81}


def test_control_panel_reuses_publisher_and_rejects_unconfirmed_action(local_kitok, monkeypatch):
    settings, _, _, _ = local_kitok
    panel = ControlPanel(settings)
    action = panel.prepare_action("publish", "one")
    with pytest.raises(ValueError, match="confirmation"):
        panel.execute(action)
    client = Mock()
    monkeypatch.setattr(panel, "client", lambda: client)
    publish = Mock(return_value={"created": 3})
    monkeypatch.setattr(Publisher, "publish_one", publish)
    assert panel.execute(action, confirmed=True) == {"created": 3}
    assert publish.call_args.args == ("one",)
    assert callable(publish.call_args.kwargs["before_execute"])
    client.close.assert_called_once()


def test_stale_confirmation_is_rejected(local_kitok):
    settings, _, state, _ = local_kitok
    panel = ControlPanel(settings)
    action = panel.prepare_action("reset", "one")
    state.update_publishing("one", "buffer", "tiktok", post_id="new")
    with pytest.raises(ValueError, match="changed"):
        panel.execute(action, confirmed=True)
    assert StateStore(state.path).get("one")["publishing"]["buffer"]["tiktok"]["post_id"] == "new"


def test_queue_edits_are_atomic_scoped_and_blocked_after_publishing(local_kitok):
    settings, queue, state, _ = local_kitok
    original = queue.by_id()["two"]
    item = edit_item(settings.queue_path, state, "one", {"caption": "New caption"},
                     expected_revision=queue_digest(settings.queue_path))
    assert item.caption == "New caption"
    assert type(queue).load(settings.queue_path).by_id()["two"] == original
    assert state.get("one")["attempts"] == 1
    state.update_publishing("one", "buffer", "tiktok", status="unknown")
    with pytest.raises(ValueError, match="metadata"):
        edit_item(settings.queue_path, state, "one", {"caption": "Unsafe edit"},
                  expected_revision=queue_digest(settings.queue_path))


def test_settings_never_expose_credentials(local_kitok):
    settings, _, _, _ = local_kitok
    settings.mpt_base_url = "http://user:password@localhost:8080/api?token=secret"
    view = str(ControlPanel(settings).settings_view())
    for secret in ("test-secret", "password", "token=secret"):
        assert secret not in view
