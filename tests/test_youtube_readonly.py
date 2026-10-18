import base64
import hashlib
import io
import json
from pathlib import Path
import stat
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from kitok.youtube.client import ANALYTICS, DATA, REPORTING, YouTubeReadOnly, parse_table
from kitok.youtube.oauth import (AUTH_URL, TOKEN_URL, SCOPES, AuthorizationAttempt,
    PrivateStore, YouTubeError, access_token, connect, save_tokens, token_request, validate_scopes)


CHANNEL = "UCLnP8Kb1USd06TW3D1JLFvg"
VIDEO = "abcdefghijk"


@pytest.fixture
def store(tmp_path):
    store = PrivateStore(tmp_path / "private")
    store.write("client.json", {"client_id": "desktop-client", "client_secret": "private-client-value"})
    store.write("tokens.json", {"access_token": "private-access-value", "refresh_token": "private-refresh-value",
                               "scope": " ".join(SCOPES), "expires_at": time.time() + 3600})
    return store


def token_payload(**updates):
    return {"access_token": "new-access", "refresh_token": "new-refresh", "scope": " ".join(SCOPES),
            "expires_in": 3600, "token_type": "Bearer", **updates}


def test_pkce_loopback_exact_readonly_scopes():
    attempt = AuthorizationAttempt("client", "http://127.0.0.1:12345/oauth/callback")
    parts = urlsplit(attempt.url)
    query = parse_qs(parts.query)
    assert parts.scheme + "://" + parts.netloc + parts.path == AUTH_URL
    assert set(query["scope"][0].split()) == set(SCOPES)
    expected = base64.urlsafe_b64encode(hashlib.sha256(attempt.verifier.encode()).digest()).decode().rstrip("=")
    assert query["code_challenge"] == [expected]
    assert query["code_challenge_method"] == ["S256"]
    assert 43 <= len(attempt.verifier) <= 128
    assert "include_granted_scopes" not in query


@pytest.mark.parametrize("url", ["http://localhost:1234/x", "https://127.0.0.1:1234/x", "http://evil.test:1234/x", "http://127.0.0.1/x"])
def test_nonloopback_rejected(url):
    with pytest.raises(YouTubeError):
        AuthorizationAttempt("client", url)


def test_state_replay_expiry_and_duplicate_codes():
    attempt = AuthorizationAttempt("client", "http://127.0.0.1:1234/oauth/callback")
    with pytest.raises(YouTubeError, match="estado"):
        attempt.consume("state=wrong&code=secret")
    with pytest.raises(YouTubeError, match="estado"):
        attempt.consume("state=%C3%A9&code=secret")
    assert not attempt.used
    assert attempt.consume("state=" + attempt.state + "&code=secret") == "secret"
    with pytest.raises(YouTubeError, match="utilizada"):
        attempt.consume("state=" + attempt.state + "&code=secret")
    expired = AuthorizationAttempt("client", "http://127.0.0.1:1234/oauth/callback", ttl=-1)
    with pytest.raises(YouTubeError, match="caducado"):
        expired.consume("state=" + expired.state + "&code=secret")
    other = AuthorizationAttempt("client", "http://127.0.0.1:1234/oauth/callback")
    with pytest.raises(YouTubeError, match="válido"):
        other.consume("state=" + other.state + "&code=a&code=b")
    assert other.used


def test_denial_consumes_valid_attempt():
    attempt = AuthorizationAttempt("client", "http://127.0.0.1:1234/oauth/callback")
    with pytest.raises(YouTubeError, match="concedida"):
        attempt.consume("state=" + attempt.state + "&error=access_denied")
    assert attempt.used


def test_private_atomic_permissions_and_no_secret_status(store):
    save_tokens(store, token_payload())
    assert stat.S_IMODE(store.directory.stat().st_mode) == 0o700
    for name in ("client.json", "tokens.json"):
        assert stat.S_IMODE(store.path(name).stat().st_mode) == 0o600
    status = store.status()
    assert not status["live_verified"]
    assert "new-access" not in json.dumps(status)
    assert "new-refresh" not in json.dumps(status)
    assert not list(store.directory.glob(".private-*"))


