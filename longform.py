from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from kitok.config import PROJECT_ROOT, Settings
from kitok.models import ContentItem, MPTTask
from kitok.mpt_client import MPTClient, TASK_STATE_COMPLETE, TASK_STATE_FAILED


POLL_INTERVAL_SECONDS = 5
MAX_WAIT_SECONDS = 90 * 60


class LongformError(RuntimeError):
    """A human-readable long-form runner error."""


@dataclass(frozen=True)
class LongformDefinition:
    item: ContentItem
    voice_name: str
    voice_rate: float
    video_clip_duration: float


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

    voice_name = _required_text(raw, "voice_name")
    voice_rate = _positive_number(raw, "voice_rate", 1.0)
    video_clip_duration = _positive_number(raw, "video_clip_duration", 5.0)

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
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> Path:
    content_id = definition.item.id
    destination = longform_output_path(content_id, project_root=project_root)
    task_path = longform_task_path(content_id, project_root=project_root)

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
