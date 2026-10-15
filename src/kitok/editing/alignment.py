from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def detect_pauses(audio: Path, ffmpeg: str = "ffmpeg") -> list[float]:
    """Local signal analysis only; returns silence midpoints, not word alignment."""
    try:
        result = subprocess.run(
            [ffmpeg, "-nostdin", "-hide_banner", "-i", str(audio), "-af", "silencedetect=noise=-35dB:d=0.22", "-f", "null", "-"],
            capture_output=True, text=True, check=True, timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    pauses, start = [], None
    for match in re.finditer(r"silence_(start|end):\s*([0-9.]+)", result.stderr):
        if match[1] == "start":
            start = float(match[2])
        elif start is not None:
            pauses.append((start + float(match[2])) / 2)
            start = None
    return pauses


def read_word_alignment(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if data.get("words") else None
