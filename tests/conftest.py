"""Unit tests must never reach external services."""
import socket

import pytest


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("External network access is forbidden in unit tests")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture
def local_kitok(tmp_path, monkeypatch):
    """A complete local workspace; all tests remain independent of the real queue."""
    import json
    from datetime import datetime, timedelta, timezone
    from kitok.config import Settings
    from kitok.models import ContentQueue
    from kitok.state import StateStore
    monkeypatch.setattr("kitok.config.PROJECT_ROOT", tmp_path)
    settings = Settings(_env_file=None, ready_dir=tmp_path / "phone", publish_enabled=True,
                        buffer_api_key="test-secret", buffer_organization_id="org")
    settings.queue_path.write_text(json.dumps([
        {"id": cid, "subject": f"Title {cid}", "script": "A sufficiently long narration script.",
         "caption": f"Caption {cid}", "keywords": ["test"],
         "publish_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()}
        for cid in ("one", "two")]))
    state = StateStore(settings.state_path)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"test-media")
    for cid in ("one", "two"):
        state.upsert(cid, status="ready", attempts=1, ready_path=str(video))
    monkeypatch.setattr("kitok.publisher.validate_for_publishing", lambda *args: [])
    return settings, ContentQueue.load(settings.queue_path), state, video
