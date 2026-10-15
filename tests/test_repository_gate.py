from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.check_repository import forbidden_path, inspect_file
from scripts.verify import run_steps


@pytest.mark.parametrize('name', [
    '.env', '.env.production', 'content_queue.json', 'state/history.json',
    'local/import.json', 'content/longform/personal.txt', 'src/pkg.egg-info/PKG-INFO',
    'frontend/dist/index.html', 'outputs/video.mp4', '.codex-work/.gitkeep', 'local/.gitkeep',
])
def test_operator_data_and_generated_files_cannot_be_published(name):
    assert forbidden_path(name)


@pytest.mark.parametrize('name', ['.env.example', 'content/README.md', 'examples/longform/demo.json', 'src/kitok/config.py'])
def test_public_configuration_and_synthetic_examples_are_allowed(name):
    assert not forbidden_path(name)


def test_gate_never_reads_or_prints_private_file_values(tmp_path):
    (tmp_path / '.env').write_text('PRIVATE_VALUE=must-not-be-read')
    errors = inspect_file(tmp_path, '.env')
    assert len(errors) == 1
    assert 'must-not-be-read' not in str(errors)


def test_signature_check_reports_location_without_value(tmp_path):
    value = 'gh' + 'p_' + 'x' * 40
    (tmp_path / 'source.txt').write_text('one\n' + value)
    errors = inspect_file(tmp_path, 'source.txt')
    assert len(errors) == 1 and 'source.txt:2:' in errors[0]
    assert value not in errors[0]


def test_verification_stops_after_failed_step_without_running_following_steps(tmp_path):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=3 if command == ['fail'] else 0)
    code = run_steps([('first', ['ok']), ('bad', ['fail']), ('last', ['must-not-run'])], run=run, cwd=tmp_path)
    assert code == 3 and calls == [['ok'], ['fail']]


def test_timed_out_verification_is_not_reported_as_success(tmp_path):
    import subprocess
    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1)
    assert run_steps([('timeout', ['fixture'])], run=run, cwd=tmp_path) == 1


def staged_fixture(tmp_path, name, content):
    import subprocess
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / name).write_text(content)
    subprocess.run(['git', 'add', '--', name], cwd=tmp_path, check=True)


def test_index_signature_cannot_be_hidden_by_clean_working_copy(tmp_path, monkeypatch, capsys):
    from scripts import check_repository
    value = 'gh' + 'p_' + 'x' * 40
    staged_fixture(tmp_path, 'source.txt', value)
    (tmp_path / 'source.txt').write_text('clean working copy')
    monkeypatch.setattr(check_repository, 'ROOT', tmp_path)
    assert check_repository.main() == 1
    output = capsys.readouterr().err
    assert 'source.txt:1:' in output and value not in output


def test_staged_symlink_cannot_be_hidden_by_regular_working_file(tmp_path, monkeypatch, capsys):
    import subprocess
    from scripts import check_repository
    staged_fixture(tmp_path, 'target.txt', 'safe fixture')
    link = tmp_path / 'source.txt'
    link.symlink_to('target.txt')
    subprocess.run(['git', 'add', '--', link.name], cwd=tmp_path, check=True)
    link.unlink()
    link.write_text('regular file now')
    monkeypatch.setattr(check_repository, 'ROOT', tmp_path)
    assert check_repository.main() == 1
    assert 'mode 120000' in capsys.readouterr().err


def test_clean_index_and_changed_safe_working_copy_are_both_allowed(tmp_path, monkeypatch):
    from scripts import check_repository
    staged_fixture(tmp_path, 'source.txt', 'safe staged content')
    (tmp_path / 'source.txt').write_text('safe working content')
    monkeypatch.setattr(check_repository, 'ROOT', tmp_path)
    assert check_repository.main() == 0
