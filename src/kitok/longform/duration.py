"""Runtime policy for production episodes of Loose Thread."""

from __future__ import annotations

import math
from pathlib import Path

from ..editing.manifest import clean_script
from .episodes import EPISODE_NUMBER, EPISODE_PATH


LOOSE_THREAD_MIN_SECONDS = 480
LOOSE_THREAD_TARGET_SECONDS = (9 * 60, 12 * 60)
# Västberga: 848 words, 282.6 seconds of speech at the channel's usual speed.
_REFERENCE_WORDS_PER_MINUTE = 180
_SLOW_WORDS_PER_MINUTE = 150
_REFERENCE_VOICE_RATE = 0.98


def is_numbered_loose_thread_episode(episode: Path, root: Path) -> bool:
    return (episode.parent == root / EPISODE_PATH / "loose_thread"
            and EPISODE_NUMBER.fullmatch(episode.name) is not None)


def loose_thread_estimate(script: str, voice_rate: float) -> tuple[int, float, float]:
    words = len(clean_script(script).split())
    word_seconds = words * 60 * _REFERENCE_VOICE_RATE / voice_rate
    return words, word_seconds / _REFERENCE_WORDS_PER_MINUTE, word_seconds / _SLOW_WORDS_PER_MINUTE


def require_loose_thread_runtime(duration: float | None, label: str) -> None:
    if duration is None or not math.isfinite(duration):
        raise ValueError(f"Loose Thread {label} has no measurable duration")
    if duration <= LOOSE_THREAD_MIN_SECONDS:
        raise ValueError(f"Loose Thread {label} must exceed {LOOSE_THREAD_MIN_SECONDS} s; measured {duration:.3f} s")
