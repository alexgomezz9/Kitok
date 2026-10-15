from __future__ import annotations

import logging
import random
import shutil
import tempfile
import time
from pathlib import Path

from ..fish_voice import FishVoiceClient
from ..longform.models import TimelineClip
from ..longform.timeline import build_timeline
from ..media.ffmpeg import FFmpegNativeEngine, write_render_manifest
from ..media.ffprobe import probe_media
from ..stock.selector import OutputGeometry
from .base import LongformRenderer, RenderResult, RenderTimings

log = logging.getLogger("kitok.rendering.native")

class NativeRenderError(RuntimeError):
    pass


VALID_TTS_ENDINGS = (".", "!", "?", '"', "'", "]", ")")


def validate_native_script(script: str) -> str:
    text = script.strip()
    if not text:
        raise NativeRenderError("TTS script is empty")
    if not text.endswith(VALID_TTS_ENDINGS):
        raise NativeRenderError(
            f"TTS script appears truncated. Last characters: {text[-150:]}"
        )
    return text


def fish_reference_id(voice_name: str) -> str:
    parts = voice_name.split(":", 2)
    if len(parts) != 3 or parts[0] != "fish_audio" or not parts[1]:
        raise NativeRenderError(
            "Native long-form currently requires narrator_voice='fish_audio:<reference_id>:<name>'; "
            "use --renderer mpt for other voice providers"
        )
    return parts[1]


