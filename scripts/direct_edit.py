#!/usr/bin/env python3
"""Prepare a local plan from an explicit brief; never render, call APIs, or generate voice."""
from pathlib import Path
import argparse
import json
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from kitok.editing.director import DirectorBrief, compile_brief, load_records
from kitok.editing.storyboard import project_file


def write_new_json(root, target, value):
    target = root / target if not target.is_absolute() else target
    if target.is_symlink():
        raise ValueError('Output cannot be a symlink')
    target = target.resolve()
    if not target.is_relative_to(root.resolve()) or target.exists() or target.suffix.lower() != '.json':
        raise ValueError('Output must be a new file inside the project')
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix='.director-', suffix='.json', dir=target.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        # Exclusive atomic publication: never overwrite a file created concurrently.
        os.link(name, target)
    finally:
        Path(name).unlink(missing_ok=True)
    return target


def main(argv=None, *, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('brief', type=Path)
    parser.add_argument('--output', required=True, type=Path,
                        help='New plan JSON, written only when every beat can be resolved')
    parser.add_argument('--ffprobe', default='ffprobe')
    args = parser.parse_args(argv)
    try:
        brief_path = project_file(root, str(args.brief))
        brief = DirectorBrief.model_validate_json(brief_path.read_text(encoding='utf-8'))
        result = compile_brief(brief, load_records(root), root=root, ffprobe_binary=args.ffprobe)
        if result['status'] == 'ready':
            plan_path = write_new_json(root, args.output, result['plan'])
            print(json.dumps({'status': 'ready', 'plan_path': str(plan_path),
                              'decisions': result['decisions'], 'provider_requests': 0}, indent=2))
            return 0
        print(json.dumps(result, indent=2))
        return 2
    except (ValueError, OSError, RuntimeError) as error:
        print(f'Director preparation failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
