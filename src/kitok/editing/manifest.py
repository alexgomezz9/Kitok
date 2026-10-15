from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..longform.models import VisualSection


@dataclass(frozen=True)
class EditStyle:
    accent: str = "#F9BB43"
    background: str = "#122135"
    text: str = "#FFFFFF"
    font_family: str = "DejaVu Sans"

    @classmethod
    def from_mapping(cls, data: dict | None) -> EditStyle:
        data = data or {}
        allowed = {key: data[key] for key in cls.__dataclass_fields__ if key in data}
        for key in ("accent", "background", "text"):
            if key in allowed and not re.fullmatch(r"#[0-9a-fA-F]{6}", allowed[key]):
                raise ValueError(f"Invalid editing color: {key}")
        if "font_family" in allowed and not re.fullmatch(r"[\w -]{1,60}", allowed["font_family"]):
            raise ValueError("Invalid editing font_family")
        return cls(**allowed)


@dataclass(frozen=True)
class EditCue:
    kind: str
    text: str
    start: float
    end: float
    section: int
    position: str = "lower"
    # Data is copied from the narration, never fabricated statistics.
    values: tuple[str, ...] = ()


@dataclass
class EditManifest:
    version: int
    script_sha256: str
    duration: float
    alignment: dict
    sections: list[VisualSection]
    cues: list[EditCue]
    style: EditStyle = field(default_factory=EditStyle)
    audio_sha256: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def write(self, path: Path) -> None:
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)


_TAGS = re.compile(r"\[[^\]\n]{1,80}\]")
_SENTENCES = re.compile(r"[^.!?\n]+(?:[.!?]+|$)")
_NUMBER = r"(?:[$€£]\s*)?\d[\d.,]*(?:\s*(?:billion|million|trillion|thousand|millones?|mil|miles|bn|k|%|euros?|dollars?|pounds?))?"
_AMOUNT = re.compile(_NUMBER, re.I)
_DATE = re.compile(r"\b(?:1[6-9]\d{2}|20\d{2}|21\d{2})\b")
_COMPARISON = re.compile(r"\b(?:from|de|desde)\s+(" + _NUMBER + r")\s+(?:to|a|hasta)\s+(" + _NUMBER + r")", re.I)
_NAME = re.compile(r"\b[A-ZÀ-Ý][a-zà-ÿ]+(?:\s+[A-ZÀ-Ý][a-zà-ÿ]+){1,3}\b")


def clean_script(script: str) -> str:
    return _TAGS.sub("", script).strip()


def script_hash(script: str) -> str:
    return hashlib.sha256(script.encode("utf-8")).hexdigest()


