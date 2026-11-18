"""Observe systemd jobs without starting production or touching episode inputs."""
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from kitok.longform import jobs


@pytest.fixture
def observed(tmp_path, monkeypatch):
    episode = tmp_path / 'content/longform/loose_thread/005_test'
    episode.mkdir(parents=True)
    source = episode / 'configuracion.json'
    source.write_text('{"operator": "preserve"}')
    values = {'LoadState': 'loaded', 'ActiveState': 'active', 'SubState': 'running',
              'Result': 'success', 'ExecMainCode': '0', 'ExecMainStatus': '0',
              'MainPID': '123', 'InvocationID': 'attempt-one',
              'WorkingDirectory': str(tmp_path),
              'ExecStart': str(episode / 'editorial/finalizar.py'),
              'ExecMainStartTimestamp': 'Wed 2026-11-18 18:39:42 CET'}
    monkeypatch.setattr(jobs, 'read_unit', lambda unit: values)
    monkeypatch.setattr(jobs, 'journal', lambda *args: 'Fish end elapsed=9.0s\nAsset download/cache start unique_assets=20\n')
    monkeypatch.setattr(jobs, 'manager_failure', lambda *args: '')
    monkeypatch.setattr(jobs, 'start_monitor', lambda root: pytest.fail('No monitor requested'))
    row = jobs.observe(tmp_path, episode, 'kitok-loose-thread-005', monitor=False)
    return tmp_path, episode, source, values, row


def complete_files(episode):
    delivery = episode / 'entrega'
    delivery.mkdir()
    for name in jobs.FILES:
        (delivery / name).write_bytes(b'existing operator output')


def test_observe_is_idempotent_and_preserves_episode(observed):
    root, episode, source, _, first = observed
    second = jobs.observe(root, episode, first['unit'], monitor=False)
    assert first['created_at'] == second['created_at']
    assert second['status'] == 'running'
    summary = (jobs.folder(root) / 'ESTADO.md').read_text()
    assert 'TRABAJANDO' in summary and 'Asset download/cache' in summary
    assert len(list(jobs.folder(root).glob('*.json'))) == 1
    assert source.read_text() == '{"operator": "preserve"}'
    assert len(list(episode.iterdir())) == 1
    assert not list(jobs.folder(root).glob('.summary-*'))


def test_failure_has_native_error_and_remains_failure_with_old_delivery(observed, monkeypatch):
    root, episode, _, values, _ = observed
    complete_files(episode)
    values.update(ActiveState='failed', SubState='failed', Result='exit-code', ExecMainCode='1',
                  ExecMainStatus='1', MainPID='0')
    monkeypatch.setattr(jobs, 'journal', lambda *args: 'ERROR: Stock video is too short: slot=23\nTraceback\n')
    row = jobs.status(root)[0]
    assert row['status'] == 'needs_review' and 'slot=23' in row['error']
    assert 'REVISAR' in (jobs.folder(root) / 'ESTADO.md').read_text()


def test_clean_process_requires_all_seven_files_and_nonempty_output(observed):
    root, episode, _, values, _ = observed
    values.update(ActiveState='inactive', SubState='dead', MainPID='0', ExecMainCode='1')
    assert jobs.status(root)[0]['status'] == 'needs_review'
    complete_files(episode)
    (episode / 'entrega/video_final.mp4').write_bytes(b'')
    assert jobs.status(root)[0]['missing_delivery'] == ['video_final.mp4']
    (episode / 'entrega/video_final.mp4').write_bytes(b'existing final video')
    assert jobs.status(root)[0]['status'] == 'technical_complete'
    summary = (jobs.folder(root) / 'ESTADO.md').read_text()
    assert 'ENTREGA GENERADA' in summary and '../../content/longform/loose_thread/005_test/entrega/' in summary


