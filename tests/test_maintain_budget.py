import json
from unittest.mock import Mock

import httpx
import pytest

from kitok.buffer_client import BufferClient, BufferError
from kitok.publisher import Publisher
from kitok.service_cache import buffer_cache


def client_for(settings, remaining):
    calls, posts = [], []
    def handler(request):
        body = json.loads(request.content)
        query = body["query"]
        calls.append(query)
        if "KitokChannels" in query:
            data = {"channels": [{"id": p, "service": p} for p in ("tiktok", "instagram", "youtube")]}
        elif "KitokPosts" in query:
            data = {"posts": {"edges": [{"node": p} for p in posts], "pageInfo": {"hasNextPage": False}}}
        elif "KitokCreatePost" in query:
            inputs = body["variables"]["input"]
            post = {"id": str(len(posts)), "status": "scheduled", "channelId": inputs["channelId"],
                    "text": inputs["text"], "dueAt": inputs["dueAt"]}
            posts.append(post)
            data = {"createPost": {"__typename": "PostActionSuccess", "post": post}}
        else:
            raise AssertionError("Unnecessary discovery or post readback")
        return httpx.Response(200, json={"data": data}, headers={
            "RateLimit": f'"short";r={remaining};t=900', "RateLimit-Policy": '"short";q=100;w=900'})
    cache = buffer_cache(settings)
    return BufferClient("test", publish_enabled=True, cache=cache, transport=httpx.MockTransport(handler)), calls


def test_maintain_bounded_reads_discovery_reuse_no_readbacks(local_kitok):
    settings, queue, state, _ = local_kitok
    client, calls = client_for(settings, 80)
    host = Mock()
    host.ensure_video.return_value = {"url": "https://example.test/video.mp4"}
    publisher = Publisher(settings, queue, state, client, host, cache=buffer_cache(settings))
    try:
        result = publisher.publish(maintain=True)
        assert result["created"] == 6
        assert result["before"] == {p: 0 for p in ("tiktok", "instagram", "youtube")}
        assert result["after_estimated"] == {p: 2 for p in ("tiktok", "instagram", "youtube")}
        assert len(calls) == 8  # one channels + one combined occupancy + six creates
        assert publisher.publish(maintain=True)["created"] == 0
        assert len(calls) == 9  # next invocation reuses discovery and only reads occupancy
        assert sum("KitokChannels" in q for q in calls) == 1
    finally:
        client.close()


def test_low_budget_aborts_before_any_upload_or_mutation(local_kitok):
    settings, queue, state, _ = local_kitok
    client, calls = client_for(settings, 4)
    host = Mock()
    before = state.path.read_bytes()
    try:
        with pytest.raises(BufferError, match="Not enough.*budget"):
            Publisher(settings, queue, state, client, host).publish(maintain=True)
    finally:
        client.close()
    assert len(calls) == 2
    assert not any("mutation" in query for query in calls)
    host.ensure_video.assert_not_called()
    assert state.path.read_bytes() == before


def test_same_client_reuses_discovery_if_persisted_cache_disappears(local_kitok):
    settings, queue, state, _ = local_kitok
    client, calls = client_for(settings, 80)
    host = Mock()
    host.ensure_video.return_value = {"url": "https://example.test/video.mp4"}
    publisher = Publisher(settings, queue, state, client, host, cache=buffer_cache(settings))
    try:
        assert publisher.publish(maintain=True)["created"] == 6
        assert len(calls) == 8
        settings.cache_path.unlink()
        assert publisher.publish(maintain=True)["created"] == 0
        assert len(calls) == 9
        assert "KitokPosts" in calls[-1]
        assert sum("KitokChannels" in query for query in calls) == 1
    finally:
        client.close()
