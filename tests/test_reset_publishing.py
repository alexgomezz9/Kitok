import json
from copy import deepcopy
from unittest.mock import Mock

import pytest

from kitok import cli
from kitok.config import Settings
from kitok.state import StateStore


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("kitok.config.PROJECT_ROOT", tmp_path)
    settings = Settings(_env_file=None)
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    queue = [
        {"id": cid, "subject": cid, "script": "A sufficiently long narration script.",
         "keywords": ["test"], "publish_at": "2026-09-20T13:00:00+02:00"}
        for cid in ("target", "other")
    ]
    settings.queue_path.write_text(json.dumps(queue))
    return settings


def forbid_clients(monkeypatch):
    blocked = Mock(side_effect=AssertionError("external client constructed"))
    monkeypatch.setattr(cli, "MPTClient", blocked)
    monkeypatch.setattr("kitok.buffer_client.BufferClient", blocked)
    monkeypatch.setattr("kitok.cloudinary_host.CloudinaryHost", blocked)
    return blocked


def test_preview_prints_state_and_performs_no_writes(isolated, monkeypatch, capsys):
    state = StateStore(isolated.state_path)
    state.upsert("target", status="ready", publishing={
        "cloudinary": {"public_id": "cloud-id", "url": "https://example.test/video.mp4"},
        "buffer": {"tiktok": {"post_id": "post-id", "status": "unknown",
                              "last_error": "needs reconciliation"}},
    })
    before = {path.relative_to(isolated.queue_path.parent): (path.read_bytes(), path.stat().st_mtime_ns)
              for path in isolated.queue_path.parent.rglob("*") if path.is_file()}
    blocked = forbid_clients(monkeypatch)

    assert cli.main(["--reset-publish-id", "target"]) == 0

    after = {path.relative_to(isolated.queue_path.parent): (path.read_bytes(), path.stat().st_mtime_ns)
             for path in isolated.queue_path.parent.rglob("*") if path.is_file()}
    assert after == before
    output = capsys.readouterr().out
    assert "cloud-id" in output and "post-id" in output
    assert "No changes made" in output
    blocked.assert_not_called()


def test_confirm_clears_only_target_publishing_state(isolated, monkeypatch, capsys):
    state = StateStore(isolated.state_path)
    publishing = {
        "cloudinary": {"public_id": "cloud-id", "url": "https://example.test/video.mp4",
                       "status": "unknown", "last_error": "upload uncertain"},
        "buffer": {"tiktok": {"post_id": "post-id", "status": "scheduled",
                              "last_error": "old error", "request": {"intent": "create"},
                              "reconciliation": {"candidate": "post-id"}}},
        "pending": {"intent": "publish"},
    }
    state.upsert("target", status="ready", attempts=7, output_path="/videos/generated.mp4",
                 ready_path="/videos/ready.mp4", mpt_task_id="task-7",
                 publishing=publishing)
    state.upsert("other", status="failed", attempts=3, output_path="/videos/other.mp4",
                 publishing={"buffer": {"youtube": {"post_id": "keep"}}})
    before_target = deepcopy(state.get("target"))
    before_other = deepcopy(state.get("other"))
    queue_before = isolated.queue_path.read_bytes()
    blocked = forbid_clients(monkeypatch)

    assert cli.main(["--reset-publish-id", "target", "--confirm"]) == 0

    saved = StateStore(isolated.state_path)
    target = saved.get("target")
    assert "publishing" not in target
    assert target == {key: value for key, value in before_target.items() if key != "publishing"}
    assert saved.get("other") == before_other
    assert isolated.queue_path.read_bytes() == queue_before
    assert "cloud-id" in capsys.readouterr().out
    blocked.assert_not_called()


def test_unknown_id_fails_without_writes(isolated, monkeypatch, capsys):
    blocked = forbid_clients(monkeypatch)
    before = isolated.queue_path.read_bytes()

    assert cli.main(["--reset-publish-id", "missing", "--confirm"]) == 2

    assert "Unknown content ID" in capsys.readouterr().out
    assert isolated.queue_path.read_bytes() == before
    assert not isolated.state_path.parent.exists()
    blocked.assert_not_called()


def test_confirm_without_publishing_state_does_not_create_state(isolated, monkeypatch):
    blocked = forbid_clients(monkeypatch)

    assert cli.main(["--reset-publish-id", "target", "--confirm"]) == 0

    assert not isolated.state_path.parent.exists()
    blocked.assert_not_called()


def test_confirm_removes_empty_publishing_block(isolated):
    state = StateStore(isolated.state_path)
    state.upsert("target", status="ready", publishing={})

    assert cli.main(["--reset-publish-id", "target", "--confirm"]) == 0

    assert "publishing" not in StateStore(isolated.state_path).get("target")


def test_reset_rejects_other_modes():
    assert cli.main(["--confirm"]) == 2
    assert cli.main(["--reset-publish-id", "target", "--id", "other"]) == 2
    assert cli.main(["--reset-publish-id", "target", "--dry-run"]) == 2
    assert cli.main(["--reset-publish-id", "target", "--publish-ready"]) == 2
    assert cli.main(["--reset-publish-id", "target", "--reset-publish-id", "other", "--confirm"]) == 2
