import copy
import json
import time

import httpx
import pytest

from kitok.youtube.management import YouTubeManagement, operation, public_receipt
from kitok.youtube.oauth import (AuthorizationAttempt, MANAGE_SCOPES, SCOPES, PrivateStore,
                                 YouTubeError, validate_scopes)
from urllib.parse import parse_qs, urlsplit

CHANNEL = 'UC9h_aIbnfQUo0ylPsPNnbrg'
VIDEO = 'abcdefghijk'


@pytest.fixture
def store(tmp_path):
    store = PrivateStore(tmp_path/'private')
    store.write('client.json', {'client_id': 'test', 'client_secret': 'secret'})
    store.write('tokens.json', {'access_token': 'private-token', 'refresh_token': 'private-refresh',
        'expires_at': time.time()+3600, 'scope': ' '.join(MANAGE_SCOPES), 'channel_id': CHANNEL})
    return store


def client(store, handler):
    def handle(request):
        if request.method == 'GET' and request.url.path == '/youtube/v3/channels':
            return httpx.Response(200, json={'items': [{'id': CHANNEL}]})
        return handler(request)
    return YouTubeManagement(store, client=httpx.Client(transport=httpx.MockTransport(handle)))


def update():
    return {'operation': 'youtube.videos.update', 'params': {'part': ['snippet']},
            'body': {'id': VIDEO, 'snippet': {'title': 'New', 'categoryId': '24', 'description': 'Full'}}}


def test_manage_scope_profile_and_read_compatibility():
    validate_scopes(' '.join(SCOPES))
    validate_scopes(' '.join(MANAGE_SCOPES))
    attempt = AuthorizationAttempt('client', 'http://127.0.0.1:12345/oauth/callback', scopes=MANAGE_SCOPES)
    assert set(parse_qs(urlsplit(attempt.url).query)['scope'][0].split()) == set(MANAGE_SCOPES)
    with pytest.raises(YouTubeError):
        validate_scopes(' '.join(MANAGE_SCOPES)+' https://www.googleapis.com/auth/drive')


def test_exact_plan_snapshot_apply_readback_and_replay(store):
    calls = []
    state = {'items': [{'id': VIDEO, 'snippet': {'title': 'Old', 'categoryId': '24'}}]}
    def handler(request):
        calls.append(request)
        if request.method == 'PUT':
            state['items'] = [json.loads(request.content)]
            return httpx.Response(200, json=state['items'][0])
        return httpx.Response(200, json=copy.deepcopy(state))
    api = client(store, handler)
    plan = api.plan(update(), CHANNEL)
    assert not any(r.method == 'PUT' for r in calls)
    assert plan['before']['items'][0]['snippet']['title'] == 'Old'
    result = api.apply(plan['sha256'], CHANNEL)
    assert result['status'] == 'succeeded'
    assert result['readback']['items'][0]['snippet']['title'] == 'New'
    with pytest.raises(YouTubeError, match='ya enviada'):
        api.apply(plan['sha256'], CHANNEL)
    assert sum(r.method == 'PUT' for r in calls) == 1


def test_wrong_channel_never_sends_mutation(store):
    calls = []
    api = client(store, lambda r: calls.append(r) or httpx.Response(200, json={}))
    with pytest.raises(YouTubeError, match='canal remoto'):
        api.plan(update(), 'UC'+'x'*22)
    assert not calls


@pytest.mark.parametrize('change', ['body', 'expires', 'remote'])
def test_tampered_stale_or_conflicting_plan_blocks_before_mutation(store, change):
    state = {'items': [{'id': VIDEO, 'snippet': {'title': 'Old'}}]}
    calls = []
    api = client(store, lambda r: calls.append(r) or httpx.Response(200, json=copy.deepcopy(state)))
    plan = api.plan(update(), CHANNEL)
    if change == 'body':
        saved = store.read('operation.json')
        saved['request']['body']['snippet']['title'] = 'Tampered'
        store.write('operation.json', saved)
    elif change == 'expires':
        import kitok.youtube.management as management
        # Hash matches but original plan is past TTL.
        saved = store.read('operation.json')
        saved['expires_at'] = 0
        saved['sha256'] = management.digest({k:v for k,v in saved.items() if k != 'sha256'})
        store.write('operation.json', saved)
        plan = saved
    else:
        state['items'][0]['snippet']['title'] = 'Other editor'
    with pytest.raises(YouTubeError):
        api.apply(plan['sha256'], CHANNEL)
    assert all(r.method == 'GET' for r in calls)


