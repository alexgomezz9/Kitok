import json
from unittest.mock import Mock

import pytest

from kitok import cli
from kitok.config import Settings
from kitok.publisher import PublishPlan


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("kitok.config.PROJECT_ROOT", tmp_path)
    settings = Settings(_env_file=None)
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    return settings


def test_check_is_read_only_even_when_enabled(isolated, monkeypatch):
    isolated.publish_enabled = True
    from pydantic import SecretStr
    isolated.buffer_api_key = SecretStr("test-secret")
    client = Mock()
    client.organizations.return_value = [{"id": "org", "name": "Org"}]
    client.channels.return_value = [{"id": "t", "service": "tiktok"}]
    monkeypatch.setattr("kitok.buffer_client.BufferClient", Mock(return_value=client))
    assert cli.main(["--buffer-check"]) == 0
    assert [c[0] for c in client.mock_calls] == ["organizations", "channels", "close"]
    assert not isolated.state_path.exists()


def test_channels_lists_ambiguous_channels(isolated, monkeypatch):
    from pydantic import SecretStr
    isolated.buffer_api_key = SecretStr("test")
    client = Mock()
    client.organizations.return_value = [{"id": "org"}]
    client.channels.return_value = [{"id": "t1", "service": "tiktok"}, {"id": "t2", "service": "tiktok"}]
    monkeypatch.setattr("kitok.buffer_client.BufferClient", Mock(return_value=client))
    assert cli.main(["--buffer-channels"]) == 0
    assert cli.main(["--buffer-check"]) == 3


def test_no_credentials_check(isolated):
    assert cli.main(["--buffer-check"]) == 3


def test_publish_disabled_before_loading_queue(isolated):
    assert cli.main(["--publish-ready"]) == 3
    assert cli.main(["--buffer-maintain"]) == 3
    assert cli.main(["--publish-id", "one"]) == 3


def test_offline_dry_run(isolated, monkeypatch):
    isolated.queue_path.write_text(json.dumps([]))
    host = Mock()
    monkeypatch.setattr("kitok.publisher.CloudinaryHost", host)
    assert cli.main(["--publish-dry-run"]) == 0
    host.return_value.ensure_video.assert_not_called()
    assert not isolated.state_path.exists()


def test_conflicting_modes_rejected():
    with pytest.raises(SystemExit) as exc:
        cli.parser().parse_args(["--publish-ready", "--publish-dry-run"])
    assert exc.value.code == 2


def test_publish_id_dry_run_selects_exact_id_without_writes(isolated, monkeypatch):
    isolated.queue_path.write_text(json.dumps([
        {"id": "selected", "subject": "Selected", "script": "A sufficiently long narration script.",
         "keywords": ["test"], "caption": "Selected caption",
         "publish_at": "2026-09-20T13:00:00+02:00"},
        {"id": "other", "subject": "Other", "script": "Another sufficiently long narration script.",
         "keywords": ["test"], "caption": "Other caption",
         "publish_at": "2026-09-20T19:00:00+02:00"},
    ]))
    plan = PublishPlan(rows=[{"id": "selected", "platform": platform,
                              "dueAt": "2026-09-20T11:00:00Z", "caption": "caption",
                              "title": "Selected" if platform == "youtube" else None,
                              "video_path": "/tmp/video.mp4"}
                             for platform in ("tiktok", "instagram", "youtube")], offline=True)
    publisher = Mock()
    publisher.plan_one.return_value = plan
    publisher_class = Mock(return_value=publisher)
    monkeypatch.setattr("kitok.publisher.Publisher", publisher_class)
    cloudinary = Mock()
    monkeypatch.setattr("kitok.publisher.CloudinaryHost", cloudinary)

    assert cli.main(["--publish-id", "selected", "--publish-dry-run"]) == 0

    publisher.plan_one.assert_called_once_with("selected")
    publisher.publish_one.assert_not_called()
    cloudinary.return_value.ensure_video.assert_not_called()
    assert not isolated.state_path.exists()


def test_publish_id_unknown_fails_cleanly(isolated, monkeypatch):
    isolated.queue_path.write_text("[]")
    publisher_class = Mock()
    monkeypatch.setattr("kitok.publisher.Publisher", publisher_class)

    assert cli.main(["--publish-id", "missing", "--publish-dry-run"]) == 3

    publisher_class.assert_not_called()


def test_publish_id_rejects_other_operation_modes():
    assert cli.main(["--publish-id", "one", "--publish-ready"]) == 2
    assert cli.main(["--publish-id", "one", "--id", "other"]) == 2
