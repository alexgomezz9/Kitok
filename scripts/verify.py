"""Run the repository's deterministic gates, stopping at the first failure."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

PYTHON_TESTS = [sys.executable, '-m', 'pytest', '-q']
PROGRESS = re.compile(rb'\.+(?:\s+\[\s*[0-9]{1,3}%\])?')
PASSED = re.compile(rb'([1-9][0-9]* passed in [0-9.]+s)(?: \([0-9:]+\))?')


def summarize_success(raw, rtk, env):
    lines = raw.strip().splitlines()
    footer = PASSED.fullmatch(lines[-1]) if lines else None
    if footer is None or any(not PROGRESS.fullmatch(line) for line in lines[:-1]):
        return None
    try:
        filtered = subprocess.run([rtk, 'pipe', '--filter', 'pytest'], input=raw, capture_output=True,
                                  env={**env, 'RTK_DB_PATH': ':memory:', 'RTK_TEE': '0'}, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    summary = filtered.stdout.strip()
    if filtered.returncode == 0 and not filtered.stderr and summary == b'Pytest: ' + footer[1]:
        return summary
    return None


def run_check(command, *, cwd, env, timeout):
    options = {'cwd': cwd, 'env': env, 'timeout': timeout}
    if command != PYTHON_TESTS or sys.stdout.isatty():
        return subprocess.run(command, **options)
    rtk = shutil.which('rtk', path=env.get('PATH'))
    if rtk is None:
        return subprocess.run(command, **options)
    # Execute the exact test command once. Pass all diagnostics through on failure
    # or on any nonstandard output. RTK only sees validated success output.
    with tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, **options)
        except (OSError, subprocess.TimeoutExpired):
            output.seek(0)
            shutil.copyfileobj(output, sys.stdout.buffer)
            sys.stdout.buffer.flush()
            raise
        output.seek(0)
        if result.returncode == 0:
            raw = output.read(131073)
            summary = summarize_success(raw, rtk, env) if len(raw) <= 131072 else None
            if summary is not None:
                print(summary.decode('ascii'), flush=True)
                return result
        output.seek(0)
        shutil.copyfileobj(output, sys.stdout.buffer)
        sys.stdout.buffer.flush()
        return result


def run_steps(steps, *, run=subprocess.run, env=None, cwd=ROOT):
    for name, command in steps:
        print(f'\n[{name}]', flush=True)
        try:
            result = run(command, cwd=cwd, env=env, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as error:
            print(f'{name} could not complete: {type(error).__name__}', file=sys.stderr)
            return 1
        if result.returncode:
            print(f'{name} failed (exit {result.returncode}).', file=sys.stderr)
            return result.returncode if result.returncode > 0 else 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--e2e', action='store_true', help='Also run the isolated browser fixtures.')
    mode.add_argument('--python-only', action='store_true', help='Run the Python suite only.')
    args = parser.parse_args(argv)
    env = dict(os.environ)
    local_node = ROOT / '.tools' / 'node' / 'bin'
    if all(shutil.which(tool, path=str(local_node)) for tool in ('node', 'npm')):
        env['PATH'] = str(local_node) + os.pathsep + env.get('PATH', os.defpath)
    env['PYTHONPATH'] = str(ROOT / 'src')
    # Test subprocesses do not need the operator's exported provider credentials.
    for key in list(env):
        if key.startswith(('FISH_', 'PEXELS_', 'BUFFER_', 'CLOUDINARY_', 'YOUTUBE_', 'GOOGLE_')) or key == 'MPT_API_KEY':
            env.pop(key)
    env['PUBLISH_ENABLED'] = 'false'
    # cinema-setup installs the shared browser here; honour an explicit override
    # and otherwise reuse it instead of requiring a duplicate download.
    if 'PLAYWRIGHT_BROWSERS_PATH' not in env and (ROOT / '.tools' / 'browsers').is_dir():
        env['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / '.tools' / 'browsers')
    python_step = ('Python tests (external network blocked by test fixtures)', PYTHON_TESTS)
    if args.python_only:
        return run_steps([python_step], run=run_check, env=env)
    if not all(shutil.which(tool, path=env.get('PATH')) for tool in ('node', 'npm')):
        print('npm is required. Install Node 22.12+ or 24.', file=sys.stderr)
        return 1
    steps = [
        ('Source hygiene', [sys.executable, 'scripts/check_repository.py']),
        ('Current documentation and public examples', [sys.executable, 'scripts/check_documentation.py']),
        python_step,
        ('Frontend tests', ['npm', '--prefix', 'frontend', 'test']),
        ('TypeScript and frontend build', ['npm', '--prefix', 'frontend', 'run', 'build']),
        ('Working whitespace', ['git', 'diff', '--check']),
        ('Staged whitespace', ['git', 'diff', '--cached', '--check']),
    ]
    if args.e2e:
        env['KITOK_E2E_UNAVAILABLE_DELIVERY'] = '1'
        steps.append(('Isolated browser workflows', ['npm', '--prefix', 'frontend', 'run', 'test:e2e']))
    return run_steps(steps, run=run_check, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
