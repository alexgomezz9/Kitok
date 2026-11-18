"""Resolve long-form sound cues against confirmed narration timing."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ..audio_library import SoundEvent, SoundKind
from .storyboard import phrase_time
from .visual_cues import VisualAnchor, anchor_word_index, script_words


class AnchoredSoundEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    anchor: VisualAnchor
    kind: SoundKind = "soft_tick"


def parse_sound_event(value, script: str) -> SoundEvent | AnchoredSoundEvent:
    if not isinstance(value, dict) or "anchor" not in value:
        return SoundEvent.model_validate(value)
    event = AnchoredSoundEvent.model_validate(value)
    if not script_words(event.anchor.phrase):
        raise ValueError("Sound anchor needs spoken words")
    try:
        anchor_word_index(script, event.anchor)
    except ValueError as error:
        raise ValueError(f"Sound anchor not found in the script: {event.anchor.phrase}") from error
    return event


def resolve_sound_events(events, *, editing, word_alignment, duration: float) -> list[dict]:
    from .motion import provider_sections

    anchored = any(isinstance(event, AnchoredSoundEvent) for event in events)
    if anchored and (editing is None or provider_sections(editing.sections, word_alignment, duration) is None):
        raise ValueError("Anchored sound events require word timing that matches the narration. Use explicit seconds to place effects without word timing.")

    resolved = []
    for event in events:
        if isinstance(event, AnchoredSoundEvent):
            time, _ = phrase_time(word_alignment["words"], event.anchor.phrase,
                                  occurrence=event.anchor.occurrence)
            event = SoundEvent(time=time, kind=event.kind)
        resolved.append(event.model_dump())
    return resolved