def test_restarted_attempt_replaces_old_error_and_uses_own_journal(observed, monkeypatch):
    root, _, _, values, _ = observed
    values.update(ActiveState='failed', SubState='failed', Result='exit-code', ExecMainStatus='1')
    monkeypatch.setattr(jobs, 'journal', lambda *args: 'ERROR: previous attempt failed\n')
    assert jobs.status(root)[0]['error']
    values.update(ActiveState='active', SubState='running', Result='success', InvocationID='attempt-two',
                  ExecMainStatus='0')
    seen = []
    def new_attempt(unit, invocation):
        seen.append(invocation)
        return 'Validation start output=/existing/video.mp4\n'
    monkeypatch.setattr(jobs, 'journal', new_attempt)
    row = jobs.status(root)[0]
    assert row['status'] == 'running' and not row['error']
    assert seen == ['attempt-two'] and row['systemd']['InvocationID'] == 'attempt-two'


def test_missing_unit_and_query_failure_are_not_reported_as_running(observed, monkeypatch):
    root, _, _, values, _ = observed
    values.clear()
    values['LoadState'] = 'not-found'
    assert jobs.status(root)[0]['status'] == 'unknown'
    def unavailable(unit):
        raise subprocess.TimeoutExpired(['systemctl'], 10)
    monkeypatch.setattr(jobs, 'read_unit', unavailable)
    assert jobs.status(root)[0]['status'] == 'unknown'


def test_collected_success_is_preserved_but_missing_delivery_is_detected(observed):
    root, episode, _, values, _ = observed
    complete_files(episode)
    values.update(ActiveState='inactive', SubState='dead', ExecMainCode='1')
    assert jobs.status(root)[0]['status'] == 'technical_complete'
    values.clear()
    values['LoadState'] = 'not-found'
    assert jobs.status(root)[0]['status'] == 'technical_complete'
    (episode / 'entrega/voz.srt').unlink()
    assert jobs.status(root)[0]['status'] == 'needs_review'


def test_binding_and_paths_block_wrong_episode_or_symlinks(observed):
    root, episode, _, values, _ = observed
    values['ExecStart'] = '/different/episode/finalizar.py'
    assert jobs.status(root)[0]['status'] == 'unknown'
    with pytest.raises(ValueError, match='corresponde'):
        jobs.observe(root, episode, 'kitok-loose-thread-006', monitor=False)
    with pytest.raises(ValueError, match='service name'):
        jobs.unit_name('../../unsafe')
    values['ExecStart'] = str(episode / 'editorial/finalizar.py')
    delivery = episode / 'entrega'
    delivery.symlink_to(root)
    row = jobs.status(root)[0]
    assert row['status'] == 'unknown' and 'symlink' in row['observation']


def test_journal_is_scoped_to_current_invocation(monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='Fish start content_id=x\n')
    monkeypatch.setattr(jobs.subprocess, 'run', run)
    assert 'Fish' in jobs.journal('kitok-loose-thread-005.service', 'a' * 32)
    assert '_SYSTEMD_INVOCATION_ID=' + 'a' * 32 in calls[0]
    assert calls[0][:2] == ['journalctl', '--user']


def test_monitor_only_starts_observer_timer(monkeypatch, tmp_path):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='not-found\n')
    monkeypatch.setattr(jobs.subprocess, 'run', run)
    jobs.start_monitor(tmp_path)
    command = calls[-1]
    assert command[:2] == ['systemd-run', '--user']
    assert '--unit=kitok-loose-thread-status' in command
    assert '--on-unit-active=10s' in command
    assert 'status' in command and '--quiet' in command
    assert not any('longform.py' == Path(part).name or part.endswith('finalizar.py') for part in command)


def test_existing_timer_is_started_without_replacing_service(monkeypatch, tmp_path):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='loaded\n')
    monkeypatch.setattr(jobs.subprocess, 'run', run)
    jobs.start_monitor(tmp_path)
    assert calls[-1] == ['systemctl', '--user', 'start', 'kitok-loose-thread-status.timer']


