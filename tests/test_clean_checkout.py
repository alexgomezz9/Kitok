"""A fresh source checkout has no operator queue or credentials."""
import pytest

from kitok.config import Settings
from kitok import cli


def test_read_only_cli_accepts_missing_local_queue_without_creating_data(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, data_root=tmp_path, ready_dir=tmp_path / 'ready')
    monkeypatch.setattr(cli, 'Settings', lambda: settings)
    settings, queue, state, preset = cli.load_all(read_only=True)
    assert queue.items == [] and state.all() == {}
    assert isinstance(preset, dict)
    assert not settings.queue_path.exists()
    assert not settings.state_path.parent.exists()


@pytest.mark.parametrize('flag', ['--dry-run', '--status'])
def test_read_only_cli_entrypoints_accept_missing_queue_without_writes(tmp_path, monkeypatch, flag):
    settings = Settings(_env_file=None, data_root=tmp_path, ready_dir=tmp_path / 'ready')
    monkeypatch.setattr(cli, 'Settings', lambda: settings)
    monkeypatch.setattr(cli.VideoValidator, 'ffprobe_available', lambda self: True)
    def forbidden(*args, **kwargs):
        raise AssertionError('A read-only command must not initialize generation or file logging')
    monkeypatch.setattr(cli, 'MPTClient', forbidden)
    monkeypatch.setattr(cli, 'run_generation', forbidden)
    monkeypatch.setattr(cli, 'configure_logging', forbidden)
    assert cli.main([flag]) == 0
    assert list(tmp_path.iterdir()) == []
