"""Run the repository's deterministic gates, stopping at the first failure."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


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
    parser.add_argument('--e2e', action='store_true', help='Also run the isolated browser fixtures.')
    args = parser.parse_args(argv)
    env = dict(os.environ)
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
    if not shutil.which('npm'):
        print('npm is required. Install Node 22.12+ or 24.', file=sys.stderr)
        return 1
    steps = [
        ('Source hygiene', [sys.executable, 'scripts/check_repository.py']),
        ('Current documentation and public examples', [sys.executable, 'scripts/check_documentation.py']),
        ('Python tests (external network blocked by test fixtures)', [sys.executable, '-m', 'pytest', '-q']),
        ('Frontend tests', ['npm', '--prefix', 'frontend', 'test']),
        ('TypeScript and frontend build', ['npm', '--prefix', 'frontend', 'run', 'build']),
        ('Working whitespace', ['git', 'diff', '--check']),
        ('Staged whitespace', ['git', 'diff', '--cached', '--check']),
    ]
    if args.e2e:
        env['KITOK_E2E_UNAVAILABLE_DELIVERY'] = '1'
        steps.append(('Isolated browser workflows', ['npm', '--prefix', 'frontend', 'run', 'test:e2e']))
    return run_steps(steps, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
