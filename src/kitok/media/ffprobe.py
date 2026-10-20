from __future__ import annotations

import json
import math
import re
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


class ProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    pixel_format: str | None = None
    bitrate: int | None = None
    size: int | None = None


def _rate(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None


def probe_media(path: Path, ffprobe: str = "ffprobe") -> MediaInfo:
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-show_entries",
                "format=duration,size,bit_rate:stream=codec_type,codec_name,width,height,avg_frame_rate,pix_fmt",
                "-of", "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        payload = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise ProbeError(f"Could not inspect media file {path}") from exc

    streams = payload.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
    fmt = payload.get("format") or {}
    try:
        duration = float(fmt["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProbeError(f"Media file has no usable duration: {path}") from exc
    if duration <= 0:
        raise ProbeError(f"Media file has invalid duration: {path}")
    return MediaInfo(
        duration=duration,
        width=int(video["width"]) if video.get("width") else None,
        height=int(video["height"]) if video.get("height") else None,
        fps=_rate(video.get("avg_frame_rate")),
        video_codec=video.get("codec_name"),
        audio_codec=audio.get("codec_name"),
        pixel_format=video.get("pix_fmt"),
        bitrate=int(fmt["bit_rate"]) if fmt.get("bit_rate") else None,
        size=int(fmt["size"]) if fmt.get("size") else None,
    )


def valid_video(path: Path, ffprobe: str = "ffprobe") -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        info = probe_media(path, ffprobe)
    except ProbeError:
        return False
    return bool(info.video_codec and info.width and info.height)


def stream_durations(path: Path, ffprobe: str = "ffprobe") -> tuple[float | None, float | None]:
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error", "-show_entries", "stream=codec_type,duration",
                "-of", "json", str(path),
            ],
            capture_output=True, text=True, check=True, timeout=60,
        )
        streams = json.loads(result.stdout).get("streams", [])
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise ProbeError(f"Could not inspect stream durations for {path}") from exc

    def duration(kind: str) -> float | None:
        value = next((item.get("duration") for item in streams if item.get("codec_type") == kind), None)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    return duration("video"), duration("audio")


def measure_loudness(path: Path, ffmpeg: str = "ffmpeg") -> dict[str, float | None]:
    """Run loudnorm analysis only; values are measured, not applied to the file."""
    try:
        result = subprocess.run(
            [
                ffmpeg, "-nostdin", "-hide_banner", "-i", str(path), "-vn",
                "-af", "loudnorm=I=-16:LRA=7:TP=-1.5:print_format=json",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, check=True, timeout=1800,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProbeError(f"Could not measure loudness for {path}") from exc
    matches = re.findall(r"\{[^{}]*\}", result.stderr, flags=re.DOTALL)
    if not matches:
        raise ProbeError(f"FFmpeg returned no loudness measurement for {path}")
    try:
        payload = json.loads(matches[-1])
    except json.JSONDecodeError as exc:
        raise ProbeError(f"FFmpeg returned malformed loudness data for {path}") from exc

    def number(key: str) -> float | None:
        try:
            return float(payload[key])
        except (KeyError, TypeError, ValueError):
            return None

    return {
        "integrated_lufs": number("input_i"),
        "loudness_range_lu": number("input_lra"),
        "true_peak_dbtp": number("input_tp"),
    }


def measured_video_duration(path: Path, ffprobe: str = "ffprobe") -> float:
    """Use the video stream, never an audio tail or a provider's rounded duration."""
    info = probe_media(path, ffprobe)
    video, _ = stream_durations(path, ffprobe)
    if not info.video_codec or video is None or not math.isfinite(video) or video <= 0:
        raise ProbeError(f"Media file has no measurable video stream duration: {path}")
    return video
