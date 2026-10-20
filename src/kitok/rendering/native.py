from __future__ import annotations

import logging
import json
import hashlib
import random
import time
import os
import tempfile
from pathlib import Path

from ..fish_voice import FishVoiceClient
from ..longform.models import TimelineClip
from ..longform.timeline import build_timeline, build_semantic_timeline
from ..editing.alignment import detect_pauses, read_word_alignment
from ..editing.manifest import load_or_create_manifest, script_hash
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
            "choose a Fish narrator; legacy Edge voices are read-only history"
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
        confirmed_narration=None,
    ):
        self.settings = settings
        self.pexels = pexels
        self.engine = engine
        self.output_path = output_path
        self.fish_factory = fish_factory
        self.seed = seed
        self.keep_workspace = keep_workspace
        self.output = output
        self.confirmed_narration = confirmed_narration

    def _audio_library(self):
        from ..audio_library import AudioLibrary
        from ..config import PROJECT_ROOT
        root = self.settings.data_root or PROJECT_ROOT
        return AudioLibrary(root / "presets" / "music_sources.json", root / "cache" / "audio-library",
                            ffmpeg=self.settings.ffmpeg_binary, ffprobe=self.settings.ffprobe_binary)

    def _stage(self, label: str, elapsed: float) -> None:
        log.info("%s end elapsed=%.2fs", label, elapsed)
        if self.output:
            self.output(f"{label}: {elapsed:.2f}s")

    def render(self, definition, *, start_over: bool = False) -> RenderResult:
        started = time.monotonic()
        if self.confirmed_narration is not None:
            self.confirmed_narration.verify(definition, self.output_path)
            from ..native_recovery import CachedStock
            if not isinstance(self.pexels, CachedStock):
                raise NativeRenderError("Recovery requires the offline-only stock adapter")
        music_mode = getattr(definition, "music_mode", None)
        mounting_style = getattr(definition, "mounting_style", "basic")
        uses_motion = mounting_style == "documentary" or music_mode in {"auto", "manual"}
        editorial_receipt = self.output_path.with_suffix(".editorial.json")
        if (editorial_receipt.exists() or editorial_receipt.is_symlink()
                or uses_motion and (self.output_path.exists() or self.output_path.is_symlink())):
            raise NativeRenderError(
                "Motion output or receipt already exists; use a new content ID to preserve the previous cut. "
                "--start-over cannot replace documentary or library-music outputs."
            )
        if self.output_path.exists() and not start_over:
            raise NativeRenderError(
                f"Output already exists: {self.output_path}. Use --start-over to replace it atomically."
            )
        content_id = getattr(getattr(definition, "item", None), "id", "unknown")
        log.info(
            "Native render start content_id=%s renderer=%s output=%s",
            content_id, self.name, self.output_path,
        )
        if mounting_style == "documentary" and music_mode is None and definition.music_enabled:
            raise NativeRenderError("Documentary music requires explicit music_mode off, auto or manual")
        if definition.music_enabled and music_mode is None and not definition.background_music_file.is_file():
            raise NativeRenderError(
                f"Background music does not exist: {definition.background_music_file}"
            )
        music_selection = None
        if music_mode in {"auto", "manual"}:
            library = self._audio_library()
            try:
                if music_mode == "auto":
                    music_selection = library.select_narrative(content_id, definition.item.script, channel="loose_thread")
                else:
                    music_selection = library.select_manual(content_id, definition.music_track, channel="loose_thread")
            finally:
                library.close()
        reference_id = fish_reference_id(definition.voice_name)
        script = validate_native_script(definition.item.script)
        preflight = getattr(self.pexels, "preflight_searches", None)
        if preflight:
            preflight(definition.item.keywords, orientation="landscape")
        work_root = self.output_path.parent / ".native-work"
        work_root.mkdir(parents=True, exist_ok=True)
        # The caller holds the content-ID generation lock. Stable workspaces preserve
        # completed audio and chunk receipts when changing only text/effects.
        workspace = work_root / definition.item.id
        if self.confirmed_narration is not None:
            from uuid import uuid4
            # Preserve every earlier failed mix/chunk/temporary artifact.
            workspace = workspace / f"recovery-{uuid4().hex}"
        workspace.mkdir(parents=True, exist_ok=True)
        success = False
        fish_seconds = search_seconds = download_seconds = timeline_seconds = 0.0
        ffmpeg_seconds = validation_seconds = 0.0
        try:
            narration = self.confirmed_narration.narration if self.confirmed_narration else workspace / "narration.mp3"
            stage = time.monotonic()
            if self.confirmed_narration is not None:
                self.confirmed_narration.verify(definition, self.output_path)
                self._stage("Confirmed narration reused offline; no Fish client", 0)
            else:
                log.info("Fish start content_id=%s", definition.item.id)
                fish = self.fish_factory(
                    self.settings.fish_api_key.get_secret_value(),
                    self.settings.fish_model,
                    timeout=self.settings.fish_tts_timeout_seconds,
                    cache_dir=self.settings.audio_cache_dir,
                    ffprobe=self.settings.ffprobe_binary,
                    timestamps=True,
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
            editing = None
            word_alignment = None
            edit_path = self.output_path.with_suffix(".edit.json")
            audio_fingerprint = hashlib.sha256(narration.read_bytes()).hexdigest()
            if getattr(definition, "editing_enabled", True):
                if edit_path.exists() and start_over:
                    old_edit = json.loads(edit_path.read_text(encoding="utf-8"))
                    if old_edit.get("script_sha256") != script_hash(script) or abs(float(old_edit.get("duration", 0)) - narration_duration) > .05 or old_edit.get("audio_sha256") != audio_fingerprint:
                        # Preserve operator edits while rebuilding for genuinely new narration.
                        backup = workspace / f"edit-{time.time_ns()}.json"
                        shutil_copy = edit_path.read_bytes()
                        backup.write_bytes(shutil_copy)
                        edit_path.unlink()
                alignment_path = getattr(definition, "alignment_file", None) or narration.with_suffix(".alignment.json")
                word_alignment = read_word_alignment(Path(alignment_path))
                options = dict(
                    audio_sha256=audio_fingerprint,
                    style=getattr(definition, "editing_style", None),
                    visual_sections=getattr(definition, "visual_sections", None),
                    word_alignment=word_alignment,
                    pauses=detect_pauses(narration, self.settings.ffmpeg_binary) if not word_alignment else None,
                )
                try:
                    editing = load_or_create_manifest(edit_path, script, narration_duration, definition.item.keywords, **options)
                except ValueError:
                    if not word_alignment or edit_path.exists():
                        raise
                    log.warning("Provider timestamps do not match transcript; falling back to explicitly estimated sentence timing")
                    options["word_alignment"] = None
                    options["pauses"] = detect_pauses(narration, self.settings.ffmpeg_binary)
                    editing = load_or_create_manifest(edit_path, script, narration_duration, definition.item.keywords, **options)
                slots = build_semantic_timeline(
                    editing.sections, narration_duration, definition.item.keywords,
                    minimum_clip=definition.video_clip_duration_min,
                    maximum_clip=definition.video_clip_duration_max,
                )
            else:
                slots = build_timeline(
                    narration_duration, definition.item.keywords,
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
            final_audio = narration
            audio_is_final_mix = False
            sfx_events = []
            music_transition = None
            if music_mode == "auto":
                from ..audio_library import narrative_transition
                sections = None
                if editing:
                    from ..editing.motion import provider_sections
                    aligned_sections = provider_sections(editing.sections, word_alignment, narration_duration)
                    if aligned_sections is None and editing.alignment.get('word_aligned') is True:
                        aligned_sections = editing.sections
                    if aligned_sections is not None:
                        sections = [{'text': section.section, 'start': section.audio_start, 'end': section.audio_end}
                                    for section in aligned_sections]
                music_transition = narrative_transition(script, narration_duration, sections=sections, channel='loose_thread')
            if mounting_style == "documentary" and music_mode == "auto":
                from ..editing.motion import automatic_sfx
                sfx_events = automatic_sfx(editing, narration_duration, word_alignment=word_alignment)
            if music_mode in {"auto", "manual"}:
                # AudioLibrary validates a separate normalized mix and keeps the
                # raw Fish narration untouched. Reuse only a matching receipt.
                from ..audio_library import MIXER_REVISION
                mix_revision = hashlib.sha256(json.dumps({
                    "mixer_revision": MIXER_REVISION,
                    "selection": music_selection, "sfx_events": sfx_events, "transition": music_transition,
                }, sort_keys=True).encode()).hexdigest()[:16]
                final_audio = workspace / f"music-{audio_fingerprint}-{mix_revision}.wav"
                library = self._audio_library()
                try:
                    receipt_path = final_audio.with_suffix(".wav.json")
                    if final_audio.exists() and receipt_path.is_file():
                        receipt = json.loads(receipt_path.read_text())
                        if (receipt.get("mixer_revision") != MIXER_REVISION
                                or receipt.get("narration_sha256") != audio_fingerprint
                                or receipt.get("job_id") != content_id
                                or receipt.get("output_sha256") != hashlib.sha256(final_audio.read_bytes()).hexdigest()):
                            raise NativeRenderError("Cached music mix changed; preserve and review it")
                    else:
                        library.mix(content_id, narration, final_audio, duration=narration_duration, sfx_events=sfx_events,
                                    transition_at=music_transition["transition_at"] if music_transition else None)
                    audio_is_final_mix = True
                finally:
                    library.close()
            if mounting_style == "documentary" or audio_is_final_mix:
                from ..editing.motion import render_motion_longform
                info = render_motion_longform(
                    clips, final_audio, narration_duration, self.output_path, workspace,
                    settings=self.settings, editing=editing,
                    style="investigation" if mounting_style == "documentary" else "basic",
                    audio_is_final_mix=audio_is_final_mix, word_alignment=word_alignment,
                    width=self.engine.spec.width, height=self.engine.spec.height, fps=self.engine.spec.fps,
                    **({'workspace_id': f'{content_id}-{workspace.name}'} if self.confirmed_narration else {}),
                )
            else:
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
                    editing=editing,
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
            stock_sources = list({choice.asset.asset_id: {
                "provider": "Pexels", "asset_id": choice.asset.asset_id,
                "source_url": choice.asset.page_url, "download_url": choice.variant.url,
                "author": getattr(choice.asset, 'author', None),
                "author_url": getattr(choice.asset, 'author_url', None),
                "license": "Pexels License", "license_url": "https://www.pexels.com/license/",
                "usage": "Illustrative stock; trimmed, cropped and edited for this video.",
            } for choice in selected}.values())
            manifest = self.output_path.with_suffix(".native.json")
            write_render_manifest(
                manifest,
                encoder=self.engine.encoder,
                spec=self.engine.spec,
                info=final_info,
                extra={
                    "renderer": "native",
                    "mounting_style": mounting_style,
                    "music_mode": music_mode,
                    "music_selection": music_selection,
                    "stock_sources": stock_sources,
                    "music_transition": music_transition,
                    "sfx_events": sfx_events,
                    "audio_is_final_mix": audio_is_final_mix,
                    "content_id": definition.item.id,
                    "narration_duration": narration_duration,
                    "edit_manifest": str(edit_path) if editing else None,
                    "alignment": editing.alignment if editing else None,
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
            credits_path = self.output_path.with_suffix(".credits.md")
            text = "# Sources and credits\n\n## Illustrative stock\n\n"
            text += "Stock illustrates the narration; it is not historical footage of the reported events.\n\n"
            for source in stock_sources:
                text += f"- Pexels asset {source['asset_id']}\n"
                text += f"  - Author: {source['author'] or 'unknown (unverified legacy metadata)'}\n"
                text += f"  - Author URL: {source['author_url'] or 'unknown'}\n"
                text += f"  - Source: {source['source_url'] or 'unknown (legacy cache)'}\n"
                text += f"  - Download: {source['download_url']}\n"
                text += f"  - License: {source['license']} — {source['license_url']}\n"
                text += f"  - Changes: {source['usage']}\n"
            if music_selection:
                text += "\n## Music\n\n" + "\n\n".join(music_selection['credits'])
                text += "\n\n" + music_selection['changes_notice'] + "\n\nContent ID: unknown.\n"
            fd, temporary = tempfile.mkstemp(prefix=".source-credits-", dir=self.output_path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(text)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, credits_path)
            finally:
                Path(temporary).unlink(missing_ok=True)
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
            if not success:
                log.warning("Native workspace preserved after failure: %s", workspace)
                if self.output:
                    self.output(f"Native workspace preserved after failure: {workspace}")
