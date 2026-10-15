"""Local, reusable editorial plates. These graphics are illustrations, never evidence.

``identity``: name (required), eyebrow, supporting_line, attribution,
icon (person/question/none; default person).
``metric``: value and label (required), eyebrow, supporting_line, attribution.
``hidden_information``: title, player_labels (two strings), supporting_line,
attribution, state (private/exposed; default private). The left account is the
viewpoint; only exposed grants it sight of the right account's cards. This
schematic always carries an explicit illustration disclaimer.

Text comes from the caller; no historical amounts, names or source claims are
inferred. Style accepts only ``palette`` (ivory/green) and a hex ``accent``.
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


_PALETTES = {
    "ivory": {"bg": "#F2F0E4", "ink": "#164E3D", "muted": "#466052", "panel": "#E2E6D6", "accent": "#BAEF68"},
    "green": {"bg": "#164E3D", "ink": "#F5F2E5", "muted": "#D0DFCD", "panel": "#22634C", "accent": "#BAEF68"},
}
_FONT_ROOT = Path("/usr/share/fonts/truetype/dejavu")
DISCLAIMER = "EDITORIAL ILLUSTRATION · NOT AN ACTUAL HAND"


def _font(size: int, *, bold: bool = False, serif: bool = False):
    filename = "DejaVuSerif.ttf" if serif else "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    # Only installed, fixed font names are accepted; caller cannot select a path.
    for candidate in (_FONT_ROOT / filename, filename):
        try:
            return ImageFont.truetype(str(candidate), size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow 10.0 has only a fixed-size bitmap fallback.
        return ImageFont.load_default()


def _text_field(data: dict, key: str, *, default: str = "", required: bool = False, limit: int = 240) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError(f"Invalid graphic {key}: expected text of at most {limit} characters")
    value = " ".join(value.split())
    if required and not value:
        raise ValueError(f"Graphic {key} is required")
    return value


def _lines(draw, text: str, font, width: float) -> list[str]:
    """Wrap by measured glyph width, including unbroken multilingual names."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if draw.textbbox((0, 0), candidate, font=font)[2] <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        for char in word:
            if current and draw.textbbox((0, 0), current + char, font=font)[2] > width:
                lines.append(current)
                current = ""
            current += char
    if current:
        lines.append(current)
    return lines


def _fit(draw, text: str, box, size: int, *, minimum: int, bold=False, serif=False, max_lines=4):
    width, height = box[2] - box[0], box[3] - box[1]
    for candidate in range(size, minimum - 1, -1):
        font = _font(candidate, bold=bold, serif=serif)
        lines = _lines(draw, text, font, width)
        spacing = max(3, round(candidate * .16))
        bounds = draw.multiline_textbbox((0, 0), "\n".join(lines), font=font, spacing=spacing)
        if len(lines) <= max_lines and bounds[2] - bounds[0] <= width and bounds[3] - bounds[1] <= height:
            return font, "\n".join(lines), spacing, bounds
    raise ValueError("Graphic text does not fit legibly; shorten the supplied text")


def _write(draw, text, box, size, color, *, minimum=18, bold=False, serif=False, max_lines=4, center=False):
    if not text:
        return
    font, wrapped, spacing, bounds = _fit(draw, text, box, size, minimum=minimum, bold=bold, serif=serif, max_lines=max_lines)
    x, y = box[0] - bounds[0], box[1] - bounds[1]
    if center:
        x += (box[2] - box[0] - (bounds[2] - bounds[0])) / 2
    draw.multiline_text((x, y), wrapped, font=font, spacing=spacing, fill=color, align="center" if center else "left")


