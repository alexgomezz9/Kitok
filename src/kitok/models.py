from __future__ import annotations
import json, re
from datetime import datetime
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field, field_validator, model_validator

ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

class ContentItem(BaseModel):
    id: str
    subject: str = Field(min_length=1, max_length=500)
    script: str = Field(min_length=20, max_length=12000)
    keywords: list[str] = Field(min_length=1, max_length=20)
    caption: str = Field(default="", max_length=2200)
    publish_at: datetime
    platforms: list[str] = Field(default_factory=lambda: ["tiktok","instagram","youtube"])

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

    @field_validator("publish_at")
    @classmethod
    def require_timezone(cls, v):
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

class MPTTask(BaseModel):
    task_id: str
    state: int|None = None
    progress: int|float|None = None
    videos: list[str] = Field(default_factory=list)
    error: str|None = None
    failed_stage: str|None = None
    raw: dict[str,Any] = Field(default_factory=dict)