def test_symlinks_rejected(tmp_path, store):
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    store.path("tokens.json").unlink()
    store.path("tokens.json").symlink_to(outside)
    with pytest.raises(YouTubeError, match="simbólico"):
        store.read("tokens.json")
    with pytest.raises(YouTubeError, match="simbólico"):
        store.write("tokens.json", {})
    linked = tmp_path / "linked"
    linked.symlink_to(store.directory, target_is_directory=True)
    with pytest.raises(YouTubeError, match="simbólico"):
        PrivateStore(linked)
    assert outside.read_text() == "{}"


def test_lock_refuses_duplicate_execution(store):
    with store.lock():
        with pytest.raises(YouTubeError, match="en curso"):
            with store.lock():
                pytest.fail("duplicate operation entered")


def test_setup_desktop_only_and_pinned_endpoints(tmp_path):
    private = PrivateStore(tmp_path / "private")
    source = tmp_path / "download.json"
    source.write_text(json.dumps({"web": {"client_id": "client"}}))
    with pytest.raises(YouTubeError, match="Desktop"):
        private.setup(source)
    source.write_text(json.dumps({"installed": {"client_id": "client", "client_secret": "secret",
                                               "token_uri": "https://evil.test/token"}}))
    private.setup(source)
    assert "token_uri" not in private.read("client.json")


@pytest.mark.parametrize("scope", ["", SCOPES[0], " ".join(SCOPES) + " https://www.googleapis.com/auth/youtube.upload", None])
def test_scope_exactness(scope):
    with pytest.raises(YouTubeError):
        validate_scopes(scope)


def test_token_post_once_no_retry_or_sensitive_error(store):
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret-in-transport-error", request=request)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(YouTubeError, match="No se reintenta") as error:
        token_request(client, {"code": "secret-code"})
    assert len(calls) == 1
    assert str(calls[0].url) == TOKEN_URL
    assert "secret" not in str(error.value)


def test_refresh_preserves_refresh_token_and_binding(store):
    prior = store.read("tokens.json")
    prior.update(expires_at=0, channel_id=CHANNEL)
    store.write("tokens.json", prior)
    # OAuth refresh may omit scope; it must preserve the previous authorized scope.
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        "access_token": "renewed", "expires_in": 3600, "token_type": "Bearer"})))
    assert access_token(store, client) == "renewed"
    saved = store.read("tokens.json")
    assert saved["refresh_token"] == prior["refresh_token"]
    assert saved["channel_id"] == CHANNEL


@pytest.mark.parametrize("response", [token_payload(), token_payload(refresh_token=None)])
def test_connect_callback_exchange_and_atomic_channel_binding(store, monkeypatch, response):
    import kitok.youtube.oauth as oauth
    prior = store.read("tokens.json")
    prior["channel_id"] = CHANNEL
    store.write("tokens.json", prior)
    captured = {}
    calls, writes = [], []
    real_write = store.write

    def record_write(name, value):
        writes.append((name, dict(value)))
        real_write(name, value)

    monkeypatch.setattr(store, "write", record_write)

    class FakeServer:
        def __init__(self, address, handler):
            assert address == ("127.0.0.1", 0)
            self.handler = handler
            self.server_port = 12345
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def handle_request(self):
            request = object.__new__(self.handler)
            request.path = "/oauth/callback?state=" + captured["state"][0] + "&code=one-use-code"
            request.wfile = io.BytesIO()
            request.send_response = lambda status: captured.update(status=status)
            request.send_header = lambda *args: None
            request.end_headers = lambda: None
            request.do_GET()

    def open_browser(url):
        captured.update(parse_qs(urlsplit(url).query))
        return True

    def handler(request):
        calls.append(request)
        assert request.method == "POST" and str(request.url) == TOKEN_URL
        data = parse_qs(request.content.decode())
        assert data["code"] == ["one-use-code"]
        assert data["redirect_uri"] == ["http://127.0.0.1:12345/oauth/callback"]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(data["code_verifier"][0].encode()).digest()).decode().rstrip("=")
        assert captured["code_challenge"] == [challenge]
        return httpx.Response(200, json=response)

    monkeypatch.setattr(oauth, "HTTPServer", FakeServer)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    if response["refresh_token"]:
        connect(store, client=client, open_browser=open_browser)
        assert store.read("tokens.json")["channel_id"] == CHANNEL
        assert len(writes) == 1 and writes[0][1]["channel_id"] == CHANNEL
    else:
        with pytest.raises(YouTubeError, match="offline"):
            connect(store, client=client, open_browser=open_browser)
        assert store.read("tokens.json") == prior
        assert not writes
    assert len(calls) == 1
    assert captured["status"] == 200


