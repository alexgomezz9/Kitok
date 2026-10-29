"""Queue persistence, recovery and concurrency without paid providers."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from kitok.youtube_stickman_es import jobs


@pytest.fixture
def queue(tmp_path, monkeypatch):
    episode = tmp_path / 'episode'
    episode.mkdir()
    source = episode / 'source.txt'
    source.write_text('immutable paid material')
    monkeypatch.setattr(jobs, 'handoff_inputs', lambda p: {'source.txt': source.read_text()})
    monkeypatch.setattr(jobs, 'choose_encoder', lambda *a, **kw: SimpleNamespace(codec='libx264', preset='medium'))
    monkeypatch.setattr(jobs.shutil, 'disk_usage', lambda *a: SimpleNamespace(free=20*1024**3))
    return tmp_path, episode, source


def test_enqueue_is_idempotent_and_has_atomic_readable_overview(queue):
    root, episode, _ = queue
    a = jobs.enqueue(root, episode, start=False)
    b = jobs.enqueue(root, episode, start=False)
    assert a['id'] == b['id']
    summary = (jobs.folder(root) / 'ESTADO.md').read_text()
    assert 'EN COLA' in summary and a['id'] + '.log' in summary
    assert len(jobs.status(root)) == 1


def test_worker_success_and_failure_have_verbose_logs_and_explicit_retry(queue, monkeypatch):
    root, episode, source = queue
    row = jobs.enqueue(root, episode, start=False)
    calls = []
    def render(root, episode, command, **kwargs):
        calls.append(command)
        assert command == 'complete' and kwargs['generate_voice'] is False
        kwargs['on_stage']('Plano 7/19: prueba detallada')
        raise subprocess.CalledProcessError(1, ['ffmpeg'], stderr='Specific filter failed: invalid timestamp')
    monkeypatch.setattr(jobs, 'execute', render)
    jobs.worker(root, settings=SimpleNamespace(ffmpeg_binary='ffmpeg'))
    state = jobs.status(root)[0]
    assert state['status'] == 'needs_review' and state['attempt'] == 1
    assert 'invalid timestamp' in state['error'] and state['failed_stage'] == 'Plano 7/19: prueba detallada'
    log = (root / state['log']).read_text()
    assert 'Traceback' in log and 'invalid timestamp' in log
    jobs.worker(root, settings=SimpleNamespace(ffmpeg_binary='ffmpeg'))
    assert len(calls) == 1  # no automatic retry
    monkeypatch.setattr(jobs, 'execute', lambda *a, **kw: {'status': 'technical_complete'})
    jobs.retry(root, row['id'], start=False)
    jobs.worker(root, settings=SimpleNamespace(ffmpeg_binary='ffmpeg'))
    state = jobs.status(root)[0]
    assert state['status'] == 'technical_complete' and state['attempt'] == 2
    assert len(state['failures']) == 1 and source.read_text() == 'immutable paid material'
    assert jobs.enqueue(root, episode, start=False)['id'] == row['id']


def test_incomplete_pipeline_return_is_not_success(queue, monkeypatch):
    root, episode, _ = queue
    jobs.enqueue(root, episode, start=False)
    monkeypatch.setattr(jobs, 'execute', lambda *a, **kw: {'status': 'images_required'})
    jobs.worker(root, settings=SimpleNamespace(ffmpeg_binary='ffmpeg'))
    assert 'images_required' in jobs.status(root)[0]['error']


def test_changed_inputs_block_explicit_retry(queue):
    root, episode, source = queue
    row = jobs.enqueue(root, episode, start=False)
    row.update(status='needs_review', error='test interruption')
    jobs._save(root, row)
    source.write_text('operator changed input')
    with pytest.raises(ValueError, match='Inputs changed'):
        jobs.retry(root, row['id'], start=False)


def test_dead_running_job_becomes_review_without_rerun(queue, monkeypatch):
    root, episode, _ = queue
    row = jobs.enqueue(root, episode, start=False)
    row.update(status='running', process_group=99999999, stage='Subtítulos')
    jobs._save(root, row)
    monkeypatch.setattr(jobs, 'execute', lambda *a, **kw: pytest.fail('Never replay interrupted job'))
    assert jobs.status(root)[0]['status'] == 'needs_review'
    assert 'Subtítulos' == jobs.status(root)[0]['failed_stage']
    jobs.worker(root, settings=SimpleNamespace(ffmpeg_binary='ffmpeg'))


def test_live_orphan_group_blocks_queue_and_retry(queue):
    root, episode, _ = queue
    row = jobs.enqueue(root, episode, start=False)
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
    try:
        row.update(status='running', process_group=child.pid, stage='FFmpeg')
        jobs._save(root, row)
        rows = jobs.status(root)
        assert rows[0]['remaining_processes'] is True and rows[0]['status'] == 'needs_review'
        with pytest.raises(RuntimeError, match='conserva procesos'):
            jobs.worker(root, settings=SimpleNamespace(ffmpeg_binary='ffmpeg'))
        with pytest.raises(ValueError, match='still alive'):
            jobs.retry(root, row['id'], start=False)
    finally:
        child.terminate()
        child.wait(timeout=5)


def test_worker_lease_prevents_duplicate_consumer(queue, monkeypatch):
    root, episode, _ = queue
    jobs.enqueue(root, episode, start=False)
    monkeypatch.setattr(jobs, 'execute', lambda *a, **kw: pytest.fail('Worker already active'))
    with jobs.lease(jobs.folder(root) / 'worker.lock'):
        assert jobs.worker(root, settings=SimpleNamespace(ffmpeg_binary='ffmpeg')) == 0
    assert jobs.status(root)[0]['status'] == 'queued'


def test_symlink_state_and_invalid_ids_are_rejected(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    root = tmp_path / 'root'
    root.mkdir()
    (root / 'local').symlink_to(outside)
    with pytest.raises(ValueError, match='symlinks'):
        jobs.status(root)
    with pytest.raises(ValueError, match='32-character'):
        jobs._path(tmp_path, '../outside')


def test_detached_worker_survives_launcher_exit(tmp_path):
    # Real process boundary: the launcher returns before a slow worker preflight.
    # It deliberately fails on an invalid episode; no media/providers are touched.
    row = {'id': 'a'*32, 'episode': 'missing', 'status': 'queued', 'stage': 'test',
           'inputs': {}, 'created_at': jobs.now(), 'attempt': 0,
           'log': 'local/stickman_jobs/' + 'a'*32 + '.log'}
    jobs._save(tmp_path, row)
    code = ('from pathlib import Path; from kitok.youtube_stickman_es.jobs import start_worker; '
            'import sys; print(start_worker(Path(sys.argv[1])))')
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')}
    # start_worker expects src under root. Supply the real module path through
    # inherited PYTHONPATH; temporary root remains the only data workspace.
    launcher = subprocess.run([sys.executable, '-c', code, str(tmp_path)], env=env,
                              capture_output=True, text=True, check=True, timeout=10)
    pid = int(launcher.stdout)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = jobs._read(tmp_path, row['id'])
        if state['status'] == 'needs_review':
            break
        time.sleep(.05)
    assert state['status'] == 'needs_review', (tmp_path / 'local/stickman_jobs/worker.log').read_text()
    assert 'existing episode folder' in state['error']
    assert (tmp_path / row['log']).exists()


def test_gpu_required_failure_is_reported_before_render(queue, monkeypatch):
    root, episode, source = queue
    jobs.enqueue(root, episode, start=False, require_gpu=True)
    def unavailable(*a, **kw):
        assert kw['requested'] == 'h264_nvenc'
        raise RuntimeError('h264_nvenc runtime probe failed')
    monkeypatch.setattr(jobs, 'choose_encoder', unavailable)
    monkeypatch.setattr(jobs, 'execute', lambda *a, **kw: pytest.fail('No CPU fallback'))
    jobs.worker(root, settings=SimpleNamespace(ffmpeg_binary='ffmpeg'))
    state = jobs.status(root)[0]
    assert state['status'] == 'needs_review' and 'runtime probe failed' in state['error']
    assert source.read_text() == 'immutable paid material'


def test_killed_worker_leaves_child_group_blocking_next_job(queue):
    root, episode, _ = queue
    row = jobs.enqueue(root, episode, start=False)
    script = '''
import sys, subprocess, time
from pathlib import Path
from types import SimpleNamespace
from kitok.youtube_stickman_es import jobs
root = Path(sys.argv[1])
jobs.choose_encoder = lambda *a, **kw: SimpleNamespace(codec='libx264', preset='medium')
def active(*a, **kw):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    (root / 'child.pid').write_text(str(child.pid))
    time.sleep(30)
jobs.execute = active
jobs.worker(root, settings=SimpleNamespace(ffmpeg_binary='ffmpeg'))
'''
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')}
    worker = subprocess.Popen([sys.executable, '-c', script, str(root)], env=env,
                              start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while not (root / 'child.pid').exists() and time.monotonic() < deadline:
            time.sleep(.05)
        assert (root / 'child.pid').exists()
        worker.kill()
        worker.wait(timeout=5)
        state = jobs.status(root)[0]
        assert state['status'] == 'needs_review' and state['remaining_processes'] is True
        with pytest.raises(RuntimeError, match='conserva procesos'):
            jobs.worker(root, settings=SimpleNamespace(ffmpeg_binary='ffmpeg'))
        with pytest.raises(ValueError, match='still alive'):
            jobs.retry(root, row['id'], start=False)
    finally:
        try:
            os.killpg(worker.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        worker.wait(timeout=5)


def test_duplicate_enqueue_rejects_changed_gpu_policy(queue):
    root, episode, _ = queue
    jobs.enqueue(root, episode, start=False, require_gpu=True)
    with pytest.raises(ValueError, match='different GPU policy'):
        jobs.enqueue(root, episode, start=False, require_gpu=False)
