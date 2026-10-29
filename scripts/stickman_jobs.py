#!/usr/bin/env python3
"""Short entrypoint for the local stickman queue; see GUIA.md."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from kitok.youtube_stickman_es.jobs import main

if __name__ == '__main__':
    raise SystemExit(main())
