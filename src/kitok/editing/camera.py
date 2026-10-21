"""Small deterministic camera vocabulary shared by photographs and stock footage."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFilter, ImageOps
from pydantic import BaseModel, ConfigDict, Field, model_validator

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}
CameraPreset = Literal['slow_push_in', 'slow_pull_out', 'pan_left', 'pan_right',
                       'pan_up', 'pan_down', 'diagonal_drift', 'subtle_rotation',
                       'zoom_and_pan', 'focus_push', 'static']


class CameraMotion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    preset: CameraPreset = 'slow_push_in'
    focus_x: float = Field(default=.5, ge=0, le=1, allow_inf_nan=False)
    focus_y: float = Field(default=.5, ge=0, le=1, allow_inf_nan=False)
    start_scale: float | None = Field(default=None, ge=1, le=1.3, allow_inf_nan=False)
    end_scale: float | None = Field(default=None, ge=1, le=1.3, allow_inf_nan=False)
    displacement: float = Field(default=.035, ge=0, le=.15, allow_inf_nan=False)
    easing: Literal['linear', 'smoothstep'] = 'smoothstep'
    rotation: float = Field(default=0, ge=-2, le=2, allow_inf_nan=False)

    @model_validator(mode='before')
    @classmethod
    def named_preset(cls, value):
        return {'preset': value} if isinstance(value, str) else value


def image_plate(source: Path, target: Path, *, width: int, height: int, fit: str,
                highlight_box: tuple[float, float, float, float] | None = None):
    """Preserve the whole supplied document/photo over its own quiet blurred backdrop.

    A little breathing room accommodates the default camera movement without
    trimming the original. Explicit cover remains available for intentional crops.
    This is only source preparation: motion and transitions use the stock engine.
    """
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert('RGB')
        if highlight_box:
            overlay = Image.new('RGBA', image.size)
            bounds = tuple(round(v * (image.width if i % 2 == 0 else image.height))
                           for i, v in enumerate(highlight_box))
            ImageDraw.Draw(overlay).rectangle(bounds, fill=(255, 210, 70, 62),
                                              outline=(255, 200, 45, 220),
                                              width=max(1, round(image.width*.003)))
            image = Image.alpha_composite(image.convert('RGBA'), overlay).convert('RGB')
        if fit == 'cover':
            plate = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
        else:
            plate = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
            plate = plate.filter(ImageFilter.GaussianBlur(max(4, height*.025)))
            plate = Image.blend(plate, Image.new('RGB', plate.size, '#10141a'), .35)
            foreground = ImageOps.contain(image, (round(width*.88), round(height*.88)),
                                          method=Image.Resampling.LANCZOS)
            plate.paste(foreground, ((width-foreground.width)//2, (height-foreground.height)//2))
        plate.save(target)


def camera_filters(camera: CameraMotion | None, *, width: int, height: int,
                   frames: int, fps: int) -> list[str]:
    if camera is None or camera.preset == 'static':
        return []
    # Work at twice delivery resolution to reduce integer zoompan sampling steps.
    progress = f'min(on/{max(1,frames-1)},1)'
    p = progress if camera.easing == 'linear' else f'({progress})*({progress})*(3-2*({progress}))'
    defaults = (1.055, 1.) if camera.preset == 'slow_pull_out' else (1., 1.055)
    if camera.preset in {'pan_left', 'pan_right', 'pan_up', 'pan_down', 'diagonal_drift'}:
        defaults = (1.075, 1.075)
    start = camera.start_scale if camera.start_scale is not None else defaults[0]
    end = camera.end_scale if camera.end_scale is not None else defaults[1]
    rotation = camera.rotation or (.65 if camera.preset == 'subtle_rotation' else 0)
    # Crop away ALL rotated corners, including unusually wide/tall delivery ratios.
    angle = abs(math.radians(rotation))
    guard = max(math.cos(angle)+height/width*math.sin(angle),
                math.cos(angle)+width/height*math.sin(angle)) + (.006 if rotation else 0)
    zoom = f'{guard:.8f}*({start:.8f}+({end-start:.8f})*({p}))'
    displacement = camera.displacement
    # Focus positions denote normalized source coordinates. Clamp the moving window
    # rather than exposing blank edges when an operator focuses near a boundary.
    x = f'iw*{camera.focus_x:.8f}-iw/zoom/2'
    y = f'ih*{camera.focus_y:.8f}-ih/zoom/2'
    if camera.preset in {'pan_left', 'pan_right', 'diagonal_drift', 'zoom_and_pan'}:
        direction = -1 if camera.preset == 'pan_left' else 1
        x += f'+iw*{direction*displacement:.8f}*(({p})-0.5)'
    if camera.preset in {'pan_up', 'pan_down', 'diagonal_drift'}:
        direction = -1 if camera.preset == 'pan_up' else 1
        y += f'+ih*{direction*displacement:.8f}*(({p})-0.5)'
    filters = [f'scale={width*2}:{height*2}']
    if rotation:
        duration = max(1, frames-1)/fps
        filters.append(f"rotate='{math.radians(rotation):.10f}*(2*min(t/{duration:.8f},1)-1)':fillcolor=black")
    safe = (1-1/guard)/2
    filters.append(f"zoompan=z='{zoom}':x='max(iw*{safe:.9f},min(iw-iw/zoom-iw*{safe:.9f},{x}))':y='max(ih*{safe:.9f},min(ih-ih/zoom-ih*{safe:.9f},{y}))':d=1:s={width}x{height}:fps={fps}")
    if camera.preset == 'focus_push':
        filters += ["gblur=sigma=5:enable='lt(t,0.12)'", "gblur=sigma=2:enable='between(t,0.12,0.25)'"]
    return filters
