"""Check tracked source hygiene without reading or printing local credentials."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = (
    re.compile(r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def forbidden_path(name: str) -> bool:
    path = PurePosixPath(name)
    if name in {'state/.gitkeep', 'logs/.gitkeep', 'outputs/generated/.gitkeep',
                'outputs/failed/.gitkeep', 'outputs/ready/.gitkeep', 'outputs/ready-phone/.gitkeep'}:
        return False
    if path.name.startswith('.env') and path.name != '.env.example':
        return True
    if any(part in {'.codex-work', '.venv', '.tools', 'node_modules', '__pycache__'}
           or part.endswith('.egg-info') for part in path.parts):
        return True
    if path.parts[0] in {'local', 'state', 'outputs', 'cache', 'logs'}:
        return True
    if path.parts[0] == 'content' and name != 'content/README.md':
        return True
    if name in {'content_queue.json', 'content_queue_backup.json', 'content_queue_before_test.json'}:
        return True
    if name.startswith(('frontend/dist/', 'frontend/test-results/', 'frontend/playwright-report/')):
        return True
    return path.suffix.lower() in {'.mp4', '.mp3', '.mov', '.mkv', '.webm', '.pyc', '.tsbuildinfo'}


def inspect_file(root: Path, name: str) -> list[str]:
    if forbidden_path(name):
        # Do not read files classified as private, even when accidentally tracked.
        return [f'{name}: operator data, private configuration or generated output is tracked']
    path = root / name
    if path.is_symlink():
        return [f'{name}: source symlinks require explicit review']
    if not path.is_file():
        return [f'{name}: tracked file is missing']
    return inspect_content(name, path.read_bytes())


def inspect_content(name: str, data: bytes) -> list[str]:
    if len(data) > 2_000_000:
        return [f'{name}: source file exceeds 2 MB; review before publication']
    source = data.decode('utf-8', errors='replace')
    return [f'{name}:{number}: possible credential signature (value hidden)'
            for number, line in enumerate(source.splitlines(), 1)
            if any(pattern.search(line) for pattern in SECRET_PATTERNS)]


def inspect_index(root: Path, name: str, mode: str, oid: str) -> list[str]:
    if forbidden_path(name):
        return [f'{name}: operator data, private configuration or generated output is staged']
    if mode not in {'100644', '100755'}:
        return [f'{name}: staged source must be a regular file (mode {mode})']
    size = subprocess.run(['git', 'cat-file', '-s', oid], cwd=root, capture_output=True, check=True)
    if int(size.stdout) > 2_000_000:
        return [f'{name}: staged source exceeds 2 MB; review before publication']
    blob = subprocess.run(['git', 'cat-file', 'blob', oid], cwd=root, capture_output=True, check=True)
    return inspect_content(name, blob.stdout)


def main() -> int:
    result = subprocess.run(['git', 'ls-files', '--stage', '-z'], cwd=ROOT, capture_output=True)
    if result.returncode:
        print('Repository checks require a Git checkout.', file=sys.stderr)
        return 1
    findings = []
    try:
        for entry in result.stdout.split(b'\0'):
            if not entry:
                continue
            metadata, raw_name = entry.split(b'\t', 1)
            mode, oid, stage = metadata.decode().split()
            name = raw_name.decode('utf-8')
            if stage != '0':
                findings.append(f'{name}: unresolved index conflict')
                continue
            # Inspect exactly what a commit would contain as well as current files.
            findings.extend(inspect_index(ROOT, name, mode, oid))
            findings.extend(inspect_file(ROOT, name))
    except (OSError, UnicodeError, ValueError, subprocess.CalledProcessError) as error:
        print(f'Repository inspection failed: {type(error).__name__}', file=sys.stderr)
        return 1
    if findings:
        print('\n'.join(dict.fromkeys(findings)), file=sys.stderr)
        return 1
    print('Index and working source hygiene passed. Signature checks are not an exhaustive secret audit.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
