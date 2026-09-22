from __future__ import annotations
from pathlib import Path
from pydantic import Field, SecretStr, field_validator, model_validator
from zoneinfo import ZoneInfo
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    mpt_base_url: str = "http://localhost:8080"
    mpt_api_key: str = ""
    fish_api_key: SecretStr = SecretStr("")
    fish_model: str = "s2.1-pro-free"
    fish_tts_timeout_seconds: float = Field(default=180.0, gt=0)
    dialogue_gap_ms: int = Field(default=140, ge=0, le=1000)
    dialogue_subtitle_max_chars: int = Field(default=26, ge=4, le=80)
    dialogue_subtitle_font_size: int = Field(default=13, ge=1, le=200)
    dialogue_subtitle_outline: float = Field(default=1.0, ge=0, le=20)
    dialogue_subtitle_bold: bool = False
    dialogue_subtitle_min_words: int = Field(default=2, ge=1, le=10)
    dialogue_subtitle_max_words: int = Field(default=5, ge=1, le=10)
    # libass uses a 288 px script canvas when an SRT has no PlayResY.
    # 48 therefore renders about 150 output pixels above the previous value 25.
    dialogue_subtitle_bottom_margin: int = Field(default=48, ge=0, le=600)
    explainer_subtitle_max_chars: int = Field(default=24, ge=4, le=80)
    explainer_subtitle_min_words: int = Field(default=2, ge=1, le=10)
    explainer_subtitle_max_words: int = Field(default=4, ge=1, le=10)
    # SRT/libass uses a 288 px script canvas; 64 places centered explainer
    # captions safely above the bottom character area in a 1920 px render.
    explainer_subtitle_bottom_margin: int = Field(default=64, ge=0, le=600)
    background_root: Path = PROJECT_ROOT / "assets" / "backgrounds"
    character_root: Path = PROJECT_ROOT / "assets" / "characters"
    data_root: Path | None = None
    character_active_height: int = Field(default=740, ge=100, le=1000)
    character_max_width: int = Field(default=660, ge=100, le=900)
    character_scale_variation: float = Field(default=0.04, ge=0, le=0.15)
    character_position_variation: int = Field(default=16, ge=0, le=80)
    character_bottom_margin: int = Field(default=350, ge=200, le=700)
    character_entry_seconds: float = Field(default=0.28, ge=0, le=1)
    character_exit_seconds: float = Field(default=0.22, ge=0, le=1)
    character_entry_horizontal_pixels: int = Field(default=48, ge=0, le=200)
    character_reaction_probability: float = Field(default=0.0, ge=0, le=1)
    character_reaction_min_seconds: float = Field(default=0.5, ge=0.1, le=2)
    character_reaction_max_seconds: float = Field(default=1.0, ge=0.1, le=3)
    single_speaker_pose_min_seconds: float = Field(default=3.0, ge=1, le=15)
    single_speaker_pose_max_seconds: float = Field(default=6.0, ge=1, le=20)
    default_visual_profile: str = "gameplay"
    default_posting_slots: list[str] = ["13:00", "19:00", "22:00"]
    character_left_anchor: int = Field(default=40, ge=0, le=300)
    character_right_anchor: int = Field(default=40, ge=0, le=300)
    ready_dir: Path = PROJECT_ROOT / "outputs" / "ready-phone"
    mpt_preset_path: Path = PROJECT_ROOT / "presets" / "mpt_default.json"

    poll_interval_seconds: float = Field(default=5.0, gt=0)
    task_timeout_minutes: float = Field(default=30.0, gt=0)
    mpt_progress_stall_minutes: float = Field(default=12.0, gt=0)
    mpt_request_timeout_seconds: float = Field(default=30.0, gt=0)
    http_retry_attempts: int = Field(default=4, ge=1, le=10)
    http_retry_base_seconds: float = Field(default=1.5, gt=0)

    ffprobe_binary: str = "ffprobe"
    ffmpeg_binary: str = "ffmpeg"
    min_video_seconds: float = 5.0
    max_video_seconds: float = 60.0
    min_vertical_width: int = 540
    min_vertical_height: int = 960
    copy_metadata_sidecars: bool = True

    publish_enabled: bool = False
    content_ai_assisted: bool = False
    tiktok_ai_generated: bool = False
    instagram_ai_generated: bool = False
    youtube_ai_generated: bool = False
    timezone: str = "Europe/Madrid"
    fixed_hashtags: str = "#curiosidades #datoscuriosos"
    buffer_api_key: SecretStr = SecretStr("")
    buffer_organization_id: str = ""
    buffer_tiktok_channel_id: str = ""
    buffer_instagram_channel_id: str = ""
    buffer_youtube_channel_id: str = ""
    buffer_max_scheduled_per_channel: int = Field(default=9, ge=1, le=9)
    buffer_request_timeout_seconds: float = Field(default=30, gt=0)
    buffer_discovery_ttl_seconds: int = Field(default=300, ge=0)
    buffer_request_reserve: int = Field(default=2, ge=0)
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: SecretStr = SecretStr("")
    cloudinary_api_secret: SecretStr = SecretStr("")
    cloudinary_usage_guard: bool = True
    cloudinary_usage_threshold: float = Field(default=0.90, gt=0, le=1)
    cloudinary_usage_max_age_seconds: int = Field(default=3600, gt=0)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("default_posting_slots")
    @classmethod
    def valid_posting_slots(cls, values):
        from datetime import time
        if not values or len(values) != len(set(values)):
            raise ValueError("Publishing slots must be non-empty and unique")
        for value in values:
            time.fromisoformat(value)
        return values

    @model_validator(mode="after")
    def valid_local_render_intervals(self):
        if self.single_speaker_pose_min_seconds > self.single_speaker_pose_max_seconds:
            raise ValueError("Single-speaker pose minimum must not exceed its maximum")
        if self.explainer_subtitle_min_words > self.explainer_subtitle_max_words:
            raise ValueError("Explainer subtitle minimum words must not exceed its maximum")
        if self.dialogue_subtitle_min_words > self.dialogue_subtitle_max_words:
            raise ValueError("Dialogue subtitle minimum words must not exceed its maximum")
        return self

    @property
    def buffer_channel_ids(self):
        return {p: getattr(self, f"buffer_{p}_channel_id")
                for p in ("tiktok", "instagram", "youtube")}

    @property
    def queue_path(self): return (self.data_root or PROJECT_ROOT) / "content_queue.json"
    @property
    def state_path(self): return (self.data_root or PROJECT_ROOT) / "state" / "state.json"
    @property
    def generated_dir(self): return (self.data_root or PROJECT_ROOT) / "outputs" / "generated"
    @property
    def failed_dir(self): return (self.data_root or PROJECT_ROOT) / "outputs" / "failed"
    @property
    def local_ready_dir(self): return (self.data_root or PROJECT_ROOT) / "outputs" / "ready"
    @property
    def logs_dir(self): return (self.data_root or PROJECT_ROOT) / "logs"
    @property
    def cache_path(self): return self.state_path.with_name("services.json")

    def ensure_directories(self) -> None:
        for p in (
            self.ready_dir, self.generated_dir, self.failed_dir,
            self.local_ready_dir, self.state_path.parent, self.logs_dir
        ):
            p.expanduser().mkdir(parents=True, exist_ok=True)