@pytest.mark.parametrize("updates", [{"expires_at": "bad"}, {"expires_at": "nan"},
                                      {"access_token": None}, {"expires_at": 0, "refresh_token": None}])
def test_corrupt_local_tokens_fail_safely_before_network(store, updates):
    tokens = store.read("tokens.json")
    tokens.update(updates)
    store.write("tokens.json", tokens)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("sent request")))
    with pytest.raises(YouTubeError):
        access_token(store, client)


@pytest.mark.parametrize("config", [{}, {"client_id": None}, {"client_id": "x", "client_secret": []}])
def test_corrupt_client_config_fails_safely_before_network(store, config):
    store.write("client.json", config)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("sent request")))
    with pytest.raises(YouTubeError, match="Desktop local"):
        access_token(store, client)


def test_parse_retention_by_column_name_without_inventing_missing():
    parsed = parse_table({"columnHeaders": [{"name": "audienceWatchRatio"}, {"name": "elapsedVideoTimeRatio"}],
                          "rows": [[1.15, 0.25], [None, 0.50]]})
    assert parsed["rows"][0] == {"audienceWatchRatio": 1.15, "elapsedVideoTimeRatio": 0.25}
    assert parsed["rows"][1]["audienceWatchRatio"] is None
    assert parse_table({"columnHeaders": [{"name": "views"}]})["status"] == "no_data"
    with pytest.raises(YouTubeError):
        parse_table({"columnHeaders": [{"name": "views"}], "rows": [[1, 2]]})


def response_for(request):
    path = request.url.path
    if path.endswith("/channels"):
        return {"items": [{"id": CHANNEL, "snippet": {"title": "Test channel"},
                           "contentDetails": {"relatedPlaylists": {"uploads": "UU-test"}}}]}
    if path.endswith("/playlistItems"):
        return {"items": [{"contentDetails": {"videoId": VIDEO}}]}
    if path.endswith("/videos"):
        return {"items": [{"id": VIDEO, "snippet": {"channelId": CHANNEL, "title": "Test video"}}]}
    if request.url.host == "youtubeanalytics.googleapis.com":
        dimension = request.url.params["dimensions"]
        return {"columnHeaders": [{"name": dimension}, {"name": "views"}], "rows": [["x", 25]]}
    if path.endswith("/reportTypes"):
        return {"reportTypes": [{"id": "channel_reach_basic_a1"}]}
    if path.endswith("/jobs"):
        return {"jobs": [{"id": "job-123"}]}
    if path.endswith("/reports"):
        return {"reports": [{"id": "report-1", "downloadUrl": "https://evil.test/no-fetch"}]}
    raise AssertionError(str(request.url))


def test_sync_official_gets_only_snapshot_provenance_no_secrets(store):
    requests = []
    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer private-access-value"
        return httpx.Response(200, json=response_for(request))
    api = YouTubeReadOnly(store, client=httpx.Client(transport=httpx.MockTransport(handler)))
    snapshot = api.sync(start="2026-01-01", end="2026-01-31", video=VIDEO)
    assert snapshot["channel_id"] == CHANNEL
    assert snapshot["period"]["date_timezone"] == "America/Los_Angeles"
    assert snapshot["retention"]["query"]["filters"] == "video==" + VIDEO
    assert not snapshot["reporting"]["creates_jobs"]
    assert not snapshot["reporting"]["downloads_reports"]
    assert "private-access-value" not in store.path("snapshot.json").read_text()
    assert all(request.url.host != "evil.test" for request in requests)
    assert stat.S_IMODE(store.path("snapshot.json").stat().st_mode) == 0o600


