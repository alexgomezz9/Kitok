"""Inspect local MP4s and repair only audio bitrate/sample rate; no remote calls."""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

from .models import ValidationResult


def _number(value, convert=float):
    try:
        number = convert(value)
        return number if math.isfinite(number) and number > 0 else None
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None


def social_errors(media: ValidationResult, platforms, *, allow_audio_fix=False) -> list[str]:
    """Check Kitok's conservative social MP4 profile; does not edit media."""
    errors = []
    if media.video_codec != "h264":
        errors.append("video must use H.264; re-export the video")
    if media.pixel_format != "yuv420p":
        errors.append("video must use yuv420p pixel format; re-export the video")
    if media.fps is None or not 23 <= media.fps <= 60:
        errors.append("video frame rate must be 23-60 FPS")
    if media.audio_codec != "aac" or media.audio_profile != "LC":
        errors.append("audio must use AAC-LC")
    if media.audio_channels is None or not 1 <= media.audio_channels <= 2:
        errors.append("audio must be mono or stereo")
    if media.audio_bitrate is None:
        errors.append("could not determine audio bitrate")
    elif media.audio_bitrate > 128_000 and not allow_audio_fix:
        errors.append("audio bitrate exceeds 128 kbps")
    if media.audio_sample_rate is None:
        errors.append("could not determine audio sample rate")
    elif media.audio_sample_rate > 48_000 and not allow_audio_fix:
        errors.append("audio sample rate exceeds 48 kHz")
    if "instagram" in platforms:
        if media.duration is None or not 5 <= media.duration <= 900:
            errors.append("Instagram Reels require 5 seconds to 15 minutes for automatic publishing")
        if media.file_size is None or media.file_size > 300_000_000:
            errors.append("Instagram video exceeds 300 MB")
        if media.video_bitrate is None or media.video_bitrate > 25_000_000:
            errors.append("Instagram video bitrate must be known and at most 25 Mbps")
    if "tiktok" in platforms:
        if media.duration is None or media.duration < 3:
            errors.append("TikTok video must be at least 3 seconds")
        if min(media.width or 0, media.height or 0) < 360:
            errors.append("TikTok video must be at least 360x360")
        if (media.file_size or 0) > 1_000_000_000:
            errors.append("TikTok video exceeds 1 GB")
    if "youtube" in platforms:
        if media.duration is None or media.duration > 180:
            errors.append("YouTube Short exceeds 3 minutes")
    if any(p in platforms for p in ("instagram", "youtube")):
        if not media.height or (media.width or 0) * 16 != media.height * 9:
            errors.append("Kitok Reels/Shorts require portrait 9:16")
    return errors


class VideoValidator:
    def __init__(self, ffprobe_binary="ffprobe", min_seconds=5.0, max_seconds=60.0,
                 min_vertical_width=540, min_vertical_height=960):
        self.ffprobe_binary = ffprobe_binary
        self.min_seconds, self.max_seconds = min_seconds, max_seconds
        self.min_vertical_width, self.min_vertical_height = min_vertical_width, min_vertical_height

    def ffprobe_available(self) -> bool:
        """Check the local executable; no media edits or external calls."""
        return shutil.which(self.ffprobe_binary) is not None

    def validate(self, path: Path) -> ValidationResult:
        """Inspect streams/container and generation bounds using ffprobe; read-only."""
        if not path.is_file() or path.stat().st_size == 0:
            return ValidationResult(ok=False, errors=["file is missing or empty"])
        if not self.ffprobe_available():
            return ValidationResult(ok=False, errors=[f"{self.ffprobe_binary!r} not found"])
        try:
            output = subprocess.run(
                [self.ffprobe_binary, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                capture_output=True, text=True, timeout=30, check=True)
            if getattr(output, "returncode", 0) != 0:
                raise ValueError("ffprobe failed")
            info = json.loads(output.stdout)
            streams = info.get("streams", [])
            video = next((s for s in streams if s.get("codec_type") == "video"), {})
            audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
            fmt = info.get("format", {})
            result = ValidationResult(
                ok=True, duration=_number(fmt.get("duration")), file_size=path.stat().st_size,
                width=_number(video.get("width"), int), height=_number(video.get("height"), int),
                video_codec=video.get("codec_name"), audio_codec=audio.get("codec_name"),
                fps=_number(video.get("avg_frame_rate") or video.get("r_frame_rate"),
                            lambda x: float(Fraction(x))), pixel_format=video.get("pix_fmt"),
                video_bitrate=_number(video.get("bit_rate"), int), audio_bitrate=_number(audio.get("bit_rate"), int),
                audio_sample_rate=_number(audio.get("sample_rate"), int), audio_profile=audio.get("profile"),
                audio_channels=_number(audio.get("channels"), int))
            if "mp4" not in fmt.get("format_name", "").split(","):
                result.errors.append("file is not an MP4 container")
            if not video:
                result.errors.append("no video stream")
            if not audio:
                result.errors.append("no audio stream")
            if result.duration is None or not self.min_seconds <= result.duration <= self.max_seconds:
                result.errors.append(f"duration must be between {self.min_seconds:g} and {self.max_seconds:g} seconds")
            if not result.width or not result.height or result.height <= result.width:
                result.errors.append("publishing requires a vertical video")
            elif result.width < self.min_vertical_width or result.height < self.min_vertical_height:
                result.warnings.append(f"low vertical resolution: {result.width}x{result.height}")
            result.ok = not result.errors
            return result
        except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
            return ValidationResult(ok=False, errors=["ffprobe could not establish valid media properties"])

    def prepare(self, path: Path, platforms, ffmpeg_binary="ffmpeg") -> ValidationResult:
        """Validate and, only if needed, normalize audio locally; video is stream-copied."""
        result = self.validate(path)
        result.errors.extend(social_errors(result, platforms, allow_audio_fix=True))
        result.ok = not result.errors
        if not result.ok:
            return result
        if result.audio_bitrate <= 128_000 and result.audio_sample_rate <= 48_000:
            return result
        fd, name = tempfile.mkstemp(prefix=".audio-", suffix=".mp4", dir=path.parent)
        os.close(fd)
        normalized = Path(name)
        try:
            subprocess.run(
                [ffmpeg_binary, "-nostdin", "-v", "error", "-y", "-i", str(path),
                 "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-c:a", "aac",
                 "-profile:a", "aac_low", "-b:a", "120k", "-ar", "48000",
                 "-movflags", "+faststart", str(normalized)],
                capture_output=True, text=True, timeout=300, check=True)
            final = self.validate(normalized)
            final.errors.extend(social_errors(final, platforms))
            final.ok = not final.errors
            if final.ok:
                normalized.replace(path)
                final.normalized = True
            return final
        except (OSError, subprocess.SubprocessError):
            result.errors.append("audio normalization failed; check ffmpeg installation and media")
            result.ok = False
            return result
        finally:
            normalized.unlink(missing_ok=True)


def validate_for_publishing(path: Path, platforms, ffprobe_binary="ffprobe") -> list[str]:
    """Check a ready file without repairing or uploading it; read-only."""
    result = VideoValidator(ffprobe_binary, min_seconds=0, max_seconds=float("inf")).validate(path)
    errors = list(result.errors)
    if path.suffix.lower() != ".mp4":
        errors.append("publishing requires an MP4")
    return errors + social_errors(result, platforms)
