#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v ffprobe >/dev/null 2>&1; then
  echo "WARNING: ffprobe not found. Install with: sudo apt update && sudo apt install -y ffmpeg"
fi
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
[ -f .env ] || cp .env.example .env
python main.py --dry-run || true
echo "Setup complete. Edit .env, start the MPT API in Windows, then run: python main.py --check-mpt"