def test_compact_dates_are_normalized_before_google_queries(store):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=response_for(request))
    api = YouTubeReadOnly(store, client=httpx.Client(transport=httpx.MockTransport(handler)))
    snapshot = api.sync(start="20260101", end="20260131")
    assert snapshot["period"]["start"] == "2026-01-01"
    analytics = [r for r in requests if r.url.host == "youtubeanalytics.googleapis.com"]
    assert all(r.url.params["startDate"] == "2026-01-01" for r in analytics)


def test_api_endpoint_allowlist_no_bearer_to_arbitrary_url(store):
    api = YouTubeReadOnly(store, client=httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("sent request"))))
    for url in ("https://evil.test/report", DATA + "videos/delete", REPORTING + "jobs/../reports"):
        with pytest.raises(YouTubeError, match="permitido"):
            api._get(url, {})


def test_analytics_forbidden_and_missing_remain_unavailable_not_zero(store):
    def handler(request):
        if request.url.host == "youtubeanalytics.googleapis.com":
            return httpx.Response(403, json={"error": "private-response"})
        return httpx.Response(200, json=response_for(request))
    api = YouTubeReadOnly(store, client=httpx.Client(transport=httpx.MockTransport(handler)))
    snapshot = api.sync(start="2026-01-01", end="2026-01-31")
    assert snapshot["daily"]["status"] == "unavailable"
    assert "rows" not in snapshot["daily"]
    assert "private-response" not in json.dumps(snapshot)
    assert snapshot["retention"]["status"] == "not_requested"


def test_refresh_timeout_between_queries_aborts_without_repeating_post(store):
    calls = []
    store.write("snapshot.json", {"prior": True})
    def handler(request):
        calls.append(request)
        if request.method == "POST":
            raise httpx.ReadTimeout("private-value", request=request)
        if request.url.host == "youtubeanalytics.googleapis.com":
            tokens = store.read("tokens.json")
            tokens["expires_at"] = 0
            store.write("tokens.json", tokens)
        return httpx.Response(200, json=response_for(request))
    api = YouTubeReadOnly(store, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(YouTubeError, match="No se reintenta"):
        api.sync(start="2026-01-01", end="2026-01-31", video=VIDEO)
    assert sum(request.method == "POST" for request in calls) == 1
    assert store.read("snapshot.json") == {"prior": True}


def test_channel_change_rejected_and_snapshot_preserved(store):
    tokens = store.read("tokens.json")
    tokens["channel_id"] = "UC" + "a" * 22
    store.write("tokens.json", tokens)
    store.write("snapshot.json", {"prior": True})
    api = YouTubeReadOnly(store, client=httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=response_for(request)))))
    with pytest.raises(YouTubeError, match="identidad cambió"):
        api.sync(start="2026-01-01", end="2026-01-31")
    assert store.read("snapshot.json") == {"prior": True}


def test_repeated_pagination_fails_instead_of_looping(store):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"items": [], "nextPageToken": "same"})
    api = YouTubeReadOnly(store, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(YouTubeError, match="paginación"):
        api._items(DATA + "channels", {}, "items")
    assert len(calls) == 2


@pytest.mark.parametrize("kwargs", [{"start": "bad", "end": "2026-01-01"},
    {"start": "2026-01-02", "end": "2026-01-01"},
    {"start": "2026-01-01", "end": "2026-01-02", "video": "x;filters=bad"},
    {"start": "2026-01-01", "end": "2026-01-02", "limit": 501}])
def test_invalid_query_rejected_before_network(store, kwargs):
    api = YouTubeReadOnly(store, client=httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("sent request"))))
    with pytest.raises(YouTubeError):
        api.sync(**kwargs)
