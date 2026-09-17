"""One generation plan shared by Pipeline and ReadyRegenerator."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .dialogue_audio import DialogueAudioService
from .dialogue_video import BackgroundPool, DialogueCompositor
from .fish_voice import FishVoiceClient
from .profiles import voice


@dataclass
class GenerationPlan:
    preset: dict
    dialogue_audio: object | None = None
    local_background: Path | None = None


class GenerationService:
    def __init__(self, settings, preset):
        self.s, self.preset = settings, preset
        self.last_warnings: list[str] = []

    def plan(self, item, workspace: Path) -> GenerationPlan:
        self.last_warnings = []
        payload = dict(self.preset)
        if item.content_format == "explainer":
            resolved = voice(item.voice_profile).mpt_voice
            if item.voice_profile != "alvaro" or "voice_name" in payload:
                payload["voice_name"] = resolved
            return GenerationPlan(payload)
        background = None
        if item.visual_profile != "pexels":
            background = BackgroundPool(self.s.background_root).choose(item.visual_profile, item.id)
        key = self.s.fish_api_key.get_secret_value()
        fish = FishVoiceClient(key, self.s.fish_model)
        try:
            audio = DialogueAudioService(fish, ffmpeg=self.s.ffmpeg_binary,
                                         ffprobe=self.s.ffprobe_binary,
                                         gap_ms=self.s.dialogue_gap_ms).generate(item, workspace)
        finally:
            fish.close()
        if background is None:
            payload.update(voice_name="no-voice", subtitle_enabled=False)
        return GenerationPlan(payload, audio, background)

    def finish(self, item, plan: GenerationPlan, source: Path | None,
               destination: Path, workspace: Path) -> Path:
        if item.content_format == "explainer":
            if source is None:
                raise RuntimeError("MPT did not provide an explainer artifact")
            return source
        video = plan.local_background or source
        if video is None:
            raise RuntimeError("No dialogue visual source is available")
        compositor = DialogueCompositor(self.s)
        result = compositor.compose(item, video, plan.dialogue_audio, destination, workspace)
        self.last_warnings = compositor.warnings
        return result
