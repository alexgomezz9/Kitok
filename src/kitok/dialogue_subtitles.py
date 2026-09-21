"""Replaceable local timing strategy for short dialogue subtitle cues."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


WEAK_ENDINGS = {
    "un", "una", "unos", "unas", "el", "la", "los", "las", "de", "del",
    "a", "en", "con", "por", "para", "que", "y", "o",
}
ARTICLES = {"un", "una", "unos", "unas", "el", "la", "los", "las"}


def _word(token: str) -> str:
    return re.sub(r"^[^\wáéíóúüñ]+|[^\wáéíóúüñ]+$", "", token.strip().casefold())


@dataclass(frozen=True)
class SubtitleCue:
    start: float
    end: float
    text: str


def _chunks(text: str, max_chars: int, min_words: int, max_words: int) -> list[str]:
    # Each token owns its preceding whitespace, so joining the cues reconstructs
    # the original text exactly (including punctuation and internal line breaks).
    words = re.findall(r"\s*\S+", text)
    if not words:
        return [text]
    trailing = text[len("".join(words)):]
    count = len(words)
    best: list[tuple[float, list[str]] | None] = [None] * (count + 1)
    best[count] = (0.0, [])
    for start in range(count - 1, -1, -1):
        options = []
        for end in range(start + 1, min(count, start + max_words) + 1):
            chunk = "".join(words[start:end])
            visible = chunk.strip()
            length = end - start
            if len(visible) > max_chars and length > 1:
                continue
            if best[end] is None:
                continue
            cost = best[end][0]
            cost += 10 if length < min_words and count > 1 else 0
            cost += abs(length - 3.5) * 0.35
            if len(visible) > max_chars:
                cost += 12
            if end < count:
                if re.search(r"[.!?]$", visible):
                    cost -= 3
                elif re.search(r"[;:,]$", visible):
                    cost -= 1.2
                else:
                    cost += 0.4
                if _word(words[end - 1]) in WEAK_ENDINGS:
                    cost += 7
                if count - end == 1:
                    cost += 5
                # Keep a short subject together with the word that follows it.
                # This avoids splits such as "Los pulpos" and
                # "Morty, en Venus" without rewriting or parsing the text.
                first = _word(words[start])
                if start == 0 and length == 2 and first in ARTICLES:
                    cost += 3
                if (start == 0 and length <= 3 and words[0].strip().endswith(",")
                        and len(words) > 1 and _word(words[1]) in WEAK_ENDINGS):
                    cost += 3
            options.append((cost, [chunk] + best[end][1]))
        if options:
            best[start] = min(options, key=lambda option: option[0])
    if best[0] is None:
        raise ValueError("Could not split dialogue subtitle")
    chunks = best[0][1]
    chunks[-1] += trailing
    return chunks


def dialogue_cues(timeline, *, max_chars: int = 26, min_words: int = 2,
                  max_words: int = 5) -> list[SubtitleCue]:
    if max_chars < 4 or min_words < 1 or max_words < min_words:
        raise ValueError("Invalid dialogue subtitle limits")
    cues = []
    for turn in timeline:
        parts = _chunks(turn.text, max_chars, min_words, max_words)
        start_ms, end_ms = round(turn.start * 1000), round(turn.end * 1000)
        span = end_ms - start_ms
        if span < len(parts):
            raise ValueError("Dialogue turn too short for subtitle cues")
        weights = [max(1, len(part.strip())) for part in parts]
        total = sum(weights)
        cursor, used = start_ms, 0
        for index, (part, weight) in enumerate(zip(parts, weights)):
            used += weight
            # Reserve at least one millisecond for every following cue.
            stop = end_ms if index == len(parts) - 1 else min(
                end_ms - (len(parts) - index - 1),
                max(cursor + 1, start_ms + round(span * used / total)),
            )
            cues.append(SubtitleCue(cursor / 1000, stop / 1000, part))
            cursor = stop
    return cues


def write_subtitles(timeline, destination: Path, *, max_chars: int = 26,
                    min_words: int = 2, max_words: int = 5) -> Path:
    def stamp(seconds):
        milliseconds = round(seconds * 1000)
        h, rem = divmod(milliseconds, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, ms = divmod(rem, 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    blocks = []
    for index, cue in enumerate(dialogue_cues(timeline, max_chars=max_chars,
                                               min_words=min_words, max_words=max_words), 1):
        rendered = cue.text
        blocks.append(f"{index}\n{stamp(cue.start)} --> {stamp(cue.end)}\n{rendered}\n")
    destination.write_text("\n".join(blocks), encoding="utf-8")
    return destination
