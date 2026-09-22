"""Local background selection, character assets and one-pass dialogue composition."""
from __future__ import annotations

import hashlib
import logging
import math
import subprocess
import time
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .dialogue_audio import media_duration
from .dialogue_subtitles import dialogue_cues, write_subtitles
from .profiles import CHARACTER_PROFILES, VISUAL_PROFILES, CHARACTERS

log = logging.getLogger("kitok.dialogue_video")
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


def _stable_number(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big")


@dataclass(frozen=True)
class BackgroundSelection:
    source: Path
    source_duration: float
    start_offset: float
    segment_duration: float
    profile: str = "gameplay"

    def metadata(self) -> dict:
        result = {"background_profile": self.profile,
                  "background_source": str(self.source),
                  "background_source_duration": self.source_duration,
                  "background_start_offset": self.start_offset,
                  "background_segment_duration": self.segment_duration}
        if self.profile == "gameplay":
            result.update(gameplay_source=str(self.source),
                          gameplay_source_duration=self.source_duration,
                          gameplay_start_offset=self.start_offset,
                          gameplay_segment_duration=self.segment_duration)
        return result


class BackgroundPool:
    def __init__(self, root: Path, ffprobe: str = "ffprobe"):
        self.root, self.ffprobe = root.resolve(), ffprobe

    def discover(self, profile: str) -> list[Path]:
        if profile not in VISUAL_PROFILES:
            raise ValueError(f"Unknown visual profile: {profile}")
        folder = VISUAL_PROFILES[profile]
        if not folder:
            raise ValueError(f"No local background pool for {profile}")
        return sorted(p for p in (self.root / folder).iterdir()
                      if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS and p.stat().st_size) if (self.root / folder).is_dir() else []

    def choose(self, profile: str, content_id: str) -> Path:
        candidates = self.discover(profile)
        if not candidates:
            if profile == "random":
                raise ValueError("No random background videos found in assets/backgrounds/random")
            raise ValueError(f"No MP4 gameplay clips in {self.root / VISUAL_PROFILES[profile]}; add a video before generating")
        return candidates[_stable_number(content_id) % len(candidates)]

    def select_segment(self, profile: str, content_id: str, required_duration: float,
                       *, seed: str | None = None, reserve_duration: float = 60.0, filename: str | None = None) -> BackgroundSelection:
        if not math.isfinite(required_duration) or required_duration <= 0:
            raise ValueError("Audio duration must be positive")
        candidates = self.discover(profile)
        if filename:
            candidates = [p for p in candidates if p.name == filename]
        if not candidates:
            if profile == "random":
                raise ValueError("No random background videos found in assets/backgrounds/random")
            raise ValueError(f"No gameplay videos in {self.root / VISUAL_PROFILES[profile]}")
        usable = []
        for path in candidates:
            try:
                duration = media_duration(path, self.ffprobe)
            except RuntimeError:
                log.warning("Skipping unreadable background: %s", path)
                continue
            if duration >= required_duration:
                usable.append((path, duration))
        if not usable:
            raise ValueError(f"No {profile} background video is at least {required_duration:.3f}s long")
        reserved = [entry for entry in usable if entry[1] >= reserve_duration]
        if reserved:
            usable = reserved
        key = f"{content_id}:{seed or 'default'}"
        source, source_duration = usable[_stable_number(key + ":file") % len(usable)]
        # Reserve the maximum expected video duration, so Fish timing jitter
        # does not move the selected start when the same content is regenerated.
        # Shorter sources fall back to zero if no stable offset can fit.
        max_offset_ms = max(0, math.floor((source_duration - max(required_duration, reserve_duration) - 0.05) * 1000))
        start_offset = (_stable_number(key + ":offset") % (max_offset_ms + 1)) / 1000
        return BackgroundSelection(source, source_duration, start_offset, required_duration, profile)


@dataclass(frozen=True)
class CharacterAsset:
    character: str
    pose: str
    path: Path


class CharacterAssetRegistry:
    def __init__(self, root: Path, warnings: list[str] | None = None):
        self.root = root
        self.warnings = warnings if warnings is not None else []
        self._cache: dict[str, list[CharacterAsset]] = {}

    def discover(self, character: str) -> list[CharacterAsset]:
        if character in self._cache:
            return self._cache[character]
        folder = self.root / character
        assets = []
        for path in sorted(folder.glob("*")):
            if not path.is_file() or path.suffix.lower() != ".png":
                continue
            try:
                with Image.open(path) as image:
                    if image.format != "PNG":
                        raise ValueError("not a PNG image")
                    image.load()
                    if "A" not in image.getbands() and "transparency" not in image.info:
                        raise ValueError("missing transparency")
                    if not image.convert("RGBA").getchannel("A").getbbox():
                        raise ValueError("no visible pixels")
            except (OSError, ValueError, UnidentifiedImageError) as error:
                self._warn(f"Skipping invalid character PNG {path}: {error}")
                continue
            assets.append(CharacterAsset(character, path.stem, path))
        if not assets:
            self._warn(f"No character PNG poses in {folder}; continuing without {character} overlay")
        self._cache[character] = assets
        return assets

    def choose(self, character: str, requested: str, key: str,
               previous: Path | None = None, *, category: str = "active") -> CharacterAsset | None:
        assets = self.discover(character)
        if not assets:
            return None
        pose_config = CHARACTERS.get(character, {})
        active_names = set(pose_config.get("active_poses", []))
        reaction_names = set(pose_config.get("reaction_poses", []))
        disabled_names = set(pose_config.get("disabled_poses", []))
        available = [asset for asset in assets if asset.pose not in disabled_names]
        if not available:
            self._warn(f"No enabled character PNG poses for {character}; continuing without overlay")
            return None
        categorized = active_names | reaction_names | disabled_names
        uncategorized = [asset for asset in available if asset.pose not in categorized]
        if category == "reaction":
            pool = [asset for asset in available if asset.pose in reaction_names]
        else:
            configured_active = [asset for asset in available if asset.pose in active_names]
            # Once a character has usable configured ACTIVE poses, unclassified
            # files must be explicitly added to the profile before rendering.
            pool = configured_active or uncategorized
        # Missing configured files and new, uncategorized characters both remain safe.
        # Active falls back to any enabled pose; reaction does the same when its
        # optional reaction pool is empty.
        if category == "active" and not pool:
            self._warn(f"No ACTIVE character PNG poses for {character}; continuing without overlay")
            return None
        options = pool or available
        # Filename stems are pose keys. Semantic words may appear with a
        # character prefix, e.g. rick_angry.png or morty_neutral.png.
        preferred = [asset for asset in options if requested.casefold() in
                     asset.pose.casefold().split("_")]
        candidates = preferred or options
        if previous is not None:
            alternatives = [asset for asset in candidates if asset.path != previous]
            if alternatives:
                candidates = alternatives
            elif len(options) > 1:
                candidates = [asset for asset in options if asset.path != previous]
        return candidates[_stable_number(key) % len(candidates)]

    def cropped(self, asset: CharacterAsset, workspace: Path) -> Path:
        destination = workspace / f"character_{asset.character}_{asset.pose}.png"
        if destination.is_file():
            return destination
        with Image.open(asset.path) as image:
            rgba = image.convert("RGBA")
            box = rgba.getchannel("A").getbbox()
            if box is None:
                raise ValueError(f"No visible pixels in {asset.path}")
            rgba.crop(box).save(destination, format="PNG")
        return destination

    def _warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)
            log.warning(message)


