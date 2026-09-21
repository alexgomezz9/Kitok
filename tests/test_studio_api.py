import io
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading

import fastapi.routing
import httpx
from PIL import Image
import pytest

from kitok.api import create_app
from kitok.config import Settings
from kitok.models import ContentQueue
from kitok.state import StateStore
from kitok import profiles


class LocalClient:
    """ASGI client that avoids this sandbox's blocked AnyIO worker threads."""
    def __init__(self, app):
        self.app = app

    def request(self, method, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as client:
                return await client.request(method, path, **kwargs)
        return asyncio.run(send())

    def get(self, path, **kwargs): return self.request('GET', path, **kwargs)
    def post(self, path, **kwargs): return self.request('POST', path, **kwargs)
    def put(self, path, **kwargs): return self.request('PUT', path, **kwargs)
    def patch(self, path, **kwargs): return self.request('PATCH', path, **kwargs)
    def delete(self, path, **kwargs): return self.request('DELETE', path, **kwargs)


@pytest.fixture
def studio(tmp_path, monkeypatch):
    async def direct(func, *args, **kwargs):
        return func(*args, **kwargs)
    monkeypatch.setattr(fastapi.routing, 'run_in_threadpool', direct)
    catalog = tmp_path / 'profiles.json'
    catalog.write_text(profiles.CATALOG_PATH.read_text())
    settings = Settings(_env_file=None, data_root=tmp_path, ready_dir=tmp_path / 'phone',
                        character_root=tmp_path / 'characters', background_root=tmp_path / 'backgrounds')
    app = create_app(settings, catalog_path=catalog)
    try:
        yield LocalClient(app), app.state.application, settings
    finally:
        app.state.application.close()
        profiles.reload_catalog()


def create(client, **changes):
    body = {'subject': 'Un vídeo de prueba', 'script': 'Una narración suficientemente larga para un vídeo.', 'keywords': ['nature']}
    body.update(changes)
    response = client.post('/api/content', json=body)
    assert response.status_code == 201, response.text
    return response.json()['item']['id']


def ready(client, app, settings, **changes):
    cid = create(client, **changes)
    media = settings.local_ready_dir / f'{cid}.mp4'
    media.write_bytes(b'local-video')
    StateStore(settings.state_path).upsert(cid, status='ready', ready_path=str(media))
    return cid, media


def test_create_defaults_unscheduled_and_backend_validation(studio):
    client, app, settings = studio
    cid = create(client)
    row = client.get(f'/api/content/{cid}').json()
    assert row['scheduled_at'] is None and row['status'] == 'pending'
    assert ContentQueue.load(settings.queue_path).by_id()[cid].schedule_enabled is False
    assert client.post('/api/content', json={'subject': 'bad', 'script': 'short'}).status_code == 422
    assert client.post('/api/content', json={'subject': 'bad', 'script': 'a'*30, 'api_key': 'secret'}).status_code == 422
    assert client.post('/api/content', json={'id': cid, 'subject': 'duplicate', 'script': 'a'*30}).status_code in {409, 422}


def test_schedule_reschedule_unschedule_keeps_media_and_timezone(studio):
    client, app, settings = studio
    cid, media = ready(*studio)
    when = (datetime.now(timezone(timedelta(hours=2))) + timedelta(days=2)).replace(microsecond=0)
    response = client.put(f'/api/content/{cid}/schedule', json={'at': when.isoformat()})
    assert response.status_code == 200, response.text
    assert response.json()['scheduled_at'].endswith('+02:00')
    later = when + timedelta(days=1)
    assert client.put(f'/api/content/{cid}/schedule', json={'at': later.isoformat()}).status_code == 200
    assert client.put(f'/api/content/{cid}/schedule', json={'at': None}).json()['scheduled_at'] is None
    assert media.read_bytes() == b'local-video'
    assert StateStore(settings.state_path).get(cid)['status'] == 'ready'
    assert cid in ContentQueue.load(settings.queue_path).by_id()


def test_schedule_conflicts_only_shared_platforms_and_past_rejected(studio):
    client, app, settings = studio
    first, _ = ready(*studio, subject='first')
    second, _ = ready(*studio, subject='second')
    when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    assert client.put(f'/api/content/{first}/schedule', json={'at': when, 'platforms': ['tiktok']}).status_code == 200
    assert client.put(f'/api/content/{second}/schedule', json={'at': when, 'platforms': ['tiktok']}).status_code == 409
    assert client.put(f'/api/content/{second}/schedule', json={'at': when, 'platforms': ['youtube']}).status_code == 200
    assert client.put(f'/api/content/{second}/schedule', json={'at': '2000-01-01T12:00:00+00:00'}).status_code == 422
    assert client.put(f'/api/content/{second}/schedule', json={'at': '2035-01-01T12:00:00'}).status_code == 422


def test_local_calendar_time_uses_configured_zone(studio):
    client, _, _ = studio
    cid, _ = ready(*studio)
    response = client.put(f'/api/content/{cid}/schedule', json={'local_time': '2035-07-02T15:00'})
    assert response.status_code == 200
    assert response.json()['scheduled_at'] == '2035-07-02T15:00:00+02:00'


def test_queue_api_reorders_and_fills_without_publishing(studio):
    client, _, settings = studio
    first, first_media = ready(*studio, subject='first')
    second, second_media = ready(*studio, subject='second')
    assert client.post(f'/api/content/{first}/queue', json={'action': 'add'}).status_code == 200
    assert client.post(f'/api/content/{second}/queue', json={'action': 'add'}).status_code == 200
    assert client.post(f'/api/content/{second}/queue', json={'action': 'top'}).status_code == 200
    queue = client.get('/api/schedule').json()['queued']
    assert [row['item']['id'] for row in queue] == [second, first]
    preview = client.post('/api/schedule/fill', json={'confirm': False}).json()
    assert [row['id'] for row in preview['assignments']] == [second, first]
    assert client.get(f'/api/content/{first}').json()['schedule_status'] == 'queued'
    assert client.post('/api/schedule/fill', json={'confirm': True}).status_code == 200
    assert client.get(f'/api/content/{first}').json()['schedule_status'] == 'scheduled'
    before = client.get(f'/api/content/{second}').json()['scheduled_at']
    moved = client.post(f'/api/content/{first}/schedule-move', json={'direction': 'earlier'})
    assert moved.status_code == 200
    assert client.get(f'/api/content/{first}').json()['scheduled_at'] == before
    assert not StateStore(settings.state_path).get(first).get('publishing')
    assert first_media.exists() and second_media.exists()


def test_buffer_history_blocks_local_drift_and_published_is_not_draft(studio):
    client, app, settings = studio
    cid, media = ready(*studio)
    state = StateStore(settings.state_path)
    for platform in ('tiktok', 'instagram', 'youtube'):
        state.update_publishing(cid, 'buffer', platform, post_id='remote-'+platform, status='sent')
    before = settings.queue_path.read_bytes()
    row = client.get(f'/api/content/{cid}').json()
    assert row['generation_status'] == 'ready'
    assert row['schedule_status'] == 'published'
    assert client.put(f'/api/content/{cid}/schedule', json={'at': None}).status_code == 422
    assert client.delete(f'/api/content/{cid}?confirm=true').status_code == 422
    assert settings.queue_path.read_bytes() == before and media.exists()


def test_duplicate_generation_is_rejected_and_job_result_is_available(studio, monkeypatch):
    client, app, settings = studio
    cid = create(client)
    started, release = threading.Event(), threading.Event()
    calls = []
    def generate(settings, queue, state, client, preset, **kwargs):
        calls.append(kwargs)
        started.set()
        assert release.wait(5)
        media = settings.local_ready_dir / 'test.mp4'
        media.write_bytes(b'video')
        state.upsert(cid, status='ready', ready_path=str(media), validation={'duration': 7.0})
    monkeypatch.setattr('kitok.application.run_generation', generate)
    try:
        assert client.post(f'/api/content/{cid}/jobs', json={}).status_code == 202
        assert started.wait(5)
        assert client.post(f'/api/content/{cid}/jobs', json={}).status_code == 409
        assert client.patch(f'/api/content/{cid}', json={'subject':'changed'}).status_code == 409
    finally:
        release.set()
        app._executor.shutdown(wait=True)
    row = client.get(f'/api/content/{cid}').json()
    assert row['job']['status'] == 'succeeded' and row['preview_url']
    assert len(calls) == 1
    assert not StateStore(settings.state_path).get(cid).get('publishing')


def test_assets_upload_add_rename_delete_and_safe_paths(studio):
    client, app, settings = studio
    assert client.post('/api/assets/characters', json={'id':'summer','display_name':'Summer'}).status_code == 201
    im = Image.new('RGBA', (100,100), (0,0,0,0))
    im.paste((255,0,0,255),(25,20,60,80))
    buffer = io.BytesIO(); im.save(buffer, format='PNG')
    route = '/api/assets/characters/summer/poses'
    assert client.post(route, data={'name':'pose feliz'}, files={'file':('pose.png',buffer.getvalue(),'image/png')}).status_code == 201
    characters = {row['id']: row for row in client.get('/api/assets/characters').json()}
    assert characters['summer']['poses'][0]['name'] == 'pose feliz'
    assert client.post(route,data={'name':'bad'},files={'file':('bad.png',b'broken','image/png')}).status_code in {422,500}
    assert client.patch(route+'/pose feliz.png',json={'name':'otra'}).status_code == 200
    assert client.delete(route+'/otra.png').status_code == 422
    assert client.delete(route+'/otra.png?confirm=true').status_code == 200
    assert client.post('/api/assets/characters',json={'id':'../outside','display_name':'Bad'}).status_code == 422
    assert client.post('/api/assets/voices',json={'id':'summer_es','display_name':'Summer','provider':'fish','value':'test-ref','character':'summer'}).status_code == 201
    assert 'summer_es' in {v['id'] for v in client.get('/api/metadata').json()['voices']}


def test_settings_do_not_expose_or_accept_secrets(studio):
    client, _, settings = studio
    data = client.get('/api/settings').json()
    assert 'fish_api_key' not in data
    assert client.patch('/api/settings',json={'fish_api_key':'bad'}).status_code == 422
    assert client.patch('/api/settings',json={'character_reaction_probability':0.5}).status_code == 200
    assert client.patch('/api/settings',json={'default_posting_slots':['25:00']}).status_code == 422
    assert client.post('/api/content',headers={'Origin':'https://unknown.example'},json={}).status_code == 403


def test_unscheduled_items_never_enter_publishing_plan(studio):
    from kitok.publish_plan import generate_publish_plan
    from kitok.publisher import Publisher
    client, app, settings = studio
    cid, _ = ready(*studio)
    queue,state=app.load()
    _,path=generate_publish_plan(queue,state.all(),settings.local_ready_dir)
    assert json.loads(path.read_text()) == []
    plan=Publisher(settings,queue,state).plan()
    assert plan.rows == []
