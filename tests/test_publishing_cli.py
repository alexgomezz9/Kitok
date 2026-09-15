import json
from unittest.mock import Mock

import pytest

from kitok import cli
from kitok.config import Settings


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
