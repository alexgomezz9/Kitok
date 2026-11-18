#!/usr/bin/env python3
"""Readable status for existing detached Loose Thread jobs; see GUIA.md."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from kitok.longform.jobs import main

if __name__ == '__main__':
    raise SystemExit(main())
