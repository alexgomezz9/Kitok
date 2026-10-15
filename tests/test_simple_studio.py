"""Offline regression tests for the guided studio and separate long-form jobs."""
import json
from pathlib import Path
import threading
import time

import pytest

from test_studio_api import studio  # Reuse isolated ASGI transport/workspace.
from kitok.locks import generation_lock
from kitok.longform_studio import LongformStudio, runner

BODY = {'subject': 'Un documental', 'script': 'Esta es una narración completa para nuestro documental.',
        'keywords': ['city', 'night'], 'music_enabled': False}


@pytest.fixture(autouse=True)
def direct_file_io(monkeypatch):
    # Same sandbox limitation as LocalClient's endpoint thread workaround.
    async def direct(func, *args, **kwargs):
        return func(*args)
    monkeypatch.setattr('anyio.to_thread.run_sync', direct)


def configured(studio, monkeypatch):
    client, app, settings = studio
    app.s = settings.model_copy(update={'fish_api_key': type(settings.fish_api_key)('test'),
                                       'pexels_api_key': type(settings.pexels_api_key)('test')})
    service = client.app.state.longform
    service.s = app.s
    monkeypatch.setattr('kitok.longform_studio.shutil.which', lambda name: '/usr/bin/' + name)
    return client, service


def wait(service, cid):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        row = service.detail(cid)
        if row['status'] not in {'queued', 'running'}:
            return row
        time.sleep(.01)
    raise AssertionError('Job did not finish')


def test_longform_preview_is_read_only_and_does_not_need_mpt(studio):
    client, app, settings = studio
    before = {p.relative_to(settings.data_root): p.read_bytes() for p in settings.data_root.rglob('*') if p.is_file()}
    response = client.post('/api/longform-preview', json=BODY)
    assert response.status_code == 200, response.text
    assert response.json()['renderer'] == 'native'
    assert response.json()['can_generate'] is False
    assert not any('MPT' in check['label'] for check in response.json()['checks'])
    after = {p.relative_to(settings.data_root): p.read_bytes() for p in settings.data_root.rglob('*') if p.is_file()}
    assert after == before


@pytest.mark.parametrize('changes', [
    {'script': 'Este guion se queda incompleto sin punto'},
    {'keywords': ['   ']}, {'subject': ' '}, {'script_file': '/etc/passwd'},
    {'renderer': 'imaginary'}, {'narrator_voice': 'edge:unsupported'},
])
def test_longform_rejects_invalid_or_unsafe_input(studio, changes):
    client, _, _ = studio
    assert client.post('/api/longform', json={**BODY, **changes}).status_code == 422
    assert client.get('/api/longform').json() == []


def test_save_draft_cli_compatibility_and_short_state_unchanged(studio):
    client, app, settings = studio
    queue_before = settings.queue_path.read_bytes()
    state_before = settings.state_path.read_bytes() if settings.state_path.exists() else None
    row = client.post('/api/longform', json=BODY).json()
    assert row['status'] == 'draft' and row['preview_url'] is None
    definition = runner().load_longform_config(row['config_path'], project_root=settings.data_root)
    assert definition.item.script == BODY['script']
    assert definition.item.keywords == BODY['keywords']
    assert definition.music_enabled is False
    assert settings.queue_path.read_bytes() == queue_before
    assert (settings.state_path.read_bytes() if settings.state_path.exists() else None) == state_before
    assert client.get(row.get('download_url') or f"/api/longform/{row['id']}/download").status_code == 422


def test_missing_prerequisites_prevent_paid_job(studio, monkeypatch):
    client, _, _ = studio
    service = client.app.state.longform
    monkeypatch.setattr(service, '_render', lambda *a: pytest.fail('Must not generate'))
    row = client.post('/api/longform', json=BODY).json()
    assert client.post(f"/api/longform/{row['id']}/jobs").status_code == 422
    assert service.detail(row['id'])['status'] == 'draft'


def test_double_start_renders_once_and_serves_only_success(studio, monkeypatch):
    client, service = configured(studio, monkeypatch)
    started, release = threading.Event(), threading.Event()
    calls = []
    def render(record, definition, stage):
        calls.append(record['id'])
        started.set()
        assert release.wait(3)
        service.output_path(record['id']).parent.mkdir(parents=True, exist_ok=True)
        service.output_path(record['id']).write_bytes(b'verified-by-renderer')
    monkeypatch.setattr(service, '_render', render)
    row = client.post('/api/longform', json=BODY).json()
    cid = row['id']
    try:
        assert client.post(f'/api/longform/{cid}/jobs').status_code == 202
        assert started.wait(3)
        assert client.post(f'/api/longform/{cid}/jobs').status_code == 409
        assert client.get(f'/api/longform/{cid}/download').status_code == 422
        # A second service must not mark a worker owning the flock interrupted.
        assert LongformStudio(service.application).detail(cid)['status'] == 'running'
    finally:
        release.set()
    result = wait(service, cid)
    assert calls == [cid] and result['status'] == 'succeeded'
    assert client.get(result['download_url']).content == b'verified-by-renderer'
    assert client.post(f'/api/longform/{cid}/jobs').status_code == 422


def test_failed_and_interrupted_jobs_never_restart(studio, monkeypatch):
    client, service = configured(studio, monkeypatch)
    def fail(*args):
        raise RuntimeError('simulated Fish timeout')
    monkeypatch.setattr(service, '_render', fail)
    row = client.post('/api/longform', json=BODY).json()
    cid = row['id']
    assert client.post(f'/api/longform/{cid}/jobs').status_code == 202
    assert wait(service, cid)['status'] == 'failed'
    assert client.post(f'/api/longform/{cid}/jobs').status_code == 422
    record = service._read(cid)
    record['status'] = 'running'
    service._write(record)
    restarted = LongformStudio(service.application)
    assert restarted.detail(cid)['status'] == 'interrupted'
    assert client.get(f'/api/longform/{cid}/download').status_code == 422


