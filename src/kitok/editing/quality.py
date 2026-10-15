"""Small local audiovisual checks and review artifacts; never call external services."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

from PIL import Image, ImageDraw, ImageFont

from ..media.ffprobe import measure_loudness, probe_media, stream_durations
from ..state import write_json_atomic
from .storyboard import file_hash


def decoded_audio_hash(path: Path, ffmpeg: str = "ffmpeg") -> str:
    result = subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a:0",
         "-c:a", "pcm_s16le", "-f", "hash", "-hash", "sha256", "-"],
        capture_output=True, text=True, check=True, timeout=300,
    )
    return result.stdout.strip().split("=", 1)[1]


def contact_sheet(video: Path, output: Path, times: list[float], *,
                  ffmpeg: str = "ffmpeg", columns: int = 4, label: str = "") -> Path:
    if not 1 <= columns <= 8:
        raise ValueError("Contact sheet columns must be between 1 and 8")
    if not times or len(times) > 80:
        raise ValueError("Contact sheets need between 1 and 80 timestamps")
    if not all(math.isfinite(t) and t >= 0 for t in times):
        raise ValueError("Contact timestamps must be finite and non-negative")
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height, band = 400, 224, 32
    rows = math.ceil(len(times) / columns)
    canvas = Image.new("RGB", (width * columns, (height + band) * rows), "#17212b")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 19)
    frames = output.parent / f".{output.stem}-frames"
    frames.mkdir(exist_ok=True)
    for i, point in enumerate(times):
        frame = frames / f"{i:03d}.jpg"
        subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-y", "-ss", f"{point:.3f}",
                        "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                        str(frame)], capture_output=True, check=True, timeout=60)
        x, y = i % columns * width, i // columns * (height + band)
        with Image.open(frame) as image:
            canvas.paste(image, (x, y + band))
        draw.text((x + 10, y + 4), f"{label} {point:.2f}s", font=font, fill="white")
    canvas.save(output)
    return output


def inspect_video(video: Path, output: Path, *, settings, comparison: Path | None = None,
                  scene_boundaries: list[float] | None = None) -> dict:
    """Measure facts, flag review points; a green report does not judge storytelling."""
    info = probe_media(video, settings.ffprobe_binary)
    if not info.video_codec or not info.audio_codec:
        raise ValueError("A deliverable needs both video and audio")
    decode = subprocess.run(
        [settings.ffmpeg_binary, "-nostdin", "-v", "error", "-threads", "2", "-i", str(video),
         "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
        capture_output=True, text=True, timeout=600,
    )
    if decode.returncode or decode.stderr.strip():
        raise RuntimeError("Full media decode failed: " + decode.stderr[-1000:])
    black = subprocess.run(
        [settings.ffmpeg_binary, "-nostdin", "-hide_banner", "-threads", "2", "-i", str(video),
         "-vf", "blackdetect=d=0.15:pix_th=0.10", "-an", "-f", "null", "-"],
        capture_output=True, text=True, check=True, timeout=600,
    )
    intervals = [
        {"start":float(a),"end":float(b),"duration":float(c)}
        for a,b,c in re.findall(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)",black.stderr)
    ]
    loudness = measure_loudness(video,settings.ffmpeg_binary)
    loudness = {k:v if v is not None and math.isfinite(v) else None for k,v in loudness.items()}
    durations = stream_durations(video, settings.ffprobe_binary)
    digest = decoded_audio_hash(video,settings.ffmpeg_binary)
    report = {
        "video":str(video), "video_sha256":file_hash(video),
        "duration":info.duration,"geometry":[info.width,info.height],"fps":info.fps,
        "full_decode":"passed","audio_stream_duration":durations[1],"video_stream_duration":durations[0],
        "decoded_audio_sha256":digest,"loudness":loudness,"black_intervals":intervals,
        "manual_review_required":["narration synchronization","relevance of footage","graphic labels and safe areas",
                                  "pacing and transitions","rights and factual provenance"],
    }
    if comparison is not None:
        reference_digest = decoded_audio_hash(comparison,settings.ffmpeg_binary)
        report["comparison"]={"reference":str(comparison),"audio_identical":digest==reference_digest,
                              "reference_decoded_audio_sha256":reference_digest}
        if digest!=reference_digest:
            raise RuntimeError("A/B audio differs; do not attribute the result only to editing")
    points = scene_boundaries or [info.duration*i/9 for i in range(1,9)]
    # Long edits can have hundreds of scenes. Bound review work and memory while
    # retaining samples from the beginning and end; this is not exhaustive QC.
    times=sorted(set(round(min(info.duration-.1,max(.1,p)),3) for p in points))
    requested = len(times)
    if requested > 80:
        times = [times[round(i * (requested - 1) / 79)] for i in range(80)]
    contact = output.with_suffix(".contact.jpg")
    contact_sheet(video,contact,times,ffmpeg=settings.ffmpeg_binary,label="Review")
    report["contact_sheet"]=str(contact)
    report["contact_sheet_sha256"]=file_hash(contact)
    report["contact_sampling"]={"available_points":requested,"sampled_points":len(times),
                                "exhaustive":requested == len(times)}
    write_json_atomic(output,report)
    return report
