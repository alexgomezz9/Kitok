"""Offline CLI checks for long-form dry-run and studio exclusion."""
import json

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
