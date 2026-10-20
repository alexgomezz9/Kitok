"""Offline CLI checks for long-form dry-run and studio exclusion."""
import json
from types import SimpleNamespace

import pytest

from test_studio_api import studio
from test_simple_studio import configured, BODY
from kitok.longform_studio import runner
from kitok.locks import generation_lock


def test_longform_cli_dry_run_has_no_writes_or_generation(studio, monkeypatch, capsys):
    client, service = configured(studio, monkeypatch)
    row = client.post('/api/longform', json=BODY).json()
    r = runner()
    loader = r.load_longform_config
    monkeypatch.setattr(r, 'Settings', lambda: service.s)
    monkeypatch.setattr(r, 'load_longform_config', lambda path: loader(path, project_root=service.root))
    def forbidden(*args, **kwargs):
        pytest.fail('Dry-run must not acquire a lock or submit a task')
    monkeypatch.setattr(r, 'generation_lock', forbidden)
    monkeypatch.setattr(r, 'run_longform', forbidden)
    before = {p: p.read_bytes() for p in service.root.rglob('*') if p.is_file()}
    assert r.main([row['config_path'], '--dry-run']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['dry_run'] is True and result['checks']['ffmpeg'] is True
    assert result['renderer'] == 'native'
    assert result['checks']['fish_configured'] is True and result['checks']['pexels_configured'] is True
    after = {p: p.read_bytes() for p in service.root.rglob('*') if p.is_file()}
    assert after == before


def test_longform_cli_respects_studio_execution_lock(studio, monkeypatch):
    client, service = configured(studio, monkeypatch)
    row = client.post('/api/longform', json=BODY).json()
    r = runner()
    loader = r.load_longform_config
    monkeypatch.setattr(r, 'Settings', lambda: service.s)
    monkeypatch.setattr(r, 'load_longform_config', lambda path: loader(path, project_root=service.root))
    with generation_lock(service.s, f"longform-{row['id']}"):
        assert r.main([row['config_path']]) == 1
    assert service.detail(row['id'])['status'] == 'draft'


def test_parser_announces_native_default_and_mpt_recovery_only():
    r = runner()
    assert r._parser().parse_args(['config.json']).renderer == 'native'
    help_text = r._parser().format_help()
    assert 'Default: native' in help_text and '--resume TASK_ID' in help_text


@pytest.mark.parametrize('options', [
    ['--renderer', 'mpt'], ['--renderer', 'mpt', '--dry-run'],
    ['--renderer', 'mpt', '--start-over'], ['--renderer', 'mpt', '--resume', ''],
    ['--resume', 'historical-task'], ['--resume', 'historical-task', '--dry-run'],
])
def test_cli_rejects_new_mpt_and_native_resume_before_loading_or_side_effects(monkeypatch, options, capsys):
    r = runner()
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid renderer operation must fail before loading config, settings or providers')
    monkeypatch.setattr(r, 'load_longform_config', forbidden)
    monkeypatch.setattr(r, 'Settings', forbidden)
    monkeypatch.setattr(r, 'run_longform', forbidden)
    assert r.main(['unused.json', *options]) == 1
    assert 'historical' in capsys.readouterr().err


def test_cli_default_dispatches_native_and_never_constructs_mpt(studio, monkeypatch):
    client, service = configured(studio, monkeypatch)
    row = client.post('/api/longform', json=BODY).json()
    r = runner()
    loader = r.load_longform_config
    monkeypatch.setattr(r, 'Settings', lambda: service.s)
    monkeypatch.setattr(r, 'load_longform_config', lambda path: loader(path, project_root=service.root))
    monkeypatch.setattr(r, 'longform_output_path', lambda cid: service.output_path(cid))
    monkeypatch.setattr(r, 'run_longform', lambda *a, **kw: pytest.fail('Native must not use MPT'))
    calls, closed = [], []
    class Provider:
        def __init__(self, *args, **kwargs): pass
        def close(self): closed.append(True)
    class Renderer:
        def __init__(self, *args, **kwargs): pass
        def render(self, definition, *, start_over=False):
            calls.append((definition.item.id, start_over))
            return SimpleNamespace(output=service.output_path(definition.item.id))
    monkeypatch.setattr('kitok.logging_setup.configure_logging', lambda *args: None)
    monkeypatch.setattr('kitok.providers.pexels.PexelsProvider', Provider)
    monkeypatch.setattr('kitok.media.ffmpeg.choose_encoder', lambda *a, **kw: object())
    monkeypatch.setattr('kitok.media.ffmpeg.FFmpegNativeEngine', lambda **kw: object())
    monkeypatch.setattr('kitok.rendering.native.NativeLongformRenderer', Renderer)
    assert r.main([row['config_path']]) == 0
    assert calls == [(row['id'], False)] and closed == [True]


def test_cli_historical_mpt_recovery_polls_downloads_and_never_submits(studio, monkeypatch):
    from kitok.models import MPTTask
    client, service = configured(studio, monkeypatch)
    row = client.post('/api/longform', json=BODY).json()
    r = runner()
    loader, original_run = r.load_longform_config, r.run_longform
    monkeypatch.setattr(r, 'Settings', lambda: service.s)
    monkeypatch.setattr(r, 'load_longform_config', lambda path: loader(path, project_root=service.root))
    calls = []
    class Client:
        def __init__(self, *a, **kw): pass
        def submit_video(self, *a, **kw): pytest.fail('Historical recovery must never submit a task')
        def get_task(self, tid):
            calls.append(tid)
            return MPTTask(task_id=tid, state=r.TASK_STATE_COMPLETE, progress=100, videos=['/historical.mp4'])
        def download_artifact(self, artifact, destination):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b'historical-video')
        def close(self): calls.append('closed')
    def recover(definition, preset, **kwargs):
        assert kwargs['resume_task_id'] == 'known-task' and kwargs['start_over'] is False
        return original_run(definition, preset, **kwargs, project_root=service.root, client_factory=Client,
                            audio_processor=lambda source, definition, settings: source)
    monkeypatch.setattr(r, 'run_longform', recover)
    assert r.main([row['config_path'], '--renderer', 'mpt', '--resume', 'known-task']) == 0
    assert calls == ['known-task', 'closed']
    assert service.output_path(row['id']).read_bytes() == b'historical-video'


