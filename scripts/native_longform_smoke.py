"""Run one isolated 60-90 second Native long-form smoke outside production state."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kitok.longform import cli as longform
from kitok.config import Settings
from kitok.logging_setup import configure_logging
from kitok.media.ffmpeg import FFmpegNativeEngine, choose_encoder
from kitok.media.ffprobe import measure_loudness, probe_media, stream_durations
from kitok.providers.pexels import PexelsProvider
from kitok.rendering.native import NativeLongformRenderer


DEFAULT_CONFIG = ROOT / "examples" / "longform" / "native_smoke.json"


def extract_frames(video: Path, manifest: dict, ffmpeg: str) -> list[str]:
    timeline = manifest.get("timeline", [])
    if not timeline:
        return []
    wanted = ("motion", "night", "casino", "detail", "screen")
    chosen = []
    for term in wanted:
        match = next((item for item in timeline if term in item["query"].casefold()), None)
        if match and match not in chosen:
            chosen.append(match)
    for item in timeline:
        if len(chosen) >= 5:
            break
        if item not in chosen:
            chosen.append(item)
    paths = []
    for index, item in enumerate(chosen[:5], start=1):
        destination = video.with_name(f"{video.stem}_frame_{index:02d}.jpg")
        timestamp = item["timeline_start"] + min(item["duration"] / 2, 2.0)
        subprocess.run(
            [
                ffmpeg, "-nostdin", "-v", "error", "-y", "-ss", f"{timestamp:.3f}",
                "-i", str(video), "-frames:v", "1", "-q:v", "2", str(destination),
            ],
            check=True,
            timeout=120,
        )
        paths.append(str(destination))
    return paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", nargs="?", default=str(DEFAULT_CONFIG))
    parser.add_argument("--encoder", choices=("auto", "h264_nvenc", "libx264"), default="auto")
    parser.add_argument("--nvenc-preset", choices=("p4", "p5", "p6", "p7"), default="p5")
    parser.add_argument("--start-over", action="store_true")
    parser.add_argument("--keep-workspace", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    settings = Settings()
    configure_logging(settings.logs_dir, args.verbose)
    definition = longform.load_longform_config(args.config)
    longform.validate_tts_script(definition.item.script)
    destination = ROOT / "outputs" / "smoke" / f"{definition.item.id}.mp4"
    provider = PexelsProvider(
        settings.pexels_api_key.get_secret_value(), settings.native_cache_dir,
        ffprobe=settings.ffprobe_binary, attempts=settings.http_retry_attempts,
    )
    try:
        engine = FFmpegNativeEngine(
            ffmpeg=settings.ffmpeg_binary,
            ffprobe=settings.ffprobe_binary,
            encoder=choose_encoder(
                settings.ffmpeg_binary,
                requested=args.encoder,
                nvenc_preset=args.nvenc_preset,
            ),
        )
        result = NativeLongformRenderer(
            settings,
            provider,
            engine,
            output_path=destination,
            keep_workspace=args.keep_workspace,
        ).render(definition, start_over=args.start_over)
    finally:
        provider.close()

    info = probe_media(result.output, settings.ffprobe_binary)
    video_duration, audio_duration = stream_durations(result.output, settings.ffprobe_binary)
    loudness = measure_loudness(result.output, settings.ffmpeg_binary)
    manifest_path = result.output.with_suffix(".native.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames = extract_frames(result.output, manifest, settings.ffmpeg_binary)
    report = {
        "output": str(result.output),
        "renderer": "native",
        "timings": asdict(result.timings),
        "media": asdict(info),
        "video_duration": video_duration,
        "audio_duration": audio_duration,
        "av_duration_delta": (
            abs(video_duration - audio_duration)
            if video_duration is not None and audio_duration is not None else None
        ),
        "loudness": loudness,
        "frames": frames,
        "gpu_utilization": None,
        "gpu_utilization_note": "Not sampled by the smoke runner; the preset benchmark samples when nvidia-smi is accessible.",
    }
    report_path = result.output.with_suffix(".smoke.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not 60 <= info.duration <= 90:
        print(f"ERROR: smoke duration {info.duration:.2f}s is outside 60-90s", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
