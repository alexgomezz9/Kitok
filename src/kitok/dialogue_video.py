"""Local visual selection, subtitles and FFmpeg composition for dialogue."""
from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path

from .dialogue_audio import media_duration
from .profiles import CHARACTER_PROFILES, VISUAL_PROFILES

log = logging.getLogger("kitok.dialogue_video")


def _stable_number(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big")


class BackgroundPool:
    def __init__(self, root: Path):
        self.root = root

    def choose(self, profile: str, content_id: str) -> Path:
        if profile not in VISUAL_PROFILES:
            raise ValueError(f"Unknown visual profile: {profile}")
        folder = VISUAL_PROFILES.get(profile)
        if not folder:
            raise ValueError(f"No local background pool for {profile}")
        candidates = sorted(p for p in (self.root / folder).glob("*.mp4") if p.is_file() and p.stat().st_size)
        if not candidates:
            raise ValueError(f"No MP4 gameplay clips in {self.root / folder}; add a video before generating")
        return candidates[_stable_number(content_id) % len(candidates)]


def write_subtitles(timeline, destination: Path) -> Path:
    def stamp(seconds):
        milliseconds = round(seconds * 1000)
        h, rem = divmod(milliseconds, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, ms = divmod(rem, 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"
    blocks = []
    for index, turn in enumerate(timeline, 1):
        text = turn.text.replace("\r", " ").replace("\n", " ").replace("--> ", "→ ")
        blocks.append(f"{index}\n{stamp(turn.start)} --> {stamp(turn.end)}\n{text}\n")
    destination.write_text("\n".join(blocks), encoding="utf-8")
    return destination


def _filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")


class DialogueCompositor:
    def __init__(self, settings):
        self.s = settings
        self.warnings: list[str] = []

    def _poses(self, item, timeline):
        if not item.character_profile:
            return []
        config = CHARACTER_PROFILES[item.character_profile]
        result = []
        previous = {}
        for index, turn in enumerate(timeline):
            if turn.speaker not in config:
                continue
            directory, side = config[turn.speaker]
            files = sorted((self.s.character_root / directory).glob("*.png"))
            if not files:
                warning = f"No character PNG poses in {self.s.character_root / directory}; continuing without {turn.speaker} overlay"
                if warning not in self.warnings:
                    self.warnings.append(warning)
                    log.warning(warning)
                continue
            choice = _stable_number(f"{item.id}:{index}:{turn.speaker}") % len(files)
            if len(files) > 1 and previous.get(turn.speaker) == choice:
                choice = (choice + 1) % len(files)
            previous[turn.speaker] = choice
            result.append((files[choice], side, turn.start, turn.end))
        return result

    def compose(self, item, source: Path, dialogue, destination: Path, workspace: Path) -> Path:
        duration = dialogue.duration
        source_duration = media_duration(source, self.s.ffprobe_binary)
        offset = 0.0 if source_duration <= duration else (_stable_number(item.id + ":segment") % 10000) / 10000 * (source_duration - duration)
        subtitle = write_subtitles(dialogue.timeline, workspace / "dialogue.srt")
        poses = self._poses(item, dialogue.timeline)
        command = [self.s.ffmpeg_binary, "-nostdin", "-v", "error", "-y",
                   "-stream_loop", "-1", "-ss", f"{offset:.3f}", "-i", str(source),
                   "-i", str(dialogue.path)]
        for path, _, _, _ in poses:
            command += ["-loop", "1", "-i", str(path)]
        filters = ["[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase,"
                   "crop=1080:1920,setsar=1,format=yuv420p[base]"]
        current = "base"
        for index, (_, side, start, end) in enumerate(poses, 2):
            scaled = f"pose{index}"
            out = f"layer{index}"
            filters.append(f"[{index}:v]scale=-1:600:flags=lanczos,format=rgba[{scaled}]")
            x = "40" if side == "left" else "W-w-40"
            filters.append(f"[{current}][{scaled}]overlay=x={x}:y=H*0.37:enable='between(t,{start:.3f},{end:.3f})'[{out}]")
            current = out
        filters.append(f"[{current}]subtitles='{_filter_path(subtitle)}':force_style='FontSize=23,Alignment=2,MarginV=115,Outline=2'[video]")
        command += ["-filter_complex", ";".join(filters), "-map", "[video]", "-map", "1:a:0",
                    "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "22",
                    "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-profile:a", "aac_low",
                    "-b:a", "120k", "-ar", "48000", "-movflags", "+faststart", str(destination)]
        try:
            subprocess.run(command, capture_output=True, text=True, check=True, timeout=900)
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError("FFmpeg could not compose dialogue video") from error
        if not destination.is_file() or destination.stat().st_size == 0:
            raise RuntimeError("FFmpeg produced no dialogue video")
        return destination
