from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from kitok.buffer_client import BufferError
from kitok.cloudinary_host import CloudinaryHost, HostingError
from kitok.config import Settings
from kitok.models import ContentItem, ContentQueue
from kitok.publisher import Publisher, already_created, available_slots, build_caption, post_content, utc_due_at
from kitok.state import StateStore

NOW = datetime(2026, 9, 15, tzinfo=timezone.utc)


def item(cid="one", **changes):
    return ContentItem(id=cid, subject=changes.pop("subject", "Subject"),
                       script="A sufficiently long narration script.", keywords=["test"],
                       caption=changes.pop("caption", "Caption"),
                       publish_at=changes.pop("publish_at", NOW + timedelta(days=1)), **changes)


@pytest.fixture
def setup(tmp_path):
    settings = Settings(_env_file=None, publish_enabled=True)
    state = StateStore(tmp_path / "state.json")
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mock-video")
    queue = ContentQueue(items=[item()])
    state.upsert("one", status="ready", ready_path=str(video), mpt_task_id="mpt")
    client = Mock()
    channels = {p: {"id": f"channel-{p}", "service": p} for p in ("tiktok", "instagram", "youtube")}
    client.discover.return_value = ("org", list(channels.values()), channels)
    client.posts.return_value = []
    def create(inputs):
        return {"id": "post-" + inputs["channelId"], "status": "scheduled", "channelId": inputs["channelId"],
                "text": inputs["text"], "dueAt": inputs["dueAt"]}
    client.create_post.side_effect = create
    host = Mock()
    host.ensure_video.return_value = {"url": "https://res.cloudinary.com/test/video/upload/video.mp4", "public_id": "video"}
    publisher = Publisher(settings, queue, state, client, host, validator=lambda *a: [], now=lambda: NOW)
    return publisher, client, host, state, video


def test_timezone_conversion():
    assert utc_due_at(datetime.fromisoformat("2026-09-18T19:00:00+02:00")) == "2026-09-18T17:00:00Z"
    assert utc_due_at(datetime.fromisoformat("2026-09-18T23:00:00-04:00")) == "2026-09-19T03:00:00Z"
    with pytest.raises(ValueError, match="timezone"):
        utc_due_at(datetime(2026, 9, 18))


def test_caption_tags_and_limits():
    assert build_caption("Caption", "#curiosidades #datoscuriosos") == "Caption #curiosidades #datoscuriosos"
    assert build_caption("Caption #curiosidades", "#curiosidades #datoscuriosos") == "Caption #curiosidades #datoscuriosos"
    assert len(post_content(item(caption="x" * 150), "tiktok", "")["text"]) == 150
    with pytest.raises(ValueError, match="maximum is 150"):
        post_content(item(caption="x" * 150), "tiktok", "#tag")
    with pytest.raises(ValueError, match="title"):
        post_content(item(subject="x" * 101), "youtube", "")


def test_platform_metadata():
    youtube = post_content(item(), "youtube", "#tag")
    assert youtube["metadata"]["youtube"] == {"title": "Subject", "categoryId": "27", "madeForKids": False,
                                               "privacy": "public", "notifySubscribers": True, "isAiGenerated": True}
    assert youtube["text"] == "Caption #tag"
    assert youtube["aiAssisted"] is True
    assert youtube["schedulingType"] == "automatic" and youtube["mode"] == "customScheduled"
    assert post_content(item(), "instagram", "")["metadata"]["instagram"] == {
        "type": "reel", "shouldShareToFeed": True, "isAiGenerated": True}
    assert post_content(item(), "tiktok", "")["metadata"]["tiktok"] == {"isAiGenerated": True}


@pytest.mark.parametrize("count,expected", [(0, 9), (8, 1), (9, 0), (10, 0)])
def test_slots(count, expected):
    assert available_slots(count) == expected


def test_config_defaults_and_cap():
    assert Settings(_env_file=None).publish_enabled is False
    with pytest.raises(ValidationError):
        Settings(_env_file=None, buffer_max_scheduled_per_channel=10)


