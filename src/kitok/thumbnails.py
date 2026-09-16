"""Local, disposable thumbnails for ready MP4 files."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from .models import ID_RE


class ThumbnailService:
    def __init__(self, cache_dir: Path, ffmpeg_binary: str = "ffmpeg") -> None:
        self.cache_dir = cache_dir
        self.ffmpeg_binary = ffmpeg_binary

    def get(self, content_id: str, video: Path | str) -> Path | None:
        """Return a current JPG, or None if local extraction is unavailable."""
        if not ID_RE.fullmatch(content_id):
            return None
        source = Path(video)
        try:
            if source.suffix.lower() != ".mp4" or not source.is_file():
                return None
            stat = source.stat()
            stamp = {"source": str(source.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        except OSError:
            return None
        try:
            image = self.cache_dir / f"{content_id}.jpg"
            metadata = self.cache_dir / f"{content_id}.json"
            if image.is_file() and image.stat().st_size and json.loads(metadata.read_text()) == stamp:
                return image
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.cache_dir, suffix=".jpg", delete=False) as temp:
                temporary = Path(temp.name)
            result = subprocess.run(
                [self.ffmpeg_binary, "-hide_banner", "-loglevel", "error", "-ss", "1.5", "-i", str(source),
                 "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "4", "-y", str(temporary)],
                capture_output=True, timeout=20, check=False,
            )
            if result.returncode or not temporary.is_file() or not temporary.stat().st_size:
                return None
            os.replace(temporary, image)
            with tempfile.NamedTemporaryFile(mode="w", dir=self.cache_dir, suffix=".json", delete=False) as meta_temp:
                json.dump(stamp, meta_temp)
                meta_path = Path(meta_temp.name)
            os.replace(meta_path, metadata)
            return image
        except (OSError, subprocess.TimeoutExpired):
            return None
        finally:
            if "temporary" in locals():
                temporary.unlink(missing_ok=True)
            if "meta_path" in locals():
                meta_path.unlink(missing_ok=True)
