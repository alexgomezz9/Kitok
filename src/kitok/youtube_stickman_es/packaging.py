"""Faithful local YouTube packaging; image generation remains an explicit agent step.

No provider calls or publishing occur here. Outputs are immutable within an episode:
use a new episode revision after changing the approved materials.
"""
from __future__ import annotations

import io
import json
import math
import os
from pathlib import Path
import re
import tempfile

from PIL import Image, ImageDraw, ImageFont, ImageOps


def _safe_path(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError(f"Symlinks are not accepted: {component}")
    return path


def _write_outputs(outputs: dict[Path, bytes]) -> None:
    """Preflight every destination before writing; never replace different content."""
    for destination, content in outputs.items():
        _safe_path(destination)
        if destination.exists() and (not destination.is_file() or destination.read_bytes() != content):
            raise FileExistsError(f"Output differs; use a new episode revision: {destination}")
    for destination, content in outputs.items():
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".packaging-", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            # A hard link publishes the complete file without overwriting a concurrent writer.
            try:
                os.link(temporary, destination)
            except FileExistsError:
                _safe_path(destination)
                if destination.read_bytes() != content:
                    raise FileExistsError(f"Concurrent output differs: {destination}") from None
        finally:
            Path(temporary).unlink(missing_ok=True)


def _json(data: object) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _line(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value:
        raise ValueError(f"{name} must be a nonempty single line")
    return value


def _first_sentence(text: str) -> str:
    # Select complete supplied text, without shortening questions or changing negation.
    return re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÜÑ¿¡])", text.strip(), maxsplit=1)[0]


