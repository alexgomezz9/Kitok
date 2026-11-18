"""Observe detached Loose Thread systemd jobs without controlling production."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote

from ..config import PROJECT_ROOT
from ..youtube_stickman_es.files import episode_path, local_file, replace_state

MONITOR = 'kitok-loose-thread-status'
UNIT = re.compile(r'kitok-loose-thread-[A-Za-z0-9_-]+\.service')
FILES = ('video_final.mp4', 'miniatura.png', 'titulo.txt', 'descripcion.txt',
         'etiquetas.txt', 'voz.srt', 'ajustes_youtube.txt')
LABELS = {'running': 'TRABAJANDO', 'technical_complete': 'ENTREGA GENERADA',
          'needs_review': 'REVISAR', 'unknown': 'SIN SEÑAL'}
PROPERTIES = ('LoadState', 'ActiveState', 'SubState', 'Result', 'ExecMainCode',
              'ExecMainStatus', 'MainPID', 'InvocationID', 'ExecMainStartTimestamp',
              'ExecMainExitTimestamp', 'WorkingDirectory', 'ExecStart')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def folder(root):
    path = local_file(root, 'local/loose_thread_jobs', exists=False)
    path.mkdir(parents=True, exist_ok=True)
    return path


def unit_name(value):
    value = value if value.endswith('.service') else value + '.service'
    if not UNIT.fullmatch(value) or value == MONITOR + '.service':
        raise ValueError('Expected the kitok-loose-thread-NNN systemd service name')
    return value


@contextmanager
def state_lock(root):
    path = local_file(folder(root), 'status.lock', exists=False)
    with os.fdopen(os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), 'a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def read_unit(unit):
    result = subprocess.run(['systemctl', '--user', 'show', unit,
                             '--property=' + ','.join(PROPERTIES)],
                            capture_output=True, text=True, timeout=10)
    values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if result.returncode and values.get('LoadState') != 'not-found':
        raise RuntimeError('No se pudo consultar systemd; comprobar systemctl --user status ' + unit)
    return values


def journal(unit, invocation):
    command = ['journalctl', '--user', '-u', unit, '-n', '100', '--no-pager', '-o', 'cat']
    if invocation:
        command.append('_SYSTEMD_INVOCATION_ID=' + invocation)
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError('No se pudo leer el journal de ' + unit)
    return result.stdout


def manager_failure(unit, invocation):
    # User-manager events have USER_INVOCATION_ID, unlike the process stdout.
    result = subprocess.run(['journalctl', '--user', '-u', unit, '-n', '20',
                             '--no-pager', '-o', 'json', 'USER_INVOCATION_ID=' + invocation],
                            capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError('No se pudo comprobar el resultado archivado de ' + unit)
    for line in result.stdout.splitlines():
        event = json.loads(line)
        if event.get('USER_UNIT') != unit or event.get('USER_INVOCATION_ID') != invocation:
            continue
        if (event.get('UNIT_RESULT') not in {None, 'success'}
                or event.get('EXIT_STATUS') not in {None, '0'}):
            return event.get('MESSAGE', 'El gestor registró un fallo del proceso')
    return ''


def _collected(root, episode, row):
    row['missing_delivery'] = _missing(episode)
    systemd = dict(row.get('systemd', {}))
    invocation = systemd.get('InvocationID')
    if row.get('status') == 'technical_complete':
        if row['missing_delivery']:
            row.update(status='needs_review', error='La entrega previamente generada está incompleta')
        row['observation'] = 'Unidad retirada de systemd; se conserva el último resultado observado'
        return row
    if not invocation:
        row.update(status='unknown', observation='Unidad retirada sin un InvocationID observado; revisar el journal')
        return row
    text = journal(row['unit'], invocation)
    phase, error = _diagnostic(text)
    failure = manager_failure(row['unit'], invocation)
    if systemd.get('Result') not in {None, '', 'success'}:
        failure = failure or row.get('error') or 'La última ejecución observada terminó con fallo'
    row.update(phase=phase or row.get('phase', ''), error=error or failure)
    # Never show the old running PID or fabricate an exit code after collection.
    systemd.update(ActiveState='retirada', SubState='sin dato', MainPID='0',
                   ExecMainStatus='no conservada', ExecMainExitTimestamp='')
    row['systemd'] = systemd
    if row['error'] or 'Traceback (most recent call last):' in text:
        row.update(status='needs_review', error=row['error'] or 'El intento terminó con un traceback')
        return row
    expected = 'Entrega: ' + str(episode / 'entrega')
    delivered = any(re.sub(r'\x1b\[[0-9;]*m', '', line).strip() == expected
                    for line in text.splitlines())
    if delivered and not row['missing_delivery']:
        row.update(status='technical_complete', completion_evidence='same_invocation_delivery_log',
                   phase='Entrega confirmada en el journal del mismo intento y siete archivos presentes',
                   observation='Unidad retirada; la salida numérica ya no está disponible')
    else:
        # Journal delivery can lag behind unit collection. Keep polling briefly.
        first = row.setdefault('collected_observed_at', now())
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(first)).total_seconds()
        if age < 30:
            row.update(status='unknown', observation='Unidad retirada; esperando la confirmación final del journal')
        else:
            row.update(status='needs_review', error='Unidad retirada sin entrega confirmada del mismo intento')
    return row


def _binding(root, episode, values):
    if values.get('LoadState') != 'loaded':
        raise ValueError('La unidad no está cargada; conserva el registro y consulta systemd')
    if values.get('WorkingDirectory') != str(root) or str(episode) + '/' not in values.get('ExecStart', ''):
        raise ValueError('La unidad no corresponde a este episodio y carpeta de Kitok')


def _diagnostic(text):
    # Extract actual Native progress. HTTP messages and full commands stay in the journal.
    phase = ''
    error = ''
    markers = ('Fish start', 'Fish end', 'Confirmed narration reused', 'Narration duration=',
               'Pexels search', 'Timeline end', 'Asset download/cache', 'FFmpeg',
               'Validation', 'Native final output', 'Final DONE:', 'Entrega:',
               'Plano ', 'Scene ', 'Chunk ', 'Audio ', 'Ensamblaje:', 'Validación del montaje:')
    for line in text.splitlines():
        line = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
        if any(marker in line for marker in markers) and 'HTTP Request:' not in line:
            phase = line[-500:]
        if line.startswith('ERROR:'):
            error = line[6:].strip()[:1000]
    return phase, error


def _missing(episode):
    missing = []
    for name in FILES:
        path = local_file(episode, 'entrega/' + name, exists=False)
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(name)
    return missing


def _refresh(root, row):
    row = dict(row)
    row['updated_at'] = now()
    try:
        episode = episode_path(root, Path(row['episode']))
        values = read_unit(unit_name(row['unit']))
        if values.get('LoadState') == 'not-found':
            return _collected(root, episode, row)
        _binding(root, episode, values)
        invocation = values.get('InvocationID', '')
        row.pop('collected_observed_at', None)
        row.pop('completion_evidence', None)
        phase, error = _diagnostic(journal(row['unit'], invocation))
        row.update(systemd={key: values.get(key, '') for key in PROPERTIES
                            if key not in {'ExecStart', 'WorkingDirectory'}},
                   phase=phase or 'Esperando una fase registrada por Kitok', error=error,
                   observation='', missing_delivery=_missing(episode))
        active = values.get('ActiveState')
        row['status'] = 'unknown'
        if active in {'activating', 'reloading', 'deactivating'} or (
                active == 'active' and values.get('SubState') != 'exited'):
            row['status'] = 'running'
        elif active == 'failed' or values.get('Result') not in {'', 'success'}:
            row['status'] = 'needs_review'
            row['error'] = error or ('El proceso terminó con resultado ' + values.get('Result', 'desconocido'))
        elif (values.get('ExecMainCode') == '1' and values.get('ExecMainStatus') == '0'
              and values.get('ExecMainStartTimestamp')):
            if row['missing_delivery']:
                row.update(status='needs_review', error='El proceso terminó sin una entrega completa')
            else:
                row.update(status='technical_complete', phase='Proceso finalizado y siete archivos de entrega presentes')
        else:
            row['observation'] = 'No consta una ejecución terminada correctamente'
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        row.update(status='unknown', observation=str(error))
    return row


def _summary(root, rows):
    lines = ['# Producción Loose Thread', '', 'Actualizado automáticamente: ' + now(), '',
             'ENTREGA GENERADA requiere siete archivos y salida correcta o registro final de entrega del mismo intento. '
             'La revisión audiovisual sigue pendiente. No publica ni reintenta trabajos.', '',
             'Consulta cada diez segundos mientras hay trabajo o falta señal. Cuando todos '
             'terminan conserva este resumen y detiene el temporizador. Tras reanudar un '
             'servicio, repite observe para registrar la nueva ejecución.', '']
    for row in rows:
        def clean(value):
            return str(value).replace('`', "'").replace('\r', ' ').replace('\n', ' ')
        lines.extend(['## ' + Path(row['episode']).name, '',
                      '- Estado: **' + LABELS[row['status']] + '**',
                      '- Fase observada: ' + clean(row.get('phase', 'Sin fase registrada')),
                      '- Última consulta: ' + row['updated_at'],
                      '- Servicio: `' + row['unit'] + '`',
                      '- Episodio: `' + row['episode'] + '`'])
        systemd = row.get('systemd', {})
        if systemd:
            lines.append('- Proceso: PID ' + systemd.get('MainPID', '?') + ', '
                         + systemd.get('ActiveState', '?') + '/' + systemd.get('SubState', '?')
                         + ', salida ' + systemd.get('ExecMainStatus', '?'))
            lines.append('- Inicio: ' + systemd.get('ExecMainStartTimestamp', '')
                         + '. Fin: ' + (systemd.get('ExecMainExitTimestamp') or
                                         ('en curso' if row['status'] == 'running' else 'no conservado')))
        if row.get('error'):
            lines.append('- Error: ' + clean(row['error']))
        if row.get('observation'):
            lines.append('- Observación: ' + clean(row['observation']))
        if row.get('missing_delivery'):
            lines.append('- Pendiente de entrega: ' + ', '.join(row['missing_delivery']))
        if row['status'] == 'technical_complete':
            target = quote('../../' + row['episode'] + '/entrega/', safe='/')
            lines.append('- [Abrir carpeta de entrega](' + target + ')')
        lines.extend(['- Registro completo: `journalctl --user -u ' + row['unit'] + ' --no-pager`', ''])
    if not rows:
        lines.extend(['No hay trabajos observados. Registra el servicio existente con `observe`.', ''])
    target = local_file(folder(root), 'ESTADO.md', exists=False)
    fd, temporary = tempfile.mkstemp(prefix='.summary-', dir=folder(root))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write('\n'.join(lines) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _status_locked(root):
    rows = []
    for path in sorted(folder(root).glob('kitok-loose-thread-*.json')):
        unit = unit_name(path.stem)
        row = json.loads(local_file(folder(root), path.name).read_text(encoding='utf-8'))
        if row['unit'] != unit:
            raise ValueError('El registro no corresponde a su unidad systemd')
        row = _refresh(root, row)
        replace_state(path, row)
        rows.append(row)
    _summary(root, rows)
    return rows


def status(root, *, stop_idle=False):
    root = root.resolve()
    with state_lock(root):
        rows = _status_locked(root)
        # Stop under the registration/start lock, never from an outdated snapshot.
        if stop_idle:
            stop_idle_monitor(rows)
    return rows


def start_monitor(root):
    timer = MONITOR + '.timer'
    result = subprocess.run(['systemctl', '--user', 'show', timer, '--property=LoadState', '--value'],
                            capture_output=True, text=True, timeout=10)
    if result.stdout.strip() == 'loaded':
        subprocess.run(['systemctl', '--user', 'start', timer], check=True, timeout=10)
        return
    subprocess.run(['systemd-run', '--user', '--unit=' + MONITOR,
                    '--on-active=1s', '--on-unit-active=10s', '--timer-property=AccuracySec=1s',
                    '--property=WorkingDirectory=' + str(root), '--property=Type=oneshot',
                    sys.executable, str(root / 'scripts/loose_thread_jobs.py'),
                    '--root', str(root), 'status', '--quiet'], check=True, timeout=10)


def stop_idle_monitor(rows):
    if not rows or any(row['status'] not in {'technical_complete', 'needs_review'} for row in rows):
        return
    # Only the observer timer is stopped; the production units are never changed.
    subprocess.run(['systemctl', '--user', 'stop', MONITOR + '.timer'], check=True, timeout=10)


def observe(root, episode, unit, *, monitor=True):
    root = root.resolve()
    episode = episode_path(root, episode)
    relative = episode.relative_to(root)
    if len(relative.parts) != 4 or relative.parts[:3] != ('content', 'longform', 'loose_thread'):
        raise ValueError('Choose content/longform/loose_thread/NNN_TEMA')
    unit = unit_name(unit)
    values = read_unit(unit)
    _binding(root, episode, values)
    with state_lock(root):
        path = local_file(folder(root), unit + '.json', exists=False)
        if path.exists():
            row = json.loads(path.read_text(encoding='utf-8'))
            if row['episode'] != str(relative):
                raise ValueError('El servicio ya está asociado a otro episodio')
        else:
            row = {'unit': unit, 'episode': str(relative), 'created_at': now()}
        if row.get('systemd', {}).get('InvocationID') != values.get('InvocationID'):
            row.pop('completion_evidence', None)
            row.pop('collected_observed_at', None)
            row.update(status='running', error='', systemd={
                key: values.get(key, '') for key in PROPERTIES
                if key not in {'ExecStart', 'WorkingDirectory'}})
        replace_state(path, row)
        rows = _status_locked(root)
        if monitor:
            start_monitor(root)
    return next(row for row in rows if row['unit'] == unit)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=PROJECT_ROOT, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest='command', required=True)
    attach = sub.add_parser('observe', help='Observar un servicio existente; nunca arranca el render')
    attach.add_argument('episode', type=Path)
    attach.add_argument('--unit', required=True)
    read = sub.add_parser('status', help='Actualizar y mostrar ESTADO.md')
    read.add_argument('--quiet', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'observe':
            observe(args.root, args.episode, args.unit)
        else:
            status(args.root, stop_idle=args.quiet)
        if not getattr(args, 'quiet', False):
            print((folder(args.root.resolve()) / 'ESTADO.md').read_text(encoding='utf-8'), end='')
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
