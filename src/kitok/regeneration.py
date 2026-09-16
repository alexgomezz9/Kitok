"""Bulk replacement of unpublished ready videos with fresh MPT renders."""
from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .file_manager import copy_atomic, output_filename
from .mpt_client import TASK_STATE_COMPLETE, TASK_STATE_FAILED
from .video_validator import VideoValidator


def skip_reason(record: dict) -> str | None:
    if record.get("status", "pending") != "ready":
        return f"status is {record.get('status', 'pending')}"
    publishing = record.get("publishing") or {}
    if not isinstance(publishing, dict):
        return "unrecognized publishing metadata exists"
    if publishing.get("cloudinary"):
        return "Cloudinary asset/metadata exists"
    if publishing.get("buffer"):
        return "Buffer publishing metadata exists"
    return None


@dataclass
class RegenerationSummary:
    regenerated: int = 0
    failed: int = 0
    skipped: int = 0
    would_regenerate: int = 0


class ReadyRegenerator:
    def __init__(self, settings, queue, state, client, preset, *, print_line=print):
        self.s, self.q, self.state = settings, queue, state
        self.client, self.preset, self.print_line = client, preset, print_line
        self.validator = VideoValidator(
            settings.ffprobe_binary, settings.min_video_seconds,
            settings.max_video_seconds, settings.min_vertical_width,
            settings.min_vertical_height,
        )

    def run(self, *, dry_run=False, ids: set[str] | None = None) -> RegenerationSummary:
        """Render fresh MPT tasks sequentially; dry-run never writes or contacts MPT."""
        summary = RegenerationSummary()
        items = [item for item in self.q.items if ids is None or item.id in ids]
        if ids and ids - set(self.q.by_id()):
            raise ValueError("Unknown regeneration content ID")
        total = len(items)
        if dry_run:
            for index, item in enumerate(items, 1):
                reason = skip_reason(self.state.get(item.id))
                if reason:
                    summary.skipped += 1
                    self.print_line(f"[{index}/{total}] SKIP {item.id}: {reason}")
                else:
                    summary.would_regenerate += 1
                    self.print_line(f"[{index}/{total}] WOULD REGENERATE {item.id}")
            return summary

        # Publishing operations use this same lock. Recheck each record under it.
        with self.state.publishing_lock():
            for index, item in enumerate(items, 1):
                reason = skip_reason(self.state.get(item.id))
                if reason:
                    summary.skipped += 1
                    self.print_line(f"[{index}/{total}] SKIP {item.id}: {reason}")
                    continue
                self.print_line(f"[{index}/{total}] REGENERATING {item.id}")
                try:
                    self._regenerate_one(item)
                except KeyboardInterrupt:
                    raise
                except Exception as error:
                    summary.failed += 1
                    self.state.upsert(item.id, status="ready", regeneration_status="failed",
                                      last_error=f"Regeneration failed: {error}")
                    self.print_line(f"[{index}/{total}] FAILED {item.id}: {error}")
                else:
                    summary.regenerated += 1
                    self.print_line(f"[{index}/{total}] REGENERATED {item.id}")
        return summary

    def _regenerate_one(self, item):
        # Never recover a prior task for this command; every attempt is fresh.
        attempts = int(self.state.get(item.id).get("attempts", 0)) + 1
        self.state.upsert(item.id, attempts=attempts, mpt_task_id=None,
                          mpt_progress=None, regeneration_status="in_progress",
                          last_error=None)
        task_id = self.client.submit_video(item, self.preset)
        self.state.upsert(item.id, mpt_task_id=task_id)
        task = self._wait(item, task_id)
        if task.state == TASK_STATE_FAILED:
            detail = task.error or "MoneyPrinterTurbo task failed"
            if task.failed_stage:
                detail += f" (stage: {task.failed_stage})"
            raise RuntimeError(detail)
        if not task.videos:
            raise RuntimeError("MPT completed without video artifacts")

        name = output_filename(item)
        generated = self.s.generated_dir / name
        local = self.s.local_ready_dir / name
        external = self.s.ready_dir.expanduser() / name
        if external.resolve() == local.resolve():
            external = local
        # A private staging directory keeps incomplete and invalid media away
        # from all published output paths. copy_atomic replaces each file only
        # after validation, using the existing .part + rename mechanism.
        with tempfile.TemporaryDirectory(prefix=".regenerate-", dir=self.s.generated_dir) as temp:
            staged = Path(temp) / name
            self.client.download_artifact(task.videos[0], staged)
            validation = self.validator.prepare(staged,item.platforms,self.s.ffmpeg_binary)
            if not validation.ok:
                raise RuntimeError("Invalid MP4: " + "; ".join(validation.errors))
            for target in dict.fromkeys((generated, local, external)):
                copy_atomic(staged, target)

        self.state.upsert(item.id, status="ready", output_path=str(generated),
                          ready_path=str(external), validation=validation.model_dump(),
                          regeneration_status="succeeded", last_error=None)

    def _wait(self, item, task_id):
        started = time.monotonic()
        timeout = self.s.task_timeout_minutes * 60
        while True:
            task = self.client.get_task(task_id)
            if task.state in (TASK_STATE_COMPLETE, TASK_STATE_FAILED):
                return task
            self.state.upsert(item.id, mpt_progress=task.progress)
            if time.monotonic() - started > timeout:
                raise TimeoutError(f"Timed out waiting for MPT task {task_id}")
            time.sleep(self.s.poll_interval_seconds)