def _sentences(script: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", clean_script(script)) if part.strip()]


def _token(text: str) -> str:
    return re.sub(r"[^\w]", "", text).casefold()


def _external_boundaries(sentences: list[str], duration: float, data: dict) -> list[tuple[float, float]]:
    words = data.get("words", [])
    if not words or not isinstance(words, list):
        raise ValueError("Alignment needs a non-empty words array")
    expected = [_token(word) for sentence in sentences for word in sentence.split() if _token(word)]
    actual = [_token(word.get("word", "")) for word in words]
    # Alignment belongs to this exact script; accepting unrelated ASR text shifts every cue.
    if actual != expected:
        raise ValueError("Alignment words do not match the narration transcript")
    previous = 0.0
    for word in words:
        start, end = float(word["start"]), float(word["end"])
        if not math.isfinite(start + end) or start < previous - .02 or end <= start or end > duration + .05:
            raise ValueError("Invalid alignment word timing")
        previous = end
    spans = []
    cursor = 0
    for sentence in sentences:
        count = len([word for word in sentence.split() if _token(word)])
        spans.append((float(words[cursor]["start"]), float(words[cursor + count - 1]["end"])))
        cursor += count
    return spans


def _estimated_boundaries(sentences: list[str], duration: float, pauses: list[float]) -> list[tuple[float, float]]:
    weights = [max(1, len(re.findall(r"\w+", text)) + text.count(",") * .4) for text in sentences]
    total = sum(weights)
    boundaries = [0.0]
    cumulative = 0.0
    for weight in weights[:-1]:
        cumulative += weight
        ideal = duration * cumulative / total
        candidates = [pause for pause in pauses if abs(pause - ideal) <= min(1.2, duration / len(sentences) / 3)]
        chosen = min(candidates, key=lambda pause: abs(pause - ideal)) if candidates else ideal
        # Keep a nonzero interval even when several ideals share a pause.
        boundaries.append(min(duration - .05, max(boundaries[-1] + .05, chosen)))
    boundaries.append(duration)
    return list(zip(boundaries, boundaries[1:]))


def build_edit_manifest(
    script: str,
    duration: float,
    keywords: list[str] | tuple[str, ...],
    *,
    style: dict | None = None,
    word_alignment: dict | None = None,
    pauses: list[float] | None = None,
    visual_sections: list[VisualSection] | None = None,
    audio_sha256: str | None = None,
) -> EditManifest:
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Editing needs a positive measured narration duration")
    sentences = _sentences(script)
    if not sentences:
        raise ValueError("Editing needs narration sentences")
    if word_alignment:
        spans = _external_boundaries(sentences, duration, word_alignment)
        alignment = {
            "method": str(word_alignment.get("method", "external-word-alignment")),
            "confidence": word_alignment.get("confidence"),
            "precision_seconds": word_alignment.get("precision_seconds"),
            "word_aligned": True,
            "note": "Externally supplied timings validated against this transcript; confidence is supplied by the aligner.",
        }
    else:
        spans = _estimated_boundaries(sentences, duration, pauses or [])
        alignment = {
            "method": "measured-audio-pause-weighted-sentences" if pauses else "measured-audio-weighted-sentences",
            "confidence": "estimated",
            "precision_seconds": None,
            "word_aligned": False,
            "note": "Sentence positions estimated from word counts and measured pauses. No measured word-level accuracy; inspect cues before release.",
        }
    sections = [VisualSection(text, tuple(keywords), start, end) for text, (start, end) in zip(sentences, spans, strict=True)]
    if visual_sections:
        # Operator-supplied sections must be fully timed. No implicit invented timing.
        for section in visual_sections:
            if section.audio_start is None or section.audio_end is None or not (0 <= section.audio_start < section.audio_end <= duration):
                raise ValueError("Visual sections need valid measured start/end timings")
        sections = list(visual_sections)
    cues: list[EditCue] = []
    budget = duration * .38
    covered = 0.0
    previous_end = -2.0
    for index, section in enumerate(sections):
        text = section.section
        kind, headline, position, values = "", "", "lower", ()
        compare = _COMPARISON.search(text)
        amount = _AMOUNT.search(text)
        date = _DATE.search(text)
        name = _NAME.search(text)
        if "?" in text and len(text) < 150:
            kind, headline, position = "question", text, "center"
        elif compare:
            kind, headline, position, values = "comparison", compare.group(), "center", compare.groups()
        elif amount and (any(char in amount.group() for char in "$€£%") or re.search(r"million|billion|trillion|thousand|mil|euros?|dollars?", amount.group(), re.I)):
            kind, headline, position = "amount", amount.group(), "center"
        elif date:
            kind, headline = "date", date.group()
        elif name:
            kind, headline, position = "name", name.group(), "side"
        if not kind:
            continue
        start = float(section.audio_start)
        end = float(section.audio_end)
        duration_needed = min(4.0 if kind != "question" else 5.0, max(1.4, len(headline) / 17))
        anchor = start + .15
        target_tokens = [_token(word) for word in headline.split() if _token(word)]
        section_tokens = [_token(word) for word in text.split() if _token(word)]
        token_offset = next((offset for offset in range(len(section_tokens)) if section_tokens[offset:offset + len(target_tokens)] == target_tokens), 0)
        if word_alignment and not visual_sections:
            word_offset = sum(len([word for word in sentence.split() if _token(word)]) for sentence in sentences[:index])
            anchor = float(word_alignment["words"][word_offset + token_offset]["start"])
        elif token_offset:
            # Explicitly approximate inside the sentence when no provider timing exists.
            anchor = start + (end - start) * token_offset / max(1, len(section_tokens))
        cue_start = max(anchor, previous_end + .8)
        cue_end = min(end, cue_start + duration_needed)
        if cue_end - cue_start < 1.1 or covered + cue_end - cue_start > budget:
            continue
        cues.append(EditCue(kind, headline, cue_start, cue_end, index, position, tuple(values)))
        covered += cue_end - cue_start
        previous_end = cue_end
    return EditManifest(1, script_hash(script), duration, alignment, sections, cues, EditStyle.from_mapping(style), audio_sha256)


def load_or_create_manifest(path: Path, script: str, duration: float, keywords, **kwargs) -> EditManifest:
    if not path.exists():
        result = build_edit_manifest(script, duration, keywords, **kwargs)
        result.write(path)
        return result
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or data.get("script_sha256") != script_hash(script) or abs(float(data["duration"]) - duration) > .05:
        raise ValueError("Edit manifest belongs to another script/audio duration; move it aside before rebuilding")
    if kwargs.get("audio_sha256") and data.get("audio_sha256") != kwargs["audio_sha256"]:
        raise ValueError("Edit manifest belongs to another audio fingerprint")
    sections = [VisualSection(**{**section, "keywords": tuple(section["keywords"])}) for section in data["sections"]]
    cues = [EditCue(**{**cue, "values": tuple(cue.get("values", []))}) for cue in data["cues"]]
    for cue in cues:
        if not (0 <= cue.start < cue.end <= duration) or len(cue.text) > 200 or cue.kind not in {"question", "comparison", "amount", "date", "name"} or cue.position not in {"lower", "center", "side"}:
            raise ValueError("Invalid editable cue")
    return EditManifest(1, data["script_sha256"], duration, data["alignment"], sections, cues, EditStyle.from_mapping(data.get("style")), data.get("audio_sha256"))
