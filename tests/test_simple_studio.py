"""Offline regression tests for the guided studio and separate long-form jobs."""
import json
from pathlib import Path
import threading
import time

import pytest

from test_audio_library import audio_library
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


def test_failed_audio_mix_exposes_measurements_and_recovery_needs_confirmed_inputs(studio, monkeypatch):
    from kitok.audio_library import AudioLibraryError
    client, service = configured(studio, monkeypatch)
    def fail(*args):
        raise AudioLibraryError('Audio validation failed: duration=654.599000s expected=654.733000s delta=-0.134000s; measured LUFS=-15.99, LRA=3.5, true_peak_dbtp=-1.8')
    monkeypatch.setattr(service, '_render', fail)
    cid = client.post('/api/longform', json=BODY).json()['id']
    assert client.post(f'/api/longform/{cid}/jobs').status_code == 202
    result = wait(service, cid)
    assert 'duration=654.599000s' in result['error'] and 'LUFS=-15.99' in result['error']
    assert client.get(f'/api/longform/{cid}/recovery').status_code == 422
    assert client.post(f'/api/longform/{cid}/recovery', json={}).status_code == 422
    assert client.post(f'/api/longform/{cid}/recovery', json={'narration_sha256':'a'*64,'audit_fingerprint':'b'*64}).status_code == 422
    assert service._read(cid)['status'] == 'failed'


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


def test_short_preview_no_queue_write_and_reports_native(studio):
    client, _, settings = studio
    before = settings.queue_path.read_bytes()
    response = client.post('/api/content-preview', json=BODY | {'music_enabled': False})
    assert response.status_code == 422  # extra options belong to long-form only
    short = {k: v for k, v in BODY.items() if k != 'music_enabled'}
    response = client.post('/api/content-preview', json=short)
    assert response.status_code == 200, response.text
    assert response.json()['uses_mpt'] is False
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


@pytest.mark.parametrize('route', ['/api/longform-preview', '/api/longform'])
def test_mpt_new_preview_and_draft_are_rejected(studio, route):
    client, _, _ = studio
    response = client.post(route, json=BODY | {'renderer': 'mpt', 'narrator_voice': 'es-ES-AlvaroNeural'})
    assert response.status_code == 422
    assert 'histórica' in response.json()['detail']
    assert client.get('/api/longform').json() == []


def test_longform_saved_definition_is_visible_after_reload(studio):
    client, _, _ = studio
    row = client.post('/api/longform', json=BODY).json()
    saved = client.get(f"/api/longform/{row['id']}").json()
    assert saved['script'] == BODY['script'] and saved['keywords'] == BODY['keywords']
    assert saved['narrator_voice'].startswith('fish_audio:')


def test_disabled_publishing_error_is_actionable(studio):
    from kitok.application import user_error
    assert 'PUBLISH_ENABLED=true' in user_error('Publishing disabled: set PUBLISH_ENABLED=true in .env')


def test_historical_mpt_draft_stays_readable_but_cannot_start(studio, monkeypatch):
    client, service = configured(studio, monkeypatch)
    row = client.post('/api/longform', json=BODY).json()
    record = service._read(row['id'])
    record['renderer'] = record['request']['renderer'] = 'mpt'
    record['request']['narrator_voice'] = 'es-ES-AlvaroNeural'
    service._write(record)
    before = (service.records / f"{row['id']}.json").read_bytes()
    historical = client.get(f"/api/longform/{row['id']}").json()
    assert historical['renderer'] == 'mpt' and historical['narrator_voice'] == 'es-ES-AlvaroNeural'
    assert client.get('/api/longform').json()[0]['renderer'] == 'mpt'
    response = client.post(f"/api/longform/{row['id']}/jobs")
    assert response.status_code == 422 and 'histórica' in response.json()['detail']
    assert (service.records / f"{row['id']}.json").read_bytes() == before
    monkeypatch.setattr(runner(), 'run_longform', lambda *a, **kw: pytest.fail('Must not submit MPT'))
    with pytest.raises(ValueError, match='histórica'):
        service._render(record, None, lambda message: None)


def test_metadata_new_classic_format_uses_fish(studio):
    client, _, _ = studio
    metadata = client.get('/api/metadata').json()
    classic = next(row for row in metadata['formats'] if row['id'] == 'classic')
    assert classic['voice_profile'] == 'rick_es'
    assert next(row for row in metadata['voices'] if row['id'] == classic['voice_profile'])['provider'] == 'fish'


