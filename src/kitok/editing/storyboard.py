"""Validated editorial decisions: assets and claims are explicit, never regex effects."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EditorialAsset(PlanModel):
    path: str = Field(min_length=1, max_length=2000)
    description: str = Field(min_length=1, max_length=600)
    source_url: str | None = Field(default=None, max_length=2000)
    credit: str | None = Field(default=None, max_length=300)
    usage: Literal["illustration", "document", "provided"] = "illustration"
    sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


from .motion_components import MotionDesign


class EditorialScene(PlanModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,70}$")
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    intention: str = Field(min_length=1, max_length=600)
    spoken_claim: str = Field(min_length=1, max_length=1500)
    evidence_url: str | None = Field(default=None, max_length=2000)
    asset: str | None = None
    source_start: float = Field(default=0, ge=0, allow_inf_nan=False)
    graphic: Literal["identity", "metric", "hidden_information", "motion"] | None = None
    graphic_data: dict = Field(default_factory=dict)
    composition: Literal['table', 'records', 'photo'] | None = None
    composition_data: dict = Field(default_factory=dict)
    motion: Literal["none", "push", "pan"] = "none"
    transition: Literal["cut", "fade", "dissolve", "wipe"] = "cut"
    motion_design: MotionDesign | None = None
    headline: str | None = Field(default=None, max_length=95)
    kicker: str | None = Field(default=None, max_length=80)
    palette: Literal["ivory", "green"] | None = None
    headline_style: Literal["caption", "impact"] = "caption"

    @model_validator(mode="after")
    def valid_scene(self):
        if self.end - self.start < .4 - 1e-6:
            raise ValueError("A scene needs at least 0.4 seconds")
        if self.graphic == 'motion' and self.motion_design is None:
            raise ValueError('A motion plate needs an explicit motion design')
        if self.motion_design and (self.motion_design.delay >= self.end-self.start-.3):
            raise ValueError('Motion delay must leave a readable interval')
        if self.motion_design and self.composition:
            raise ValueError('Motion design uses stock or a motion plate, not legacy 3D')
        if self.composition:
            from .cinema import CinemaData
            data = CinemaData.model_validate(self.composition_data)
            if self.composition == 'table' and data.engine == 'three' and data.mode not in {
                'opponent', 'aggression', 'loss', 'private', 'exposed', 'question'
            }:
                raise ValueError('Unsupported 3D table mode')
            if self.source_start:
                raise ValueError('Generated compositions require source_start=0')
            if self.graphic or (self.composition == 'photo') != bool(self.asset):
                raise ValueError('Photo compositions require an asset; table/records use their own scene')
            if self.end - self.start > 30:
                raise ValueError('A cinematic shot may not exceed 30 seconds')
        elif self.composition_data:
            raise ValueError('Composition data requires a composition')
        elif bool(self.asset) == bool(self.graphic):
            raise ValueError("Choose exactly one existing asset or generated graphic")
        if self.graphic_data and not self.graphic:
            raise ValueError("Graphic data requires a graphic template")
        return self


class EditorialPlan(PlanModel):
    version: Literal[1] = 1
    episode_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    channel_id: str = Field(default="default", pattern=r"^[A-Za-z0-9_-]{1,60}$")
    title: str = Field(min_length=1, max_length=150)
    audio_source: str = Field(min_length=1, max_length=2000)
    audio_offset: float = Field(default=0, ge=0, allow_inf_nan=False)
    # True means copy the exact approved mix; never normalize it a second time.
    audio_is_final_mix: bool = True
    duration: float = Field(gt=.4, le=7200, allow_inf_nan=False)
    width: int = Field(default=1920, ge=320, le=3840)
    height: int = Field(default=1080, ge=180, le=2160)
    fps: int = Field(default=30, ge=24, le=60)
    palette: Literal["ivory", "green"] = "ivory"
    accent: str = Field(default="#B7EA68", pattern=r"^#[0-9A-Fa-f]{6}$")
    assets: dict[str, EditorialAsset] = Field(default_factory=dict)
    scenes: list[EditorialScene] = Field(min_length=1, max_length=500)
    alignment: dict = Field(default_factory=lambda: {"method": "operator-reviewed", "precision": "unmeasured"})

    @model_validator(mode="after")
    def contiguous(self):
        if self.width % 2 or self.height % 2:
            raise ValueError("Output dimensions must be even")
        if len({s.id for s in self.scenes}) != len(self.scenes):
            raise ValueError("Scene IDs must be unique")
        cursor = 0.
        tolerance = 1e-6
        for scene in self.scenes:
            if (scene.composition == 'table' and scene.composition_data.get('engine', 'three') == 'three'
                    and (self.width > 1920 or self.height > 1080)):
                raise ValueError('3D scenes support at most 1920x1080')
            for point in (scene.start, scene.end):
                if abs(point * self.fps - round(point * self.fps)) > 1e-4:
                    raise ValueError(f"Scene boundaries must use the global {self.fps}fps frame grid; use frame_time()")
            if abs(scene.start - cursor) > tolerance:
                raise ValueError(f"Timeline gap/overlap before {scene.id}")
            if scene.asset and scene.asset not in self.assets:
                raise ValueError(f"Unknown asset in {scene.id}")
            cursor = scene.end
        if abs(cursor - self.duration) > tolerance:
            raise ValueError("Scenes must cover exactly the declared audio duration")
        if abs(self.duration * self.fps - round(self.duration * self.fps)) > 1e-4:
            raise ValueError("Duration must use the global frame grid")
        return self

    @classmethod
    def load(cls, path: Path) -> "EditorialPlan":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)


def project_file(root: Path, value: str) -> Path:
    """Plans are operator files; media must still remain in the project workspace."""
    path = Path(value).expanduser()
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Editorial media must be an existing project file: {Path(value).name}")
    return path


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def phrase_time(words: list[dict], phrase: str, *, occurrence: int = 0) -> tuple[float, float]:
    """Find real provider timestamps; zero-duration tokens are valid, never divide by them."""
    def tokens(value):
        return re.findall(r"\w+", value.casefold())
    expanded = [(token, float(w["start"]), float(w["end"]))
                for w in words for token in tokens(str(w["word"]))]
    wanted = tokens(phrase)
    if not wanted:
        raise ValueError("Narration anchor cannot be empty")
    matches = []
    for i in range(len(expanded) - len(wanted) + 1):
        if [w[0] for w in expanded[i:i + len(wanted)]] == wanted:
            start, end = expanded[i][1], expanded[i + len(wanted) - 1][2]
            if not math.isfinite(start + end) or start < 0 or end < start:
                raise ValueError("Invalid provider anchor")
            matches.append((start, end))
    if occurrence < 0 or occurrence >= len(matches):
        raise ValueError(f"Phrase not found in cached alignment: {phrase}")
    return matches[occurrence]


def frame_time(seconds: float, fps: int = 30) -> float:
    """Quantize one global boundary, rather than rounding each clip duration."""
    if not math.isfinite(seconds) or seconds < 0 or not 24 <= fps <= 60:
        raise ValueError("A frame boundary needs finite time and supported FPS")
    return round(seconds * fps) / fps