def test_terminal_jobs_stop_only_observer_timer(monkeypatch):
    calls = []
    monkeypatch.setattr(jobs.subprocess, 'run', lambda command, **kw: calls.append(command))
    jobs.stop_idle_monitor([{'status': 'technical_complete'}, {'status': 'needs_review'}])
    assert calls == [['systemctl', '--user', 'stop', 'kitok-loose-thread-status.timer']]


@pytest.mark.parametrize('rows', [[], [{'status': 'running'}], [{'status': 'unknown'}],
                                [{'status': 'needs_review'}, {'status': 'running'}]])
def test_active_or_unknown_job_keeps_observer_available(rows, monkeypatch):
    monkeypatch.setattr(jobs.subprocess, 'run', lambda *a, **kw: pytest.fail('Timer stopped prematurely'))
    jobs.stop_idle_monitor(rows)


def test_invalid_registry_unit_cannot_reach_systemctl(observed, monkeypatch):
    root, _, _, _, _ = observed
    path = jobs.folder(root) / 'kitok-loose-thread-005.service.json'
    row = json.loads(path.read_text())
    row['unit'] = 'unrelated.service'
    path.write_text(json.dumps(row))
    monkeypatch.setattr(jobs, 'read_unit', lambda unit: pytest.fail('Invalid unit reached systemd'))
    with pytest.raises(ValueError, match='registro'):
        jobs.status(root)


def test_collected_running_attempt_recovers_only_its_delivery(observed, monkeypatch):
    root, episode, _, values, _ = observed
    complete_files(episode)
    values.clear()
    values['LoadState'] = 'not-found'
    calls = []
    def archived(unit, invocation):
        calls.append(invocation)
        return 'Entrega: ' + str(episode / 'entrega') + '\n'
    monkeypatch.setattr(jobs, 'journal', archived)
    row = jobs.status(root)[0]
    assert calls == ['attempt-one']
    assert row['status'] == 'technical_complete'
    assert row['completion_evidence'] == 'same_invocation_delivery_log'
    assert row['systemd']['MainPID'] == '0'
    assert row['systemd']['ExecMainStatus'] == 'no conservada'


def test_collected_failure_is_not_success_even_after_delivery(observed, monkeypatch):
    root, episode, _, values, _ = observed
    complete_files(episode)
    values.clear()
    values['LoadState'] = 'not-found'
    monkeypatch.setattr(jobs, 'journal', lambda *a: 'Entrega: ' + str(episode / 'entrega') + '\n')
    monkeypatch.setattr(jobs, 'manager_failure', lambda *a: 'Main process exited, status=1/FAILURE')
    row = jobs.status(root)[0]
    assert row['status'] == 'needs_review' and 'FAILURE' in row['error']


@pytest.mark.parametrize('message', ['Entrega: /another/episode/entrega\n',
                                    'Final DONE: /some/output.mp4\n',
                                    'prefix Entrega: {delivery}\n'])
def test_collected_old_files_require_exact_delivery_message(observed, monkeypatch, message):
    root, episode, _, values, _ = observed
    complete_files(episode)
    values.clear()
    values['LoadState'] = 'not-found'
    monkeypatch.setattr(jobs, 'journal', lambda *a: message.format(delivery=episode / 'entrega'))
    row = jobs.status(root)[0]
    assert row['status'] == 'unknown'
    path = jobs.folder(root) / (row['unit'] + '.json')
    row['collected_observed_at'] = '2000-01-01T00:00:00+00:00'
    path.write_text(json.dumps(row))
    assert jobs.status(root)[0]['status'] == 'needs_review'


def test_collected_delivery_waits_for_seven_files(observed, monkeypatch):
    root, episode, _, values, _ = observed
    values.clear()
    values['LoadState'] = 'not-found'
    monkeypatch.setattr(jobs, 'journal', lambda *a: 'Entrega: ' + str(episode / 'entrega') + '\n')
    assert jobs.status(root)[0]['status'] == 'unknown'
    complete_files(episode)
    assert jobs.status(root)[0]['status'] == 'technical_complete'


