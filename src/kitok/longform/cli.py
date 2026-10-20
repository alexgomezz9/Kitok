from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import math
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from kitok.config import PROJECT_ROOT, Settings
from kitok.locks import generation_lock
from kitok.dialogue_audio import media_duration
from kitok.models import ContentItem, MPTTask
from kitok.mpt_client import MPTClient, TASK_STATE_COMPLETE, TASK_STATE_FAILED


POLL_INTERVAL_SECONDS = 5
MAX_WAIT_SECONDS = 90 * 60
DEFAULT_NARRATOR_VOICE = (
    "fish_audio:e686ae649ee44f219a108aacba206c1a:Loose Thread Narrator"
)
DEFAULT_VOICE_RATE = 0.98
DEFAULT_BACKGROUND_MUSIC_FILE = Path("assets/music/loose_thread/level.mp3")
DEFAULT_BACKGROUND_MUSIC_VOLUME = 0.06
DEFAULT_AUDIO_LOUDNESS_TARGET = -16.0
DEFAULT_AUDIO_LRA_TARGET = 7.0
DEFAULT_AUDIO_TRUE_PEAK_TARGET = -1.5
STOCK_CLIP_DURATION_MIN = 5.5
STOCK_CLIP_DURATION_MAX = 8.5
VISUAL_FADE_IN_SECONDS = 0.6
VISUAL_FADE_OUT_SECONDS = 1.25
VALID_TTS_ENDINGS = (".", "!", "?", '"', "'", "]", ")")


class LongformError(RuntimeError):
    """A human-readable long-form runner error."""


