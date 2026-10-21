"""Small, explicit photograph cues compiled into the ordinary editorial timeline."""
from __future__ import annotations

from pathlib import Path
import re
import warnings
from typing import Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .motion_components import MotionDesign, Effect
from .camera import CameraMotion
from .storyboard import file_hash, phrase_time


class CueModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class VisualAnchor(CueModel):
    phrase: str = Field(min_length=1, max_length=600)
    occurrence: int = Field(default=0, ge=0)


class VisualCue(CueModel):
    asset: str | None = Field(default=None, min_length=1, max_length=1000)
    background: Literal['automatic_stock', 'black'] = 'automatic_stock'
    anchor: VisualAnchor | None = None
    start: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    duration: float | None = Field(default=None, ge=.4, le=30, allow_inf_nan=False)
    camera: CameraMotion | None = None
    image_fit: Literal['auto', 'contain', 'cover'] = 'auto'
    transition: Literal['cut', 'fade', 'dissolve', 'wipe', 'fade_black', 'slide', 'focus', 'match_cut'] | None = None
    effect: Effect | None = None
    text: str = Field(default='', max_length=180)
    motion_data: dict = Field(default_factory=dict)
    description: str = Field(default='Fotografía aportada; procedencia sin verificar', min_length=1, max_length=600)
    source_url: str | None = Field(default=None, max_length=2000)
    credit: str | None = Field(default=None, max_length=300)
    license: str | None = Field(default=None, max_length=500)
    license_url: str | None = Field(default=None, max_length=2000)
    usage: Literal['provided', 'document', 'illustration'] = 'provided'

    @model_validator(mode='after')
    def coherent(self):
        if self.asset is None and self.effect is None:
            raise ValueError('A visual cue needs an asset or an explicit effect')
        if self.asset is not None and self.background == 'black':
            raise ValueError('Photographs use their image; black background is for effect-only cues')
        if (self.anchor is None) == (self.start is None):
            raise ValueError('A visual cue needs exactly one anchor or start')
        if self.anchor and not re.findall(r'\w+', self.anchor.phrase):
            raise ValueError('Visual anchor needs spoken words')
        if self.effect in {'dissolve', 'wipe'}:
            raise ValueError(f'Visual effect {self.effect!r} is a transition; use the transition field')
        if self.effect:
            design = MotionDesign.model_validate({'delay': 0, **self.motion_data, 'effect': self.effect, 'text': self.text})
            if design.delay > 15:
                raise ValueError('Visual effect source delay may not exceed 15 seconds')
            available = (self.duration or 4.) - design.delay
            if available < .4 - 1e-6:
                raise ValueError('Visual effect delay must leave a readable interval')
            if design.hold is not None and design.hold > available + 1e-6:
                raise ValueError('Visual effect hold must fit inside the cue duration after its delay')
        elif self.text or self.motion_data:
            raise ValueError('Visual text/motion_data require an explicit effect')
        return self


class VisualPlan(CueModel):
    visual_cues: list[VisualCue] = Field(default_factory=list, max_length=200)
    fade_in: float = Field(default=.6, ge=0, le=3, allow_inf_nan=False)
    fade_out: float = Field(default=.8, ge=0, le=3, allow_inf_nan=False)


def visual_file(root: Path, visual_root: Path | str | None, asset: str) -> Path:
    root = Path(root).absolute()
    base = Path(visual_root) if visual_root is not None else root
    base = base if base.is_absolute() else root / base
    if '..' in base.parts:
        raise ValueError('Visual root must remain inside the project workspace')
    requested = Path(asset)
    if requested.is_absolute() or '..' in requested.parts:
        raise ValueError('Visual asset must be a relative episode file')
    path = base / requested
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise ValueError('Visual root must remain inside the project workspace') from None
    for candidate in (root, *(root / Path(*relative.parts[:i]) for i in range(1, len(relative.parts) + 1))):
        if candidate.is_symlink():
            raise ValueError('Visual assets do not follow symlinks')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Visual root must remain inside the project workspace')
    if not path.is_file() or path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
        raise ValueError(f'Visual asset must be an existing JPG/PNG/WebP: {requested.name}')
    if path.stat().st_size > 40 * 1024 * 1024:
        raise ValueError('Visual image exceeds 40 MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.width < 32 or image.height < 32 or image.width * image.height > 40_000_000:
                    raise ValueError('Visual image dimensions must be at least 32px and at most 40 megapixels')
                image.verify()
            with Image.open(path) as image:
                image.load()
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError(f'Visual image cannot be decoded safely: {requested.name}') from exc
    return path


def script_words(script: str):
    from .manifest import clean_script
    return re.findall(r'\w+', clean_script(script).casefold())


def anchor_word_index(script: str, anchor: VisualAnchor) -> int:
    words, wanted = script_words(script), script_words(anchor.phrase)
    matches = [i for i in range(len(words)-len(wanted)+1) if words[i:i+len(wanted)] == wanted]
    if anchor.occurrence >= len(matches):
        raise ValueError(f'Visual anchor not found in the script: {anchor.phrase}')
    return matches[anchor.occurrence]


def validate_visual_plan(plan, script: str, root: Path, visual_root=None, *, validate_assets=True) -> VisualPlan:
    """Local read-only validation, safe to perform before any paid provider call."""
    plan = VisualPlan.model_validate(plan or {})
    for cue in plan.visual_cues:
        if cue.asset and validate_assets:
            visual_file(root, visual_root, cue.asset)
        if cue.anchor:
            anchor_word_index(script, cue.anchor)
    anchors = [anchor_word_index(script, cue.anchor) for cue in plan.visual_cues if cue.anchor]
    if len(set(anchors)) != len(anchors):
        raise ValueError('Visual cues overlap at the same spoken anchor')
    starts = sorted(cue.start for cue in plan.visual_cues if cue.start is not None)
    if any(right-left < .4-1e-6 for left,right in zip(starts, starts[1:])):
        raise ValueError('Visual cues need at least 0.4s between explicit starts')
    explicit = sorted((cue.start, cue.start + cue.duration) for cue in plan.visual_cues
                      if cue.start is not None and cue.duration is not None)
    if any(left[1] > right[0] for left,right in zip(explicit, explicit[1:])):
        raise ValueError('Visual cues overlap; adjust start or duration')
    return plan


def visual_sources(plan, root, visual_root=None):
    sources = []
    for cue in plan.visual_cues:
        if not cue.asset:
            continue
        path = visual_file(root, visual_root, cue.asset)
        sources.append({'path': str(path.relative_to(root)), 'sha256': file_hash(path),
                        'description': cue.description, 'source_url': cue.source_url,
                        'credit': cue.credit, 'usage': cue.usage,
                        'license': cue.license, 'license_url': cue.license_url,
                        'provenance': 'provided; verify source, identity and license before publication'})
    return sources


def cue_start(cue, script, duration, *, alignment=None):
    if cue.start is not None:
        return cue.start, 'explicit-seconds'
    if alignment:
        return phrase_time(alignment['words'], cue.anchor.phrase, occurrence=cue.anchor.occurrence)[0], 'provider-phrase-anchor'
    return duration * anchor_word_index(script, cue.anchor) / max(1, len(script_words(script))), 'estimated-script-words'
