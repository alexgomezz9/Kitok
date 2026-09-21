"""Explicit, isolated real-service smoke test. Never reads the production queue/state."""
from __future__ import annotations

import json
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import PROJECT_ROOT, Settings
from .dialogue_video import BackgroundPool
from .file_manager import copy_atomic
from .generation import GenerationService
from .models import ContentItem
from .mpt_client import MPTClient, TASK_STATE_FAILED
from .mpt_watch import wait_for_mpt_task
from .pipeline import load_preset
from .state import StateStore
from .video_validator import VideoValidator


class SmokeSettings(Settings):
    smoke_root: Path

    @property
    def queue_path(self): return self.smoke_root / "content_queue.json"
    @property
    def state_path(self): return self.smoke_root / "state" / "state.json"
    @property
    def generated_dir(self): return self.smoke_root / "generated"
    @property
    def failed_dir(self): return self.smoke_root / "failed"
    @property
    def local_ready_dir(self): return self.smoke_root / "ready"
    @property
    def logs_dir(self): return self.smoke_root / "logs"


class StageReporter:
    def __init__(self, output=print):
        self.output = output
        self.active = "Preflight"
        self.started = time.monotonic()

    def begin(self, label, _event="start", _elapsed=None):
        self.active = label
        self.started = time.monotonic()

    def ok(self, label, elapsed=None):
        elapsed = time.monotonic() - self.started if elapsed is None else elapsed
        self.output(f"{label:.<27} OK   {elapsed:.1f}s")
        self.active = None

    def event(self, label, event, elapsed=None):
        if event == "start":
            self.begin(label)
        elif event == "ok":
            self.ok(label, elapsed)


def _smoke_item() -> ContentItem:
    return ContentItem(
        id="smoke_dialogue_pexels", subject="Ocean waves for a short test",
        script="", keywords=["ocean", "sea waves"], caption="Temporary integration test",
        publish_at=datetime.now(timezone.utc) + timedelta(days=1),
        content_format="dialogue", dialogue_preset="rick_morty_es",
        visual_profile="pexels",
        dialogue=[
            {"speaker": "rick_es", "text": "Morty, esto es una prueba. Comprobemos que el video, la voz y los subtítulos funcionan juntos."},
            {"speaker": "morty_es", "text": "Rick, espero que funcione. Veo el océano y escucho claramente las dos voces en este video de prueba."},
        ],
    )


