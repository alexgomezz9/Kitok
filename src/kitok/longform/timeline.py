from __future__ import annotations

import random

from .models import TimelineSlot


class TimelineError(ValueError):
    pass


def build_timeline(
    narration_duration: float,
    keywords: list[str] | tuple[str, ...],
    *,
    minimum_clip: float = 5.5,
    maximum_clip: float = 8.5,
    seed: str | int | None = None,
) -> list[TimelineSlot]:
    if narration_duration <= 0:
        raise TimelineError("Narration duration must be positive")
    if not keywords:
        raise TimelineError("At least one stock keyword is required")
    if minimum_clip <= 0 or maximum_clip < minimum_clip:
        raise TimelineError("Invalid stock clip duration range")

    generator = random.Random(seed)
    durations: list[float] = []
    remaining = float(narration_duration)
    epsilon = 1e-9
    while remaining > maximum_clip + epsilon:
        duration = generator.uniform(minimum_clip, maximum_clip)
        tail = remaining - duration
        if 0 < tail < minimum_clip:
            duration = remaining / 2
        durations.append(duration)
        remaining -= duration
    if remaining > epsilon:
        durations.append(remaining)

    slots: list[TimelineSlot] = []
    start = 0.0
    for index, duration in enumerate(durations):
        # Force the final boundary to the authoritative measured audio duration.
        if index == len(durations) - 1:
            duration = narration_duration - start
        slots.append(
            TimelineSlot(
                index=index,
                query=keywords[index % len(keywords)],
                start=start,
                duration=duration,
            )
        )
        start += duration
    return slots