@dataclass(frozen=True)
class LongformDefinition:
    item: ContentItem
    voice_name: str
    voice_rate: float
    video_clip_duration_min: float
    video_clip_duration_max: float
    background_music_file: Path
    background_music_volume: float
    audio_loudness_target: float
    audio_lra_target: float
    audio_true_peak_target: float
    music_enabled: bool
    preserve_debug_audio: bool
    music_mode: str | None = None
    music_track: str | None = None
    mounting_style: str = "basic"


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise LongformError(f"{label} does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LongformError(
            f"{label} is not valid JSON ({path}:{exc.lineno}:{exc.colno}): {exc.msg}"
        ) from exc
    except OSError as exc:
        raise LongformError(f"Could not read {label.lower()} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LongformError(f"{label} must contain a JSON object: {path}")
    return value


def _required_text(raw: dict[str, Any], field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise LongformError(f"Long-form config field '{field}' is required and must not be blank")
    return value.strip()


def _positive_number(raw: dict[str, Any], field: str, default: float) -> float:
    value = raw.get(field, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise LongformError(f"Long-form config field '{field}' must be a positive number")
    return float(value)


def _number(raw: dict[str, Any], field: str, default: float, *, minimum: float | None = None) -> float:
    value = raw.get(field, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LongformError(f"Long-form config field '{field}' must be a number")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        qualifier = f" at least {minimum:g}" if minimum is not None else " finite"
        raise LongformError(f"Long-form config field '{field}' must be{qualifier}")
    return result


def _boolean(raw: dict[str, Any], field: str, default: bool) -> bool:
    value = raw.get(field, default)
    if not isinstance(value, bool):
        raise LongformError(f"Long-form config field '{field}' must be true or false")
    return value


def _optional_text(raw: dict[str, Any], field: str, default: str) -> str:
    value = raw.get(field, default)
    if not isinstance(value, str) or not value.strip():
        raise LongformError(f"Long-form config field '{field}' must not be blank")
    return value.strip()


def validate_tts_script(script: str) -> str:
    """Normalize and reject narration that appears truncated before MPT reaches Fish."""
    text = script.strip()
    if not text:
        raise LongformError("TTS script is empty")
    if not text.endswith(VALID_TTS_ENDINGS):
        raise LongformError(
            "TTS script appears truncated. "
            f"Last characters: {text[-150:]}"
        )
    return text


def log_tts_script_validation(script: str) -> None:
    ending = json.dumps(script[-150:], ensure_ascii=False)
    print("TTS SCRIPT VALIDATION")
    print(f"characters={len(script)}")
    print(f"words={len(script.split())}")
    print(f"ending={ending}")


def load_longform_config(
    config_path: str | Path, *, project_root: Path = PROJECT_ROOT
) -> LongformDefinition:
    path = Path(config_path).expanduser()
    if not path.is_absolute():
        path = project_root / path
    raw = _read_json_object(path, "Long-form config")

    content_id = _required_text(raw, "id")
    subject = _required_text(raw, "subject")
    script_value = _required_text(raw, "script_file")
    script_path = Path(script_value).expanduser()
    if not script_path.is_absolute():
        script_path = project_root / script_path
    if not script_path.is_file():
        raise LongformError(f"Narration script does not exist: {script_path}")
    try:
        script = script_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise LongformError(f"Could not read narration script {script_path}: {exc}") from exc
    if not script:
        raise LongformError(f"Narration script is empty: {script_path}")

    keywords = raw.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        raise LongformError("Long-form config field 'keywords' is required and must be a non-empty list")
    if len(keywords) > 20:
        raise LongformError("Long-form config has more than the 20 keywords ContentItem supports")
    if any(not isinstance(keyword, str) for keyword in keywords):
        raise LongformError("Every value in long-form config field 'keywords' must be a string")

    # narrator_voice is the descriptive key for new Loose Thread configs.
    # voice_name remains supported so existing configs (including Daniel) keep working.
    voice_name = _optional_text(
        raw, "narrator_voice", raw.get("voice_name", DEFAULT_NARRATOR_VOICE)
    )
    voice_rate = _positive_number(raw, "voice_rate", DEFAULT_VOICE_RATE)
    music_value = _optional_text(
        raw, "background_music_file", str(DEFAULT_BACKGROUND_MUSIC_FILE)
    )
    background_music_file = Path(music_value).expanduser()
    if not background_music_file.is_absolute():
        background_music_file = project_root / background_music_file
    background_music_volume = _number(
        raw, "background_music_volume", DEFAULT_BACKGROUND_MUSIC_VOLUME, minimum=0
    )
    audio_loudness_target = _number(
        raw, "audio_loudness_target", DEFAULT_AUDIO_LOUDNESS_TARGET
    )
    audio_lra_target = _number(
        raw, "audio_lra_target", DEFAULT_AUDIO_LRA_TARGET, minimum=0
    )
    audio_true_peak_target = _number(
        raw, "audio_true_peak_target", DEFAULT_AUDIO_TRUE_PEAK_TARGET
    )
    music_enabled = _boolean(raw, "music_enabled", True)
    preserve_debug_audio = _boolean(raw, "preserve_debug_audio", False)
    music_mode = raw.get("music_mode")
    if music_mode not in (None, "off", "auto", "manual"):
        raise LongformError("music_mode must be off, auto or manual")
    music_track = raw.get("music_track")
    mounting_style = raw.get("mounting_style", "basic")
    if mounting_style not in ("basic", "documentary"):
        raise LongformError("mounting_style must be basic or documentary")
    if music_mode == "manual":
        from ..audio_library import ID
        if not isinstance(music_track, str) or not ID.fullmatch(music_track):
            raise LongformError("Manual music requires a catalog track ID")
    elif music_track is not None:
        raise LongformError("music_track requires music_mode manual")
    if music_mode is not None:
        music_enabled = music_mode != "off"
    if mounting_style == "documentary" and music_mode is None and music_enabled:
        raise LongformError("Documentary music requires explicit music_mode off, auto or manual")

    try:
        item = ContentItem(
            id=content_id,
            subject=subject,
            script=script,
            keywords=keywords,
            caption="",
            youtube_title=raw.get("youtube_title") or subject,
            platforms=["youtube"],
            content_format="explainer",
            visual_profile="pexels",
            schedule_enabled=False,
        )
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise LongformError(f"Invalid long-form content: {details}") from exc

    return LongformDefinition(
        item=item,
        voice_name=voice_name,
        voice_rate=voice_rate,
        video_clip_duration_min=STOCK_CLIP_DURATION_MIN,
        video_clip_duration_max=STOCK_CLIP_DURATION_MAX,
        background_music_file=background_music_file,
        background_music_volume=background_music_volume,
        audio_loudness_target=audio_loudness_target,
        audio_lra_target=audio_lra_target,
        audio_true_peak_target=audio_true_peak_target,
        music_enabled=music_enabled,
        preserve_debug_audio=preserve_debug_audio,
        music_mode=music_mode, music_track=music_track, mounting_style=mounting_style,
    )


def build_longform_preset(
    definition: LongformDefinition,
    *,
    preset_path: Path = PROJECT_ROOT / "presets" / "mpt_default.json",
) -> dict[str, Any]:
    preset = _read_json_object(preset_path, "MPT preset")
    preset.update(
        {
            "video_aspect": "16:9",
            "video_fit_mode": "cover",
            "video_concat_mode": "sequential",
            "video_transition_mode": None,
            # MPT still uses video_clip_duration as its maximum when downloading
            # candidates. The explicit range controls each final stock cut.
            "video_clip_duration": definition.video_clip_duration_max,
            "video_clip_duration_min": definition.video_clip_duration_min,
            "video_clip_duration_max": definition.video_clip_duration_max,
            "video_clip_speed": 1.0,
            "match_materials_to_script": True,
            "video_count": 1,
            "video_source": "pexels",
            "video_language": "en",
            "voice_name": definition.voice_name,
            "voice_volume": 1.0,
            "voice_rate": definition.voice_rate,
            "bgm_type": "",
            "bgm_file": "",
            "bgm_volume": 0.0,
            "subtitle_enabled": False,
        }
    )
    return preset


def longform_output_path(content_id: str, *, project_root: Path = PROJECT_ROOT) -> Path:
    return project_root / "outputs" / "longform" / f"{content_id}.mp4"


def longform_task_path(content_id: str, *, project_root: Path = PROJECT_ROOT) -> Path:
    return project_root / "outputs" / "longform" / "tasks" / f"{content_id}.json"


def longform_music_ready(definition: LongformDefinition, settings) -> bool:
    if not definition.music_enabled:
        return True
    if definition.music_mode is None:
        return definition.background_music_file.is_file()
    from ..audio_library import AudioLibrary
    root = settings.data_root or PROJECT_ROOT
    catalog, cache = root / "presets" / "music_sources.json", root / "cache" / "audio-library"
    if not catalog.is_file() or not cache.is_dir():
        return False
    library = AudioLibrary(catalog, cache, ffmpeg=settings.ffmpeg_binary, ffprobe=settings.ffprobe_binary)
    try:
        if definition.music_mode == "auto":
            return library.narrative_options(definition.item.script, channel="loose_thread")['eligible']
        return any(t["id"] == definition.music_track for t in library.available(channel="loose_thread"))
    finally:
        library.close()


def _require_longform_music(definition: LongformDefinition) -> None:
    if definition.music_enabled and definition.music_mode is None and not definition.background_music_file.is_file():
        raise LongformError(
            "Loose Thread background music is enabled but the file does not exist: "
            f"{definition.background_music_file}"
        )


def _debug_audio_paths(source: Path, content_id: str) -> tuple[Path, Path, Path]:
    debug_dir = source.parent / "debug"
    return (
        debug_dir / f"{content_id}_01_raw.mp3",
        debug_dir / f"{content_id}_02_normalized.mp3",
        debug_dir / f"{content_id}_03_final_mix.mp3",
    )


def _export_debug_audio(
    source: Path,
    destination: Path,
    *,
    settings: Settings,
    stage: str,
    audio_filter: str | None = None,
) -> Path:
    """Atomically export one opt-in Loose Thread debug audio stage."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp{destination.suffix}")
    temporary.unlink(missing_ok=True)
    command = [
        settings.ffmpeg_binary, "-nostdin", "-v", "error", "-y", "-i", str(source),
        "-map", "0:a:0", "-vn",
    ]
    if audio_filter:
        command += ["-af", audio_filter]
    command += ["-c:a", "libmp3lame", "-b:a", "192k", str(temporary)]
    try:
        subprocess.run(
            command, capture_output=True, text=True, check=True, timeout=1800
        )
    except subprocess.CalledProcessError as exc:
        temporary.unlink(missing_ok=True)
        detail = (exc.stderr or "").strip()[-500:]
        suffix = f": {detail}" if detail else ""
        raise LongformError(
            f"Loose Thread debug audio export failed during {stage}{suffix}"
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        temporary.unlink(missing_ok=True)
        raise LongformError(
            f"Loose Thread debug audio export failed during {stage}"
        ) from exc
    if not temporary.is_file() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise LongformError(
            f"Loose Thread debug audio export failed during {stage}: no output"
        )
    temporary.replace(destination)
    return destination


def postprocess_longform_audio(
    source: Path,
    definition: LongformDefinition,
    *,
    settings: Settings,
) -> Path:
    """Normalize Loose Thread narration and optionally mix its local music."""
    _require_longform_music(definition)
    if not source.is_file():
        raise LongformError(f"Downloaded MPT video does not exist: {source}")

    temporary = source.with_name(f".{source.name}.postprocess.tmp{source.suffix}")
    temporary.unlink(missing_ok=True)
    loudnorm = (
        f"loudnorm=I={definition.audio_loudness_target:g}:"
        f"LRA={definition.audio_lra_target:g}:"
        f"TP={definition.audio_true_peak_target:g}"
    )
    debug_paths = _debug_audio_paths(source, definition.item.id)
    if definition.preserve_debug_audio:
        _export_debug_audio(
            source, debug_paths[0], settings=settings, stage="raw MPT narration"
        )
        _export_debug_audio(
            source,
            debug_paths[1],
            settings=settings,
            stage="normalized narration",
            audio_filter=loudnorm,
        )
    command = [
        settings.ffmpeg_binary, "-nostdin", "-v", "error", "-y", "-i", str(source)
    ]

    try:
        source_duration = media_duration(source, settings.ffprobe_binary)
    except RuntimeError as exc:
        raise LongformError(
            f"Loose Thread audio post-processing failed during duration probe: {exc}"
        ) from exc
    output_duration = source_duration + VISUAL_FADE_OUT_SECONDS
    source_duration_text = f"{source_duration:g}"
    output_duration_text = f"{output_duration:g}"
    video_filter = (
        f"[0:v:0]fade=t=in:st=0:d={VISUAL_FADE_IN_SECONDS:g},"
        f"tpad=stop_mode=clone:stop_duration={VISUAL_FADE_OUT_SECONDS:g},"
        f"fade=t=out:st={source_duration_text}:d={VISUAL_FADE_OUT_SECONDS:g}[video]"
    )
    # Padding after loudness normalization keeps silence out of loudnorm's
    # analysis. It also leaves the narration untouched while the final held
    # frame fades to black after the original video/audio has ended.
    voice_filter = (
        f"[0:a:0]{loudnorm},apad=whole_dur={output_duration_text},"
        f"atrim=duration={output_duration_text}[voice]"
    )

    if definition.music_enabled:
        command += ["-stream_loop", "-1", "-i", str(definition.background_music_file)]
        filters = (
            f"{video_filter};{voice_filter};"
            f"[1:a:0]volume={definition.background_music_volume:g},"
            f"afade=t=in:st=0:d=1,"
            f"afade=t=out:st={source_duration_text}:d={VISUAL_FADE_OUT_SECONDS:g},"
            f"atrim=duration={output_duration_text}[music];"
            "[voice][music]amix=inputs=2:duration=first:"
            "dropout_transition=2:normalize=0,"
            f"atrim=duration={output_duration_text}[audio]"
        )
    else:
        filters = f"{video_filter};{voice_filter.replace('[voice]', '[audio]')}"

    command += [
        "-filter_complex", filters,
        "-map", "[video]", "-map", "[audio]",
        "-map_metadata", "0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{output_duration:.6f}",
        "-movflags", "+faststart",
        str(temporary),
    ]
    try:
        subprocess.run(
            command, capture_output=True, text=True, check=True, timeout=1800
        )
    except subprocess.CalledProcessError as exc:
        temporary.unlink(missing_ok=True)
        detail = (exc.stderr or "").strip()[-500:]
        suffix = f": {detail}" if detail else ""
        raise LongformError(
            f"Loose Thread audio post-processing failed during FFmpeg mix{suffix}"
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        temporary.unlink(missing_ok=True)
        raise LongformError(
            "Loose Thread audio post-processing failed while starting or waiting for FFmpeg"
        ) from exc

    if not temporary.is_file() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        raise LongformError(
            "Loose Thread audio post-processing failed: FFmpeg produced no output"
        )
    if definition.preserve_debug_audio:
        try:
            _export_debug_audio(
                temporary,
                debug_paths[2],
                settings=settings,
                stage="final narration and music mix",
            )
        except LongformError:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(source)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise LongformError(
            "Loose Thread audio post-processing failed during atomic replacement; "
            "the downloaded MPT video was preserved"
        ) from exc
    return source


def _save_task(task_path: Path, task_id: str, content_id: str) -> None:
    try:
        task_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "task_id": task_id,
            "content_id": content_id,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
        temporary = task_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        temporary.replace(task_path)
    except OSError as exc:
        raise LongformError(
            f"MPT accepted task {task_id}, but its recovery marker could not be saved "
            f"to {task_path}: {exc}. Keep this task ID and resume it manually."
        ) from exc


def _saved_task_id(task_path: Path) -> str | None:
    if not task_path.exists():
        return None
    try:
        record = json.loads(task_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    task_id = record.get("task_id") if isinstance(record, dict) else None
    return str(task_id) if task_id else None


def _task_failure(task: MPTTask) -> LongformError:
    return LongformError(
        f"MPT task {task.task_id} failed: error={task.error!r}, "
        f"failed_stage={task.failed_stage!r}, raw={task.raw!r}"
    )


def poll_and_download(
    client: MPTClient,
    task_id: str,
    destination: Path,
    *,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> Path:
    started = monotonic()
    last_status: tuple[int | None, int | float | None, int] | None = None

    while True:
        if monotonic() - started >= MAX_WAIT_SECONDS:
            raise LongformError(
                f"Timed out after 90 minutes waiting for MPT task {task_id}. "
                f"Resume it with --resume {task_id}."
            )

        task = client.get_task(task_id)
        status = (task.state, task.progress, len(task.videos))
        if status != last_status:
            print(f"state={task.state} progress={task.progress} videos={len(task.videos)}")
            last_status = status

        if task.state == TASK_STATE_COMPLETE:
            if not task.videos:
                raise LongformError(f"MPT task {task_id} completed but returned no video")
            print(f"MPT task complete: {datetime.now(timezone.utc).isoformat()}")
            download_started = monotonic()
            print(f"Artifact download start: {datetime.now(timezone.utc).isoformat()}")
            client.download_artifact(task.videos[0], destination)
            print(
                f"Artifact download end: {datetime.now(timezone.utc).isoformat()} "
                f"({monotonic() - download_started:.2f}s)"
            )
            return destination

        if task.state == TASK_STATE_FAILED:
            raise _task_failure(task)

        sleep(POLL_INTERVAL_SECONDS)


def run_longform(
    definition: LongformDefinition,
    preset: dict[str, Any],
    *,
    settings: Settings,
    project_root: Path = PROJECT_ROOT,
    resume_task_id: str | None = None,
    start_over: bool = False,
    client_factory: Callable[..., MPTClient] = MPTClient,
    audio_processor: Callable[..., Path] = postprocess_longform_audio,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> Path:
    content_id = definition.item.id
    destination = longform_output_path(content_id, project_root=project_root)
    task_path = longform_task_path(content_id, project_root=project_root)
    _require_longform_music(definition)

    if resume_task_id is None:
        validated_script = validate_tts_script(definition.item.script)
        log_tts_script_validation(validated_script)
        saved_task_id = _saved_task_id(task_path)
        if task_path.exists() and not start_over:
            task_label = saved_task_id or "an unreadable saved task"
            raise LongformError(
                f"Refusing to submit another render: {task_label} is saved for {content_id}. "
                f"Resume it with '--resume {saved_task_id}' or explicitly use --start-over."
                if saved_task_id
                else f"Refusing to submit another render: {task_path} already exists. "
                "Inspect it, resume its task ID, or explicitly use --start-over."
            )
        if destination.exists() and not start_over:
            raise LongformError(
                f"Output already exists: {destination}. Use --start-over to render it again."
            )
        if start_over:
            task_path.unlink(missing_ok=True)

    client = client_factory(
        settings.mpt_base_url,
        settings.mpt_api_key,
        timeout_seconds=settings.mpt_request_timeout_seconds,
        retry_attempts=settings.http_retry_attempts,
        retry_base_seconds=settings.http_retry_base_seconds,
    )
    active_task_id = resume_task_id
    try:
        if active_task_id is None:
            print("Submitting...")
            active_task_id = client.submit_video(definition.item, preset)
            print(f"Task: {active_task_id}")
            _save_task(task_path, active_task_id, content_id)
        else:
            print(f"Resuming task: {active_task_id}")

        result = poll_and_download(
            client,
            active_task_id,
            destination,
            sleep=sleep,
            monotonic=monotonic,
        )
        postprocess_started = monotonic()
        print(f"Kitok postprocess start: {datetime.now(timezone.utc).isoformat()}")
        result = audio_processor(result, definition, settings=settings)
        print(
            f"Kitok postprocess end: {datetime.now(timezone.utc).isoformat()} "
            f"({monotonic() - postprocess_started:.2f}s)"
        )
        if _saved_task_id(task_path) == active_task_id:
            task_path.unlink(missing_ok=True)
        print(f"Final DONE: {datetime.now(timezone.utc).isoformat()} {result.resolve()}")
        return result
    finally:
        client.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render new long-form videos with experimental Native (Fish + Pexels + FFmpeg). MPT only recovers existing tasks."
    )
    parser.add_argument("config", help="Path to the long-form JSON content definition")
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Validate the script and local prerequisites without generating, network calls or writes.',
    )
    parser.add_argument(
        "--renderer", choices=("native", "mpt"), default="native",
        help="Default: native (experimental). mpt is allowed only with --resume TASK_ID; it never submits a new task.",
    )
    parser.add_argument(
        "--encoder", choices=("auto", "h264_nvenc", "libx264"), default="auto",
        help="Native video encoder; auto runtime-probes NVENC and falls back to libx264.",
    )
    parser.add_argument(
        "--nvenc-preset", choices=("p4", "p5", "p6", "p7"), default="p5",
        help="Native NVENC preset. p5 is the benchmark-backed quality-first default.",
    )
    parser.add_argument(
        "--keep-native-workspace", action="store_true",
        help="Keep Native temporary narration, filter scripts and chunks after success.",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show Native DEBUG details such as cache decisions, selections and FFmpeg commands.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--resume", metavar="TASK_ID", help="Recover a known historical task; requires --renderer mpt and never submits a new render")
    group.add_argument(
        "--start-over",
        action="store_true",
        help="Explicitly render again with Native; may use paid providers. Existing documentary/library-music outputs require a new content ID. Unavailable for MPT.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    lease = ExitStack()
    try:
        if args.renderer == 'mpt' and (not args.resume or not args.resume.strip() or args.start_over):
            raise LongformError('MPT is historical recovery only: use --renderer mpt --resume TASK_ID. New MPT tasks and --start-over are disabled.')
        if args.renderer == 'native' and args.resume:
            raise LongformError('--resume requires --renderer mpt and a known historical task ID')
        definition = load_longform_config(args.config)
        if args.renderer == 'mpt' and (definition.mounting_style != 'basic' or definition.music_mode is not None):
            raise LongformError('mounting_style and music_mode options are Native-only; historical MPT recovery requires basic mounting and legacy music configuration')
        settings = Settings()
        if args.dry_run:
            renderer = args.renderer
            validate_tts_script(definition.item.script)
            checks = {
                'ffmpeg': bool(shutil.which(settings.ffmpeg_binary)),
                'ffprobe': bool(shutil.which(settings.ffprobe_binary)),
                'music': longform_music_ready(definition, settings),
            }
            if renderer == 'native':
                from kitok.rendering.native import fish_reference_id
                fish_reference_id(definition.voice_name)
                checks.update(fish_configured=bool(settings.fish_api_key.get_secret_value()),
                              pexels_configured=bool(settings.pexels_api_key.get_secret_value()))
            print(json.dumps({'dry_run': True, 'renderer': renderer,
                              'words': len(definition.item.script.split()), 'checks': checks,
                              'note': 'Local checks only; no network, rendering, uploads or scheduling.'},
                             ensure_ascii=False, indent=2))
            return 0 if all(checks.values()) else 1
        lease.enter_context(generation_lock(settings, f'longform-{definition.item.id}'))
        if args.renderer == 'native':
            historical_task = longform_task_path(definition.item.id, project_root=settings.data_root or PROJECT_ROOT)
            if historical_task.exists():
                saved_id = _saved_task_id(historical_task)
                recovery = f'--renderer mpt --resume {saved_id or "TASK_ID"}'
                raise LongformError(
                    f'A historical MPT task marker exists for {definition.item.id}. '
                    f'Review and recover it with {recovery} before generating another voice. '
                    'Native --start-over does not discard historical MPT tasks.'
                )
        if args.renderer == "mpt":
            from kitok.rendering.mpt import MptRenderer

            preset = build_longform_preset(definition)
            renderer = MptRenderer(
                lambda current, *, start_over=False: run_longform(
                    current,
                    preset,
                    settings=settings,
                    resume_task_id=args.resume,
                    start_over=start_over,
                )
            )
            renderer.render(definition, start_over=args.start_over)
        else:
            if args.resume:
                raise LongformError("--resume is MPT-only; Native never creates an MPT task")
            from kitok.logging_setup import configure_logging
            from kitok.media.ffmpeg import FFmpegNativeEngine, choose_encoder
            from kitok.providers.pexels import PexelsProvider
            from kitok.rendering.native import NativeLongformRenderer

            configure_logging(settings.logs_dir, args.verbose)
            provider = PexelsProvider(
                settings.pexels_api_key.get_secret_value(),
                settings.native_cache_dir,
                ffprobe=settings.ffprobe_binary,
                attempts=settings.http_retry_attempts,
            )
            try:
                encoder = choose_encoder(
                    settings.ffmpeg_binary,
                    requested=args.encoder,
                    nvenc_preset=args.nvenc_preset,
                )
                engine = FFmpegNativeEngine(
                    ffmpeg=settings.ffmpeg_binary,
                    ffprobe=settings.ffprobe_binary,
                    encoder=encoder,
                )
                result = NativeLongformRenderer(
                    settings,
                    provider,
                    engine,
                    output_path=longform_output_path(definition.item.id),
                    keep_workspace=args.keep_native_workspace,
                ).render(definition, start_over=args.start_over)
                print(f"Final DONE: {datetime.now(timezone.utc).isoformat()} {result.output.resolve()}")
            finally:
                provider.close()
    except (LongformError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        lease.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