@pytest.mark.parametrize('mode,track', [('off', None), ('auto', None), ('manual', 'long_note_two')])
def test_longform_music_and_mounting_config_are_saved_without_generation(studio, monkeypatch, mode, track):
    client, app, settings = studio
    service = client.app.state.longform
    monkeypatch.setattr(service, 'music_options', lambda: [
        {'id': 'long_note_two', 'title': 'Long Note Two', 'moods': ['investigation']},
        {'id': 'darkest_child', 'title': 'Darkest Child', 'moods': ['investigation']},
    ])
    monkeypatch.setattr(service, 'music_narrative_options', lambda script: {'eligible': True})
    monkeypatch.setattr(service, '_render', lambda *args: pytest.fail('Saving must not generate'))
    body = {**BODY, 'music_mode': mode, 'music_track': track, 'mounting_style': 'documentary'}
    before = settings.queue_path.read_bytes()
    assert client.post('/api/longform-preview', json=body).status_code == 200
    response = client.post('/api/longform', json=body)
    assert response.status_code == 201, response.text
    row = response.json()
    definition = runner().load_longform_config(row['config_path'], project_root=settings.data_root)
    assert definition.music_mode == mode and definition.music_track == track
    assert definition.mounting_style == 'documentary'
    assert definition.voice_name == runner().DEFAULT_NARRATOR_VOICE
    assert row['status'] == 'draft' and row['music_mode'] == mode
    assert settings.queue_path.read_bytes() == before


def test_music_preview_is_read_only_and_missing_cache_blocks_start(studio):
    client, app, settings = studio
    before = {p.relative_to(settings.data_root): p.read_bytes() for p in settings.data_root.rglob('*') if p.is_file()}
    assert client.get('/api/longform-options').json() == {'music_tracks': []}
    response = client.post('/api/longform-preview', json={**BODY, 'music_mode': 'auto'})
    assert response.status_code == 200 and response.json()['can_generate'] is False
    after = {p.relative_to(settings.data_root): p.read_bytes() for p in settings.data_root.rglob('*') if p.is_file()}
    assert after == before


@pytest.mark.parametrize('changes', [
    {'music_mode': 'manual'}, {'music_mode': 'manual', 'music_track': '../secret'},
    {'music_mode': 'off', 'music_track': 'long_note_two'}, {'mounting_style': 'arbitrary'},
])
def test_invalid_music_mounting_choices_rejected_before_save(studio, changes):
    client, _, _ = studio
    assert client.post('/api/longform', json={**BODY, **changes}).status_code == 422
    assert client.get('/api/longform').json() == []


def test_motion_gallery_api_serves_only_review_files_without_render(studio):
    client, app, settings = studio
    folder = settings.data_root / 'outputs' / 'motion-gallery' / 'generic'
    folder.mkdir(parents=True)
    (folder / 'item.json').write_text(json.dumps({'id': 'generic', 'title': 'Sample', 'family': 'investigation', 'duration': 18, 'kind': 'sample'}))
    (folder / 'preview.mp4').write_bytes(b'local preview')
    (folder / 'CREDITS.md').write_text('Local credits')
    response = client.get('/api/motion')
    assert response.status_code == 200
    row = response.json()[0]
    assert row['id'] == 'generic'
    assert client.get(row['files']['preview.mp4']).content == b'local preview'
    partial = client.get(row['files']['preview.mp4'], headers={'Range': 'bytes=0-4'})
    assert partial.status_code == 206 and partial.content == b'local'
    assert partial.headers['content-type'] == 'video/mp4'
    assert partial.headers['content-range'] == 'bytes 0-4/13'
    assert client.get(row['files']['CREDITS.md']).text == 'Local credits'
    assert client.get('/api/motion/generic/files/item.json').status_code == 422
    assert client.get('/api/motion/not_found/files/preview.mp4').status_code == 422
    assert client.get('/api/longform').json() == []


