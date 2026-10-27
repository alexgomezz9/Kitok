from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, model_serializer

from ..editing.camera import CameraMotion


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Reference(Model):
    path: str = Field(min_length=1, max_length=500)
    role: Literal['interior', 'thumbnail', 'character']
    notes: str = Field(default='', max_length=2000)


class Voice(Model):
    reference_id: str | None = None
    model: str | None = None
    speed: float = Field(default=1, ge=.5, le=2, allow_inf_nan=False)
    transcript_verification: Literal['off', 'local_asr', 'local_asr_autocut'] = 'off'

    @model_serializer(mode='wrap')
    def preserve_legacy_identity(self, handler):
        data = handler(self)
        # Existing plans hash all configuration fields. An optional guard that
        # is disabled must not invalidate their already paid/rendered inputs.
        if self.transcript_verification == 'off':
            data.pop('transcript_verification', None)
        return data


class Music(Model):
    mode: Literal['auto', 'manual', 'off'] = 'auto'
    channel: str = 'documentary'
    mood: str = 'investigation'
    track_id: str | None = None
    count: int = Field(default=2, ge=1, le=2)


class Config(Model):
    pipeline: Literal['youtube_stickman_es'] = 'youtube_stickman_es'
    version: Literal[1] = 1
    target_scene_seconds: float = Field(default=5, ge=3, le=7, allow_inf_nan=False)
    max_scene_seconds: float = Field(default=8, ge=5, le=12, allow_inf_nan=False)
    style_prompt: str = Field(default=(
        'Original 2D stickman explanatory illustration. Uniform dark outlines, simple expressive '
        'characters, clean light backgrounds and a consistent restrained palette. Landscape 16:9. '
        'Use supplied interior frames only to guide technique and character consistency; do not copy '
        'a specific composition. No typography, letters, captions, logos or watermarks.'), max_length=12000)
    characters: dict[str, str] = Field(default_factory=dict)
    references: list[Reference] = Field(default_factory=list, max_length=20)
    voice: Voice = Field(default_factory=Voice)
    music: Music = Field(default_factory=Music)
    sfx_events: list[dict] = Field(default_factory=list, max_length=24)
    transition_duration: float = Field(default=.4, ge=.05, le=1, allow_inf_nan=False)
    fade_in: float = Field(default=.6, ge=0, le=3, allow_inf_nan=False)
    fade_out: float = Field(default=.8, ge=0, le=3, allow_inf_nan=False)
    chapters: list[dict] | None = None
    sources: list[dict] = Field(default_factory=list)
    description: str | None = Field(default=None, max_length=4500)
    thumbnail_text: dict[str,str] = Field(default_factory=dict)


class Direction(Model):
    scene_id: str
    visual_description: str = Field(min_length=20, max_length=600)
    scene_prompt: str = Field(min_length=30, max_length=6000)
    characters: list[str] = Field(default_factory=list)
    camera: CameraMotion | None = None


class Scene(Model):
    id: str = Field(pattern=r'^s\d{4}_\d{9}$')
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    narration: str = Field(min_length=1)
    image_file: str
    visual_description: str = ''
    scene_prompt: str = ''
    style_prompt: str
    characters: list[str] = Field(default_factory=list)
    reference_files: list[str] = Field(default_factory=list)
    camera: CameraMotion
    transition: Literal['cut', 'dissolve'] = 'dissolve'

    @model_validator(mode='after')
    def interval(self):
        if self.end-self.start < .4-1e-6:
            raise ValueError('An illustration needs at least 0.4 seconds')
        return self


class IllustrationPlan(Model):
    version: Literal[1] = 1
    pipeline: Literal['youtube_stickman_es'] = 'youtube_stickman_es'
    title: str
    script_sha256: str
    audio_sha256: str
    srt_sha256: str
    config_sha256: str
    duration: float
    narration_duration: float
    fps: Literal[30] = 30
    references: list[dict] = Field(default_factory=list)
    scenes: list[Scene] = Field(min_length=1, max_length=500)
    direction_complete: bool = False
    timing_method: str
    srt_cues: list[dict] = Field(default_factory=list)

    @model_validator(mode='after')
    def coverage(self):
        cursor = 0.
        for scene in self.scenes:
            if abs(scene.start-cursor) > 1e-6:
                raise ValueError('Illustration plan contains a gap or overlap')
            if any(abs(t*30-round(t*30)) > 1e-4 for t in (scene.start, scene.end)):
                raise ValueError('Illustration cuts must use the shared 30fps clock')
            cursor = scene.end
        if abs(cursor-self.duration) > 1e-6:
            raise ValueError('Illustrations must cover all narration')
        if len({s.id for s in self.scenes}) != len(self.scenes):
            raise ValueError('Duplicate illustration ID')
        if self.direction_complete != all(s.visual_description and s.scene_prompt for s in self.scenes):
            raise ValueError('Semantic direction status does not match scenes')
        return self