def test_very_short_attempt_keeps_invocation_from_initial_binding(tmp_path, monkeypatch):
    episode = tmp_path / 'content/longform/loose_thread/006_short'
    episode.mkdir(parents=True)
    complete_files(episode)
    live = {'LoadState': 'loaded', 'ActiveState': 'active', 'SubState': 'running',
            'Result': 'success', 'InvocationID': 'short-attempt',
            'WorkingDirectory': str(tmp_path), 'ExecStart': str(episode / 'editorial/finish.py')}
    states = iter([live, {'LoadState': 'not-found'}])
    monkeypatch.setattr(jobs, 'read_unit', lambda *a: next(states))
    monkeypatch.setattr(jobs, 'journal', lambda unit, invocation: (
        'Entrega: ' + str(episode / 'entrega') + '\n' if invocation == 'short-attempt' else ''))
    monkeypatch.setattr(jobs, 'manager_failure', lambda *a: '')
    row = jobs.observe(tmp_path, episode, 'kitok-loose-thread-006', monitor=False)
    assert row['status'] == 'technical_complete'


def test_manager_failure_checks_exact_unit_and_invocation(monkeypatch):
    events = [
        {'USER_UNIT': 'other.service', 'USER_INVOCATION_ID': 'attempt', 'EXIT_STATUS': '9'},
        {'USER_UNIT': 'kitok-loose-thread-005.service', 'USER_INVOCATION_ID': 'old', 'EXIT_STATUS': '2'},
        {'USER_UNIT': 'kitok-loose-thread-005.service', 'USER_INVOCATION_ID': 'attempt',
         'UNIT_RESULT': 'exit-code', 'MESSAGE': 'current invocation failed'},
    ]
    calls = []
    def run(command, **kw):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='\n'.join(json.dumps(event) for event in events))
    monkeypatch.setattr(jobs.subprocess, 'run', run)
    assert jobs.manager_failure('kitok-loose-thread-005.service', 'attempt') == 'current invocation failed'
    assert 'USER_INVOCATION_ID=attempt' in calls[0]


def test_registration_cannot_lose_its_timer_to_an_old_terminal_snapshot(observed, monkeypatch):
    import threading
    root, episode, _, values, _ = observed
    other = episode.parent / '006_new'
    other.mkdir()
    values.update(ActiveState='failed', SubState='failed', Result='exit-code')
    current = dict(values, ActiveState='active', SubState='running', Result='success',
                   InvocationID='next-attempt', ExecStart=str(other / 'editorial/finish.py'))
    monkeypatch.setattr(jobs, 'read_unit', lambda unit: current if '-006.' in unit else values)
    stopping = threading.Event()
    release = threading.Event()
    registering = threading.Event()
    finished = threading.Event()
    order = []
    failures = []
    def stop(rows):
        assert all(row['status'] == 'needs_review' for row in rows)
        stopping.set()
        assert release.wait(3)
        order.append('stop')
    monkeypatch.setattr(jobs, 'stop_idle_monitor', stop)
    monkeypatch.setattr(jobs, 'start_monitor', lambda root: order.append('start'))
    def poll():
        try:
            jobs.status(root, stop_idle=True)
        except Exception as error:
            failures.append(error)
    def register():
        registering.set()
        try:
            jobs.observe(root, other, 'kitok-loose-thread-006')
        except Exception as error:
            failures.append(error)
        finally:
            finished.set()
    first = threading.Thread(target=poll)
    second = threading.Thread(target=register)
    first.start()
    try:
        assert stopping.wait(3)
        second.start()
        assert registering.wait(3)
        assert not finished.wait(.05)
    finally:
        release.set()
        first.join(3)
        if second.ident is not None:
            second.join(3)
    assert not failures and not first.is_alive() and not second.is_alive()
    assert order == ['stop', 'start']
    assert any(row['unit'] == 'kitok-loose-thread-006.service' and row['status'] == 'running'
               for row in jobs.status(root))
