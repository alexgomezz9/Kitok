"""Bulk replacement of unpublished ready videos with native renders."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from .file_manager import copy_atomic, output_filename
from .video_validator import VideoValidator
from .generation import GenerationService
from .locks import generation_lock, GenerationBusy


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
        self.generator = GenerationService(settings,preset)

    def run(self, *, dry_run=False, ids: set[str] | None = None) -> RegenerationSummary:
        """Render native replacements sequentially; dry-run never writes or uses providers."""
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
                except GenerationBusy as error:
                    summary.skipped += 1
                    self.print_line(f"SKIP {item.id}: {error}")
                    continue
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
        with generation_lock(self.s, item.id):
            self._regenerate_locked(item)

    def _regenerate_locked(self, item):
        # Never recover a prior task for this command; every attempt is fresh.
        attempts = int(self.state.get(item.id).get("attempts", 0)) + 1
        self.state.upsert(item.id, attempts=attempts, generation_renderer="native",
                          regeneration_status="in_progress",
                          last_error=None)
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
            workspace = Path(temp)
            plan = self.generator.plan(item, workspace)
            source = None
            staged = Path(temp) / name
            self.generator.finish(item, plan, source, staged, workspace)
            validation = self.validator.prepare(staged,item.platforms,self.s.ffmpeg_binary)
            if not validation.ok:
                raise RuntimeError("Invalid MP4: " + "; ".join(validation.errors))
            for target in dict.fromkeys((generated, local, external)):
                copy_atomic(staged, target)

        self.state.upsert(item.id, status="ready", output_path=str(generated),
                          ready_path=str(external), validation=validation.model_dump(),
                          regeneration_status="succeeded", last_error=None,
                          generation_warnings=self.generator.last_warnings,
                          generation_debug=self.generator.last_metadata)