def test_queue_fills_earliest_per_channel(setup):
    publisher, client, _, state, video = setup
    publisher.q = ContentQueue(items=[item(str(n), publish_at=NOW + timedelta(days=1, minutes=n)) for n in reversed(range(12))])
    for i in publisher.q.items:
        state.upsert(i.id, status="ready", ready_path=str(video))
    client.posts.return_value = [{"id": str(n), "channelId": "channel-tiktok", "status": "scheduled"} for n in range(8)]
    plan = publisher.plan()
    assert [r["id"] for r in plan.rows if r["platform"] == "tiktok"] == ["0"]
    assert len([r for r in plan.rows if r["platform"] == "instagram"]) == 9
    assert len([r for r in plan.rows if r["platform"] == "youtube"]) == 9
    assert plan.deferred == 17


def test_past_needs_attention_and_keeps_generation(setup):
    publisher, client, host, state, _ = setup
    publisher.q = ContentQueue(items=[item(publish_at=NOW - timedelta(seconds=1))])
    result = publisher.publish()
    assert len(result["attention"]) == 3
    client.create_post.assert_not_called()
    host.ensure_video.assert_not_called()
    saved = StateStore(state.path).get("one")
    assert saved["status"] == "ready" and saved["mpt_task_id"] == "mpt"
    assert saved["publishing"]["buffer"]["tiktok"]["status"] == "needs_attention"


def test_disabled_publish_never_contacts_services(setup):
    publisher, client, host, _, _ = setup
    publisher.s.publish_enabled = False
    with pytest.raises(BufferError, match="disabled"):
        publisher.publish()
    assert not client.mock_calls and not host.mock_calls


def test_dry_run_is_read_only(setup):
    publisher, client, host, state, _ = setup
    before = state.path.read_bytes()
    plan = publisher.plan()
    assert len(plan.rows) == 3 and plan.rows[0]["dueAt"] == "2026-09-16T00:00:00Z"
    assert plan.rows[2]["title"] == "Subject"
    assert state.path.read_bytes() == before
    client.create_post.assert_not_called()
    host.ensure_video.assert_not_called()


def test_idempotency_and_immediate_persistence(setup):
    publisher, client, _, state, _ = setup
    original = client.create_post.side_effect
    def check(inputs):
        platform = inputs["channelId"].removeprefix("channel-")
        saved = StateStore(state.path).get("one")["publishing"]["buffer"]
        assert saved[platform]["status"] == "unknown"
        if platform == "instagram":
            assert saved["tiktok"]["post_id"]
        return original(inputs)
    client.create_post.side_effect = check
    assert publisher.publish()["created"] == 3
    assert publisher.publish()["created"] == 0
    assert client.create_post.call_count == 3
    saved = StateStore(state.path).get("one")
    assert saved["status"] == "ready"
    for post in saved["publishing"]["buffer"].values():
        assert post["post_id"] and post["status"] == "scheduled"


def test_unknown_timeout_blocks_recreation_and_reconciles(setup):
    publisher, client, _, state, _ = setup
    publisher.q.items[0].platforms = ["tiktok"]
    client.create_post.side_effect = BufferError("timeout", ambiguous=True)
    publisher.publish()
    publisher.publish()
    assert client.create_post.call_count == 1
    record = StateStore(state.path).get("one")["publishing"]["buffer"]["tiktok"]
    assert record["status"] == "unknown"
    inputs = record["request"]
    client.posts.return_value = [{"id": "reconciled", "channelId": inputs["channelId"], "text": inputs["text"],
                                  "dueAt": inputs["dueAt"], "status": "scheduled"}]
    assert publisher.sync()["reconciled"] == 1
    assert StateStore(state.path).get("one")["publishing"]["buffer"]["tiktok"]["post_id"] == "reconciled"
    publisher.publish()
    assert client.create_post.call_count == 1


def test_unmatched_unknown_stays_blocked(setup):
    publisher, client, _, state, _ = setup
    publisher.q.items[0].platforms = ["tiktok"]
    state.update_publishing("one", "buffer", "tiktok", status="unknown", channel_id="channel-tiktok",
                            request={"channelId": "channel-tiktok", "dueAt": "2026-09-16T00:00:00Z", "text": "Caption"})
    assert publisher.sync()["attention"]
    publisher.publish()
    client.create_post.assert_not_called()
    assert state.get("one")["publishing"]["buffer"]["tiktok"]["status"] == "unknown"