def test_timeout_receipt_blocks_retries_and_new_plans(store):
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == 'POST':
            raise httpx.ReadTimeout('private-token', request=request)
        return httpx.Response(200, json={})
    api = client(store, handler)
    req = {'operation': 'youtube.playlists.insert', 'params': {'part': ['snippet']},
           'body': {'snippet': {'title': 'List'}}}
    plan = api.plan(req, CHANNEL)
    with pytest.raises(YouTubeError, match='incierto') as exc:
        api.apply(plan['sha256'], CHANNEL)
    assert 'private-token' not in str(exc.value)
    assert store.read('receipt.json')['status'] == 'uncertain'
    with pytest.raises(YouTubeError):
        api.apply(plan['sha256'], CHANNEL)
    with pytest.raises(YouTubeError):
        api.plan(req, CHANNEL)
    assert sum(r.method == 'POST' for r in calls) == 1


@pytest.mark.parametrize('payload', [
    {'operation': 'evil.request'},
    {'operation': 'youtube.channels.list', 'params': {'access_token': 'oops'}},
    {'operation': 'youtube.channels.list', 'params': {'part': 'snippet'}},
    {'operation': 'youtube.channels.list', 'params': {'part': ['snippet'], 'onBehalfOfContentOwner': 'x'}},
    {'operation': 'youtube.videos.update', 'params': {'part': ['snippet']}, 'body': {'nonsense': True}},
    {'operation': 'youtubereporting.jobs.get', 'params': {'jobId': '../bad'}},
])
def test_bad_request_rejected_before_any_network(store, payload):
    api = YouTubeManagement(store, client=httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail(str(r.url)))))
    with pytest.raises(YouTubeError):
        api.query(payload, CHANNEL)


def test_readonly_cannot_apply_writes(store):
    tokens = store.read('tokens.json')
    tokens['scope'] = ' '.join(SCOPES)
    store.write('tokens.json', tokens)
    api = client(store, lambda r: httpx.Response(200, json={'items': []}))
    plan = api.plan(update(), CHANNEL)
    assert not plan['scope_ready']
    with pytest.raises(YouTubeError, match='Falta permiso'):
        api.apply(plan['sha256'], CHANNEL)
    assert store.read('receipt.json') is None


@pytest.mark.parametrize('host', ['www.googleapis.com', 'evil.test'])
def test_upload_streams_file_and_rejects_foreign_session(store, tmp_path, host):
    media = tmp_path/'movie.mp4'
    media.write_bytes(b'video-data')
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == 'POST':
            return httpx.Response(200, headers={'Location': 'https://'+host+'/upload/youtube/v3/videos?upload_id=secret'})
        assert request.content == b'video-data'
        return httpx.Response(200, json={'id': VIDEO})
    api = client(store, handler)
    req = {'operation': 'youtube.videos.insert', 'params': {'part': ['snippet', 'status']},
        'body': {'snippet': {'title': 'Test', 'categoryId': '24'}, 'status': {'privacyStatus': 'private'}}, 'media': str(media)}
    plan = api.plan(req, CHANNEL)
    if host == 'evil.test':
        with pytest.raises(YouTubeError, match='URL de subida'):
            api.apply(plan['sha256'], CHANNEL)
        assert not any(r.url.host == 'evil.test' for r in calls)
    else:
        receipt = api.apply(plan['sha256'], CHANNEL)
        assert receipt['response']['id'] == VIDEO
        assert 'upload_id' not in json.dumps(public_receipt(receipt))
        assert sum(r.method == 'PUT' for r in calls) == 1


def test_download_never_sends_bearer_to_report_url_from_other_host(store, tmp_path):
    calls = []
    api = client(store, lambda r: calls.append(r) or httpx.Response(200, json={'downloadUrl': 'https://evil.test/report'}))
    with pytest.raises(YouTubeError, match='URL de informe'):
        api.download_report('job', 'report', CHANNEL, tmp_path/'data.csv')
    assert all(r.url.host != 'evil.test' for r in calls)


