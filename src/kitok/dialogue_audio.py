"""Generate individual turns and a measured, reusable dialogue timeline."""
from __future__ import annotations

import json
import math
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .profiles import voice


def media_duration(path: Path, ffprobe: str = "ffprobe") -> float:
    try:
        result = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                                 "-of", "json", str(path)], capture_output=True, text=True,
                                check=True, timeout=30)
        duration = float(json.loads(result.stdout)["format"]["duration"])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("non-positive duration")
        return duration
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
        raise RuntimeError(f"Could not measure media duration: {path.name}") from error


@dataclass(frozen=True)
class TimedTurn:
    speaker: str
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class DialogueAudio:
    path: Path
    timeline: list[TimedTurn]
    duration: float


class DialogueAudioService:
    def __init__(self, fish, *, ffmpeg="ffmpeg", ffprobe="ffprobe", gap_ms=140, on_stage=None):
        self.fish, self.ffmpeg, self.ffprobe, self.gap_ms = fish, ffmpeg, ffprobe, gap_ms
        self.on_stage = on_stage

    def _stage(self, label, event, elapsed=None):
        if self.on_stage is not None:
            self.on_stage(label, event, elapsed)

    def generate(self, item, workspace: Path) -> DialogueAudio:
        paths, timeline = [], []
        cursor = 0.0
        gap = self.gap_ms / 1000
        for index, turn in enumerate(item.dialogue or [], 1):
            profile = voice(turn.speaker)
            if profile.provider != "fish":
                raise ValueError(f"Dialogue speaker {turn.speaker} is not a Fish voice")
            path = workspace / f"turn_{index:03d}_{turn.speaker}.mp3"
            label = f"Fish {profile.display_name}"
            self._stage(label, "start")
            started = time.monotonic()
            self.fish.synthesize(turn.text, profile.value, path)
            duration = media_duration(path, self.ffprobe)
            self._stage(label, "ok", time.monotonic() - started)
            timeline.append(TimedTurn(turn.speaker, cursor, cursor + duration, turn.text))
            paths.append(path)
            cursor += duration + (gap if index < len(item.dialogue) else 0)
        if len(paths) < 2:
            raise ValueError("Dialogue requires at least two turns")
        filters = []
        labels = []
        for index in range(len(paths)):
            filters.append(f"[{index}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{index}]")
            labels.append(f"[a{index}]")
            if index < len(paths) - 1 and gap:
                filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={gap:.3f}[g{index}]")
                labels.append(f"[g{index}]")
        filters.append("".join(labels) + f"concat=n={len(labels)}:v=0:a=1[out]")
        target = workspace / "dialogue.m4a"
        command = [self.ffmpeg, "-nostdin", "-v", "error", "-y"]
        for path in paths:
            command += ["-i", str(path)]
        command += ["-filter_complex", ";".join(filters), "-map", "[out]", "-c:a", "aac",
                    "-b:a", "120k", str(target)]
        self._stage("Dialogue audio", "start")
        started = time.monotonic()
        try:
            subprocess.run(command, capture_output=True, text=True, check=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError("FFmpeg could not concatenate dialogue audio") from error
        self._stage("Dialogue audio", "ok", time.monotonic() - started)
        return DialogueAudio(target, timeline, timeline[-1].end)

    def generate_single(self, item, workspace: Path) -> DialogueAudio:
        """Generate one measured Fish narration without an unnecessary concat pass."""
        profile = voice(item.voice_profile)
        if profile.provider != "fish":
            raise ValueError(f"Single-speaker local narration requires a Fish voice: {item.voice_profile}")
        target = workspace / f"narration_{item.voice_profile}.mp3"
        label = f"Fish {profile.display_name.removesuffix(' ES')}"
        self._stage(label, "start")
        started = time.monotonic()
        self.fish.synthesize(item.script, profile.value, target)
        duration = media_duration(target, self.ffprobe)
        self._stage(label, "ok", time.monotonic() - started)
        return DialogueAudio(
            target,
            [TimedTurn(item.voice_profile, 0.0, duration, item.script)],
            duration,
        )