def test_partial_success_id_is_saved(setup):
    publisher, client, _, state, _ = setup
    publisher.q.items[0].platforms = ["tiktok"]
    client.create_post.side_effect = BufferError("partial", ambiguous=True,
                                               post={"id": "saved", "status": "scheduled", "channelId": "channel-tiktok"})
    publisher.publish()
    publisher.publish()
    assert client.create_post.call_count == 1
    assert StateStore(state.path).get("one")["publishing"]["buffer"]["tiktok"]["post_id"] == "saved"


@pytest.mark.parametrize("status", ["draft", "error", "needs_approval", "scheduled", "sending", "sent"])
def test_post_id_always_prevents_recreation(status):
    assert already_created({"post_id": "known", "status": status})


def test_cloudinary_uploaded_once_shared_across_channels(setup):
    publisher, client, _, state, video = setup
    def upload(path, **kw):
        assert kw["resource_type"] == "video" and kw["overwrite"] is False
        assert StateStore(state.path).get("one")["publishing"]["cloudinary"]["status"] == "uploading"
        return {"secure_url": "https://res.cloudinary.com/test/video/upload/video.mp4", "public_id": kw["public_id"]}
    uploader = Mock(side_effect=upload)
    host = CloudinaryHost(publisher.s, state, uploader=uploader, lookup=Mock())
    publisher.host = host
    publisher.publish()
    uploader.assert_called_once()
    urls = {call.args[0]["assets"][0]["video"]["url"] for call in client.create_post.call_args_list}
    assert urls == {"https://res.cloudinary.com/test/video/upload/video.mp4"}
    # Reuse works after restart without importing/configuring the SDK.
    restored = CloudinaryHost(publisher.s, StateStore(state.path))
    assert restored.ensure_video("one", video)["url"] == next(iter(urls))


def test_cloudinary_timeout_reconciles_without_second_upload(setup):
    publisher, _, _, state, video = setup
    uploader = Mock(side_effect=TimeoutError("do not expose credentials"))
    lookup = Mock()
    host = CloudinaryHost(publisher.s, state, uploader=uploader, lookup=lookup)
    with pytest.raises(HostingError, match="unknown"):
        host.ensure_video("one", video)
    public_id = state.get("one")["publishing"]["cloudinary"]["public_id"]
    lookup.return_value = {"public_id": public_id, "secure_url": "https://res.cloudinary.com/test/video/upload/v.mp4"}
    assert host.ensure_video("one", video)["public_id"] == public_id
    assert uploader.call_count == 1 and lookup.call_count == 1


def test_state_merge_across_generation_and_publishing(tmp_path):
    generation = StateStore(tmp_path / "state.json")
    publishing = StateStore(generation.path)
    publishing.update_publishing("a", "buffer", "tiktok", post_id="keep", status="scheduled")
    generation.upsert("a", status="ready", mpt_task_id="task")
    publishing.update_publishing("a", "cloudinary", public_id="media", url="https://example.com/a.mp4")
    saved = StateStore(generation.path).get("a")
    assert saved["status"] == "ready" and saved["mpt_task_id"] == "task"
    assert saved["publishing"]["buffer"]["tiktok"]["post_id"] == "keep"


def test_concurrent_publishing_is_blocked(tmp_path):
    one = StateStore(tmp_path / "state.json")
    two = StateStore(one.path)
    with one.publishing_lock():
        with pytest.raises(RuntimeError, match="Another"):
            with two.publishing_lock():
                pytest.fail("second lock acquired")


def test_maintain_syncs_before_filling(setup):
    publisher, client, _, state, _ = setup
    state.update_publishing("old", "buffer", "tiktok", post_id="old-post", status="scheduled", channel_id="channel-tiktok")
    client.post.return_value = {"id": "old-post", "channelId": "channel-tiktok", "status": "sent"}
    result = publisher.publish(maintain=True)
    assert result["synced"] == 1 and result["created"] == 3
    assert state.get("old")["publishing"]["buffer"]["tiktok"]["status"] == "sent"
    calls = [c[0] for c in client.mock_calls]
    assert calls.index("post") < calls.index("create_post")


