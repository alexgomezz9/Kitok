"""HTTP contract. Business validation remains in application/model services."""
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from ..models import DialogueTurn, ContentItem


class Request(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CreateContent(Request):
    id: str | None = None
    subject: str = Field(min_length=1, max_length=500)
    script: str = Field(default='', max_length=24000)
    keywords: list[str] = Field(default_factory=lambda: ['nature'], min_length=1, max_length=20)
    caption: str = ''
    content_format: Literal['explainer', 'dialogue'] = 'explainer'
    voice_profile: str = 'rick_es'
    visual_profile: str = 'pexels'
    dialogue_preset: str | None = None
    character_profile: str | None = None
    dialogue: list[DialogueTurn] | None = None
    visual_seed: str | None = None
    background_seed: str | None = None
    background_file: str | None = None
    platforms: list[Literal['tiktok', 'instagram', 'youtube']] = ['tiktok', 'instagram', 'youtube']
    publish_at: datetime | None = None
    schedule_enabled: bool | None = None


    @model_validator(mode='before')
    @classmethod
    def new_fish_voice(cls, values):
        if isinstance(values, dict):
            values = dict(values)
            if values.get('content_format') == 'dialogue':
                values.setdefault('voice_profile', 'alvaro')  # Historical model sentinel, no Edge synthesis.
            else:
                from ..profiles import VOICES
                voice = values.get('voice_profile', 'rick_es')
                if voice in VOICES and VOICES[voice].provider != 'fish':
                    raise ValueError('Los vídeos nuevos requieren una voz Fish. Elige una voz Fish; la voz Edge histórica se conserva sólo para consulta.')
        return values


class EditContent(Request):
    subject: str | None = None
    caption: str | None = None
    script: str | None = None
    keywords: list[str] | None = None
    dialogue: list[DialogueTurn] | None = None
    youtube_title: str | None = None


class JobRequest(Request):
    action: Literal['generate', 'retry', 'regenerate', 'background'] = 'generate'


class ScheduleRequest(Request):
    local_time: str | None = None
    at: datetime | None = None
    platforms: list[Literal['tiktok', 'instagram', 'youtube']] | None = None


class QueueRequest(Request):
    action: Literal['add', 'remove', 'up', 'down', 'top', 'bottom']


class ScheduleMoveRequest(Request):
    direction: Literal['earlier', 'later']


class ConfirmRequest(Request):
    confirm: bool = False
    queue_after: bool = False


class CharacterRequest(Request):
    id: str
    display_name: str = Field(min_length=1, max_length=80)
    side: Literal['left', 'right'] = 'left'
    scale: float = Field(default=1, ge=0.3, le=1.4)


class VoiceRequest(Request):
    id: str
    display_name: str = Field(min_length=1, max_length=80)
    provider: Literal['fish'] = 'fish'
    value: str = Field(min_length=1, max_length=200)
    character: str | None = None


class RenamePose(Request):
    name: str = Field(min_length=1, max_length=100)


class BackgroundImport(Request):
    source: str
    pool: str = 'gameplay'


class JobResponse(BaseModel):
    id: str
    status: str
    action: str
    created_at: str
    error: str | None = None


class ContentView(BaseModel):
    item: ContentItem
    status: str
    generation_status: str
    schedule_status: Literal['unscheduled', 'queued', 'scheduled', 'published']
    publishing_status: str | None = None
    queue_position: int | None = None
    stage: str | None = None
    job: dict[str, Any]
    error: str | None = None
    technical_error: str | None = None
    preview_url: str | None = None
    thumbnail_url: str | None = None
    duration: float | None = None
    scheduled_at: str | None = None
    buffer: dict[str, dict[str, Any]]
    remote_locked: bool
    warnings: list[str]


class ScheduleView(BaseModel):
    timezone: str
    items: list[ContentView]
    queued: list[ContentView]
    unscheduled: list[ContentView]
    conflicts: list[dict[str, Any]]
    slots: list[dict[str, Any]]
    remote_changes_supported: bool


class PreferencesRequest(Request):
    default_visual_profile: str | None = None
    character_active_height: int | None = Field(default=None, ge=100, le=1000)
    character_max_width: int | None = Field(default=None, ge=100, le=900)
    character_scale_variation: float | None = Field(default=None, ge=0, le=0.15)
    character_position_variation: int | None = Field(default=None, ge=0, le=80)
    character_bottom_margin: int | None = Field(default=None, ge=200, le=700)
    character_entry_seconds: float | None = Field(default=None, ge=0, le=1)
    character_exit_seconds: float | None = Field(default=None, ge=0, le=1)
    character_entry_horizontal_pixels: int | None = Field(default=None, ge=0, le=200)
    character_left_anchor: int | None = Field(default=None, ge=0, le=300)
    character_right_anchor: int | None = Field(default=None, ge=0, le=300)
    character_reaction_probability: float | None = Field(default=None, ge=0, le=1)
    character_reaction_min_seconds: float | None = Field(default=None, ge=0.1, le=2)
    character_reaction_max_seconds: float | None = Field(default=None, ge=0.1, le=3)
    dialogue_subtitle_max_chars: int | None = Field(default=None, ge=4, le=80)
    dialogue_gap_ms: int | None = Field(default=None, ge=0, le=1000)
    default_posting_slots: list[str] | None = None
    timezone: str | None = None


class LongformRequest(Request):
    subject: str = Field(min_length=1, max_length=100)
    script: str = Field(min_length=20, max_length=24000)
    keywords: list[str] = Field(min_length=1, max_length=20)
    renderer: Literal['native', 'mpt'] = 'native'
    music_enabled: bool = False
    music_mode: Literal['off', 'auto', 'manual'] | None = None
    music_track: str | None = Field(default=None, pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}$')
    mounting_style: Literal['basic', 'documentary'] = 'basic'
    narrator_voice: str | None = Field(default=None, max_length=200)

    @field_validator('subject', 'script', mode='before')
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class VoiceFavoriteRequest(Request):
    enabled: bool


class VoiceAssignmentRequest(Request):
    channel: str = Field(default='loose_thread', pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}$')
    voice_id: str = Field(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}$')
