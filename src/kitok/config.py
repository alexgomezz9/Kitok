from __future__ import annotations
from pathlib import Path
from pydantic import Field
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
    ready_dir: Path = PROJECT_ROOT / "outputs" / "ready-phone"
    mpt_preset_path: Path = PROJECT_ROOT / "presets" / "mpt_default.json"

    poll_interval_seconds: float = Field(default=5.0, gt=0)
    task_timeout_minutes: float = Field(default=30.0, gt=0)
    mpt_request_timeout_seconds: float = Field(default=30.0, gt=0)
    http_retry_attempts: int = Field(default=4, ge=1, le=10)
    http_retry_base_seconds: float = Field(default=1.5, gt=0)

    ffprobe_binary: str = "ffprobe"
    min_video_seconds: float = 5.0
    max_video_seconds: float = 60.0
    min_vertical_width: int = 540
    min_vertical_height: int = 960
    copy_metadata_sidecars: bool = True

    @property
    def queue_path(self): return PROJECT_ROOT / "content_queue.json"
    @property
    def state_path(self): return PROJECT_ROOT / "state" / "state.json"
    @property
    def generated_dir(self): return PROJECT_ROOT / "outputs" / "generated"
    @property
    def failed_dir(self): return PROJECT_ROOT / "outputs" / "failed"
    @property
    def local_ready_dir(self): return PROJECT_ROOT / "outputs" / "ready"
    @property
    def logs_dir(self): return PROJECT_ROOT / "logs"

    def ensure_directories(self) -> None:
        for p in (
            self.ready_dir, self.generated_dir, self.failed_dir,
            self.local_ready_dir, self.state_path.parent, self.logs_dir
        ):
            p.expanduser().mkdir(parents=True, exist_ok=True)
