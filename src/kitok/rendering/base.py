from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RenderTimings:
    fish: float = 0.0
    pexels_search: float = 0.0
    pexels_download_cache: float = 0.0
    timeline: float = 0.0
    ffmpeg: float = 0.0
    validation: float = 0.0
    total: float = 0.0


@dataclass(frozen=True)
class RenderResult:
    output: Path
    renderer: str
    timings: RenderTimings = field(default_factory=RenderTimings)
    metadata: dict = field(default_factory=dict)


class LongformRenderer(ABC):
    name: str

    @abstractmethod
    def render(self, definition, *, start_over: bool = False) -> RenderResult:
        raise NotImplementedError