def render_graphic(kind: str, data: dict, output: Path, *, width: int = 1920, height: int = 1080, style: dict | None = None) -> Path:
    """Render an opaque PNG without network access, generated assets, or factual defaults.

    Dimensions are bounded to keep operator input from allocating excessive memory.
    Text which cannot fit at a readable size raises ``ValueError`` before saving.
    """
    if kind not in {"identity", "metric", "hidden_information"}:
        raise ValueError(f"Unknown graphic kind: {kind}")
    if not isinstance(data, dict) or (style is not None and not isinstance(style, dict)):
        raise ValueError("Graphic data and style must be objects")
    if any(type(v) is not int or not 480 <= v <= 4096 for v in (width, height)):
        raise ValueError("Graphic dimensions must be integers from 480 to 4096")
    style = style or {}
    if set(style) - {"palette", "accent"}:
        raise ValueError("Graphic style only accepts palette and accent")
    palette = style.get("palette", "ivory")
    if not isinstance(palette, str) or palette not in _PALETTES:
        raise ValueError("Unknown graphic palette")
    colors = dict(_PALETTES[palette])
    if "accent" in style:
        if not isinstance(style["accent"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", style["accent"]):
            raise ValueError("Graphic accent must be a six-digit hex color")
        colors["accent"] = style["accent"]
    allowed = {"supporting_line", "attribution"} | ({"name", "eyebrow", "icon"} if kind == "identity" else {"value", "label", "eyebrow"} if kind == "metric" else {"title", "player_labels", "state"})
    if any(not isinstance(key, str) for key in data):
        raise ValueError("Graphic field names must be strings")
    if set(data) - allowed:
        raise ValueError(f"Unknown fields for graphic {kind}: {', '.join(sorted(set(data) - allowed))}")
    supporting = _text_field(data, "supporting_line", limit=240)
    attribution = _text_field(data, "attribution", limit=200)
    image = Image.new("RGB", (width, height), colors["bg"])
    draw = ImageDraw.Draw(image)
    # 7.5% margins protect all text from common video crops and animation moves.
    left, right = width * .075, width * .925
    top, bottom = height * .075, height * .925
    scale = min(width / 1920, height / 1080)
    minimum = max(12, round(22 * scale))
    portrait = height > width

    def text(value, box, size, color=None, **kwargs):
        _write(draw, value, box, max(minimum, round(size * scale)), color or colors["ink"], minimum=minimum, **kwargs)

    draw.rectangle((left, top, left + width * .065, top + max(5, height * .009)), fill=colors["accent"])
    if kind in {"identity", "metric"}:
        eyebrow = _text_field(data, "eyebrow", default="ACCOUNT ALIAS" if kind == "identity" else "", limit=80)
        text(eyebrow, (left, height * .125, right, height * .20), 30, bold=True, max_lines=2)
        if kind == "identity":
            name = _text_field(data, "name", required=True, limit=100)
            icon = data.get("icon", "person")
            if not isinstance(icon, str) or icon not in {"person", "question", "none"}:
                raise ValueError("Graphic icon must be person, question or none")
            if icon != "none":
                # Abstract editorial marker, never a recreated account UI.
                panel_x = left if portrait else width * .72
                panel_y = height * .56 if portrait else height * .27
                panel_w = width * .26 if portrait else width * .19
                panel_h = height * .15 if portrait else height * .37
                draw.rounded_rectangle((panel_x, panel_y, panel_x + panel_w, panel_y + panel_h), radius=max(8, int(28 * scale)), fill=colors["accent"])
                if icon == "person":
                    cx, cy = panel_x + panel_w / 2, panel_y + panel_h * .34
                    radius = min(panel_w, panel_h) * .15
                    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline="#164E3D", width=max(2, round(6 * scale)))
                    draw.arc((panel_x + panel_w * .22, panel_y + panel_h * .52, panel_x + panel_w * .78, panel_y + panel_h * .97), 180, 360, fill="#164E3D", width=max(2, round(6 * scale)))
                else:
                    text("?", (panel_x + panel_w * .1, panel_y + panel_h * .14, panel_x + panel_w * .9, panel_y + panel_h * .9), 290, "#164E3D", bold=True, center=True, max_lines=1)
            name_right = right if portrait or icon == "none" else width * .67
            name_bottom = height * (.66 if portrait and icon == "none" else .52 if portrait else .58)
            text(name, (left, height * .27, name_right, name_bottom), 174, bold=True, max_lines=3)
            supporting_top = height * (.70 if portrait and icon == "none" else .75 if portrait else .65)
            text(supporting, (left, supporting_top, right, height * .85), 43, max_lines=3)
        else:
            value = _text_field(data, "value", required=True, limit=40)
            label = _text_field(data, "label", required=True, limit=160)
            text(value, (left, height * .27, right, height * .53), 220, bold=True, max_lines=2)
            draw.rectangle((left, height * .56, left + width * .14, height * .575), fill=colors["accent"])
            text(label, (left, height * .62, right, height * .76), 61, serif=True, max_lines=3)
            text(supporting, (left, height * .79, right, height * .855), 30, colors["muted"], max_lines=2)
        text(attribution, (left, height * .89, right, bottom), 23, colors["muted"], max_lines=2)
    else:
        title = _text_field(data, "title", default="The information advantage", limit=140)
        players = data.get("player_labels", ["PLAYER ONE", "PLAYER TWO"])
        if not isinstance(players, (list, tuple)) or len(players) != 2:
            raise ValueError("Graphic player_labels requires exactly two labels")
        players = [_text_field({"player": item}, "player", required=True, limit=80) for item in players]
        state = data.get("state", "private")
        if not isinstance(state, str) or state not in {"private", "exposed"}:
            raise ValueError("Graphic state must be private or exposed")
        exposed = state == "exposed"
        text(title, (left, height * .13, right, height * .285), 76, bold=True, max_lines=2)
        text(supporting, (left, height * .30, right, height * .39), 32, colors["muted"], max_lines=2)
        gap = width * .055
        panel_w = (right - left - gap) / 2
        panel_top, panel_bottom = height * .48, height * .765
        for index, label in enumerate(players):
            x = left + index * (panel_w + gap)
            privileged = exposed and index == 0
            draw.rounded_rectangle((x, panel_top, x + panel_w, panel_bottom), radius=max(8, round(20 * scale)), fill=colors["panel"], outline=colors["accent"] if privileged else None, width=max(2, round(7 * scale)))
            text(label, (x + panel_w * .08, panel_top + height * .026, x + panel_w * .92, panel_top + height * .085), 29, bold=True, max_lines=2)
            cw, ch = panel_w * .26, (panel_bottom - panel_top) * .40
            cy = panel_top + (panel_bottom - panel_top) * .37
            visible = index == 0 or exposed
            for card_index in range(2):
                cx = x + panel_w * (.24 + card_index * .29)
                card_color = colors["accent"] if index == 1 and exposed else colors["bg"]
                card_ink = "#164E3D" if index == 1 and exposed else colors["ink"]
                draw.rounded_rectangle((cx, cy, cx + cw, cy + ch), radius=max(3, round(9 * scale)), fill=card_color, outline=colors["muted"], width=max(1, round(2 * scale)))
                inset = min(cw, ch) * .16
                draw.rectangle((cx + inset, cy + inset, cx + cw - inset, cy + ch - inset), outline=colors["muted"], width=max(1, round(2 * scale)))
                if visible:
                    text("VISIBLE", (cx + cw * .08, cy + ch * .43, cx + cw * .92, cy + ch * .67), 22, card_ink, bold=True, center=True, max_lines=1)
                else:
                    # Repeated lines identify hidden backs, without invented suits.
                    for stripe in (.36, .5, .64):
                        sy = cy + ch * stripe
                        draw.line((cx + cw * .32, sy, cx + cw * .68, sy), fill=colors["muted"], width=max(1, round(3 * scale)))
            status = "OWN PRIVATE CARDS" if index == 0 else "VISIBLE TO THIS ACCOUNT" if exposed else "HIDDEN FROM THIS ACCOUNT"
            text(status, (x + panel_w * .07, panel_bottom - height * .055, x + panel_w * .93, panel_bottom - height * .012), 22, colors["muted"], center=True, max_lines=1)
        # The eye belongs to the LEFT account; the barrier persists in both states.
        barrier_x = width / 2
        dash = max(4, round(height * .012))
        for y in range(round(height * .405), round(panel_bottom), dash * 2):
            draw.line((barrier_x, y, barrier_x, min(y + dash, panel_bottom)), fill=colors["muted"], width=max(2, round(3 * scale)))
        eye_x, eye_y = left + panel_w * .76, height * .435
        eye_w, eye_h = width * .026, height * .016
        draw.ellipse((eye_x - eye_w, eye_y - eye_h, eye_x + eye_w, eye_y + eye_h), fill=colors["accent"], outline=colors["ink"], width=max(1, round(2 * scale)))
        draw.ellipse((eye_x - eye_h * .5, eye_y - eye_h * .5, eye_x + eye_h * .5, eye_y + eye_h * .5), fill="#164E3D")
        view_label = "PRIVILEGED VIEW" if exposed else "ACCOUNT VIEW"
        text(view_label, (left, height * .415, eye_x - eye_w * 1.6, height * .46), 25, bold=True, max_lines=1)
        own_x = left + panel_w * .5
        draw.line((eye_x, eye_y + eye_h, own_x, panel_top), fill=colors["ink"], width=max(2, round(3 * scale)))
        if exposed:
            # A single arrow crosses from this account to the opponent's holdings.
            target_x = right - panel_w * .5
            path = (eye_x + eye_w, eye_y, target_x, eye_y, target_x, panel_top - height * .008)
            draw.line(path, fill=colors["ink"], width=max(3, round(8 * scale)))
            draw.line(path, fill=colors["accent"], width=max(2, round(4 * scale)))
            arrow = width * .008
            tip_y = panel_top - height * .002
            draw.polygon(((target_x, tip_y), (target_x - arrow, tip_y - arrow), (target_x + arrow, tip_y - arrow)), fill=colors["ink"])
        text(DISCLAIMER, (left, height * .805, right, height * .875), 29, bold=True, max_lines=2, center=True)
        text(attribution, (left, height * .89, right, bottom), 23, colors["muted"], max_lines=2)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG")
    return output
