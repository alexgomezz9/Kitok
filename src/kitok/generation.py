"""One native generation plan shared by Pipeline and ReadyRegenerator."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import random
import time

from .dialogue_audio import DialogueAudioService
from .dialogue_video import BackgroundPool, BackgroundSelection, DialogueCompositor
from .fish_voice import FishVoiceClient
from .longform.models import TimelineClip
from .longform.timeline import build_timeline
from .media.ffmpeg import FFmpegNativeEngine, RenderSpec
from .profiles import voice
from .providers.pexels import PexelsProvider
from .stock.selector import OutputGeometry


@dataclass
class GenerationPlan:
    preset: dict
    dialogue_audio: object | None = None
    local_background: Path | None = None
    background_selection: BackgroundSelection | None = None
    selection_seconds: float = 0.0
    stock_timeline: list | None = None
    music: Path | None = None


class GenerationService:
    def __init__(self, settings, preset, *, on_stage=None):
        self.s, self.preset = settings, preset
        self.on_stage = on_stage
        self.last_warnings: list[str] = []
        self.last_metadata: dict = {}

    def _stock_timeline(self, item, audio):
        provider = PexelsProvider(self.s.pexels_api_key.get_secret_value(), self.s.native_cache_dir,
                                  ffprobe=self.s.ffprobe_binary)
        try:
            slots = build_timeline(audio.duration, item.keywords,
                                   minimum_clip=float(self.preset.get("video_clip_duration", 2)),
                                   maximum_clip=float(self.preset.get("video_clip_duration", 2)),
                                   seed=item.id)
            searches = {q: provider.search_videos(q, orientation="portrait")
                        for q in dict.fromkeys(slot.query for slot in slots)}
            clips, used = [], set()
            rng = random.Random(item.id)
            for slot in slots:
                selected = provider.select_candidate(searches[slot.query], target=OutputGeometry(1080, 1920),
                                                     minimum_duration=slot.duration, used_ids=used)
                source = provider.download_asset(selected)
                used.add(selected.asset.asset_id)
                clips.append(TimelineClip(slot, selected.asset.asset_id, source,
                                          rng.uniform(0, max(0, selected.asset.duration - slot.duration))))
            return clips
        finally:
            provider.close()

    def _music(self, item):
        kind, filename = self.preset.get("bgm_type"), self.preset.get("bgm_file")
        if not kind:
            return None
        if filename:
            path = Path(filename).expanduser()
            if not path.is_file():
                raise ValueError(f"Configured background music does not exist: {path}")
            return path
        if kind == "random":
            from .config import PROJECT_ROOT
            tracks = sorted((PROJECT_ROOT / "assets" / "music").rglob("*.mp3"))
            if tracks:
                import hashlib
                index = int(hashlib.sha256(item.id.encode()).hexdigest(), 16) % len(tracks)
                return tracks[index]
        raise ValueError("Background music is enabled but no usable local music file is configured")

    def plan(self, item, workspace: Path) -> GenerationPlan:
        self.last_warnings, self.last_metadata = [], {}
        profile = voice(item.voice_profile)
        if item.content_format == "explainer" and profile.provider != "fish":
            raise ValueError(
                f"Legacy voice '{item.voice_profile}' remains readable but native generation requires a Fish voice. "
                "Duplicate the draft and explicitly choose a Fish voice before generating."
            )
        workspace.mkdir(parents=True, exist_ok=True)
        payload = dict(self.preset)
        music = self._music(item)
        pool = BackgroundPool(self.s.background_root, self.s.ffprobe_binary)
        background = None
        if item.visual_profile != "pexels":
            if item.visual_profile in {"random", "gameplay"}:
                available = pool.discover(item.visual_profile)
                if item.background_file:
                    available = [p for p in available if p.name == item.background_file]
                if not available:
                    if item.visual_profile == "random":
                        raise ValueError("No random background videos found in assets/backgrounds/random")
                    raise ValueError(f"No gameplay videos in {self.s.background_root / 'gameplay'}")
            else:
                background = pool.choose(item.visual_profile, item.id)
        else:
            # Validate stock availability before any synthesis that might consume balance.
            provider = PexelsProvider(self.s.pexels_api_key.get_secret_value(), self.s.native_cache_dir,
                                      ffprobe=self.s.ffprobe_binary)
            try:
                provider.preflight_searches(item.keywords, orientation="portrait")
            finally:
                provider.close()
        if item.content_format == "explainer":
            payload["voice_name"] = profile.mpt_voice
        speech = FishVoiceClient(self.s.fish_api_key.get_secret_value(), self.s.fish_model,
                                 timeout=self.s.fish_tts_timeout_seconds,
                                 cache_dir=self.s.audio_cache_dir, ffprobe=self.s.ffprobe_binary)
        try:
            audio_service = DialogueAudioService(speech, ffmpeg=self.s.ffmpeg_binary,
                                                ffprobe=self.s.ffprobe_binary,
                                                gap_ms=self.s.dialogue_gap_ms, on_stage=self.on_stage)
            if item.content_format == "explainer":
                # Existing local Rick timing stays intact; Pexels respects its configured narration rate.
                audio = audio_service.generate_single(item, workspace,
                            **({"speed": float(payload.get("voice_rate", 1))}
                               if item.visual_profile == "pexels" else {}))
            else:
                audio = audio_service.generate(item, workspace)
        finally:
            speech.close()
        selection, seconds, clips = None, 0.0, None
        if item.visual_profile in {"random", "gameplay"}:
            selecting = time.monotonic()
            # Concatenated AAC timing is authoritative for dialogue (container padding may differ).
            from .dialogue_audio import media_duration
            required_duration = (media_duration(audio.path, self.s.ffprobe_binary)
                                 if item.content_format == "dialogue" and item.visual_profile == "gameplay"
                                 else audio.duration)
            selection = pool.select_segment(item.visual_profile, item.id, required_duration,
                                            seed=item.background_seed or item.visual_seed,
                                            reserve_duration=self.s.max_video_seconds,
                                            filename=item.background_file)
            background, seconds = selection.source, time.monotonic() - selecting
        elif item.visual_profile == "pexels":
            clips = self._stock_timeline(item, audio)
        return GenerationPlan(payload, audio, background, selection, seconds, clips, music)

    def finish(self, item, plan: GenerationPlan, source: Path | None,
               destination: Path, workspace: Path) -> Path:
        video = plan.local_background
        if plan.stock_timeline:
            video = workspace / "native-stock.mp4"
            engine = FFmpegNativeEngine(ffmpeg=self.s.ffmpeg_binary, ffprobe=self.s.ffprobe_binary,
                                       spec=RenderSpec(width=1080, height=1920, fade_in=0, fade_out=0))
            engine.render(plan.stock_timeline, plan.dialogue_audio.path, plan.dialogue_audio.duration,
                          video, workspace / "stock-render", music=None, music_volume=0,
                          loudness_target=-16, lra_target=7, true_peak_target=-1.5)
        if video is None:
            raise RuntimeError("Native generation has no visual source")
        if self.on_stage:
            self.on_stage("Rendering characters and subtitles", "start")
        compositor = DialogueCompositor(self.s)
        result = compositor.compose(item, video, plan.dialogue_audio, destination, workspace,
                                    selection=plan.background_selection,
                                    music=plan.music,
                                    music_volume=float(plan.preset.get("bgm_volume", 0)),
                                    voice_volume=float(plan.preset.get("voice_volume", 1)),
                                    subtitle_enabled=plan.preset.get("subtitle_enabled", True))
        self.last_warnings = compositor.warnings
        self.last_metadata = {**compositor.metadata, "renderer": "native", "stock_timeline": [
            {"asset_id": c.asset_id, "query": c.slot.query, "start": c.slot.start,
             "duration": c.slot.duration, "source_start": c.source_start}
            for c in (plan.stock_timeline or [])]}
        return result
