import io
import json
import threading

import pytest

from kitok.youtube_stickman_es import __main__ as cli
from kitok.youtube_stickman_es.progress import TerminalProgress


@pytest.mark.parametrize('quiet', [False, True])
def test_cli_progress_keeps_stdout_json_and_quiet_hides_only_progress(monkeypatch, capsys, quiet):
    def execute(*args, on_stage, **options):
        on_stage('Voz existente: validando')
        return {'status': 'ready_to_render'}
    monkeypatch.setattr(cli, 'execute', execute)
    assert cli.main(['prepare', 'episode'] + (['--quiet'] if quiet else [])) == 0
    out = capsys.readouterr()
    assert json.loads(out.out) == {'status': 'ready_to_render'}
    assert ('Voz existente: validando' in out.err) is not quiet
    if quiet:
        assert not out.err


def test_cli_failure_never_announces_completion(monkeypatch, capsys):
    def execute(*args, on_stage, **options):
        on_stage('Alineación: calculando cortes')
        raise ValueError('Invalid alignment')
    monkeypatch.setattr(cli, 'execute', execute)
    assert cli.main(['produce', 'episode']) == 2
    out = capsys.readouterr()
    assert not out.out
    assert 'Alineación: calculando cortes' in out.err
    assert 'Comando terminado' not in out.err
    assert json.loads(out.err.splitlines()[-1])['status'] == 'blocked'


def test_heartbeat_reports_current_phase_and_stops():
    written = threading.Event()
    class Stream(io.StringIO):
        def write(self, text):
            if 'En curso:' in text:
                written.set()
            return super().write(text)
    stream = Stream()
    with TerminalProgress(interval=.01, stream=stream) as progress:
        progress('Mezcla local\n' + 'x' * 500)
        assert written.wait(2)
    assert not progress.thread.is_alive()
    lines = stream.getvalue().splitlines()
    assert all(len(line) <= 308 for line in lines)
    assert 'Mezcla local' in lines[-1]