class NativeLongformRenderer(LongformRenderer):
    """Experimental isolated Fish + Pexels + FFmpeg long-form path."""

    name = "native"

    def __init__(
        self,
        settings,
        pexels,
        engine: FFmpegNativeEngine,
        *,
        output_path: Path,
        fish_factory=FishVoiceClient,
        seed: str | None = None,
        keep_workspace: bool = False,
        output=None,
    ):
        self.settings = settings
        self.pexels = pexels
        self.engine = engine
        self.output_path = output_path
        self.fish_factory = fish_factory
        self.seed = seed
        self.keep_workspace = keep_workspace
        self.output = output

    def _stage(self, label: str, elapsed: float) -> None:
        log.info("%s end elapsed=%.2fs", label, elapsed)
        if self.output:
            self.output(f"{label}: {elapsed:.2f}s")

    def render(self, definition, *, start_over: bool = False) -> RenderResult:
        started = time.monotonic()
        if self.output_path.exists() and not start_over:
            raise NativeRenderError(
                f"Output already exists: {self.output_path}. Use --start-over to replace it atomically."
            )
        content_id = getattr(getattr(definition, "item", None), "id", "unknown")
        log.info(
            "Native render start content_id=%s renderer=%s output=%s",
            content_id, self.name, self.output_path,
        )
        if definition.music_enabled and not definition.background_music_file.is_file():
            raise NativeRenderError(
                f"Loose Thread background music does not exist: {definition.background_music_file}"
            )
        reference_id = fish_reference_id(definition.voice_name)
        script = validate_native_script(definition.item.script)
        preflight = getattr(self.pexels, "preflight_searches", None)
        if preflight:
            preflight(definition.item.keywords, orientation="landscape")
        work_root = self.output_path.parent / ".native-work"
        work_root.mkdir(parents=True, exist_ok=True)
        workspace = Path(tempfile.mkdtemp(prefix=f"{definition.item.id}-", dir=work_root))
        success = False
        fish_seconds = search_seconds = download_seconds = timeline_seconds = 0.0
        ffmpeg_seconds = validation_seconds = 0.0
        try:
            narration = workspace / "narration.mp3"
            stage = time.monotonic()
            log.info("Fish start content_id=%s", definition.item.id)
            fish = self.fish_factory(
                self.settings.fish_api_key.get_secret_value(),
                self.settings.fish_model,
                timeout=self.settings.fish_tts_timeout_seconds,
            )
            try:
                # One coherent call: direction tags are forwarded verbatim.
                fish.synthesize(
                    script,
                    reference_id,
                    narration,
                    speed=definition.voice_rate,
                    temperature=0.8,
                    top_p=0.7,
                )
            finally:
                fish.close()
            fish_seconds = time.monotonic() - stage
            self._stage("Fish", fish_seconds)
            narration_duration = probe_media(narration, self.settings.ffprobe_binary).duration
            log.info("Narration duration=%.3fs", narration_duration)

            stage = time.monotonic()
            timeline_seed = self.seed or definition.item.id
            slots = build_timeline(
                narration_duration,
                definition.item.keywords,
                minimum_clip=definition.video_clip_duration_min,
                maximum_clip=definition.video_clip_duration_max,
                seed=timeline_seed,
            )
            timeline_seconds = time.monotonic() - stage

            stage = time.monotonic()
            ordered_queries = list(dict.fromkeys(slot.query for slot in slots))
            log.info("Pexels search start queries=%d", len(ordered_queries))
            log.debug("Pexels search queries=%r", ordered_queries)
            searches = {
                query: self.pexels.search_videos(query, orientation="landscape")
                for query in ordered_queries
            }
            search_seconds = time.monotonic() - stage
            self._stage("Pexels search", search_seconds)

            stage = time.monotonic()
            selected = []
            used_ids: set[int] = set()
            target = OutputGeometry(self.engine.spec.width, self.engine.spec.height)
            for slot in slots:
                choice = self.pexels.select_candidate(
                    searches[slot.query],
                    target=target,
                    minimum_duration=slot.duration,
                    used_ids=used_ids,
                )
                selected.append(choice)
                used_ids.add(choice.asset.asset_id)
                source_width = choice.variant.width
                source_height = choice.variant.height
                scale_factor = max(target.width / source_width, target.height / source_height)
                scale_kind = (
                    "upscale" if scale_factor > 1.000001
                    else "downscale" if scale_factor < 0.999999
                    else "none"
                )
                log.debug(
                    "Selected Pexels asset_id=%s query=%r source=%dx%d target=%dx%d scale=%s",
                    choice.asset.asset_id, slot.query, source_width, source_height,
                    target.width, target.height, scale_kind,
                )
            timeline_seconds += time.monotonic() - stage
            self._stage("Timeline", timeline_seconds)
            timeline_duration = sum(slot.duration for slot in slots)
            log.info(
                "Timeline clips=%d narration_duration=%.3fs timeline_duration=%.3fs",
                len(slots), narration_duration, timeline_duration,
            )

            stage = time.monotonic()
            log.info("Asset download/cache start unique_assets=%d", len(used_ids))
            local_by_id = {}
            for choice in selected:
                if choice.asset.asset_id not in local_by_id:
                    local_by_id[choice.asset.asset_id] = self.pexels.download_asset(choice)
            download_seconds = time.monotonic() - stage
            self._stage("Asset download/cache", download_seconds)

            source_rng = random.Random(f"{timeline_seed}:source-offsets")
            clips = []
            for slot, choice in zip(slots, selected, strict=True):
                available = max(0.0, choice.asset.duration - slot.duration)
                source_start = source_rng.uniform(0, available) if available else 0.0
                log.debug(
                    "Timeline clip=%d asset_id=%s source_offset=%.3fs duration=%.3fs path=%s",
                    slot.index + 1, choice.asset.asset_id, source_start,
                    slot.duration, local_by_id[choice.asset.asset_id],
                )
                clips.append(
                    TimelineClip(
                        slot=slot,
                        asset_id=choice.asset.asset_id,
                        source=local_by_id[choice.asset.asset_id],
                        source_start=source_start,
                    )
                )

            stage = time.monotonic()
            info = self.engine.render(
                clips,
                narration,
                narration_duration,
                self.output_path,
                workspace,
                music=definition.background_music_file if definition.music_enabled else None,
                music_volume=definition.background_music_volume,
                loudness_target=definition.audio_loudness_target,
                lra_target=definition.audio_lra_target,
                true_peak_target=definition.audio_true_peak_target,
                on_stage=self.output,
            )
            ffmpeg_seconds = time.monotonic() - stage
            self._stage("FFmpeg", ffmpeg_seconds)

            stage = time.monotonic()
            log.info("Validation start output=%s", self.output_path)
            final_info = probe_media(self.output_path, self.settings.ffprobe_binary)
            validation_seconds = time.monotonic() - stage
            self._stage("Validation", validation_seconds)
            total = time.monotonic() - started
            timings = RenderTimings(
                fish=fish_seconds,
                pexels_search=search_seconds,
                pexels_download_cache=download_seconds,
                timeline=timeline_seconds,
                ffmpeg=ffmpeg_seconds,
                validation=validation_seconds,
                total=total,
            )
            manifest = self.output_path.with_suffix(".native.json")
            write_render_manifest(
                manifest,
                encoder=self.engine.encoder,
                spec=self.engine.spec,
                info=final_info,
                extra={
                    "renderer": "native",
                    "content_id": definition.item.id,
                    "narration_duration": narration_duration,
                    "timings": timings.__dict__,
                    "timeline": [
                        {
                            "index": clip.slot.index,
                            "query": clip.slot.query,
                            "timeline_start": clip.slot.start,
                            "duration": clip.slot.duration,
                            "asset_id": clip.asset_id,
                            "source_start": clip.source_start,
                            "cache_path": str(clip.source),
                        }
                        for clip in clips
                    ],
                },
            )
            self._stage("TOTAL", total)
            log.info("Native final output path=%s", self.output_path.resolve())
            log.info(
                "Native render complete content_id=%s renderer=%s total_elapsed=%.2fs",
                definition.item.id, self.name, total,
            )
            success = True
            return RenderResult(
                output=self.output_path,
                renderer=self.name,
                timings=timings,
                metadata={
                    "manifest": str(manifest),
                    "narration_duration": narration_duration,
                    "clips": len(clips),
                    "encoder": self.engine.encoder.codec,
                    "preset": self.engine.encoder.preset,
                    "media": final_info,
                },
            )
        finally:
            if success and not self.keep_workspace:
                shutil.rmtree(workspace)
            elif not success:
                log.warning("Native workspace preserved after failure: %s", workspace)
                if self.output:
                    self.output(f"Native workspace preserved after failure: {workspace}")