def test_download_is_private_streamed_and_no_overwrite(store, tmp_path):
    def handler(request):
        if '/reports/' in request.url.path:
            return httpx.Response(200, json={'downloadUrl': 'https://youtubereporting.googleapis.com/v1/media/test'})
        assert request.url.params['alt'] == 'media'
        return httpx.Response(200, content=b'day,views\n20260101,7\n')
    api = client(store, handler)
    output = tmp_path/'report.csv'
    api.download_report('job', 'report', CHANNEL, output)
    assert output.read_bytes().endswith(b',7\n')
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        api.download_report('job', 'report', CHANNEL, output)
    assert output.read_bytes().endswith(b',7\n')


def test_localization_maps_are_accepted(store):
    api = client(store, lambda r: httpx.Response(200, json={'items': []}))
    req = {'operation': 'youtube.videos.update', 'params': {'part': ['localizations']},
           'body': {'id': VIDEO, 'localizations': {'es': {'title': 'Español', 'description': 'Texto'}}}}
    assert api.plan(req, CHANNEL)['request']['body']['localizations']['es']['title'] == 'Español'


def test_definitive_rejection_allows_new_plan(store):
    api = client(store, lambda r: httpx.Response(400, json={}) if r.method == 'PUT' else httpx.Response(200, json={'items': []}))
    plan = api.plan(update(), CHANNEL)
    with pytest.raises(YouTubeError, match='HTTP 400'):
        api.apply(plan['sha256'], CHANNEL)
    assert store.read('receipt.json')['status'] == 'failed'
    assert api.plan(update(), CHANNEL)['sha256'] != plan['sha256']


def test_explicit_resolution_records_evidence_without_mutation(store):
    api = client(store, lambda r: pytest.fail('unexpected call'))
    store.write('receipt.json', {'sha256': 'a'*64, 'channel_id': CHANNEL, 'status': 'uncertain'})
    result = api.resolve('a'*64, CHANNEL, 'not_applied', 'Remote catalog checked at 14:20; no new resource exists.')
    assert result['status'] == 'resolved'
    assert result['resolved_outcome'] == 'not_applied'


@pytest.mark.parametrize('action', ['update', 'delete'])
def test_caption_mutations_without_video_context_declare_snapshot_unsupported(store, action):
    api = client(store, lambda r: httpx.Response(204) if r.method == 'DELETE' else httpx.Response(200, json={'id': 'caption1'}))
    req = {'operation': 'youtube.captions.'+action, 'params': {'id': 'caption1'} if action == 'delete' else {'part': ['snippet']}}
    if action == 'update':
        req['body'] = {'id': 'caption1', 'snippet': {'isDraft': False}}
    plan = api.plan(req, CHANNEL)
    assert plan['before'] is None
    assert api.apply(plan['sha256'], CHANNEL)['status'] == 'succeeded'


def test_discovery_streaming_exception_is_explicit(store):
    api = YouTubeManagement(store, client=httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail('sent request'))))
    with pytest.raises(YouTubeError, match='streaming RPC'):
        api.query({'operation': 'youtube.youtube.v3.liveChat.messages.stream'}, CHANNEL)


def test_receipts_survive_subsequent_operations_and_block_old_plan_replay(store):
    api = client(store, lambda r: httpx.Response(200, json={'id': 'playlist-new'}))
    req = {'operation': 'youtube.playlists.insert', 'params': {'part': ['snippet']}, 'body': {'snippet': {'title': 'A'}}}
    plan = api.plan(req, CHANNEL)
    api.apply(plan['sha256'], CHANNEL)
    req['body']['snippet']['title'] = 'B'
    other = api.plan(req, CHANNEL)
    api.apply(other['sha256'], CHANNEL)
    assert store.read('receipt-'+plan['sha256']+'.json')['status'] == 'succeeded'
    store.write('operation.json', plan)
    with pytest.raises(YouTubeError, match='ya enviada'):
        api.apply(plan['sha256'], CHANNEL)
