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


def build_semantic_timeline(
    sections, narration_duration: float, keywords, *, minimum_clip: float = 5.5, maximum_clip: float = 8.5,
) -> list[TimelineSlot]:
    """Cut at sentence boundaries where practical, keeping measured audio coverage."""
    if not sections:
        return build_timeline(narration_duration, keywords, minimum_clip=minimum_clip, maximum_clip=maximum_clip, seed="semantic")
    if minimum_clip <= 0 or maximum_clip < minimum_clip or narration_duration <= 0 or not keywords:
        raise TimelineError("Invalid semantic timeline inputs")
    # Include boundaries near a sensible shot length rather than cutting each short phrase.
    boundaries = [0.0]
    section_boundaries = sorted({float(section.audio_end) for section in sections if section.audio_end is not None and 0 < section.audio_end < narration_duration})
    while narration_duration - boundaries[-1] > maximum_clip:
        start = boundaries[-1]
        candidates = [value for value in section_boundaries if minimum_clip <= value - start <= maximum_clip]
        chosen = min(candidates, key=lambda value: abs((minimum_clip + maximum_clip) / 2 - (value - start))) if candidates else start + (minimum_clip + maximum_clip) / 2
        if 0 < narration_duration - chosen < minimum_clip:
            chosen = start + (narration_duration - start) / 2
        boundaries.append(chosen)
    boundaries.append(narration_duration)
    slots = []
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
        overlap = [section for section in sections if section.audio_start is not None and section.audio_end is not None and section.audio_start < end and section.audio_end > start]
        text = " ".join(section.section for section in overlap)
        explicit_keywords = [keyword for section in overlap for keyword in section.keywords]
        matches = [keyword for keyword in dict.fromkeys(explicit_keywords) if any(token.casefold() in text.casefold() for token in keyword.split() if len(token) > 2)]
        query = matches[0] if matches else keywords[index % len(keywords)]
        slots.append(TimelineSlot(index, query, start, end - start, text))
    return slots