@dataclass(frozen=True)
class PoseLayer:
    asset: CharacterAsset
    side: str
    start: float
    end: float
    active: bool
    turn_index: int
    speaker: str
    entry_seconds: float = 0.0
    exit_seconds: float = 0.0
    initial: bool = False
    scale: float = 1.0
    anchor_offset: int = 0

    def x_expression(self, anchor: int, travel: int) -> str:
        rest = (f"{anchor + self.anchor_offset}" if self.side == "left" else
                f"W-w-{anchor + self.anchor_offset}")
        direction = -1 if self.side == "left" else 1
        entry_end = self.start + self.entry_seconds
        exit_start = self.end - self.exit_seconds
        if self.entry_seconds:
            progress = (f"((t-{self.start:.6f})/{self.entry_seconds:.6f})")
            smooth = f"({progress}*{progress}*(3-2*{progress}))"
            enter = f"({rest})+({direction * travel})*(1-{smooth})"
        else:
            enter = rest
        if self.exit_seconds:
            progress = f"((t-{exit_start:.6f})/{self.exit_seconds:.6f})"
            leave = f"({rest})+({direction * travel})*pow({progress},2)"
        else:
            leave = rest
        return f"if(lt(t,{entry_end:.6f}),{enter},if(gt(t,{exit_start:.6f}),{leave},{rest}))"

    def y_expression(self, bottom_margin: int) -> str:
        rest = f"H-h-{bottom_margin}"
        entry_end = self.start + self.entry_seconds
        exit_start = self.end - self.exit_seconds
        # Smoothstep entry, quadratic exit. First appearance starts at rest at t=0.
        enter = (f"H-({bottom_margin}+h)*(pow((t-{self.start:.6f})/{self.entry_seconds:.6f},2)*"
                 f"(3-2*(t-{self.start:.6f})/{self.entry_seconds:.6f}))") if self.entry_seconds else rest
        leave = (f"({rest})+({bottom_margin}+h)*pow((t-{exit_start:.6f})/{self.exit_seconds:.6f},2)") if self.exit_seconds else rest
        return f"if(lt(t,{entry_end:.6f}),{enter},if(gt(t,{exit_start:.6f}),{leave},{rest}))"


