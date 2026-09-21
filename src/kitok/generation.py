"""One generation plan shared by Pipeline and ReadyRegenerator."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

from .dialogue_audio import DialogueAudioService
from .dialogue_video import BackgroundPool, BackgroundSelection, DialogueCompositor
from .fish_voice import FishVoiceClient
from .profiles import voice


@dataclass
class GenerationPlan:
    preset: dict
    dialogue_audio: object | None = None
    local_background: Path | None = None
    background_selection: BackgroundSelection | None = None
    selection_seconds: float = 0.0


class GenerationService:
    def __init__(self, settings, preset, *, on_stage=None):
        self.s, self.preset = settings, preset
        self.on_stage = on_stage
        self.last_warnings: list[str] = []
        self.last_metadata: dict = {}

    def plan(self, item, workspace: Path) -> GenerationPlan:
        self.last_warnings = []
        self.last_metadata = {}
        payload = dict(self.preset)
        if item.content_format == "explainer" and item.visual_profile == "pexels":
            resolved = voice(item.voice_profile).mpt_voice
            if item.voice_profile != "alvaro" or "voice_name" in payload:
                payload["voice_name"] = resolved
            return GenerationPlan(payload)
        if item.content_format == "explainer":
            pool = BackgroundPool(self.s.background_root, self.s.ffprobe_binary)
            available = pool.discover("random")
            if item.background_file:
                available = [path for path in available if path.name == item.background_file]
            if not available:
                raise ValueError("No random background videos found in assets/backgrounds/random")
            key = self.s.fish_api_key.get_secret_value()
            fish = FishVoiceClient(key, self.s.fish_model, timeout=self.s.fish_tts_timeout_seconds)
            try:
                audio = DialogueAudioService(
                    fish, ffmpeg=self.s.ffmpeg_binary, ffprobe=self.s.ffprobe_binary,
                    gap_ms=self.s.dialogue_gap_ms, on_stage=self.on_stage,
                ).generate_single(item, workspace)
            finally:
                fish.close()
            selecting = time.monotonic()
            selection = pool.select_segment(
                "random", item.id, audio.duration,
                seed=item.background_seed or item.visual_seed,
                reserve_duration=self.s.max_video_seconds,
                filename=item.background_file,
            )
            return GenerationPlan(
                payload, audio, selection.source, selection,
                time.monotonic() - selecting,
            )
        background = None
        pool = BackgroundPool(self.s.background_root, self.s.ffprobe_binary)
        if item.visual_profile != "pexels":
            if item.visual_profile == "gameplay":
                available = pool.discover("gameplay")
                if item.background_file:
                    available = [p for p in available if p.name == item.background_file]
                if not available:
                    raise ValueError(f"No gameplay videos in {self.s.background_root / 'gameplay'}")
            else:
                background = pool.choose(item.visual_profile, item.id)
        key = self.s.fish_api_key.get_secret_value()
        fish = FishVoiceClient(key, self.s.fish_model, timeout=self.s.fish_tts_timeout_seconds)
        try:
            audio = DialogueAudioService(fish, ffmpeg=self.s.ffmpeg_binary,
                                         ffprobe=self.s.ffprobe_binary,
                                         gap_ms=self.s.dialogue_gap_ms,
                                         on_stage=self.on_stage).generate(item, workspace)
        finally:
            fish.close()
        selection = None
        selection_seconds = 0.0
        if item.visual_profile == "gameplay":
            # The concatenated Fish audio is the authority for segment length.
            from .dialogue_audio import media_duration
            actual_duration = media_duration(audio.path, self.s.ffprobe_binary)
            selecting = time.monotonic()
            selection = pool.select_segment("gameplay", item.id, actual_duration,
                                            seed=item.background_seed,
                                            reserve_duration=self.s.max_video_seconds, filename=item.background_file)
            selection_seconds = time.monotonic() - selecting
            background = selection.source
        if background is None:
            # MPT estimates no-voice duration from video_script. The full dialogue
            # made it render many two-second clips even though Kitok later replaces
            # that silent audio and loops the visual to the measured dialogue length.
            payload.update(voice_name="no-voice", subtitle_enabled=False,
                           video_script=item.keywords[0][:24])
        return GenerationPlan(payload, audio, background, selection, selection_seconds)

    def finish(self, item, plan: GenerationPlan, source: Path | None,
               destination: Path, workspace: Path) -> Path:
        if item.content_format == "explainer" and plan.local_background is None:
            if source is None:
                raise RuntimeError("MPT did not provide an explainer artifact")
            return source
        video = plan.local_background or source
        if video is None:
            raise RuntimeError("No dialogue visual source is available")
        if self.on_stage:
            self.on_stage("Rendering characters and subtitles", "start")
        compositor = DialogueCompositor(self.s)
        result = compositor.compose(item, video, plan.dialogue_audio, destination, workspace,
                                    selection=plan.background_selection)
        self.last_warnings = compositor.warnings
        self.last_metadata = compositor.metadata
        return result
