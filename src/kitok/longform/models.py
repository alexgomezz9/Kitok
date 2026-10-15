from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VisualSection:
    """Future-ready semantic timing; start/end remain optional until Fish alignment exists."""

    section: str
    keywords: tuple[str, ...]
    audio_start: float | None = None
    audio_end: float | None = None


@dataclass(frozen=True)
class TimelineSlot:
    index: int
    query: str
    start: float
    duration: float
    section: str | None = None

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass(frozen=True)
class TimelineClip:
    slot: TimelineSlot
    asset_id: int
    source: Path
    source_start: float
