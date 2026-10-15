"""Native CLI/control-panel entrypoints never initialize an inert MPT transport."""
from unittest.mock import Mock

import pytest

from kitok import cli
from kitok.control_panel import ControlPanel
from kitok.mpt_client import MPTError
from kitok.regeneration import RegenerationSummary


def setup_cli(local_kitok, monkeypatch):
    settings, queue, state, _ = local_kitok
    monkeypatch.setattr(cli, 'load_all', lambda **kwargs: (settings, queue, state, {'font_size': 81}))
    monkeypatch.setattr(cli, 'configure_logging', lambda *args: None)
    forbidden = Mock(side_effect=AssertionError('Native entrypoints must not construct MPTClient'))
    monkeypatch.setattr(cli, 'MPTClient', forbidden)
    return settings, queue, state, forbidden


@pytest.mark.parametrize('options', [[], ['--id', 'one'], ['--retry-failed']])
def test_cli_generation_passes_none_for_legacy_client(local_kitok, monkeypatch, options):
    settings, queue, state, mpt = setup_cli(local_kitok, monkeypatch)
    generate = Mock()
    monkeypatch.setattr(cli, 'run_generation', generate)
    assert cli.main(options) == 0
    assert generate.call_args.args[:4] == (settings, queue, state, None)
    mpt.assert_not_called()


@pytest.mark.parametrize('dry_run', [False, True])
def test_cli_regeneration_passes_none_for_legacy_client(local_kitok, monkeypatch, dry_run):
    settings, queue, state, mpt = setup_cli(local_kitok, monkeypatch)
    regenerate = Mock()
    regenerate.return_value.run.return_value = RegenerationSummary(regenerated=0 if dry_run else 1)
    monkeypatch.setattr(cli, 'ReadyRegenerator', regenerate)
    assert cli.main(['--regenerate-all-ready', *(['--dry-run'] if dry_run else [])]) == 0
    assert regenerate.call_args.args[:4] == (settings, queue, state, None)
    regenerate.return_value.run.assert_called_once_with(dry_run=dry_run)
    mpt.assert_not_called()


@pytest.mark.parametrize('failure', [False, True])
def test_only_explicit_diagnostic_constructs_checks_and_closes_mpt(local_kitok, monkeypatch, failure):
    setup_cli(local_kitok, monkeypatch)
    client = Mock()
    if failure:
        client.check.side_effect = MPTError('Historical service unavailable')
    factory = Mock(return_value=client)
    monkeypatch.setattr(cli, 'MPTClient', factory)
    monkeypatch.setattr(cli, 'run_generation', lambda *a, **kw: pytest.fail('Diagnostic must not generate'))
    assert cli.main(['--check-mpt']) == (3 if failure else 0)
    factory.assert_called_once()
    client.check.assert_called_once_with()
    client.close.assert_called_once_with()


@pytest.mark.parametrize('kind', ['generate', 'regenerate'])
def test_control_panel_native_actions_pass_none_and_no_mpt_summary(local_kitok, monkeypatch, kind):
    settings, queue, state, _ = local_kitok
    settings.mpt_preset_path = settings.queue_path.parent / 'preset.json'
    settings.mpt_preset_path.write_text('{"font_size": 81}')
    if kind == 'generate':
        state.upsert('one', status='pending')
    panel = ControlPanel(settings)
    action = panel.prepare_action(kind, 'one')
    assert action.summary['Renderer'] == 'Native (Fish + Pexels + FFmpeg)'
    assert not any('MPT' in key for key in action.summary)
    forbidden = Mock(side_effect=AssertionError('Native control-panel action must not construct MPTClient'))
    monkeypatch.setattr('kitok.control_panel.MPTClient', forbidden)
    if kind == 'generate':
        constructor = Mock()
        monkeypatch.setattr('kitok.control_panel.Pipeline', constructor)
    else:
        constructor = Mock()
        constructor.return_value.run.return_value = RegenerationSummary(regenerated=1)
        monkeypatch.setattr('kitok.control_panel.ReadyRegenerator', constructor)
    panel.execute(action, confirmed=True)
    assert constructor.call_args.args[3] is None
    assert constructor.call_args.args[4] == {'font_size': 81}
    forbidden.assert_not_called()


def test_cli_read_only_output_names_native_and_labels_only_historical_state(local_kitok, monkeypatch, capsys):
    settings, queue, state, mpt = setup_cli(local_kitok, monkeypatch)
    monkeypatch.setattr(cli.VideoValidator, 'ffprobe_available', lambda self: True)
    assert cli.main(['--dry-run']) == 0
    output = capsys.readouterr().out
    assert 'Renderer: native' in output and 'MPT' not in output
    assert cli.main(['--status']) == 0
    assert 'MPT' not in capsys.readouterr().out
    state.upsert('one', status='submitted', mpt_task_id='old-id', mpt_progress=45)
    before = state.path.read_bytes()
    assert cli.main(['--status']) == 0
    output = capsys.readouterr().out
    assert 'Historical' in output and 'MPT' in output
    assert state.path.read_bytes() == before
    mpt.assert_not_called()
