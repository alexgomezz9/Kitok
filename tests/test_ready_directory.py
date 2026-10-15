"""An unavailable optional sync directory must not prevent local production."""
from pathlib import Path

import pytest

from kitok.config import Settings
from kitok.app_settings import configured, save_preferences


def settings_at(root, **changes):
    return Settings(_env_file=None, data_root=root, ready_dir=root / 'phone', **changes)


def test_permission_denied_delivery_falls_back_without_changing_config_file(tmp_path, monkeypatch, caplog):
    settings = settings_at(tmp_path)
    original = settings.ready_dir
    env = tmp_path / '.env'
    env.write_text('READY_DIR=/example/drive/ready\n')
    mkdir = Path.mkdir
    def denied(path, *args, **kwargs):
        if path == original:
            raise PermissionError('drive unavailable')
        return mkdir(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'mkdir', denied)
    settings.ensure_directories()
    assert settings.ready_dir == settings.local_ready_dir
    assert settings.local_ready_dir.is_dir() and settings.state_path.parent.is_dir()
    assert str(original) in settings.ready_directory_warning
    assert 'unidad externa' in caplog.text
    assert env.read_text() == 'READY_DIR=/example/drive/ready\n'
    # Repeated service initialization preserves the visible warning.
    settings.ensure_directories()
    assert settings.ready_directory_warning


def test_existing_file_as_delivery_target_is_optional(tmp_path):
    settings = settings_at(tmp_path)
    settings.ready_dir.write_text('keep this file')
    settings.ensure_directories()
    assert settings.ready_dir == settings.local_ready_dir
    assert (tmp_path / 'phone').read_text() == 'keep this file'


def test_healthy_delivery_remains_configured(tmp_path):
    settings = settings_at(tmp_path)
    settings.ensure_directories()
    assert settings.ready_dir == tmp_path / 'phone'
    assert settings.ready_dir.is_dir()
    assert settings.ready_directory_warning is None


def test_local_production_directory_failure_is_not_hidden(tmp_path, monkeypatch):
    settings = settings_at(tmp_path)
    mkdir = Path.mkdir
    def denied(path, *args, **kwargs):
        if path == settings.local_ready_dir:
            raise PermissionError('local disk read-only')
        return mkdir(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'mkdir', denied)
    with pytest.raises(PermissionError, match='local disk read-only'):
        settings.ensure_directories()
    assert settings.ready_directory_warning is None


def test_fallback_warning_survives_editable_preferences(tmp_path):
    settings = settings_at(tmp_path)
    settings.ready_dir.write_text('blocked')
    settings.ensure_directories()
    saved = save_preferences(settings, {'default_posting_slots': ['12:00']})
    assert saved.ready_dir == settings.local_ready_dir
    assert saved.ready_directory_warning == settings.ready_directory_warning
    assert configured(saved).ready_directory_warning == settings.ready_directory_warning


def test_api_opens_with_missing_delivery_and_exposes_fallback(tmp_path, monkeypatch):
    import fastapi.routing
    from kitok.api import create_app
    from test_studio_api import LocalClient
    async def direct(func, *args, **kwargs):
        return func(*args, **kwargs)
    monkeypatch.setattr(fastapi.routing, 'run_in_threadpool', direct)
    settings = settings_at(tmp_path, background_root=tmp_path / 'backgrounds', character_root=tmp_path / 'characters')
    settings.ready_dir.write_text('external destination unavailable')
    app = create_app(settings)
    try:
        client = LocalClient(app)
        response = client.get('/api/health')
        assert response.status_code == 200
        assert response.json()['delivery_directory'] == str(settings.local_ready_dir)
        assert response.json()['delivery_warning']
        assert client.get('/api/metadata').json()['delivery_warning'] == settings.ready_directory_warning
        assert client.get('/api/content').json() == []
    finally:
        app.state.application.close()


def test_generation_completes_ready_in_local_folder_after_delivery_failure(tmp_path):
    from unittest.mock import Mock
    from kitok.generation import GenerationPlan
    from kitok.models import ContentItem, ContentQueue, ValidationResult
    from kitok.pipeline import Pipeline
    from kitok.state import StateStore
    settings = settings_at(tmp_path)
    settings.ready_dir.write_text('external destination unavailable')
    settings.ensure_directories()
    item = ContentItem(id='local_fallback', subject='Example', script='A complete narration for our fixture.',
                       keywords=['city'], voice_profile='rick_es')
    state = StateStore(settings.state_path)
    client = Mock()
    for method in ('submit_video', 'get_task', 'download_artifact'):
        getattr(client, method).side_effect = AssertionError('Native generation must not use MPT')
    pipeline = Pipeline(settings, ContentQueue(items=[item]), state, client, {})
    pipeline.generator.plan = Mock(return_value=GenerationPlan({}))
    pipeline.generator.finish = Mock(side_effect=lambda item, plan, source, target, workspace:
                                     target.write_bytes(b'mock-rendered-video'))
    pipeline.validator.prepare = Mock(return_value=ValidationResult(ok=True))
    pipeline.process(ids={item.id})
    assert client.mock_calls == []
    pipeline.generator.plan.assert_called_once()
    pipeline.generator.finish.assert_called_once()
    pipeline.validator.prepare.assert_called_once()
    result = state.get(item.id)
    assert result['status'] == 'ready', result
    assert Path(result['ready_path']).parent == settings.local_ready_dir
    assert Path(result['ready_path']).read_bytes() == b'mock-rendered-video'
    assert (tmp_path / 'phone').read_text() == 'external destination unavailable'


def test_existing_read_only_delivery_is_detected_by_real_write_probe(tmp_path, monkeypatch):
    import kitok.config as config
    settings = settings_at(tmp_path)
    external = settings.ready_dir
    external.mkdir()
    original_probe = config.tempfile.TemporaryFile
    def read_only(*args, **kwargs):
        if kwargs.get('dir') == external:
            raise OSError('Read-only file system')
        return original_probe(*args, **kwargs)
    monkeypatch.setattr(config.tempfile, 'TemporaryFile', read_only)
    settings.ensure_directories()
    assert settings.ready_dir == settings.local_ready_dir
    assert settings.ready_directory_warning
    assert list(external.iterdir()) == []


def test_local_write_failure_still_prevents_startup(tmp_path, monkeypatch):
    import kitok.config as config
    settings = settings_at(tmp_path)
    def read_only(*args, **kwargs):
        raise PermissionError('local write denied')
    monkeypatch.setattr(config.tempfile, 'TemporaryFile', read_only)
    with pytest.raises(PermissionError, match='local write denied'):
        settings.ensure_directories()
    assert settings.ready_directory_warning is None


def test_default_delivery_is_local_without_a_second_copy(monkeypatch):
    monkeypatch.delenv('READY_DIR', raising=False)
    settings = Settings(_env_file=None, data_root=None)
    assert settings.ready_dir == settings.local_ready_dir