def run_dialogue_pexels_smoke(*, settings: Settings | None = None, output=print) -> int:
    started = time.monotonic()
    reporter = StageReporter(output)
    source_settings = settings or Settings()
    if not source_settings.fish_api_key.get_secret_value():
        output("Preflight FAILED: FISH_API_KEY is not configured")
        return 2
    preset_path = source_settings.mpt_preset_path
    if not preset_path.is_absolute():
        preset_path = (PROJECT_ROOT / preset_path).resolve()
    client = None
    try:
        preset = load_preset(preset_path)
        with tempfile.TemporaryDirectory(prefix="kitok-dialogue-smoke-") as temp:
            root = Path(temp)
            isolated_values = source_settings.model_dump()
            isolated_values.update(smoke_root=root, ready_dir=root / "ready-phone",
                                   publish_enabled=False)
            smoke_settings = SmokeSettings(
                _env_file=None, **isolated_values,
            )
            smoke_settings.ensure_directories()
            state = StateStore(smoke_settings.state_path)
            item = _smoke_item()
            state.upsert(item.id, status="pending")
            client = MPTClient(smoke_settings.mpt_base_url, smoke_settings.mpt_api_key,
                               smoke_settings.mpt_request_timeout_seconds,
                               smoke_settings.http_retry_attempts,
                               smoke_settings.http_retry_base_seconds)
            reporter.begin("MPT connectivity")
            client.check()
            reporter.ok("MPT connectivity")

            generator = GenerationService(smoke_settings, preset, on_stage=reporter.event)
            plan = generator.plan(item, root)
            request = MPTClient.build_payload(item, plan.preset)
            output("MPT request: " + json.dumps(request, ensure_ascii=False, sort_keys=True))
            output(f"Dialogue timeline: {[(t.speaker, round(t.start, 2), round(t.end, 2)) for t in plan.dialogue_audio.timeline]}")

            reporter.begin("MPT submit")
            task_id = client.submit_video(item, plan.preset)
            state.upsert(item.id, status="submitted", mpt_task_id=task_id)
            reporter.ok("MPT submit")
            output(f"MPT task: {task_id}")

            reporter.begin("MPT materials")
            materials_done = False
            last_status = None
            def on_update(task):
                nonlocal materials_done, last_status
                state.upsert(item.id, status="generating", mpt_progress=task.progress)
                status = (task.state, task.progress)
                if status != last_status:
                    output(f"MPT polling: state={task.state}, progress={task.progress}")
                    last_status = status
                if not materials_done and task.progress is not None and task.progress >= 50:
                    reporter.ok("MPT materials")
                    reporter.begin("MPT concat")
                    materials_done = True

            task = wait_for_mpt_task(
                client, task_id, poll_seconds=smoke_settings.poll_interval_seconds,
                timeout_seconds=smoke_settings.task_timeout_minutes * 60,
                stall_seconds=smoke_settings.mpt_progress_stall_minutes * 60,
                on_update=on_update,
            )
            if task.state == TASK_STATE_FAILED:
                raise RuntimeError(f"MPT task failed at {task.failed_stage}: {task.error}")
            if not task.videos:
                raise RuntimeError("MPT completed without a visual artifact")
            if not materials_done:
                reporter.ok("MPT materials")
                reporter.begin("MPT concat")
            reporter.ok("MPT concat")

            reporter.begin("MPT artifact")
            visual = root / "mpt_visual.mp4"
            client.download_artifact(task.videos[0], visual)
            reporter.ok("MPT artifact")

            reporter.begin("Kitok composition")
            staged = root / "dialogue_final.mp4"
            generator.finish(item, plan, visual, staged, root)
            reporter.ok("Kitok composition")

            reporter.begin("Validation")
            validation = VideoValidator(
                smoke_settings.ffprobe_binary, smoke_settings.min_video_seconds,
                smoke_settings.max_video_seconds, smoke_settings.min_vertical_width,
                smoke_settings.min_vertical_height,
            ).prepare(staged, item.platforms, smoke_settings.ffmpeg_binary)
            if not validation.ok:
                raise RuntimeError("Invalid final MP4: " + "; ".join(validation.errors))
            copy_atomic(staged, smoke_settings.local_ready_dir / staged.name)
            state.upsert(item.id, status="ready", validation=validation.model_dump(),
                         ready_path=str(smoke_settings.local_ready_dir / staged.name))
            reporter.ok("Validation")
            output(f"Final temporary MP4: duration={validation.duration:.2f}s, "
                   f"size={validation.width}x{validation.height}, fps={validation.fps}, "
                   f"video={validation.video_codec}/{validation.pixel_format}, "
                   f"audio={validation.audio_codec}/{validation.audio_profile} "
                   f"{validation.audio_sample_rate}Hz {validation.audio_bitrate}bps")
            output(f"TOTAL .................... {time.monotonic() - started:.1f}s")
            return 0
    except Exception as error:
        output(f"{reporter.active or 'Smoke test'} FAILED: {error}")
        output(f"TOTAL .................... {time.monotonic() - started:.1f}s")
        return 1
    finally:
        if client is not None:
            client.close()


