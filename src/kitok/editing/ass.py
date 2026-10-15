from __future__ import annotations

import math
import re
from pathlib import Path

from .manifest import EditManifest


def _color(value: str, alpha: str = "00") -> str:
    value = value.lstrip("#")
    return f"&H{alpha}{value[4:6]}{value[2:4]}{value[:2]}"


def _time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    return f"{hours}:{minutes:02d}:{remainder // 100:02d}.{remainder % 100:02d}"


def _text(text: str) -> str:
    # Operator narration is never ASS code. Braces/backslashes cannot inject tags.
    return text.replace("\\", "／").replace("{", "(").replace("}", ")").replace("\n", " ")


def _wrap(text: str, width: int) -> str:
    lines, current = [], ""
    for word in _text(text).split():
        if current and len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return r"\N".join(lines)


def _event(layer: int, start: float, end: float, content: str) -> str:
    return f"Dialogue: {layer},{_time(start)},{_time(end)},Default,,0,0,0,,{content}"


def write_chunk_ass(manifest: EditManifest, path: Path, *, start: float, end: float, width: int, height: int) -> bool:
    """Render only semantic highlights, with vector panels and restrained phrase motion."""
    events = []
    scale = height / 1080
    font_size = max(22, round(52 * scale))
    accent = _color(manifest.style.accent)
    foreground = _color(manifest.style.text)
    background = _color(manifest.style.background)
    for cue in manifest.cues:
        if cue.end <= start or cue.start >= end:
            continue
        local_start = max(0., cue.start - start)
        local_end = min(end, cue.end) - start
        centered = cue.position == "center"
        side = cue.position == "side"
        size = round(font_size * (1.75 if cue.kind == "amount" else 1.12 if centered else 1))
        max_chars = max(16, int(width / (size * .58)) - 8)
        headline = _wrap(cue.text, max_chars)
        lines = headline.count(r"\N") + 1
        panel_width = min(round(width * .84), max(round(width * .32), int(min(max_chars, max(len(line) for line in headline.split(r"\N"))) * size * .60 + 90 * scale)))
        panel_height = round((size * lines * 1.3 + 82 * scale) * (1.2 if cue.kind == "comparison" else 1))
        x = round(width * .08) if side else (width - panel_width) // 2
        y = (height - panel_height) // 2 if centered or side else height - panel_height - round(height * .12)
        # A single native vector panel is cheaper and sharper than a raster overlay.
        panel = (
            rf"{{\an7\pos({x},{y})\fad(180,220)\1c{background}\1a&H16&\bord0\p1}}"
            f"m 0 0 l {panel_width} 0 l {panel_width} {panel_height} l 0 {panel_height}"
        )
        events.append(_event(0, local_start, local_end, panel))
        stripe_width = max(3, round(6 * scale))
        stripe = (
            rf"{{\an7\pos({x},{y})\fad(180,220)\1c{accent}\bord0\p1}}"
            f"m 0 0 l {stripe_width} 0 l {stripe_width} {panel_height} l 0 {panel_height}"
        )
        events.append(_event(1, local_start, local_end, stripe))
        if cue.kind == "comparison" and len(cue.values) == 2:
            headline = _wrap(f"{cue.values[0]}  →  {cue.values[1]}", max_chars)
        ty = y + panel_height // 2
        tx = x + panel_width // 2
        # Phrase motion rather than fabricated per-word karaoke timing.
        motion = rf"\move({tx},{ty + round(10 * scale)},{tx},{ty},0,240)"
        text = (
            rf"{{\an5{motion}\fad(180,220)\fs{size}\1c{accent if cue.kind in {'amount', 'date'} else foreground}"
            rf"\bord0\shad0\b1}}{headline}"
        )
        events.append(_event(2, local_start, local_end, text))
        if cue.kind == "date":
            # A timeline marker, conveying only the spoken date, no invented history.
            line_y = y + panel_height - round(18 * scale)
            length = round(panel_width * .65)
            line = (
                rf"{{\an7\pos({tx - length // 2},{line_y})\1c{accent}\bord0\p1\fad(250,220)}}"
                f"m 0 0 l {length} 0 l {length} {max(2, round(3 * scale))} l 0 {max(2, round(3 * scale))}"
            )
            events.append(_event(1, local_start, local_end, line))
        if cue.kind == "comparison" and len(cue.values) == 2:
            # Only chart comparable literal numbers. Units/currencies must agree.
            numbers = [re.fullmatch(r"\s*([$€£]?)\s*(\d+(?:\.\d+)?)\s*([^\d]*)", value) for value in cue.values]
            if all(numbers) and numbers[0][1] == numbers[1][1] and numbers[0][3].strip().casefold() == numbers[1][3].strip().casefold():
                magnitudes = [float(value[2]) for value in numbers]
                if min(magnitudes) >= 0 and max(magnitudes) > 0:
                    available = panel_width * .68
                    for number_index, value in enumerate(magnitudes):
                        bar_width = max(2, round(available * value / max(magnitudes)))
                        bar_height = max(2, round(5 * scale))
                        bar_x = x + round(panel_width * .16)
                        bar_y = y + panel_height - round((28 - number_index * 10) * scale)
                        bar = (
                            rf"{{\an7\pos({bar_x},{bar_y})\1c{accent}\bord0\p1\fad(250,220)}}"
                            f"m 0 0 l {bar_width} 0 l {bar_width} {bar_height} l 0 {bar_height}"
                        )
                        events.append(_event(1, local_start, local_end, bar))
    if not events:
        return False
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{manifest.style.font_family},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,0,0,5,30,30,30,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return True


def filter_path(path: Path) -> str:
    # Escape filtergraph and quoted option syntaxes, not shell syntax (no shell used).
    value = str(path.resolve())
    for character in ("\\", "'", ":", ",", ";", "[", "]"):
        value = value.replace(character, "\\" + character)
    return value


def clip_edit_filters(manifest: EditManifest, start: float, duration: float, width: int, height: int, fps: int) -> list[str]:
    nearby = [cue for cue in manifest.cues if cue.start < start + duration and cue.end > start]
    if not nearby:
        return []
    filters = []
    if any(cue.kind in {"amount", "comparison"} for cue in nearby):
        # zoompan d=1 preserves real video frames and timing; a maximum 3% push.
        frame_count = max(1, round(duration * fps))
        filters.append(f"zoompan=z='1+0.03*min(on/{frame_count},1)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={width}x{height}:fps={fps}")
    elif any(cue.kind == "date" for cue in nearby):
        # Controlled 4% horizontal pan makes timeline/context scenes distinct.
        filters += [f"scale={math.ceil(width * 1.04 / 2) * 2}:{math.ceil(height * 1.04 / 2) * 2}", f"crop={width}:{height}:x='(iw-ow)*min(t/{duration:.6f},1)':y='(ih-oh)/2'"]
    if any(cue.kind == "question" for cue in nearby):
        # Semantic chapter/revelation dip, no duration overlap or audio shift.
        filters.append("fade=t=in:st=0:d=0.22")
    return filters
