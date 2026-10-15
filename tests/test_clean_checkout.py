"""A fresh source checkout has no operator queue or credentials."""
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
