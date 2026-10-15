from __future__ import annotations

import json
import hashlib
import logging
import queue
import re
import shlex
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

from ..longform.models import TimelineClip
from ..editing.ass import clip_edit_filters, filter_path, write_chunk_ass
from ..editing.manifest import EditManifest
from .ffprobe import MediaInfo, probe_media

log = logging.getLogger(__name__)

# Lossy AAC encoding can recreate small inter-sample peaks after FFmpeg's
# true-peak limiter. Reserve a narrow codec margin so the decoded deliverable,
# rather than only the pre-encode PCM, respects the requested ceiling.
AAC_TRUE_PEAK_HEADROOM_DB = 0.3
FINAL_AUDIO_SAMPLE_RATE = 48_000
FINAL_AUDIO_BITRATE = "192k"
NARRATION_GAIN_DB = 2.5


class FFmpegError(RuntimeError):
    pass


@dataclass(frozen=True)
class EncoderSettings:
    codec: str
    preset: str
    cq: int = 18
    maxrate: str = "20M"
    bufsize: str = "40M"

    @property
    def is_nvenc(self) -> bool:
        return self.codec == "h264_nvenc"


@dataclass(frozen=True)
class RenderSpec:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    fade_in: float = 0.6
    fade_out: float = 1.25
    chunk_size: int = 12


@dataclass(frozen=True)
class LoudnormMeasurement:
    input_i: float
    input_lra: float
    input_tp: float
    input_thresh: float
    target_offset: float


@dataclass(frozen=True)
class FFmpegProgress:
    encoded_seconds: float = 0.0
    speed: float | None = None
    state: str | None = None

    def percentage(self, expected_duration: float) -> float:
        if expected_duration <= 0:
            return 0.0
        return min(100.0, max(0.0, self.encoded_seconds / expected_duration * 100))


class FFmpegProgressParser:
    """Parse machine-readable records emitted by ``-progress pipe:1``."""

    def __init__(self):
        self.encoded_seconds = 0.0
        self.speed: float | None = None
        self._has_microseconds = False

    def feed(self, line: str) -> FFmpegProgress | None:
        key, separator, raw_value = line.strip().partition("=")
        if not separator:
            return None
        if key == "out_time_us":
            try:
                self.encoded_seconds = max(0.0, int(raw_value) / 1_000_000)
                self._has_microseconds = True
            except ValueError:
                pass
        elif key == "out_time" and not self._has_microseconds:
            parsed = _parse_progress_timestamp(raw_value)
            if parsed is not None:
                self.encoded_seconds = parsed
        elif key == "speed":
            try:
                self.speed = float(raw_value.removesuffix("x"))
            except ValueError:
                self.speed = None
        elif key == "progress":
            return FFmpegProgress(self.encoded_seconds, self.speed, raw_value)
        return None


def _parse_progress_timestamp(value: str) -> float | None:
    try:
        hours, minutes, seconds = value.split(":", 2)
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except (ValueError, TypeError):
        return None


def _media_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{seconds:05.2f}"


def log_ffmpeg_progress(
    label: str,
    progress: FFmpegProgress,
    expected_duration: float,
    *,
    chunk: tuple[int, int] | None = None,
) -> None:
    speed = f"{progress.speed:.2f}x" if progress.speed is not None else "n/a"
    prefix = f"chunk {chunk[0]}/{chunk[1]}" if chunk is not None else label
    log.info(
        "%s progress media=%s/%s percentage=%.1f%% speed=%s",
        prefix,
        _media_time(progress.encoded_seconds),
        _media_time(expected_duration),
        progress.percentage(expected_duration),
        speed,
    )