@pytest.mark.parametrize('options', [[], ['--renderer', 'native'], ['--start-over']])
@pytest.mark.parametrize('marker_bytes', [b'{"task_id":"pending-task","id":"saved"}', b'corrupt historical marker'])
def test_native_cli_blocks_pending_mpt_under_lock_and_preserves_marker(studio, monkeypatch, capsys, options, marker_bytes):
    from contextlib import contextmanager
    client, service = configured(studio, monkeypatch)
    row = client.post('/api/longform', json=BODY).json()
    r = runner()
    loader = r.load_longform_config
    monkeypatch.setattr(r, 'Settings', lambda: service.s)
    monkeypatch.setattr(r, 'load_longform_config', lambda path: loader(path, project_root=service.root))
    task_path = r.longform_task_path(row['id'], project_root=service.root)
    task_path.parent.mkdir(parents=True, exist_ok=True)
    held = []
    @contextmanager
    def locked(settings, cid):
        assert cid == f"longform-{row['id']}"
        held.append(True)
        # Simulate a marker appearing during lock acquisition to prove the check is inside it.
        task_path.write_bytes(marker_bytes)
        try:
            yield
        finally:
            held.pop()
    original_task_path = r.longform_task_path
    def guarded_path(*args, **kwargs):
        assert held, 'Historical task checks must run while holding the generation lock'
        return original_task_path(*args, **kwargs)
    def forbidden(*args, **kwargs):
        pytest.fail('Pending historical MPT task must block all new providers and renderers')
    monkeypatch.setattr(r, 'generation_lock', locked)
    monkeypatch.setattr(r, 'longform_task_path', guarded_path)
    monkeypatch.setattr('kitok.providers.pexels.PexelsProvider', forbidden)
    monkeypatch.setattr('kitok.rendering.native.FishVoiceClient', forbidden)
    monkeypatch.setattr('kitok.rendering.native.NativeLongformRenderer', forbidden)
    assert r.main([row['config_path'], *options]) == 1
    assert task_path.read_bytes() == marker_bytes
    assert not held
    message = capsys.readouterr().err
    assert '--renderer mpt --resume' in message
    assert ('pending-task' if marker_bytes.startswith(b'{') else 'TASK_ID') in message


def test_cli_dry_run_rejects_documentary_legacy_music_before_settings_or_providers(studio, monkeypatch, capsys):
    client, service = configured(studio, monkeypatch)
    row = client.post('/api/longform', json=BODY).json()
    config = service.folder / f"{row['id']}.json"
    data = json.loads(config.read_text())
    data.update(mounting_style='documentary', music_enabled=True)
    config.write_text(json.dumps(data))
    r = runner()
    loader = r.load_longform_config
    monkeypatch.setattr(r, 'load_longform_config', lambda path: loader(path, project_root=service.root))
    monkeypatch.setattr(r, 'Settings', lambda: pytest.fail('Invalid mounting/music config must fail before providers or settings'))
    assert r.main([str(config), '--dry-run']) == 1
    assert 'explicit music_mode off, auto or manual' in capsys.readouterr().err


@pytest.mark.parametrize('mode', ['off', 'auto', 'manual'])
def test_documentary_accepts_explicit_music_modes_in_cli_config(studio, mode):
    client, app, settings = studio
    row = client.post('/api/longform', json=BODY).json()
    config = app.s.data_root / 'content' / 'longform' / 'studio' / f"{row['id']}.json"
    data = json.loads(config.read_text())
    data.update(mounting_style='documentary', music_mode=mode,
                music_track='long_note_two' if mode == 'manual' else None)
    config.write_text(json.dumps(data))
    definition = runner().load_longform_config(config, project_root=settings.data_root)
    assert definition.music_mode == mode and definition.mounting_style == 'documentary'


@pytest.mark.parametrize('options', [
    {'mounting_style': 'documentary', 'music_mode': 'off'},
    {'music_mode': 'auto'}, {'music_mode': 'manual', 'music_track': 'long_note_two'},
    {'music_mode': 'off'},
])
def test_mpt_recovery_rejects_new_native_options_before_settings_or_download(studio, monkeypatch, capsys, options):
    client, app, settings = studio
    row = client.post('/api/longform', json=BODY).json()
    config = settings.data_root / 'content' / 'longform' / 'studio' / f"{row['id']}.json"
    data = json.loads(config.read_text())
    data.update(options)
    config.write_text(json.dumps(data))
    r = runner()
    loader = r.load_longform_config
    monkeypatch.setattr(r, 'load_longform_config', lambda path: loader(path, project_root=settings.data_root))
    monkeypatch.setattr(r, 'Settings', lambda: pytest.fail('New Native options must fail before any MPT work'))
    assert r.main([str(config), '--renderer', 'mpt', '--resume', 'historical-task']) == 1
    assert 'Native-only' in capsys.readouterr().err