def test_voice_library_preferences_and_samples_are_explicit_and_local(studio):
    import hashlib
    client, app, settings = studio
    root = settings.data_root
    catalog = root / 'presets' / 'voice_sources.json'
    catalog.parent.mkdir(parents=True, exist_ok=True)
    sample = root / 'cache' / 'voice-library' / 'baseline.mp3'
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_bytes(b'existing narration preview')
    catalog.write_text(json.dumps({'version': 1, 'voices': [{
        'id': 'baseline', 'reference_id': 'e686ae649ee44f219a108aacba206c1a',
        'display_name': 'Loose Thread', 'selectable': True, 'api_licensed': False,
        'languages': ['en'], 'tags': ['documentary'],
        'samples': [{'path': 'cache/voice-library/baseline.mp3',
                     'sha256': hashlib.sha256(sample.read_bytes()).hexdigest(), 'kind': 'local'}],
    }]}))
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    rows = client.get('/api/voices-library').json()
    assert rows[0]['favorite'] is False and rows[0]['assigned_channels'] == ['loose_thread']
    assert client.get(rows[0]['samples'][0]['url']).content == sample.read_bytes()
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()} == before
    response = client.post('/api/voices-library/baseline/favorite', json={'enabled': True})
    assert response.status_code == 200 and response.json()[0]['favorite'] is True
    response = client.post('/api/voices-library/assign', json={'channel': 'another_channel', 'voice_id': 'baseline'})
    assert response.status_code == 200 and 'another_channel' in response.json()[0]['assigned_channels']
    assert client.get('/api/voices-library/unknown/samples/0').status_code == 422
    assert client.post('/api/voices-library/assign', json={'channel': '../bad', 'voice_id': 'baseline'}).status_code == 422
    assert client.get('/api/longform').json() == []
    sample.write_bytes(b'changed')
    assert client.get('/api/voices-library/baseline/samples/0').status_code == 422


def test_longform_music_credits_are_downloadable_only_after_success(studio):
    client, app, settings = studio
    service = client.app.state.longform
    row = client.post('/api/longform', json=BODY).json()
    cid = row['id']
    assert client.get(f'/api/longform/{cid}/credits').status_code == 422
    output = service.output_path(cid)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b'finished movie')
    output.with_suffix('.credits.md').write_text('Music by author, CC BY 4.0. Mixed and ducked.')
    record = service._read(cid)
    record['status'] = 'succeeded'
    service._write(record)
    saved = client.get(f'/api/longform/{cid}').json()
    assert saved['credits_url'] == f'/api/longform/{cid}/credits'
    assert 'CC BY 4.0' in client.get(saved['credits_url']).text


def test_auto_music_preflight_uses_narrative_eligibility(studio, monkeypatch):
    client, service = configured(studio, monkeypatch)
    def options(script):
        assert script == BODY['script']
        return {'eligible': True, 'opening_mood': 'investigation', 'closing_mood': 'reflective'}
    monkeypatch.setattr(service, 'music_narrative_options', options)
    result = client.post('/api/longform-preview', json={**BODY, 'music_mode': 'auto'})
    assert result.status_code == 200 and result.json()['can_generate'] is True
    monkeypatch.setattr(service, 'music_narrative_options', lambda script: {'eligible': False})
    result = client.post('/api/longform-preview', json={**BODY, 'music_mode': 'auto'})
    assert result.status_code == 200 and result.json()['can_generate'] is False



def test_music_preview_http_requires_verified_cache_and_never_downloads(studio, audio_library):
    import shutil
    client, app, settings = studio
    library, catalog, audio, requests = audio_library
    library.fetch('long_note_two')  # MockTransport fixture only, never external network.
    folder = settings.data_root / 'presets'
    folder.mkdir(exist_ok=True)
    (folder / 'music_sources.json').write_text(json.dumps(catalog))
    cache = settings.data_root / 'cache' / 'audio-library'
    shutil.copytree(library.cache, cache)
    before = {p: p.read_bytes() for p in settings.data_root.rglob('*') if p.is_file()}
    calls = len(requests)
    tracks = client.get('/api/longform-options').json()['music_tracks']
    assert len(tracks) == 1 and tracks[0]['id'] == 'long_note_two'
    response = client.get(tracks[0]['preview_url'])
    assert response.status_code == 200 and response.content == audio['long_note_two']
    assert response.headers['content-type'] == 'audio/mpeg'
    assert client.get('/api/longform/music/not_a_track/preview').status_code == 422
    assert client.get('/api/longform/music/darkest_child/preview').status_code == 422
    assert len(requests) == calls
    assert {p: p.read_bytes() for p in settings.data_root.rglob('*') if p.is_file()} == before
    (cache / 'long_note_two' / 'music.mp3').write_bytes(b'changed music')
    assert client.get('/api/longform/music/long_note_two/preview').status_code == 422
    assert len(requests) == calls