def run_dialogue_gameplay_smoke(*, settings: Settings | None = None, output=print) -> int:
    """Exercise real Fish, local AV1, overlays, subtitles and validation in isolation."""
    started = time.monotonic()
    reporter = StageReporter(output)
    source_settings = settings or Settings()
    if not source_settings.fish_api_key.get_secret_value():
        output("Preflight FAILED: FISH_API_KEY is not configured")
        return 2
    if not (source_settings.background_root / "gameplay" / "minecraft_01.mp4").is_file():
        output("Preflight FAILED: assets/backgrounds/gameplay/minecraft_01.mp4 is missing")
        return 2
    try:
        preset_path = source_settings.mpt_preset_path
        if not preset_path.is_absolute():
            preset_path = (PROJECT_ROOT / preset_path).resolve()
        preset = load_preset(preset_path)
        with tempfile.TemporaryDirectory(prefix="kitok-gameplay-smoke-") as temp:
            root = Path(temp)
            isolated_values = source_settings.model_dump()
            isolated_values.update(smoke_root=root, ready_dir=root / "ready-phone",
                                   publish_enabled=False)
            smoke_settings = SmokeSettings(_env_file=None, **isolated_values)
            smoke_settings.ensure_directories()
            item = ContentItem(
                id="smoke_dialogue_gameplay", subject="Minecraft local integration test",
                script="", keywords=["minecraft"], caption="Temporary integration test",
                publish_at=datetime.now(timezone.utc) + timedelta(days=1),
                content_format="dialogue", dialogue_preset="rick_morty_es",
                visual_profile="gameplay", character_profile="rick_morty_es",
                visual_seed="gameplay-preview-v2",
                dialogue=[
                    {"speaker": "rick_es", "text": "Morty, hay una rana que puede congelarse durante todo el invierno."},
                    {"speaker": "morty_es", "text": "¿Se congela por completo? Eso parece imposible."},
                    {"speaker": "rick_es", "text": "Su corazón se detiene, pero vuelve a latir cuando llega la primavera."},
                    {"speaker": "morty_es", "text": "Entonces pasa meses como un cubito de hielo viviente."},
                    {"speaker": "rick_es", "text": "Exacto, Morty. La rana de bosque fabrica su propio anticongelante."},
                    {"speaker": "morty_es", "text": "Vale, eso sí merece aparecer en nuestro video."},
                ],
            )
            generator = GenerationService(smoke_settings, preset, on_stage=reporter.event)
            plan = generator.plan(item, root)
            output("Dialogue timeline ......... OK (measured Fish turn boundaries)")
            selection = plan.background_selection
            if selection is None:
                raise RuntimeError("Gameplay selection was not created")
            reporter.ok("Gameplay selection", plan.selection_seconds)
            output(f"Selected gameplay file: {selection.source}")
            output(f"Selected start offset: {selection.start_offset:.3f}s")
            output(f"Required duration: {selection.segment_duration:.3f}s")
            output(f"Dialogue timeline: {[(t.speaker, round(t.start, 3), round(t.end, 3)) for t in plan.dialogue_audio.timeline]}")
            output(f"Gameplay seek ............. OK (input -ss {selection.start_offset:.3f}s)")
            staged = root / "dialogue_final.mp4"
            generator.finish(item, plan, None, staged, root)
            timings = generator.last_metadata["stage_timings"]
            reporter.ok("Character overlays", timings["character_overlays"])
            reporter.ok("Chunked subtitles", timings["chunked_subtitles"])
            reporter.ok("Final composition", timings["final_composition"])
            output("Selected poses: " + json.dumps(generator.last_metadata.get("character_poses", []), ensure_ascii=False))
            reactions = [entry for entry in generator.last_metadata.get("character_appearances", [])
                         if entry.get("reaction")]
            output("Reaction appearances: " + json.dumps(reactions, ensure_ascii=False))
            output("Subtitle cues: " + json.dumps(generator.last_metadata.get("subtitle_cues", []), ensure_ascii=False))
            reporter.begin("Validation")
            validation = VideoValidator(
                smoke_settings.ffprobe_binary, smoke_settings.min_video_seconds,
                smoke_settings.max_video_seconds, smoke_settings.min_vertical_width,
                smoke_settings.min_vertical_height,
            ).prepare(staged, item.platforms, smoke_settings.ffmpeg_binary)
            if not validation.ok:
                raise RuntimeError("Invalid final MP4: " + "; ".join(validation.errors))
            reporter.ok("Validation")
            preview_dir = PROJECT_ROOT / "outputs" / "smoke"
            preview_dir.mkdir(parents=True, exist_ok=True)
            preview = preview_dir / "dialogue_gameplay_preview.mp4"
            copy_atomic(staged, preview)
            debug = {**generator.last_metadata, "validation": validation.model_dump(),
                     "preview": str(preview)}
            (preview_dir / "dialogue_gameplay_preview.json").write_text(
                json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
            output(f"Preview: {preview}")
            output(f"Final MP4: duration={validation.duration:.3f}s, "
                   f"size={validation.width}x{validation.height}, fps={validation.fps}, "
                   f"video={validation.video_codec}/{validation.pixel_format}, "
                   f"audio={validation.audio_codec}/{validation.audio_profile}")
            output(f"TOTAL .................... {time.monotonic() - started:.1f}s")
            return 0
    except Exception as error:
        output(f"{reporter.active or 'Smoke test'} FAILED: {error}")
        output(f"TOTAL .................... {time.monotonic() - started:.1f}s")
        return 1


def run_rick_random_smoke(*, settings: Settings | None = None, output=print) -> int:
    """Exercise real Fish and the single-speaker local random-background path."""
    started = time.monotonic()
    reporter = StageReporter(output)
    source_settings = settings or Settings()
    if not source_settings.fish_api_key.get_secret_value():
        output("Preflight FAILED: FISH_API_KEY is not configured")
        return 2
    random_files = BackgroundPool(
        source_settings.background_root, source_settings.ffprobe_binary,
    ).discover("random")
    if not random_files:
        output("Preflight FAILED: No random background videos found in assets/backgrounds/random")
        return 2
    try:
        preset_path = source_settings.mpt_preset_path
        if not preset_path.is_absolute():
            preset_path = (PROJECT_ROOT / preset_path).resolve()
        preset = load_preset(preset_path)
        with tempfile.TemporaryDirectory(prefix="kitok-rick-random-smoke-") as temp:
            root = Path(temp)
            isolated_values = source_settings.model_dump()
            isolated_values.update(smoke_root=root, ready_dir=root / "ready-phone",
                                   publish_enabled=False)
            smoke_settings = SmokeSettings(_env_file=None, **isolated_values)
            smoke_settings.ensure_directories()
            item = ContentItem(
                id="smoke_rick_random",
                subject="Tiburones anteriores a los árboles",
                script=("¿Sabías que los tiburones existen desde antes que los árboles? "
                        "Los primeros tiburones aparecieron hace más de cuatrocientos millones de "
                        "años, mientras que los primeros árboles llegaron bastante después."),
                keywords=["tiburones", "árboles", "historia natural"],
                caption="Temporary Rick random-background integration test",
                publish_at=datetime.now(timezone.utc) + timedelta(days=1),
                content_format="explainer", voice_profile="rick_es",
                visual_profile="random", visual_seed="rick-random-preview-v1",
            )
            generator = GenerationService(smoke_settings, preset, on_stage=reporter.event)
            plan = generator.plan(item, root)
            audio = plan.dialogue_audio
            selection = plan.background_selection
            if audio is None or selection is None:
                raise RuntimeError("Rick random plan did not create local audio and background")
            output(f"Audio duration ............. OK   {audio.duration:.3f}s")
            output("Random background ......... OK")
            output(f"Selected file: {selection.source}")
            output(f"Selected offset: {selection.start_offset:.3f}s")

            staged = root / "rick_random_final.mp4"
            generator.finish(item, plan, None, staged, root)
            poses = [entry["pose"] for entry in
                     generator.last_metadata.get("character_appearances", [])]
            output("Rick poses: " + json.dumps(poses, ensure_ascii=False))
            cues = generator.last_metadata.get("subtitle_cues", [])
            if not cues or cues[0]["start"] != 0 or abs(cues[-1]["end"] - audio.duration) > 0.001:
                raise RuntimeError("Chunked subtitles do not span the measured Fish audio")
            timings = generator.last_metadata["stage_timings"]
            reporter.ok("Chunked subtitles", timings["chunked_subtitles"])
            reporter.ok("Composition", timings["final_composition"])

            reporter.begin("Validation")
            validation = VideoValidator(
                smoke_settings.ffprobe_binary, smoke_settings.min_video_seconds,
                smoke_settings.max_video_seconds, smoke_settings.min_vertical_width,
                smoke_settings.min_vertical_height,
            ).prepare(staged, item.platforms, smoke_settings.ffmpeg_binary)
            if not validation.ok:
                raise RuntimeError("Invalid final MP4: " + "; ".join(validation.errors))
            reporter.ok("Validation")

            preview_dir = PROJECT_ROOT / "outputs" / "smoke"
            preview_dir.mkdir(parents=True, exist_ok=True)
            preview = preview_dir / "rick_random_preview.mp4"
            copy_atomic(staged, preview)
            debug = {**generator.last_metadata, "validation": validation.model_dump(),
                     "preview": str(preview)}
            (preview_dir / "rick_random_preview.json").write_text(
                json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
            output(f"Preview: {preview}")
            output(f"Final MP4: duration={validation.duration:.3f}s, "
                   f"size={validation.width}x{validation.height}, fps={validation.fps}, "
                   f"video={validation.video_codec}/{validation.pixel_format}, "
                   f"audio={validation.audio_codec}/{validation.audio_profile} "
                   f"{validation.audio_sample_rate}Hz {validation.audio_bitrate}bps")
            output(f"TOTAL .................... {time.monotonic() - started:.1f}s")
            return 0
    except Exception as error:
        output(f"{reporter.active or 'Smoke test'} FAILED: {error}")
        output(f"TOTAL .................... {time.monotonic() - started:.1f}s")
        return 1
