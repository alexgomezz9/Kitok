"""Local durable stickman queue. No providers, publication or automatic retry.

Run ``python -m kitok.youtube_stickman_es.jobs --help``. One detached worker
serializes this queue; unrelated Studio/CLI renders are outside its lease.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import tempfile
import traceback
import uuid

from ..config import PROJECT_ROOT, Settings
from ..media.ffmpeg import choose_encoder
from .completion import handoff_inputs
from .files import episode_lock, episode_path, local_file, replace_state
from .pipeline import execute
from .progress import TerminalProgress

LABELS = {'queued': 'EN COLA', 'running': 'TRABAJANDO', 'technical_complete': 'TERMINADO',
          'needs_review': 'REVISAR'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def folder(root):
    path = local_file(root.resolve(), 'local/stickman_jobs', exists=False)
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def lease(path, *, blocking=True):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            yield None
            return
        try:
            yield handle
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _path(root, ident):
    if not re.fullmatch(r'[a-f0-9]{32}', ident):
        raise ValueError('Expected the 32-character job ID from enqueue/status')
    return local_file(folder(root), ident + '.json', exists=False)


def _read(root, ident):
    return json.loads(_path(root, ident).read_text())


def _records(root):
    return sorted((json.loads(local_file(folder(root), p.name).read_text())
                   for p in folder(root).glob('*.json') if re.fullmatch(r'[a-f0-9]{32}\.json', p.name)),
                  key=lambda row: (row['created_at'], row['id']))


def _summary(root):
    rows = _records(root)
    lines = ['# Producción stickman', '', 'Terminado = QA técnico, entrega y limpieza comprobados. '
             'Escucha y revisión visual del operador pendientes. No publica vídeos.', '',
             '| Estado | Episodio | Fase / error | Registro |', '| --- | --- | --- | --- |']
    for row in rows:
        message = str(row.get('error') or row.get('stage', '')).replace('|', '/').replace('\n', ' ')
        lines.append(f"| {LABELS[row['status']]} | {row['episode']} | {message} | [log]({row['id']}.log) |")
    # Atomic publication: readers can leave this file open without partial tables.
    target = local_file(folder(root), 'ESTADO.md', exists=False)
    fd, temporary = tempfile.mkstemp(prefix='.summary-', dir=folder(root))
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write('\n'.join(lines) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _save(root, row):
    row['updated_at'] = now()
    replace_state(_path(root, row['id']), row)
    _summary(root)


def _alive_group(group):
    if not group:
        return False
    try:
        os.killpg(group, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _recover(root):
    """Worker lease held: a previous live session may still own FFmpeg children."""
    for row in _records(root):
        if row['status'] == 'running':
            row.update(status='needs_review', error='Proceso interrumpido; materiales conservados. Revisar antes de retry.',
                       failed_stage=row.get('stage'), finished_at=now())
            _save(root, row)
        group = row.get('process_group')
        if group and group != os.getpgrp() and _alive_group(group):
            raise RuntimeError(f"Job {row['id']} conserva procesos del grupo {group}; esperar o revisarlos antes de continuar la cola")


def status(root):
    """Reconcile dead workers only after acquiring their lease."""
    with lease(folder(root) / 'worker.lock', blocking=False) as worker_lock:
        if worker_lock:
            with lease(folder(root) / 'queue.lock'):
                try:
                    _recover(root)
                except RuntimeError:
                    pass  # Specific orphan warning remains in the job below.
                rows = _records(root)
                _summary(root)
        else:
            with lease(folder(root) / 'queue.lock'):
                rows = _records(root)
    for row in rows:
        group = row.get('process_group')
        row['remaining_processes'] = bool(row['status'] == 'needs_review' and group and _alive_group(group))
    return rows


def enqueue(root, episode, *, start=True, require_gpu=False):
    root = root.resolve()
    episode = episode_path(root, episode)
    with lease(folder(root) / 'queue.lock'):
        for previous in _records(root):
            if previous['episode'] == str(episode.relative_to(root)):
                if previous['status'] in {'queued', 'running', 'technical_complete'}:
                    if bool(previous.get('require_gpu')) != require_gpu:
                        raise ValueError('Existing job has a different GPU policy; preserve its original options')
                    result = previous
                    break
                raise ValueError('This episode has an interrupted/failed job; inspect it and use retry with the same inputs')
        else:
            with episode_lock(episode):
                inputs = handoff_inputs(episode)
            ident = uuid.uuid4().hex
            result = {'id': ident, 'episode': str(episode.relative_to(root)), 'status': 'queued',
                      'stage': 'Esperando worker; inputs editoriales congelados', 'inputs': inputs,
                      'created_at': now(), 'attempt': 0, 'require_gpu': require_gpu, 'log': f'local/stickman_jobs/{ident}.log',
                      'human_review_required': True, 'publishing_automated': False}
            _save(root, result)
    if start and result['status'] != 'technical_complete':
        start_worker(root)
    return result


def retry(root, ident, *, start=True):
    with lease(folder(root) / 'worker.lock', blocking=False) as worker_lock:
        # An active worker may be processing another episode; queue lease protects
        # the retry transition and the previous job's process group must be gone.
        with lease(folder(root) / 'queue.lock'):
            row = _read(root, ident)
            if row['status'] != 'needs_review':
                raise ValueError('Only needs_review jobs can be explicitly retried')
            if _alive_group(row.get('process_group')):
                raise ValueError('Previous process group is still alive; review it before retry')
            episode = episode_path(root, Path(row['episode']))
            with episode_lock(episode):
                if handoff_inputs(episode) != row['inputs']:
                    raise ValueError('Inputs changed; create a new episode revision and a new handoff')
            row.setdefault('failures', []).append({key: row.get(key) for key in
                ('attempt', 'error', 'failed_stage', 'finished_at')})
            for key in ('error', 'failed_stage', 'finished_at', 'process_group'):
                row.pop(key, None)
            row.update(status='queued', stage='Reanudación explícita; conserva voz, PNG y renders válidos')
            _save(root, row)
    if start:
        start_worker(root)
    return row


def start_worker(root):
    """Independent session; no inherited chat pipes or terminal stdin."""
    env = {**os.environ, 'PYTHONPATH': str(root / 'src') + os.pathsep + os.environ.get('PYTHONPATH', '')}
    with (folder(root) / 'worker.log').open('a') as log:
        process = subprocess.Popen([sys.executable, '-u', '-m', __name__, '--root', str(root), 'worker'],
            cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            start_new_session=True, close_fds=True)
    return process.pid


def _error_text(error):
    message = f'{type(error).__name__}: {error}'
    if isinstance(error, subprocess.CalledProcessError):
        stderr = error.stderr or ''
        message += '\n' + (stderr.decode(errors='replace') if isinstance(stderr, bytes) else stderr)[-16000:]
    return message


def worker(root, *, settings=None):
    root = root.resolve()
    with lease(folder(root) / 'worker.lock', blocking=False) as worker_lock:
        if not worker_lock:
            return 0
        with lease(folder(root) / 'queue.lock'):
            _recover(root)
        while True:
            with lease(folder(root) / 'queue.lock'):
                pending = [row for row in _records(root) if row['status'] == 'queued']
                if not pending:
                    # Release while queue is held: enqueue cannot lose a wakeup
                    # between the empty check and worker exit.
                    fcntl.flock(worker_lock, fcntl.LOCK_UN)
                    return 0
                row = pending[0]
                row.update(status='running', stage='Preflight: recursos, GPU/CPU y disco',
                           attempt=row['attempt'] + 1, started_at=now(),
                           process_group=os.getpgrp())
                _save(root, row)
            with local_file(folder(root), row['id'] + '.log', exists=False).open('a', buffering=1) as log:
                with TerminalProgress(stream=log) as progress:
                    def emit(message):
                        progress(message)
                        with lease(folder(root) / 'queue.lock'):
                            row['stage'] = str(message)
                            _save(root, row)
                    try:
                        emit(f"Intento {row['attempt']} · {row['episode']}")
                        episode = episode_path(root, Path(row['episode']))
                        active_settings = settings or Settings()
                        encoder = choose_encoder(active_settings.ffmpeg_binary, nvenc_preset='p5',
                                                 requested='h264_nvenc' if row.get('require_gpu') else 'auto')
                        free = shutil.disk_usage(episode).free
                        emit(f'Preflight: codificador {encoder.codec} ({encoder.preset}); disco libre {free // (1024**2)} MiB')
                        if free < 2 * 1024**3:
                            raise ValueError('Menos de 2 GiB libres; liberar espacio antes de retry. No se borran fuentes.')
                        result = execute(root, episode, 'complete', settings=active_settings, on_stage=emit,
                                         handoff=row['inputs'], generate_voice=False, require_gpu=row.get('require_gpu', False))
                        if result.get('status') != 'technical_complete':
                            raise ValueError('Pipeline returned an incomplete state: ' + str(result.get('status')))
                        row.update(status='technical_complete', result=result, finished_at=now())
                        # This session may process another job; completed jobs do
                        # not own its group and must not block later recovery.
                        row.pop('process_group', None)
                    except Exception as error:
                        detail = _error_text(error)
                        traceback.print_exc(file=log)
                        print(detail, file=log, flush=True)
                        row.update(status='needs_review', error=detail, failed_stage=row['stage'], finished_at=now())
                        row.pop('process_group', None)
                    with lease(folder(root) / 'queue.lock'):
                        _save(root, row)


def watch(root, ident):
    path = local_file(folder(root), ident + '.log', exists=False)
    offset = 0
    while True:
        if path.exists():
            with path.open() as log:
                log.seek(offset)
                print(log.read(), end='', flush=True)
                offset = log.tell()
        row = next((row for row in status(root) if row['id'] == ident), None)
        if row is None:
            raise ValueError('Unknown job ID')
        if row['status'] in {'technical_complete', 'needs_review'}:
            # Drain final writes on the next open before returning.
            if path.exists():
                with path.open() as log:
                    log.seek(offset)
                    print(log.read(), end='', flush=True)
            print(f"\n{LABELS[row['status']]} · {row.get('error', row.get('stage', ''))}")
            return 0 if row['status'] == 'technical_complete' else 2
        time.sleep(1)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Cola stickman local: entrega y limpieza sin mantener abierto el chat.')
    parser.add_argument('--root', type=Path, default=PROJECT_ROOT, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest='command', required=True)
    enqueue_parser = sub.add_parser('enqueue', help='Entregar inputs terminados y arrancar worker desacoplado')
    enqueue_parser.add_argument('episode', type=Path)
    enqueue_parser.add_argument('--require-gpu', action='store_true', help='Bloquear antes de montar si NVENC no está accesible; no caer a CPU')
    sub.add_parser('retry').add_argument('id')
    sub.add_parser('watch').add_argument('id', nargs='?', help='Sin ID sigue el trabajo activo o el último')
    sub.add_parser('status', help='Resumen de todos los episodios')
    sub.add_parser('worker', help='Reactivar cola pendiente tras reiniciar WSL; no repite fallidos')
    sub.add_parser('start', help='Arrancar worker desacoplado sin mantener la terminal')
    args = parser.parse_args(argv)
    try:
        if args.command == 'enqueue':
            result = enqueue(args.root, args.episode, require_gpu=args.require_gpu)
        elif args.command == 'retry':
            result = retry(args.root, args.id)
        elif args.command == 'start':
            result = {'worker_pid': start_worker(args.root), 'worker_log': 'local/stickman_jobs/worker.log'}
        elif args.command == 'worker':
            return worker(args.root)
        elif args.command == 'watch':
            if args.id is None:
                rows = status(args.root)
                active = [row for row in rows if row['status'] in {'running', 'queued'}]
                if not rows:
                    print('Sin trabajos para seguir.')
                    return 0
                args.id = (active[0] if active else rows[-1])['id']
            _path(args.root, args.id)  # Validate before resolving a log path.
            return watch(args.root, args.id)
        else:
            rows = status(args.root)
            for row in rows:
                print(f"{LABELS[row['status']]} · {row['episode']} · {row.get('error') or row['stage']}\n"
                      f"  {row['id']} · {row['log']}")
                if row.get('remaining_processes'):
                    print('  Procesos anteriores vivos: cola bloqueada hasta que terminen o se revisen.')
            if not rows:
                print('Sin trabajos. Los episodios anteriores no se importan ni se limpian automáticamente.')
            return 0
        print(json.dumps({k: v for k, v in result.items() if k != 'inputs'}, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        print(_error_text(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
