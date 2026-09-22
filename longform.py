from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from kitok.config import PROJECT_ROOT, Settings
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
DEFAULT_BACKGROUND_MUSIC_VOLUME = 0.07
DEFAULT_AUDIO_LOUDNESS_TARGET = -16.0
DEFAULT_AUDIO_LRA_TARGET = 7.0
DEFAULT_AUDIO_TRUE_PEAK_TARGET = -1.5


class LongformError(RuntimeError):
    """A human-readable long-form runner error."""


@dataclass(frozen=True)
class LongformDefinition:
    item: ContentItem
    voice_name: str
    voice_rate: float
    video_clip_duration: float
    background_music_file: Path
    background_music_volume: float
    audio_loudness_target: float
    audio_lra_target: float
    audio_true_peak_target: float
    music_enabled: bool
    preserve_debug_audio: bool


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
    video_clip_duration = _positive_number(raw, "video_clip_duration", 5.0)
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
        video_clip_duration=video_clip_duration,
        background_music_file=background_music_file,
        background_music_volume=background_music_volume,
        audio_loudness_target=audio_loudness_target,
        audio_lra_target=audio_lra_target,
        audio_true_peak_target=audio_true_peak_target,
        music_enabled=music_enabled,
        preserve_debug_audio=preserve_debug_audio,
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
            "video_clip_duration": definition.video_clip_duration,
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


def _require_longform_music(definition: LongformDefinition) -> None:
    if definition.music_enabled and not definition.background_music_file.is_file():
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
        video_duration = media_duration(source, settings.ffprobe_binary)
    except RuntimeError as exc:
        raise LongformError(
            f"Loose Thread audio post-processing failed during duration probe: {exc}"
        ) from exc
    duration_text = f"{video_duration:g}"
    # Padding after loudness normalization keeps silence out of loudnorm's
    # analysis while making the first amix input last exactly as long as video.
    voice_filter = (
        f"[0:a:0]{loudnorm},apad=whole_dur={duration_text},"
        f"atrim=duration={duration_text}[voice]"
    )

    if definition.music_enabled:
        fade_out_duration = min(1.5, video_duration)
        fade_out_start = max(0.0, video_duration - fade_out_duration)
        command += ["-stream_loop", "-1", "-i", str(definition.background_music_file)]
        filters = (
            f"{voice_filter};"
            f"[1:a:0]volume={definition.background_music_volume:g},"
            f"afade=t=in:st=0:d=1,"
            f"afade=t=out:st={fade_out_start:g}:d={fade_out_duration:g},"
            f"atrim=duration={duration_text}[music];"
            "[voice][music]amix=inputs=2:duration=first:"
            "dropout_transition=2:normalize=0,"
            f"atrim=duration={duration_text}[audio]"
        )
    else:
        filters = voice_filter.replace("[voice]", "[audio]")

    command += [
        "-filter_complex", filters,
        "-map", "0:v:0", "-map", "[audio]",
        "-map_metadata", "0",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{video_duration:.6f}",
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
            print("Downloading...")
            client.download_artifact(task.videos[0], destination)
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
        print("Normalizing narration and mixing Loose Thread music...")
        result = audio_processor(result, definition, settings=settings)
        if _saved_task_id(task_path) == active_task_id:
            task_path.unlink(missing_ok=True)
        print(f"DONE: {result.resolve()}")
        return result
    finally:
        client.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit or resume an experimental long-form MPT video render."
    )
    parser.add_argument("config", help="Path to the long-form JSON content definition")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--resume", metavar="TASK_ID", help="Resume without submitting a new render")
    group.add_argument(
        "--start-over",
        action="store_true",
        help="Explicitly discard the saved task marker and submit a fresh render",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        definition = load_longform_config(args.config)
        preset = build_longform_preset(definition)
        run_longform(
            definition,
            preset,
            settings=Settings(),
            resume_task_id=args.resume,
            start_over=args.start_over,
        )
    except LongformError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
