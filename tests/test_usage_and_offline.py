import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import httpx
import pytest

from kitok import cli
from kitok.buffer_client import BufferClient, BufferError
from kitok.buffer_usage import parse_rate_limits, usage_rows
from kitok.publisher import Publisher, post_content
from kitok.service_cache import ServiceCache, buffer_cache


def headers(remaining=90):
    return [("RateLimit", f'"custom-short";r={remaining};t=900'),
            ("RateLimit", '"daily";r=200;t=86400'),
            ("RateLimit", '"monthly";r=2900;t=2592000'),
            ("RateLimit-Policy", '"custom-short";q=100;w=900;pk=:abc:'),
            ("RateLimit-Policy", '"daily";q=250;w=86400'),
            ("RateLimit-Policy", '"monthly";q=3000;w=2592000')]


def test_rate_headers_repeated_combined_and_partial():
    now = datetime(2026, 9, 16, tzinfo=timezone.utc)
    report = parse_rate_limits(httpx.Headers(headers()), now=now)
    assert [row["Window"] for row in usage_rows(report)] == ["15m", "24h", "30d"]
    assert report["windows"]["custom-short"]["reset_at"] == (now + timedelta(seconds=900)).isoformat()
    assert report["windows"]["daily"]["quota"] == 250
    partial = parse_rate_limits(httpx.Headers({"RateLimit": '"custom-short";r=0;t=60'}), report, now=now)
    assert partial["windows"]["daily"] == report["windows"]["daily"]
    assert partial["windows"]["custom-short"]["window_seconds"] == 900
    assert parse_rate_limits(httpx.Headers({"X-RateLimit-Remaining": "123"})) == {}


def test_buffer_usage_refresh_exactly_one_request_and_cache(tmp_path):
    cache = ServiceCache(tmp_path / "cache.json", "test")
    handler = Mock(return_value=httpx.Response(200, headers=headers(), json={"data": {"account": {"id": "a"}}}))
    client = BufferClient("test", cache=cache, transport=httpx.MockTransport(handler))
    try:
        client.refresh_usage()
    finally:
        client.close()
    assert handler.call_count == 1
    assert ServiceCache(cache.path, "test").get("usage")["windows"]["custom-short"]["remaining"] == 90
    assert ServiceCache(cache.path, "other-account").get("usage") == {}


def test_429_reset_fallback_and_cooldown_are_persisted(tmp_path):
    cache = ServiceCache(tmp_path / "cache.json", "test")
    handler = Mock(return_value=httpx.Response(429, headers=headers(0)))
    sleep = Mock()
    client = BufferClient("test", cache=cache, transport=httpx.MockTransport(handler), sleep=sleep)
    try:
        with pytest.raises(BufferError) as error:
            client.refresh_usage()
        assert error.value.retry_after > 890
        with pytest.raises(BufferError, match="cooldown"):
            client.organizations()
    finally:
        client.close()
    assert handler.call_count == 1
    sleep.assert_not_called()
    assert cache.get("usage")["retry_at"]


def test_offline_dry_run_zero_http_even_with_credentials(local_kitok, monkeypatch, capsys):
    settings, _, state, _ = local_kitok
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    http = Mock(side_effect=AssertionError("HTTP request attempted"))
    monkeypatch.setattr(httpx.Client, "send", http)
    monkeypatch.setattr("cloudinary.api.usage", http)
    monkeypatch.setattr("cloudinary.uploader.upload_large", http)
    before = state.path.read_bytes()
    assert cli.main(["--publish-dry-run"]) == 0
    assert state.path.read_bytes() == before
    assert not settings.cache_path.exists()
    http.assert_not_called()
    text = capsys.readouterr().out
    assert "OFFLINE DRY-RUN" in text and "disclosure" in text and "local_publish_at" in text


def test_live_dry_run_reads_without_any_writes(local_kitok, monkeypatch):
    settings, _, state, _ = local_kitok
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert "mutation" not in body["query"]
        if "KitokChannels" in body["query"]:
            data = {"channels": [{"id": p, "service": p} for p in ("tiktok", "instagram", "youtube")]}
        else:
            data = {"posts": {"edges": [], "pageInfo": {"hasNextPage": False}}}
        return httpx.Response(200, headers=headers(), json={"data": data})
    monkeypatch.setattr("kitok.buffer_client.BufferClient", lambda *a, **kw:
                        BufferClient(*a, **kw, transport=httpx.MockTransport(handler)))
    before = state.path.read_bytes()
    assert cli.main(["--publish-dry-run", "--live"]) == 0
    assert len(calls) == 2
    assert state.path.read_bytes() == before
    assert not settings.cache_path.exists()


def test_buffer_usage_default_is_offline(local_kitok, monkeypatch, capsys):
    settings, _, _, _ = local_kitok
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    buffer_cache(settings).put("usage", parse_rate_limits(httpx.Headers(headers())))
    blocked = Mock(side_effect=AssertionError("HTTP request"))
    monkeypatch.setattr(httpx.Client, "send", blocked)
    assert cli.main(["--buffer-usage"]) == 0
    assert "90 / 100" in capsys.readouterr().out
    blocked.assert_not_called()


def test_offline_occupancy_uses_saved_channel_ids_without_configuration(local_kitok):
    settings, queue, state, _ = local_kitok
    state.update_publishing("old", "buffer", "tiktok", post_id="saved", status="scheduled", channel_id="saved-channel")
    plan = Publisher(settings, queue, state).plan()
    assert plan.offline and plan.counts["tiktok"] == 1


def test_unknown_budget_does_not_allow_a_publishing_batch():
    client = BufferClient("test", transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    try:
        with pytest.raises(BufferError, match="unknown or stale"):
            client.ensure_budget(3)
    finally:
        client.close()


@pytest.mark.parametrize("enabled", [True, False])
def test_disclosure_configuration_applies_to_every_plan_row(local_kitok, enabled):
    settings, queue, state, _ = local_kitok
    settings.content_ai_assisted = settings.tiktok_ai_generated = settings.youtube_ai_generated = settings.instagram_ai_generated = enabled
    plan = Publisher(settings, queue, state).plan()
    assert len(plan.rows) == 6
    for row in plan.rows:
        assert row["input"]["aiAssisted"] is enabled
        metadata = row["input"]["metadata"][row["platform"]]
        if row["platform"] == "instagram":
            assert set(metadata) == {"type", "shouldShareToFeed", "isAiGenerated"}
        assert metadata["isAiGenerated"] is enabled