def test_start_respects_cli_lock_and_existing_output(studio, monkeypatch):
    client, service = configured(studio, monkeypatch)
    row = client.post('/api/longform', json=BODY).json()
    cid = row['id']
    with generation_lock(service.s, f'longform-{cid}'):
        assert client.post(f'/api/longform/{cid}/jobs').status_code == 409
    output = service.output_path(cid)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b'preserve-existing-video')
    assert client.post(f'/api/longform/{cid}/jobs').status_code == 422
    assert output.read_bytes() == b'preserve-existing-video'


@pytest.mark.parametrize('cid', ['lf_bad', 'other', 'lf_' + '_' * 32, 'lf_' + '+' + 'a' * 31])
def test_longform_ids_cannot_address_arbitrary_paths(studio, cid):
    client, _, _ = studio
    assert client.get(f'/api/longform/{cid}/download').status_code == 422


def test_short_preview_no_queue_write_and_reports_mpt(studio):
    client, _, settings = studio
    before = settings.queue_path.read_bytes()
    response = client.post('/api/content-preview', json=BODY | {'music_enabled': False})
    assert response.status_code == 422  # extra options belong to long-form only
    short = {k: v for k, v in BODY.items() if k != 'music_enabled'}
    response = client.post('/api/content-preview', json=short)
    assert response.status_code == 200, response.text
    assert response.json()['uses_mpt'] is True
    assert settings.queue_path.read_bytes() == before


def test_native_dispatch_never_constructs_mpt(studio, monkeypatch):
    client, service = configured(studio, monkeypatch)
    row = client.post('/api/longform', json=BODY).json()
    def forbidden(*args, **kwargs):
        pytest.fail('Native must never submit MPT')
    monkeypatch.setattr(runner(), 'run_longform', forbidden)
    closed = []
    class Provider:
        def __init__(self, *args, **kwargs): pass
        def close(self): closed.append(True)
    class Renderer:
        def __init__(self, *args, output_path, **kwargs): self.output = output_path
        def render(self, definition):
            assert definition.item.script == BODY['script']
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self.output.write_bytes(b'rendered-native')
    monkeypatch.setattr('kitok.providers.pexels.PexelsProvider', Provider)
    monkeypatch.setattr('kitok.media.ffmpeg.choose_encoder', lambda *a, **kw: object())
    monkeypatch.setattr('kitok.media.ffmpeg.FFmpegNativeEngine', lambda **kw: object())
    monkeypatch.setattr('kitok.rendering.native.NativeLongformRenderer', Renderer)
    assert client.post(f"/api/longform/{row['id']}/jobs").status_code == 202
    assert wait(service, row['id'])['status'] == 'succeeded'
    assert closed == [True]


def test_outside_edits_cannot_change_reviewed_job(studio, monkeypatch):
    client, service = configured(studio, monkeypatch)
    row = client.post('/api/longform', json=BODY).json()
    Path(row['script_path']).write_text('Esta narración es diferente de la que se revisó.')
    assert client.post(f"/api/longform/{row['id']}/jobs").status_code == 422
    assert service.detail(row['id'])['status'] == 'draft'



@pytest.mark.parametrize('hidden', [{'voice_rate': 2.0}, {'audio_loudness_target': -30}, {'script_file': '/etc/passwd'}])
def test_hidden_config_edits_are_rejected_before_loading(studio, monkeypatch, hidden):
    client, service = configured(studio, monkeypatch)
    row = client.post('/api/longform', json=BODY).json()
    config = Path(row['config_path'])
    config.write_text(json.dumps(json.loads(config.read_text()) | hidden))
    assert client.post(f"/api/longform/{row['id']}/jobs").status_code == 422
    assert service.detail(row['id'])['status'] == 'draft'


def test_worker_keeps_lease_if_response_construction_fails(studio, monkeypatch):
    from kitok.locks import GenerationBusy
    client, service = configured(studio, monkeypatch)
    row = client.post('/api/longform', json=BODY).json()
    cid = row['id']
    started, release = threading.Event(), threading.Event()
    def render(*args):
        started.set()
        assert release.wait(3)
    def broken_response(*args):
        raise OSError('simulated response read error')
    monkeypatch.setattr(service, '_render', render)
    detail = service.detail
    monkeypatch.setattr(service, 'detail', broken_response)
    try:
        with pytest.raises(OSError):
            service.start(cid)
        assert started.wait(3)
        with pytest.raises(GenerationBusy):
            with generation_lock(service.s, f'longform-{cid}'):
                pytest.fail('Worker lost its lease')
    finally:
        release.set()
        monkeypatch.setattr(service, 'detail', detail)
    wait(service, cid)


def test_mpt_preview_allows_its_existing_edge_voice(studio):
    client, _, _ = studio
    response = client.post('/api/longform-preview', json=BODY | {'renderer': 'mpt', 'narrator_voice': 'es-ES-AlvaroNeural'})
    assert response.status_code == 200
    assert response.json()['renderer'] == 'mpt'


def test_longform_saved_definition_is_visible_after_reload(studio):
    client, _, _ = studio
    row = client.post('/api/longform', json=BODY).json()
    saved = client.get(f"/api/longform/{row['id']}").json()
    assert saved['script'] == BODY['script'] and saved['keywords'] == BODY['keywords']
    assert saved['narrator_voice'].startswith('fish_audio:')


def test_disabled_publishing_error_is_actionable(studio):
    from kitok.application import user_error
    assert 'PUBLISH_ENABLED=true' in user_error('Publishing disabled: set PUBLISH_ENABLED=true in .env')
