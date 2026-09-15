import json
from unittest.mock import Mock

import httpx
import pytest

from kitok.buffer_client import BufferClient, BufferError, BufferMutationError, select_channels


@pytest.fixture
def make_client():
    clients = []

    def make(handler, **kwargs):
        client = BufferClient("secret-key", transport=httpx.MockTransport(handler), **kwargs)
        clients.append(client)
        return client
    yield make
    for client in clients:
        client.close()


def test_channel_discovery(make_client):
    requests = []
    def handler(request):
        assert request.url == "https://api.buffer.com"
        assert request.headers["Authorization"] == "Bearer secret-key"
        body = json.loads(request.content)
        requests.append(body)
        if "KitokOrganizations" in body["query"]:
            return httpx.Response(200, json={"data": {"account": {"organizations": [{"id": "org", "name": "O"}]}}})
        assert body["variables"] == {"input": {"organizationId": "org"}}
        return httpx.Response(200, json={"data": {"channels": [{"id": p, "service": p} for p in ("tiktok", "instagram", "youtube")]}})
    org, channels, selected = make_client(handler).discover()
    assert org == "org" and len(channels) == len(selected) == 3
    assert len(requests) == 2


def test_discovery_ambiguity_and_explicit_ids():
    orgs = [{"id": "a"}, {"id": "b"}]
    channels = [{"id": "t1", "service": "tiktok"}, {"id": "t2", "service": "tiktok"}]
    with pytest.raises(BufferError, match="ORGANIZATION"):
        select_channels(orgs, channels)
    with pytest.raises(BufferError, match="TIKTOK_CHANNEL_ID"):
        select_channels(orgs, channels, "a")
    assert select_channels(orgs, channels, "a", {"tiktok": "t2"})[1]["tiktok"]["id"] == "t2"
    with pytest.raises(BufferError):
        select_channels(orgs, channels, "a", {"youtube": "t2"})
    with pytest.raises(BufferError):
        select_channels(orgs, channels, "missing")


def test_top_level_errors_and_redaction(make_client):
    client = make_client(lambda r: httpx.Response(200, json={"errors": [{"message": "bad secret-key"}]}))
    with pytest.raises(BufferError, match="GraphQL") as exc:
        client.organizations()
    assert "secret-key" not in str(exc.value)


def test_typed_mutation_error(make_client):
    client = make_client(lambda r: httpx.Response(200, json={"data": {"createPost": {"__typename": "LimitReachedError", "message": "queue full"}}}), publish_enabled=True)
    with pytest.raises(BufferMutationError, match="queue full") as exc:
        client.create_post({})
    assert not exc.value.ambiguous


@pytest.mark.parametrize("response", [
    httpx.Response(503), httpx.Response(200, text="bad JSON"),
    httpx.Response(200, json={"data": {"createPost": {"__typename": "PostActionSuccess", "post": {}}}}),
    httpx.Response(200, json={"errors": [{"message": "resolver failed"}]}),
])
def test_ambiguous_mutation_never_retries(make_client, response):
    handler = Mock(return_value=response)
    with pytest.raises(BufferError) as exc:
        make_client(handler, publish_enabled=True).create_post({})
    assert exc.value.ambiguous
    assert handler.call_count == 1


def test_timeout_never_retries(make_client):
    handler = Mock(side_effect=httpx.ReadTimeout("secret must not leak"))
    with pytest.raises(BufferError) as exc:
        make_client(handler, publish_enabled=True).create_post({})
    assert exc.value.ambiguous
    assert handler.call_count == 1
    assert "secret must not leak" not in str(exc.value)


def test_partial_success_preserves_id(make_client):
    post = {"id": "committed", "status": "scheduled"}
    handler = lambda r: httpx.Response(200, json={"data": {"createPost": {"post": post}}, "errors": [{"message": "partial error"}]})
    with pytest.raises(BufferError) as exc:
        make_client(handler, publish_enabled=True).create_post({})
    assert exc.value.post == post


def test_disabled_client_blocks_mutations(make_client):
    handler = Mock()
    with pytest.raises(BufferError, match="disabled"):
        make_client(handler).create_post({})
    handler.assert_not_called()


def test_read_rate_limit_backoff(make_client):
    sleep = Mock()
    handler = Mock(side_effect=[httpx.Response(429, headers={"Retry-After": "2"}),
                               httpx.Response(200, json={"data": {"account": {"organizations": []}}})])
    assert make_client(handler, sleep=sleep).organizations() == []
    sleep.assert_called_once_with(2)


def test_mutation_rate_limit_no_retry(make_client):
    handler = Mock(return_value=httpx.Response(429, headers={"Retry-After": "900"}))
    with pytest.raises(BufferError) as exc:
        make_client(handler, publish_enabled=True).create_post({})
    assert exc.value.retry_after == 900 and not exc.value.ambiguous
    assert handler.call_count == 1


def test_graphql_rate_limit_read(make_client):
    handler = Mock(side_effect=[httpx.Response(200, headers={"Retry-After": "1"}, json={"errors": [{"message": "limited", "extensions": {"code": "RATE_LIMITED"}}]}),
                               httpx.Response(200, json={"data": {"account": {"organizations": []}}})])
    sleep = Mock()
    assert make_client(handler, sleep=sleep).organizations() == []
    assert sleep.call_count == 1


def test_post_pagination(make_client):
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        cursor = body["variables"]["after"]
        return httpx.Response(200, json={"data": {"posts": {
            "edges": [{"node": {"id": "a" if cursor is None else "b"}}],
            "pageInfo": {"hasNextPage": cursor is None, "endCursor": "next" if cursor is None else None}}}})
    assert [p["id"] for p in make_client(handler).posts("org", ["t"], ["scheduled"])] == ["a", "b"]
    assert calls[1]["variables"]["after"] == "next"
    assert calls[0]["variables"]["input"]["filter"] == {"channelIds": ["t"], "status": ["scheduled"]}