def _timestamp(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def _chapter_plan(script: str, scenes: list[dict], duration: float,
                  explicit: list[dict] | None) -> dict:
    by_id = {scene["id"]: scene for scene in scenes}
    if explicit is not None:
        selected = []
        for chapter in explicit:
            if chapter.get("scene_id") not in by_id:
                raise ValueError("Chapter references an unknown scene_id")
            scene = by_id[chapter["scene_id"]]
            selected.append({"scene_id": scene["id"], "start": math.floor(float(scene["start"])),
                             "title": _line(chapter.get("title"), "Chapter title")})
    else:
        selected = []
        normalized = " ".join(script.split())
        target_gap = max(10.0, duration / 5)
        search_from = 0
        for scene in scenes:
            narration = " ".join(str(scene.get("narration", "")).split())
            if not narration:
                continue
            position = normalized.find(narration, search_from)
            if position < 0:
                continue
            search_from = position + len(narration)
            at_sentence = position == 0 or normalized[:position].rstrip().endswith((".", "!", "?"))
            start = math.floor(float(scene["start"]))
            if not selected:
                if start != 0 or position != 0:
                    continue
            elif not at_sentence or start - selected[-1]["start"] < target_gap:
                continue
            if duration - start < 10:
                continue
            selected.append({"scene_id": scene["id"], "start": start,
                             "title": _first_sentence(str(scene["narration"])).replace("\n", " ").replace("\r", " ")})
    valid = (len(selected) >= 3 and selected[0]["start"] == 0
             and all(b["start"] - a["start"] >= 10 for a, b in zip(selected, selected[1:]))
             and duration - selected[-1]["start"] >= 10)
    if explicit is not None and not valid:
        raise ValueError("Chapters require >=3 entries, first 00:00 and >=10 seconds per chapter")
    if not valid:
        return {"status": "insufficient_duration" if duration < 30 else "editorial_selection_required",
                "entries": [], "timing_source": "scene_timestamps"}
    return {"status": "prepared", "entries": selected, "timing_source": "scene_timestamps"}


def _concepts(title: str, script: str, scenes: list[dict], references: list[dict]) -> list[dict]:
    treatments = [
        ("A", "mecanismo", "Show the supplied mechanism or central element as one large visual focal point; "
         "use a small contextual cue and a clear cause/effect arrangement. No invented objects or claims."),
        ("B", "anomalia", "Use an asymmetric composition and a visible contrast already present in the supplied story. "
         "Create curiosity through framing or negative space, never invent a mystery, event or quantitative claim."),
        ("C", "consecuencia_humana", "Use an expressive stickman foreground figure and the story element in the background "
         "to communicate human consequence or scale. Illustrative anonymous character only; do not invent a victim or event."),
    ]
    return [{"id": key, "concept": name, "approved_title": title,
             "scene_id": scene["id"], "narration_anchor": scene.get("narration", ""),
             "visual_context": scene.get("visual_description", ""), "reference_files": references,
             "background_file": f"miniaturas/fondo_{key}.png",
             "output_file": f"miniaturas/miniatura_{key}.png", "text": "",
             "generation_status": "requires_imagegen_and_editorial_review",
             "prompt": (
                 "Create an original horizontal 16:9 YouTube thumbnail illustration. "
                 "Use the supplied visual references for technique, uniform line weight, palette and character consistency, "
                 "without copying a recognizable illustration or composition. Clean bright background, expressive 2D stickmen, "
                 "one dominant element, legible at mobile size. No lettering, symbols resembling text or watermarks. "
                 "Keep focal elements inside a 5 percent safe margin. " + treatment
                 + "\nApproved title (context only, do not draw text): " + title
                 + "\nSupplied scene visual context (use only when it supports this concept): "
                 + str(scene.get("visual_description", ""))
                 + "\nVerbatim story context:\n" + script
             )} for (key, name, treatment), scene in zip(treatments, (scenes[0], scenes[len(scenes) // 2], scenes[-1]))]


def _thumbnail_availability(episode: Path, concepts: list[dict]) -> list[dict]:
    results = []
    for concept in concepts:
        path = _safe_path(episode / concept["output_file"])
        status = "missing"
        if path.exists():
            try:
                with Image.open(path) as image:
                    image.load()
                    status = "prepared_review_required" if image.format == "PNG" and image.size == (1280, 720) else "invalid"
            except (OSError, ValueError):
                status = "invalid"
        results.append({"id": concept["id"], "file": concept["output_file"], "status": status})
    return results


def prepare_packaging(episode: Path, *, title: str, script: str, scenes: list[dict], duration: float,
                      references: list[dict] | None = None, chapters: list[dict] | None = None,
                      sources: list[dict] | None = None, description: str | None = None,
                      thumbnail_text: dict[str,str] | None = None) -> dict:
    """Prepare exact title, extractive description, real-time chapters and three image briefs.

    This does not generate thumbnails. Returned readiness explicitly requires three
    valid PNGs and human visual review; metadata never claims publication readiness.
    """
    episode = _safe_path(episode)
    _line(title, "Approved title")
    if not isinstance(script, str) or not script.strip():
        raise ValueError("A supplied final script is required")
    if not math.isfinite(duration) or duration <= 0 or not scenes:
        raise ValueError("Positive measured duration and timed scenes are required")
    previous_end = 0.0
    ids = set()
    for scene in scenes:
        start, end = float(scene["start"]), float(scene["end"])
        if (not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start
                or start < previous_end - 0.001 or end > duration + 0.001 or scene["id"] in ids):
            raise ValueError("Scenes must have unique IDs and ordered real nonoverlapping timestamps")
        previous_end = end
        ids.add(scene["id"])
    sources = sources or []
    for source in sources:
        _line(source.get("title"), "Source title")
        if not isinstance(source.get("url"), str) or not re.fullmatch(r"https?://[^\s]+", source["url"]):
            raise ValueError("Sources require an explicitly supplied HTTP(S) URL")
    chapter_plan = _chapter_plan(script, scenes, float(duration), chapters)
    chapter_text = "\n".join(f"{_timestamp(entry['start'])} {entry['title']}" for entry in chapter_plan["entries"])
    # Extract complete paragraphs/sentences. A long script is not rewritten into an invented synopsis.
    paragraphs = re.split(r"\n\s*\n", script.strip())
    excerpt = []
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if sum(map(len, excerpt)) + len(paragraph) > 3200:
            if not excerpt:
                first = _first_sentence(paragraph)
                if len(first) > 3200:
                    raise ValueError("Opening sentence exceeds description budget; supply a shorter approved introduction")
                excerpt.append(first)
            break
        excerpt.append(paragraph)
        if len(excerpt) == 3:
            break
    if description is not None and (not isinstance(description,str) or not description.strip()):
        raise ValueError('An explicitly supplied editorial description must be nonempty')
    description_mode = 'editorial_supplied' if description is not None else 'extractive_supplied_script'
    description_parts = [title, description.strip() if description is not None else "\n\n".join(excerpt)]
    if chapter_text:
        description_parts.append(chapter_text)
    if sources:
        description_parts.append("Fuentes proporcionadas:\n" + "\n".join(f"{s['title']}: {s['url']}" for s in sources))
    description = "\n\n".join(description_parts) + "\n"
    if len(description) > 5000:
        raise ValueError("Description including exact chapter titles and sources exceeds 5000 characters")
    concepts = _concepts(title, script, scenes, references or [])
    thumbnail_text=thumbnail_text or {}
    if set(thumbnail_text)-{'A','B','C'}:
        raise ValueError('Thumbnail text keys must be A, B or C')
    for concept in concepts:
        text=thumbnail_text.get(concept['id'],'')
        if not isinstance(text,str) or len(text.split())>3 or '\n' in text or '\r' in text:
            raise ValueError('Thumbnail text must contain zero to three words on one line')
        concept['text']=text.strip()
    metadata = {"schema_version": 1, "pipeline": "youtube_stickman_es", "title": title,
                "title_alternatives": [], "duration_seconds": duration,
                "description_file": "descripcion_youtube.txt", "description_mode": description_mode,
                "chapters_file": "capitulos.txt", "chapters": chapter_plan, "sources": sources,
                "thumbnail_concepts_file": "miniaturas/conceptos.json",
                "thumbnail_files": [item["output_file"] for item in concepts],
                "human_review_required": ["description_editorial_quality", "chapter_meaning", "thumbnail_style_and_mobile_legibility"],
                "publishing_automated": False}
    outputs = {episode / "descripcion_youtube.txt": description.encode("utf-8"),
               episode / "capitulos.txt": (chapter_text + "\n" if chapter_text else "").encode("utf-8"),
               episode / "metadata_youtube.json": _json(metadata),
               episode / "miniaturas/conceptos.json": _json({"concepts": concepts})}
    for concept in concepts:
        outputs[episode / f"miniaturas/prompt_{concept['id']}.txt"] = (concept["prompt"] + "\n").encode("utf-8")
    available = _thumbnail_availability(episode, concepts)
    _write_outputs(outputs)
    return {"concepts_ready": True, "chapters": chapter_plan,
            "thumbnails": available,
            "thumbnails_ready": all(item["status"] == "prepared_review_required" for item in available),
            "status": "human_review_required" if all(item["status"] == "prepared_review_required" for item in available)
                      else "thumbnail_images_required", "metadata": metadata}


def compose_thumbnail(background: Path, output: Path, text: str = "") -> dict:
    """Compose a genuine supplied illustration with optional real-font 0–3 word text."""
    background, output = _safe_path(background), _safe_path(output)
    if output.suffix.lower() != ".png":
        raise ValueError("Thumbnail output must be PNG")
    if not isinstance(text, str) or len(text.split()) > 3 or "\n" in text or "\r" in text:
        raise ValueError("Thumbnail text must contain zero to three words on one line")
    with Image.open(background) as source:
        source.load()
        if source.width < 640 or source.height < 360:
            raise ValueError("Thumbnail illustration is too small (minimum 640x360)")
        # Fit preserves the complete illustration instead of silently cutting off a subject.
        canvas = Image.new("RGB", (1280, 720), "#faf8f2")
        fitted = ImageOps.contain(source.convert("RGB"), (1280, 720), Image.Resampling.LANCZOS)
        canvas.paste(fitted, ((1280 - fitted.width) // 2, (720 - fitted.height) // 2))
    text = text.strip()
    if text:
        draw = ImageDraw.Draw(canvas)
        font = None
        for size in range(116, 31, -2):
            try:
                candidate = ImageFont.truetype("DejaVuSans-Bold.ttf", size)
            except OSError as exc:
                raise RuntimeError("A real DejaVuSans-Bold.ttf font is required for thumbnail text") from exc
            bounds = draw.textbbox((0, 0), text, font=candidate, stroke_width=3)
            if bounds[2] - bounds[0] <= 1120:
                font = candidate
                break
        if font is None:
            raise ValueError("Thumbnail text cannot fit within safe areas")
        x, y = 80 - bounds[0], 80 - bounds[1]
        draw.rounded_rectangle((58, 58, 102 + bounds[2] - bounds[0], 102 + bounds[3] - bounds[1]),
                               radius=18, fill="#fffdf4")
        draw.text((x, y), text, font=font, fill="#18202c", stroke_width=3, stroke_fill="#fffdf4")
    data = io.BytesIO()
    canvas.save(data, format="PNG", optimize=True)
    _write_outputs({output: data.getvalue()})
    return {"file": str(output), "width": 1280, "height": 720, "format": "PNG", "text": text,
            "status": "prepared_review_required", "review": "Check at 320x180 for mobile legibility, composition and style"}