def test_interrupted_creation_remains_unknown(setup):
    publisher, client, _, state, _ = setup
    publisher.q.items[0].platforms = ["tiktok"]
    client.create_post.side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        publisher.publish()
    assert StateStore(state.path).get("one")["publishing"]["buffer"]["tiktok"]["status"] == "unknown"
    publisher.publish()
    assert client.create_post.call_count == 1


def test_known_id_survives_failed_status_query(setup):
    publisher, client, _, state, _ = setup
    state.update_publishing("one", "buffer", "tiktok", post_id="keep", status="scheduled", channel_id="channel-tiktok")
    client.post.side_effect = BufferError("post inaccessible")
    assert publisher.sync()["attention"]
    assert state.get("one")["publishing"]["buffer"]["tiktok"]["post_id"] == "keep"
    assert "tiktok" not in [row["platform"] for row in publisher.plan().rows]


def test_invalid_video_never_uploads(setup):
    publisher, client, host, _, _ = setup
    publisher.validator = lambda *a: ["invalid video"]
    assert len(publisher.publish()["attention"]) == 3
    client.create_post.assert_not_called()
    host.ensure_video.assert_not_called()


def test_rate_limit_stops_batch_and_persists_cooldown(setup):
    publisher, client, _, state, _ = setup
    client.create_post.side_effect = BufferError("limited", retry_after=900)
    publisher.publish()
    assert client.create_post.call_count == 1
    record = StateStore(state.path).get("one")["publishing"]["buffer"]["tiktok"]
    assert record["retry_at"] == utc_due_at(NOW + timedelta(seconds=900))
    assert "tiktok" not in [r["platform"] for r in publisher.plan().rows]


def test_cloudinary_unknown_not_found_does_not_reupload(setup):
    publisher, _, _, state, video = setup
    state.update_publishing("one", "cloudinary", status="unknown", public_id="saved")
    upload = Mock()
    lookup = Mock(side_effect=RuntimeError("Not Found"))
    host = CloudinaryHost(publisher.s, state, uploader=upload, lookup=lookup)
    with pytest.raises(HostingError, match="unresolved"):
        host.ensure_video("one", video)
    upload.assert_not_called()


def test_multiple_reconciliation_matches_are_not_adopted(setup):
    publisher, client, _, state, _ = setup
    req = {"channelId": "channel-tiktok", "dueAt": "2026-09-16T00:00:00Z", "text": "Caption"}
    state.update_publishing("one", "buffer", "tiktok", status="unknown", channel_id="channel-tiktok", request=req)
    client.posts.return_value = [{"id": str(i), "status": "scheduled", **req} for i in range(2)]
    assert publisher.sync()["attention"]
    assert not state.get("one")["publishing"]["buffer"]["tiktok"].get("post_id")


def test_official_sdk_upload_arguments(setup, monkeypatch):
    from pydantic import SecretStr
    import cloudinary.uploader
    import cloudinary.api

    publisher, _, _, state, video = setup
    publisher.s.cloudinary_cloud_name = "cloud"
    publisher.s.cloudinary_api_key = SecretStr("api-key")
    publisher.s.cloudinary_api_secret = SecretStr("api-secret")
    def upload(path, **kwargs):
        assert path == str(video)
        assert kwargs["resource_type"] == "video"
        assert kwargs["type"] == "upload" and kwargs["overwrite"] is False
        assert kwargs["cloud_name"] == "cloud" and kwargs["secure"] is True
        assert kwargs["api_key"] == "api-key" and kwargs["api_secret"] == "api-secret"
        return {"public_id": kwargs["public_id"], "secure_url": "https://res.cloudinary.com/cloud/video/upload/test.mp4"}
    mocked = Mock(side_effect=upload)
    monkeypatch.setattr(cloudinary.uploader, "upload_large", mocked)
    monkeypatch.setattr(cloudinary.api, "resource", Mock())
    assert CloudinaryHost(publisher.s, state).ensure_video("one", video)["status"] == "uploaded"
    mocked.assert_called_once()
