"""Compare NVENC p4/p5/p6/p7 with identical source, CQ/VBR settings and audio."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path

from kitok.media.ffmpeg import EncoderSettings, encoder_arguments, nvenc_available
from kitok.media.ffprobe import probe_media


PRESETS = ("p4", "p5", "p6", "p7")


def gpu_utilization() -> float | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        return float(result.stdout.splitlines()[0].strip())
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def encode(source: Path, destination: Path, preset: str, ffmpeg: str, *,
           start: float, duration: float | None) -> tuple[float, list[float]]:
    settings = EncoderSettings("h264_nvenc", preset)
    command = [
        ffmpeg, "-nostdin", "-v", "error", "-y", "-ss", f"{start:g}",
    ]
    if duration is not None:
        command += ["-t", f"{duration:g}"]
    command += [
        "-i", str(source),
        "-map", "0:v:0", "-map", "0:a?", *encoder_arguments(settings),
        "-vf", "fps=30", "-profile:v", "high", "-level:v", "4.2", "-pix_fmt", "yuv420p",
        "-g", "60", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(destination),
    ]
    started = time.monotonic()
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    samples = []
    while process.poll() is None:
        sample = gpu_utilization()
        if sample is not None:
            samples.append(sample)
        time.sleep(0.5)
    _, stderr = process.communicate()
    if process.returncode:
        raise RuntimeError(f"NVENC {preset} failed: {(stderr or '')[-1200:]}")
    return time.monotonic() - started, samples


def quality(source: Path, encoded: Path, ffmpeg: str, *, start: float,
            duration: float | None) -> dict[str, float | None]:
    command = [ffmpeg, "-nostdin", "-hide_banner", "-ss", f"{start:g}"]
    if duration is not None:
        command += ["-t", f"{duration:g}"]
    command += [
        "-i", str(source), "-i", str(encoded),
        "-filter_complex",
        "[0:v:0]fps=30,setpts=PTS-STARTPTS,split=2[reference_ssim][reference_psnr];"
        "[1:v:0]setpts=PTS-STARTPTS,split=2[encoded_ssim][encoded_psnr];"
        "[reference_ssim][encoded_ssim]ssim=shortest=1[ssim_out];"
        "[reference_psnr][encoded_psnr]psnr=shortest=1[psnr_out]",
        "-map", "[ssim_out]", "-map", "[psnr_out]", "-f", "null", "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=3600)
    text = result.stderr or ""
    ssim = re.findall(r"All:([0-9.]+)", text)
    psnr = re.findall(r"average:([0-9.]+)", text)
    return {
        "ssim": float(ssim[-1]) if ssim else None,
        "psnr_db": float(psnr[-1]) if psnr else None,
    }


def extract_frames(video: Path, directory: Path, ffmpeg: str, duration: float) -> list[str]:
    frames = []
    for index, fraction in enumerate((0.12, 0.32, 0.52, 0.72, 0.88), start=1):
        target = directory / f"{video.stem}_frame_{index:02d}.jpg"
        subprocess.run(
            [ffmpeg, "-nostdin", "-v", "error", "-y", "-ss", f"{duration * fraction:.3f}",
             "-i", str(video), "-frames:v", "1", "-q:v", "2", str(target)],
            check=True, timeout=120,
        )
        frames.append(str(target))
    return frames


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/smoke/nvenc-benchmark"))
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--duration", type=float)
    args = parser.parse_args(argv)
    if not args.input.is_file():
        parser.error(f"input does not exist: {args.input}")
    if not nvenc_available(args.ffmpeg):
        parser.error("h264_nvenc runtime probe failed; benchmark cannot use a CPU fallback")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    source_info = probe_media(args.input, args.ffprobe)
    results = []
    for preset in PRESETS:
        destination = args.output_dir / f"{args.input.stem}_{preset}.mp4"
        elapsed, samples = encode(
            args.input, destination, preset, args.ffmpeg,
            start=args.start, duration=args.duration,
        )
        info = probe_media(destination, args.ffprobe)
        result = {
            "preset": preset,
            "elapsed_seconds": elapsed,
            "encode_speed_x": (args.duration or source_info.duration) / elapsed,
            "filesize_bytes": info.size,
            "average_bitrate": info.bitrate,
            "gpu_utilization_average": sum(samples) / len(samples) if samples else None,
            "gpu_utilization_peak": max(samples) if samples else None,
            "quality_vs_identical_source": quality(
                args.input, destination, args.ffmpeg,
                start=args.start, duration=args.duration,
            ),
            "frames": extract_frames(destination, args.output_dir, args.ffmpeg, info.duration),
        }
        results.append(result)
        print(json.dumps(result, indent=2))

    report = {
        "source": str(args.input),
        "source_start": args.start,
        "source_duration": args.duration or source_info.duration,
        "method": (
            "One identical decoded 1080p30 input and unchanged audio for every preset; "
            "NVENC VBR HQ, CQ 18, maxrate 20M, bufsize 40M, full-resolution multipass, "
            "spatial/temporal AQ and lookahead 32. SSIM/PSNR use the same input as reference."
        ),
        "results": results,
    }
    report_path = args.output_dir / "benchmark.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
