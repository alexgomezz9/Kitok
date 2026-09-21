from __future__ import annotations
import json, re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from .profiles import VOICES, VISUAL_PROFILES, CHARACTER_PROFILES, DIALOGUE_PRESETS

ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

class DialogueTurn(BaseModel):
    speaker: str
    text: str = Field(min_length=1)

    @field_validator("speaker", "text")
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("speaker")
    @classmethod
    def known_speaker(cls, value):
        if value not in VOICES or VOICES[value].provider != "fish":
            raise ValueError(f"Dialogue speaker requires a Fish voice profile: {value}")
        return value


class ContentItem(BaseModel):
    id: str
    subject: str = Field(min_length=1, max_length=500)
    script: str = Field(default="", max_length=12000)
    keywords: list[str] = Field(min_length=1, max_length=20)
    caption: str = Field(default="", max_length=2200)
    youtube_title: str | None = Field(default=None, max_length=100)
    editorial_status: str = "active"
    publish_at: datetime | None = None
    platforms: list[str] = Field(default_factory=lambda: ["tiktok","instagram","youtube"])
    content_format: Literal["explainer", "dialogue"] = "explainer"
    voice_profile: str = "alvaro"
    dialogue: list[DialogueTurn] | None = None
    dialogue_preset: str | None = None
    visual_profile: str = "pexels"
    background_seed: str | None = Field(default=None, max_length=100)
    visual_seed: str | None = Field(default=None, max_length=100)
    background_file: str | None = None
    schedule_enabled: bool = True
    character_profile: str | None = None

    @model_validator(mode="after")
    def validate_generation(self):
        if self.schedule_enabled and self.publish_at is None:
            raise ValueError("Scheduled content requires publish_at")
        if self.voice_profile not in VOICES:
            raise ValueError(f"Unknown voice profile: {self.voice_profile}")
        if self.visual_profile not in VISUAL_PROFILES:
            raise ValueError(f"Unknown visual profile: {self.visual_profile}")
        if self.character_profile is not None and self.character_profile not in CHARACTER_PROFILES:
            raise ValueError(f"Unknown character profile: {self.character_profile}")
        if self.dialogue_preset is not None and self.dialogue_preset not in DIALOGUE_PRESETS:
            raise ValueError(f"Unknown dialogue preset: {self.dialogue_preset}")
        if self.content_format == "dialogue":
            if self.voice_profile != "alvaro":
                raise ValueError("Dialogue uses each turn's speaker; leave voice_profile at its default")
            if not self.dialogue or len(self.dialogue) < 2:
                raise ValueError("Dialogue requires at least two valid turns")
            if self.script:
                raise ValueError("Dialogue script is derived from turns; leave script empty")
            if self.dialogue_preset and any(t.speaker not in DIALOGUE_PRESETS[self.dialogue_preset] for t in self.dialogue):
                raise ValueError("Dialogue speaker is not in the selected preset")
        elif len(self.script) < 20:
            raise ValueError("Explainer script must contain at least 20 characters")
        elif self.dialogue or self.dialogue_preset is not None or self.character_profile is not None:
            raise ValueError("Explainers use their script and do not accept dialogue configuration")
        elif self.visual_profile == "pexels":
            if self.background_seed is not None or self.visual_seed is not None or self.background_file is not None:
                raise ValueError("Pexels explainers do not accept local background configuration")
        elif self.visual_profile != "random" or self.voice_profile != "rick_es":
            raise ValueError("Local explainers currently require voice_profile='rick_es' and visual_profile='random'")
        return self

    @field_validator("background_file")
    @classmethod
    def valid_background_file(cls, value):
        if value is not None and (Path(value).name != value or value in {".", ".."}):
            raise ValueError("Background must be a filename within its pool")
        return value

    @field_validator("platforms")
    @classmethod
    def valid_platforms(cls, value):
        if not value or set(value) - {"tiktok", "instagram", "youtube"}:
            raise ValueError("Choose valid platforms")
        return list(dict.fromkeys(value))

    @property
    def effective_script(self) -> str:
        return "\n".join(turn.text for turn in self.dialogue or []) if self.content_format == "dialogue" else self.script

    @field_validator("editorial_status")
    @classmethod
    def validate_editorial_status(cls, value):
        if value not in {"active", "skipped", "archived"}:
            raise ValueError("editorial_status must be active, skipped or archived")
        return value

    @field_validator("id")
    @classmethod
    def validate_id(cls, v):
        v = v.strip()
        if not ID_RE.fullmatch(v):
            raise ValueError("id must contain only letters, numbers, '_' or '-'")
        return v

    @field_validator("subject","script","caption")
    @classmethod
    def strip_text(cls, v): return v.strip()

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, values):
        out, seen = [], set()
        for raw in values:
            term = raw.strip()
            if term and term.casefold() not in seen:
                seen.add(term.casefold()); out.append(term)
        if not out:
            raise ValueError("at least one keyword is required")
        return out

    @model_validator(mode="before")
    @classmethod
    def default_schedule_from_publish_at(cls, values):
        if isinstance(values, dict) and "schedule_enabled" not in values:
            values = dict(values)
            values["schedule_enabled"] = values.get("publish_at") is not None
        return values

    @field_validator("publish_at")
    @classmethod
    def require_timezone(cls, v):
        if v is None:
            return v
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("publish_at must include timezone offset, e.g. +02:00")
        return v

class ContentQueue(BaseModel):
    items: list[ContentItem]

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [x.id for x in self.items]
        duplicates = sorted({x for x in ids if ids.count(x) > 1})
        if duplicates:
            raise ValueError(f"duplicate ids: {', '.join(duplicates)}")
        return self

    @classmethod
    def load(cls, path: Path):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("content_queue.json must contain a JSON array")
        return cls(items=[ContentItem.model_validate(x) for x in raw])

    def by_id(self): return {x.id:x for x in self.items}

class ValidationResult(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duration: float|None = None
    width: int|None = None
    height: int|None = None
    video_codec: str|None = None
    audio_codec: str|None = None
    fps: float|None = None
    pixel_format: str|None = None
    video_bitrate: int|None = None
    audio_bitrate: int|None = None
    audio_sample_rate: int|None = None
    audio_profile: str|None = None
    audio_channels: int|None = None
    file_size: int|None = None
    normalized: bool = False

class MPTTask(BaseModel):
    task_id: str
    state: int|None = None
    progress: int|float|None = None
    videos: list[str] = Field(default_factory=list)
    error: str|None = None
    failed_stage: str|None = None
    raw: dict[str,Any] = Field(default_factory=dict)