def nvenc_available(
    ffmpeg: str = "ffmpeg", *, run: Callable[..., subprocess.CompletedProcess] = subprocess.run
) -> bool:
    """Check both encoder registration and a one-frame runtime initialization."""
    try:
        listed = run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        if "h264_nvenc" not in listed.stdout:
            return False
        run(
            [
                ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                # Current NVENC rejects 64x64 even when the encoder is healthy.
                "color=c=black:s=256x256:r=1:d=0.1", "-frames:v", "1",
                "-c:v", "h264_nvenc", "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def choose_encoder(
    ffmpeg: str = "ffmpeg",
    *,
    requested: str = "auto",
    nvenc_preset: str = "p5",
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> EncoderSettings:
    if requested not in {"auto", "h264_nvenc", "libx264"}:
        raise ValueError(f"Unsupported encoder: {requested}")
    if nvenc_preset not in {"p4", "p5", "p6", "p7"}:
        raise ValueError(f"Unsupported NVENC preset: {nvenc_preset}")
    available = nvenc_available(ffmpeg, run=run)
    if requested == "h264_nvenc" and not available:
        raise FFmpegError("h264_nvenc was requested but its runtime probe failed")
    if requested != "libx264" and available:
        return EncoderSettings("h264_nvenc", nvenc_preset)
    return EncoderSettings("libx264", "medium")


def encoder_arguments(settings: EncoderSettings) -> list[str]:
    if settings.is_nvenc:
        return [
            "-c:v", "h264_nvenc",
            "-preset", settings.preset,
            "-tune", "hq",
            "-rc", "vbr",
            "-cq", str(settings.cq),
            "-b:v", "0",
            "-maxrate", settings.maxrate,
            "-bufsize", settings.bufsize,
            "-multipass", "fullres",
            "-spatial_aq", "1",
            "-temporal_aq", "1",
            "-aq-strength", "8",
            "-rc-lookahead", "32",
            "-bf", "3",
        ]
    return ["-c:v", "libx264", "-preset", settings.preset, "-crf", str(settings.cq)]


def build_chunk_command(
    clips: Sequence[TimelineClip],
    destination: Path,
    filter_script: Path,
    *,
    ffmpeg: str,
    encoder: EncoderSettings,
    spec: RenderSpec,
    first_chunk: bool,
    last_chunk: bool,
    editing: EditManifest | None = None,
    subtitles: Path | None = None,
) -> tuple[list[str], str]:
    if not clips:
        raise ValueError("A render chunk needs at least one clip")
    command = [ffmpeg, "-nostdin", "-v", "error", "-y"]
    filters: list[str] = []
    labels: list[str] = []
    for index, clip in enumerate(clips):
        command += ["-i", str(clip.source)]
        label = f"v{index}"
        labels.append(f"[{label}]")
        clip_effects = clip_edit_filters(editing, clip.slot.start, clip.slot.duration, spec.width, spec.height, spec.fps) if editing else []
        effect_chain = "," + ",".join(clip_effects) + ",setsar=1" if clip_effects else ""
        filters.append(
            f"[{index}:v:0]trim=start={clip.source_start:.6f}:duration={clip.slot.duration:.6f},"
            "setpts=PTS-STARTPTS,"
            f"scale={spec.width}:{spec.height}:force_original_aspect_ratio=increase:force_divisible_by=2,"
            f"crop={spec.width}:{spec.height},fps={spec.fps},setsar=1,format=yuv420p{effect_chain}[{label}]"
        )
    filters.append("".join(labels) + f"concat=n={len(clips)}:v=1:a=0[joined]")
    current = "joined"
    effects: list[str] = []
    if subtitles:
        effects.append(f"ass=filename='{filter_path(subtitles)}'")
    if first_chunk:
        effects.append(f"fade=t=in:st=0:d={spec.fade_in:g}")
    if last_chunk:
        local_end = sum(clip.slot.duration for clip in clips)
        effects += [
            f"tpad=stop_mode=clone:stop_duration={spec.fade_out:g}",
            f"fade=t=out:st={local_end:.6f}:d={spec.fade_out:g}",
        ]
    if effects:
        filters.append(f"[{current}]" + ",".join(effects) + "[video]")
        current = "video"
    script = ";\n".join(filters) + "\n"
    command += [
        "-filter_complex_script", str(filter_script),
        "-map", f"[{current}]",
        "-an",
        *encoder_arguments(encoder),
        "-profile:v", "high",
        "-level:v", "4.2",
        "-pix_fmt", "yuv420p",
        "-r", str(spec.fps),
        "-g", str(spec.fps * 2),
        "-video_track_timescale", "90000",
        "-movflags", "+faststart",
        str(destination),
    ]
    return command, script


def build_audio_mux_command(
    visual: Path,
    narration: Path,
    temporary: Path,
    *,
    ffmpeg: str,
    narration_duration: float,
    fade_out: float,
    music: Path | None,
    music_volume: float,
    loudness_target: float,
    lra_target: float,
    true_peak_target: float,
    loudnorm_measurement: LoudnormMeasurement | None = None,
    loudnorm_print: bool = False,
) -> tuple[list[str], str]:
    final_duration = narration_duration + fade_out
    command = [
        ffmpeg, "-nostdin", "-v", "error", "-y",
        "-i", str(visual), "-i", str(narration),
    ]
    encoded_true_peak_target = true_peak_target - AAC_TRUE_PEAK_HEADROOM_DB
    loudnorm = (
        f"loudnorm=I={loudness_target:g}:LRA={lra_target:g}:"
        f"TP={encoded_true_peak_target:g}"
    )
    if loudnorm_measurement is not None:
        loudnorm += (
            f":measured_I={loudnorm_measurement.input_i:g}"
            f":measured_LRA={loudnorm_measurement.input_lra:g}"
            f":measured_TP={loudnorm_measurement.input_tp:g}"
            f":measured_thresh={loudnorm_measurement.input_thresh:g}"
            f":offset={loudnorm_measurement.target_offset:g}:linear=true"
        )
    if loudnorm_print:
        loudnorm += ":print_format=json"
    # Narration is silence-padded only and deliberately has no fade-out. Loudness
    # normalization belongs after music is added so it measures/limits the master.
    voice = (
        f"[1:a:0]volume={NARRATION_GAIN_DB:g}dB,pan=stereo|c0=c0|c1=c0,"
        f"apad=whole_dur={final_duration:.6f},"
        f"atrim=duration={final_duration:.6f}[voice]"
    )
    master_format = (
        f"aresample={FINAL_AUDIO_SAMPLE_RATE},"
        f"aformat=sample_rates={FINAL_AUDIO_SAMPLE_RATE}:channel_layouts=stereo"
    )
    if music:
        command += ["-stream_loop", "-1", "-i", str(music)]
        filters = (
            f"{voice};[2:a:0]volume={music_volume:g},afade=t=in:st=0:d=1,"
            f"afade=t=out:st={narration_duration:.6f}:d={fade_out:g},"
            f"atrim=duration={final_duration:.6f}[music];"
            "[voice][music]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,"
            f"atrim=duration={final_duration:.6f}[premaster];"
            f"[premaster]{loudnorm},{master_format}[audio]"
        )
    else:
        filters = f"{voice};[voice]{loudnorm},{master_format}[audio]"
    command += [
        "-filter_complex", filters,
        "-map", "0:v:0", "-map", "[audio]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", FINAL_AUDIO_BITRATE,
        "-ar", str(FINAL_AUDIO_SAMPLE_RATE), "-ac", "2",
        "-t", f"{final_duration:.6f}",
        "-movflags", "+faststart", str(temporary),
    ]
    return command, filters


def build_audio_analysis_command(
    visual: Path,
    narration: Path,
    *,
    ffmpeg: str,
    narration_duration: float,
    fade_out: float,
    music: Path | None,
    music_volume: float,
    loudness_target: float,
    lra_target: float,
    true_peak_target: float,
) -> tuple[list[str], str]:
    mux_command, filters = build_audio_mux_command(
        visual,
        narration,
        Path("-"),
        ffmpeg=ffmpeg,
        narration_duration=narration_duration,
        fade_out=fade_out,
        music=music,
        music_volume=music_volume,
        loudness_target=loudness_target,
        lra_target=lra_target,
        true_peak_target=true_peak_target,
        loudnorm_print=True,
    )
    filter_index = mux_command.index("-filter_complex")
    inputs = mux_command[:filter_index]
    inputs[inputs.index("-v") + 1] = "info"
    command = inputs + [
        "-filter_complex", filters,
        "-map", "[audio]", "-vn", "-f", "null", "-",
    ]
    return command, filters


def parse_loudnorm_measurement(stderr: str) -> LoudnormMeasurement:
    matches = re.findall(r"\{[^{}]*\}", stderr, flags=re.DOTALL)
    if not matches:
        raise FFmpegError("FFmpeg loudnorm analysis returned no measurement")
    try:
        payload = json.loads(matches[-1])
        return LoudnormMeasurement(
            input_i=float(payload["input_i"]),
            input_lra=float(payload["input_lra"]),
            input_tp=float(payload["input_tp"]),
            input_thresh=float(payload["input_thresh"]),
            target_offset=float(payload["target_offset"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FFmpegError("FFmpeg loudnorm analysis returned malformed measurement data") from exc


class FFmpegNativeEngine:
    def __init__(
        self,
        *,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        encoder: EncoderSettings | None = None,
        spec: RenderSpec = RenderSpec(),
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        popen_factory=subprocess.Popen,
        progress_interval_seconds: float = 7.5,
    ):
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.encoder = encoder or choose_encoder(ffmpeg, run=runner)
        self.spec = spec
        self.runner = runner
        self.popen_factory = popen_factory
        self.progress_interval_seconds = progress_interval_seconds

    def _run(
        self, command: list[str], label: str, timeout: float = 7200
    ) -> subprocess.CompletedProcess:
        log.debug("FFmpeg command stage=%s command=%s", label, shlex.join(command))
        try:
            return self.runner(
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip()[-1200:]
            raise FFmpegError(f"FFmpeg failed during {label}: {detail}") from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise FFmpegError(f"Could not run FFmpeg during {label}") from exc

    def _run_progress(
        self,
        command: list[str],
        label: str,
        *,
        expected_duration: float,
        chunk: tuple[int, int] | None = None,
        timeout: float = 7200,
    ) -> subprocess.CompletedProcess:
        progress_command = command[:-1] + [
            "-progress", "pipe:1", "-nostats", "-stats_period", "1", command[-1]
        ]
        log.debug(
            "FFmpeg command stage=%s command=%s", label, shlex.join(progress_command)
        )
        parser = FFmpegProgressParser()
        latest = FFmpegProgress()
        stderr_lines: list[str] = []
        started = last_heartbeat = time.monotonic()
        try:
            process = self.popen_factory(
                progress_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise FFmpegError(f"Could not run FFmpeg during {label}") from exc

        assert process.stdout is not None
        assert process.stderr is not None
        events: queue.Queue[tuple[str, str | None]] = queue.Queue()

        def read_stream(kind: str, stream) -> None:
            try:
                for line in stream:
                    events.put((kind, line))
            finally:
                events.put((kind, None))

        readers = [
            threading.Thread(
                target=read_stream, args=("stdout", process.stdout), daemon=True
            ),
            threading.Thread(
                target=read_stream, args=("stderr", process.stderr), daemon=True
            ),
        ]
        for reader in readers:
            reader.start()
        open_streams = len(readers)
        try:
            while open_streams:
                now = time.monotonic()
                if now - started >= timeout:
                    process.kill()
                    process.wait()
                    raise FFmpegError(f"FFmpeg timed out during {label}")
                try:
                    kind, line = events.get(timeout=1.0)
                    if line is None:
                        open_streams -= 1
                    elif kind == "stderr":
                        stderr_lines.append(line)
                    else:
                        update = parser.feed(line)
                        if update is not None:
                            latest = update
                except queue.Empty:
                    pass
                now = time.monotonic()
                if now - last_heartbeat >= self.progress_interval_seconds:
                    log_ffmpeg_progress(
                        label, latest, expected_duration, chunk=chunk
                    )
                    last_heartbeat = now
            return_code = process.wait()
        except BaseException:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise
        finally:
            for reader in readers:
                reader.join(timeout=1)
        stderr = "".join(stderr_lines)
        result = subprocess.CompletedProcess(
            progress_command, return_code, stdout="", stderr=stderr
        )
        if return_code:
            detail = stderr.strip()[-1200:]
            raise FFmpegError(f"FFmpeg failed during {label}: {detail}")
        return result

    def render(
        self,
        clips: Sequence[TimelineClip],
        narration: Path,
        narration_duration: float,
        output: Path,
        workspace: Path,
        *,
        music: Path | None,
        music_volume: float,
        loudness_target: float,
        lra_target: float,
        true_peak_target: float,
        on_stage: Callable[[str], None] | None = None,
        editing: EditManifest | None = None,
    ) -> MediaInfo:
        if not clips:
            raise FFmpegError("Native render has no timeline clips")
        workspace.mkdir(parents=True, exist_ok=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        chunks: list[Path] = []
        groups = [clips[index:index + self.spec.chunk_size]
                  for index in range(0, len(clips), self.spec.chunk_size)]
        log.info("Native render chunks total=%d", len(groups))
        for index, group in enumerate(groups):
            chunk_number = index + 1
            if on_stage:
                on_stage(f"FFmpeg chunk {chunk_number}/{len(groups)}")
            chunk_started = time.monotonic()
            chunk_duration = sum(clip.slot.duration for clip in group)
            if index == len(groups) - 1:
                chunk_duration += self.spec.fade_out
            log.info(
                "FFmpeg chunk %d/%d start clips=%d media_duration=%.3fs",
                chunk_number, len(groups), len(group), chunk_duration,
            )
            chunk = workspace / f"chunk-{index:04d}.mp4"
            filter_script = workspace / f"chunk-{index:04d}.filters"
            subtitles = workspace / f"chunk-{index:04d}.ass"
            has_subtitles = bool(editing and write_chunk_ass(
                editing, subtitles, start=group[0].slot.start,
                end=group[-1].slot.end, width=self.spec.width, height=self.spec.height,
            ))
            command, script = build_chunk_command(
                group,
                chunk,
                filter_script,
                ffmpeg=self.ffmpeg,
                encoder=self.encoder,
                spec=self.spec,
                first_chunk=index == 0,
                last_chunk=index == len(groups) - 1,
                editing=editing,
                subtitles=subtitles if has_subtitles else None,
            )
            filter_script.write_text(script, encoding="utf-8")
            log.debug("FFmpeg filter stage=chunk %d/%d filter=%s", chunk_number, len(groups), script)
            fingerprint = hashlib.sha256(json.dumps({
                "command": command, "filters": script,
                "sources": [(str(clip.source), clip.source.stat().st_size, clip.source.stat().st_mtime_ns) for clip in group],
                "subtitles": subtitles.read_text(encoding="utf-8") if has_subtitles else "",
            }, sort_keys=True).encode()).hexdigest()
            receipt = chunk.with_suffix(".sha256")
            reusable = chunk.is_file() and receipt.is_file() and receipt.read_text() == fingerprint
            if reusable:
                try:
                    cached = probe_media(chunk, self.ffprobe)
                    reusable = abs(cached.duration - chunk_duration) < .25 and (cached.width, cached.height) == (self.spec.width, self.spec.height)
                except Exception:
                    reusable = False
            if not reusable:
                receipt.unlink(missing_ok=True)
                self._run_progress(
                    command,
                    f"chunk {chunk_number}/{len(groups)}",
                    expected_duration=chunk_duration,
                    chunk=(chunk_number, len(groups)),
                )
                receipt.write_text(fingerprint)
            else:
                log.info("FFmpeg chunk %d/%d cache hit", chunk_number, len(groups))
            chunks.append(chunk)
            log.info(
                "FFmpeg chunk %d/%d complete elapsed=%.2fs media=%s percentage=100.0%%",
                chunk_number, len(groups), time.monotonic() - chunk_started,
                _media_time(chunk_duration),
            )

        visual = workspace / "visual.mp4"
        concat_started = time.monotonic()
        log.info("FFmpeg concat start chunks=%d mode=stream-copy", len(chunks))
        if len(chunks) == 1:
            visual = chunks[0]
        else:
            concat_file = workspace / "chunks.ffconcat"
            lines = ["ffconcat version 1.0"]
            for chunk in chunks:
                escaped = str(chunk.resolve()).replace("'", "'\\''")
                lines.append(f"file '{escaped}'")
            concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self._run(
                [
                    self.ffmpeg, "-nostdin", "-v", "error", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(concat_file),
                    "-map", "0:v:0", "-c:v", "copy", "-an", str(visual),
                ],
                "chunk concat (stream copy)",
            )
        log.info("FFmpeg concat end elapsed=%.2fs", time.monotonic() - concat_started)

        if on_stage:
            on_stage("FFmpeg final mix loudness analysis")
        loudness_started = time.monotonic()
        log.info("FFmpeg loudness analysis start")
        final_duration = narration_duration + self.spec.fade_out
        temporary = output.with_name(f".{output.stem}.part{output.suffix}")
        temporary.unlink(missing_ok=True)
        analysis_command, _ = build_audio_analysis_command(
            visual,
            narration,
            ffmpeg=self.ffmpeg,
            narration_duration=narration_duration,
            fade_out=self.spec.fade_out,
            music=music,
            music_volume=music_volume,
            loudness_target=loudness_target,
            lra_target=lra_target,
            true_peak_target=true_peak_target,
        )
        analysis = self._run_progress(
            analysis_command,
            "loudness analysis",
            expected_duration=final_duration,
        )
        measurement = parse_loudnorm_measurement(analysis.stderr or "")
        log.info(
            "FFmpeg loudness analysis end elapsed=%.2fs input_i=%.2f input_lra=%.2f input_tp=%.2f",
            time.monotonic() - loudness_started,
            measurement.input_i, measurement.input_lra, measurement.input_tp,
        )
        if on_stage:
            on_stage("FFmpeg audio mix and stream-copy mux")
        mux_started = time.monotonic()
        log.info("FFmpeg final audio mux start")
        command, _ = build_audio_mux_command(
            visual,
            narration,
            temporary,
            ffmpeg=self.ffmpeg,
            narration_duration=narration_duration,
            fade_out=self.spec.fade_out,
            music=music,
            music_volume=music_volume,
            loudness_target=loudness_target,
            lra_target=lra_target,
            true_peak_target=true_peak_target,
            loudnorm_measurement=measurement,
        )
        try:
            self._run_progress(
                command,
                "final audio mux",
                expected_duration=final_duration,
            )
            log.info("FFmpeg final audio mux end elapsed=%.2fs", time.monotonic() - mux_started)
            info = probe_media(temporary, self.ffprobe)
            self._validate(info, final_duration)
            temporary.replace(output)
            return info
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _validate(self, info: MediaInfo, expected_duration: float) -> None:
        errors: list[str] = []
        if (info.width, info.height) != (self.spec.width, self.spec.height):
            errors.append(f"geometry is {info.width}x{info.height}")
        if info.fps is None or abs(info.fps - self.spec.fps) > 0.05:
            errors.append(f"fps is {info.fps}")
        if info.video_codec != "h264":
            errors.append(f"video codec is {info.video_codec}")
        if info.audio_codec != "aac":
            errors.append(f"audio codec is {info.audio_codec}")
        if abs(info.duration - expected_duration) > 0.25:
            errors.append(f"duration is {info.duration:.3f}s; expected {expected_duration:.3f}s")
        if errors:
            raise FFmpegError("Native output validation failed: " + "; ".join(errors))


def write_render_manifest(path: Path, *, encoder: EncoderSettings, spec: RenderSpec,
                          info: MediaInfo, extra: dict) -> None:
    payload = {
        "encoder": asdict(encoder),
        "render": asdict(spec),
        "output": asdict(info),
        **extra,
    }
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