def _filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")


class DialogueCompositor:
    def __init__(self, settings):
        self.s = settings
        self.warnings: list[str] = []
        self.metadata: dict = {}
        self.registry = CharacterAssetRegistry(settings.character_root, self.warnings)

    def _poses(self, item, timeline) -> list[PoseLayer]:
        profile = item.character_profile or (item.dialogue_preset if item.visual_profile == "gameplay"
                                              and item.dialogue_preset in CHARACTER_PROFILES else None)
        config = CHARACTER_PROFILES.get(profile) if profile else None
        if config is None and item.content_format == "explainer" and item.visual_profile == "random":
            for candidate, mapping in CHARACTER_PROFILES.items():
                if item.voice_profile in mapping:
                    config = {item.voice_profile: mapping[item.voice_profile]}
                    profile = f"single:{item.voice_profile}"
                    break
        if config is None:
            return []
        self.metadata["character_profile"] = profile
        layers = []
        previous: dict[str, Path] = {}
        sequence = []
        seed = getattr(item, "visual_seed", None) or "default"
        entry = getattr(self.s, "character_entry_seconds", 0.28)
        exit_time = getattr(self.s, "character_exit_seconds", 0.22)
        scale_variation = getattr(self.s, "character_scale_variation", 0.04)
        position_variation = getattr(self.s, "character_position_variation", 16)
        pose_timeline = self._pose_timeline(item, timeline)
        for index, turn in enumerate(pose_timeline):
            selected = {}
            placement = config.get(turn.speaker)
            if placement is None:
                sequence.append({"turn": index, "speaker": turn.speaker, "poses": selected})
                continue
            speaker = turn.speaker
            character, side = placement
            key = f"{item.id}:{seed}:{index}:{speaker}"
            start = turn.start
            stop = turn.end
            initial = index == 0 and start == 0
            entry_time = 0 if initial else min(entry, (turn.end - turn.start) / 3)
            if index > 0 and pose_timeline[index - 1].speaker == speaker:
                entry_time = 0
                for old_index in range(len(layers) - 1, -1, -1):
                    if layers[old_index].speaker == speaker:
                        layers[old_index] = replace(layers[old_index], end=start, exit_seconds=0)
                        break
            asset = self.registry.choose(
                character, "talking", key, previous.get(speaker), category="active",
            )
            if asset is not None:
                previous[speaker] = asset.path
                selected[speaker] = asset.pose
                scale_unit = (_stable_number(key + ":scale") % 10001) / 10000
                scale = 1 + (scale_unit * 2 - 1) * scale_variation
                position_unit = (_stable_number(key + ":position") % 10001) / 10000
                position = round((position_unit * 2 - 1) * position_variation)
                layers.append(PoseLayer(asset, side, start, stop, True, index, speaker,
                                        entry_time, min(exit_time, (stop - start) / 3), initial,
                                        scale, position))
            sequence.append({"turn": index, "speaker": turn.speaker, "poses": selected})
        self.metadata["character_poses"] = sequence
        self.metadata["character_appearances"] = [
            {"speaker": layer.speaker, "pose": layer.asset.pose, "start": layer.start,
             "end": layer.end, "active": layer.active, "initial": layer.initial,
             "entry_seconds": layer.entry_seconds, "exit_seconds": layer.exit_seconds,
             "scale": layer.scale, "anchor_offset": layer.anchor_offset,
             "reaction": False, "pose_category": "active"}
            for layer in layers]
        return layers

    def _pose_timeline(self, item, timeline):
        """Split long single-speaker narration into stable pose intervals."""
        if item.content_format != "explainer" or len(timeline) != 1:
            return timeline
        turn = timeline[0]
        minimum = getattr(self.s, "single_speaker_pose_min_seconds", 3.0)
        maximum = getattr(self.s, "single_speaker_pose_max_seconds", 6.0)
        if minimum > maximum:
            raise ValueError("Single-speaker pose minimum must not exceed its maximum")
        if turn.end - turn.start <= maximum:
            return timeline
        seed = getattr(item, "visual_seed", None) or "default"
        result, cursor, index = [], turn.start, 0
        while cursor < turn.end - 0.0005:
            remaining = turn.end - cursor
            if remaining <= maximum:
                stop = turn.end
            else:
                unit = (_stable_number(f"{item.id}:{seed}:pose-span:{index}") % 10001) / 10000
                span = minimum + unit * (maximum - minimum)
                if 0 < remaining - span < minimum:
                    span = remaining - minimum
                stop = min(turn.end, cursor + span)
            result.append(replace(turn, start=cursor, end=stop))
            cursor, index = stop, index + 1
        return result

    def _target_size(self, cropped: Path, layer: PoseLayer) -> tuple[int, int]:
        with Image.open(cropped) as image:
            source_width, source_height = image.size
        profile_scale = CHARACTERS.get(layer.asset.character, {}).get("scale", 1.0)
        target_height = round(getattr(self.s, "character_active_height", 740) *
                              profile_scale * layer.scale)
        max_width = getattr(self.s, "character_max_width", 660)
        factor = min(target_height / source_height, max_width / source_width)
        return max(2, round(source_width * factor)), max(2, round(source_height * factor))

    def compose(self, item, source: Path, dialogue, destination: Path, workspace: Path,
                *, selection: BackgroundSelection | None = None) -> Path:
        duration = selection.segment_duration if selection else dialogue.duration
        if selection:
            if selection.source != source or selection.start_offset + duration > selection.source_duration + 0.001:
                raise ValueError("Background selection does not fit source")
            offset = selection.start_offset
            self.metadata.update(selection.metadata())
        else:
            source_duration = media_duration(source, self.s.ffprobe_binary)
            offset = 0.0 if source_duration <= duration else (_stable_number(item.id + ":segment") % 10000) / 10000 * (source_duration - duration)
        self.metadata["final_dialogue_duration"] = duration
        self.metadata["final_audio_duration"] = duration
        subtitle_started = time.monotonic()
        single = item.content_format == "explainer"
        max_chars = getattr(
            self.s, "explainer_subtitle_max_chars" if single else "dialogue_subtitle_max_chars",
            24 if single else 26,
        )
        min_words = getattr(
            self.s, "explainer_subtitle_min_words" if single else "dialogue_subtitle_min_words",
            2,
        )
        max_words = getattr(
            self.s, "explainer_subtitle_max_words" if single else "dialogue_subtitle_max_words",
            4 if single else 5,
        )
        subtitle = write_subtitles(
            dialogue.timeline, workspace / "dialogue.srt", max_chars=max_chars,
            min_words=min_words, max_words=max_words,
        )
        self.metadata["subtitle_cues"] = [
            {"start": cue.start, "end": cue.end, "text": cue.text}
            for cue in dialogue_cues(dialogue.timeline, max_chars=max_chars,
                                     min_words=min_words, max_words=max_words)]
        subtitle_seconds = time.monotonic() - subtitle_started
        character_started = time.monotonic()
        poses = self._poses(item, dialogue.timeline)
        command = [self.s.ffmpeg_binary, "-nostdin", "-v", "error", "-y"]
        if not selection:
            command += ["-stream_loop", "-1"]
        # Input-level seek avoids decoding hours of AV1 before the chosen offset.
        command += ["-ss", f"{offset:.3f}", "-i", str(source.resolve()), "-i", str(dialogue.path.resolve())]
        rendered = []
        for layer in poses:
            cropped = self.registry.cropped(layer.asset, workspace).resolve()
            width, height = self._target_size(cropped, layer)
            rendered.append((layer, cropped, width, height))
            command += ["-loop", "1", "-i", str(cropped)]
        for appearance, (_, _, width, height) in zip(
                self.metadata.get("character_appearances", []), rendered):
            appearance.update(render_width=width, render_height=height)
        character_seconds = time.monotonic() - character_started
        filters = ["[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase,"
                   "crop=1080:1920,setsar=1,format=yuv420p[base]"]
        current = "base"
        for index, (layer, _, width, height) in enumerate(rendered, 2):
            scaled, out = f"pose{index}", f"layer{index}"
            filters.append(f"[{index}:v]format=rgba,scale={width}:{height}:flags=lanczos[{scaled}]")
            anchor = (getattr(self.s, "character_left_anchor", 40) if layer.side == "left" else
                      getattr(self.s, "character_right_anchor", 40))
            x = layer.x_expression(anchor, getattr(self.s, "character_entry_horizontal_pixels", 48))
            y = layer.y_expression(getattr(self.s, "character_bottom_margin", 350))
            filters.append(f"[{current}][{scaled}]overlay=x='{x}':y='{y}':"
                           f"enable='gte(t,{layer.start:.3f})*lt(t,{layer.end:.3f})'[{out}]")
            current = out
        subtitle_margin = getattr(
            self.s,
            "explainer_subtitle_bottom_margin" if single else "dialogue_subtitle_bottom_margin",
            64 if single else 48,
        )
        self.metadata["dialogue_subtitle_bottom_margin"] = subtitle_margin
        self.metadata["subtitle_bottom_margin"] = subtitle_margin
        if single:
            subtitle_style = f"FontSize=13,Alignment=2,MarginV={subtitle_margin},Outline=1"
        else:
            font_size = getattr(self.s, "dialogue_subtitle_font_size", 13)
            outline = getattr(self.s, "dialogue_subtitle_outline", 1.0)
            bold = ",Bold=1" if getattr(self.s, "dialogue_subtitle_bold", False) else ""
            subtitle_style = (f"FontSize={font_size}{bold},Alignment=2,"
                              f"MarginV={subtitle_margin},Outline={outline:g}")
        filters.append(f"[{current}]subtitles='dialogue.srt':"
                       f"force_style='{subtitle_style}'[video]")
        command += ["-filter_complex", ";".join(filters), "-map", "[video]", "-map", "1:a:0",
                    "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "22",
                    "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-profile:a", "aac_low",
                    "-b:a", "120k", "-ar", "48000", "-movflags", "+faststart", str(destination.resolve())]
        render_started = time.monotonic()
        try:
            subprocess.run(command, capture_output=True, text=True, check=True, timeout=900, cwd=workspace)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"FFmpeg could not compose dialogue video: {error.stderr[-800:]}") from error
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError("FFmpeg could not compose dialogue video") from error
        if not destination.is_file() or destination.stat().st_size == 0:
            raise RuntimeError("FFmpeg produced no dialogue video")
        self.metadata["stage_timings"] = {"chunked_subtitles": subtitle_seconds,
                                          "character_overlays": character_seconds,
                                          "final_composition": time.monotonic() - render_started}
        return destination
