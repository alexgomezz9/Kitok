#!/usr/bin/env python3
"""Audit by default; explicitly recover a failed studio job without paid speech."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('id', help='ID del trabajo lf_… fallido o interrumpido')
    parser.add_argument('--recover', action='store_true', help='Iniciar montaje local explícitamente, sin Fish ni red')
    parser.add_argument('--narration-sha256')
    parser.add_argument('--audit-fingerprint')
    args = parser.parse_args(argv)
    from kitok.config import Settings
    from kitok.longform_studio import LongformStudio
    settings = Settings()
    if not args.recover:
        # Do not construct Application or LongformStudio: constructors create
        # folders and reconcile interrupted jobs. Audit is strictly read-only.
        studio = LongformStudio.__new__(LongformStudio)
        from kitok.config import PROJECT_ROOT
        studio.s = settings
        studio.root = settings.data_root or PROJECT_ROOT
        studio.folder = studio.root / 'content' / 'longform' / 'studio'
        studio.records = settings.state_path.parent / 'longform'
        try:
            print(json.dumps(studio.recovery_audit(args.id), indent=2, ensure_ascii=False))
            return 0
        except (ValueError, RuntimeError, OSError) as exc:
            print(f'ERROR: {exc}', file=sys.stderr)
            return 1
    if not args.narration_sha256 or not args.audit_fingerprint:
        parser.error('--recover requiere --narration-sha256 y --audit-fingerprint de la auditoría actual')
    from kitok.application import Application
    application = Application(settings)
    try:
        studio = LongformStudio(application)
        studio.recover(args.id, args.narration_sha256, args.audit_fingerprint)
        application._executor.shutdown(wait=True)
        result = studio.detail(args.id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['status'] == 'succeeded' else 1
    except (ValueError, RuntimeError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    finally:
        application.close()


if __name__ == '__main__':
    raise SystemExit(main())
