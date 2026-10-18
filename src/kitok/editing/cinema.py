"""Deterministic cinematic illustrations: moving objects, not full-screen text cards.

All poker hands are explicitly illustrative, never historical hand records.
The renderer streams frames; no frame sequence is accumulated in RAM or on disk.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import math
import os
import signal
from random import Random
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from ..media.ffmpeg import encoder_arguments
from ..media.ffprobe import probe_media
from ..state import write_json_atomic
from .storyboard import file_hash

VERSION = 1
W, H = 1920, 1080
CREAM = '#f4eee2'
AMBER = '#e6ae60'
RED = '#de685c'
TEAL = '#81c2b4'


class CinemaData(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['opponent', 'aggression', 'loss', 'records', 'question', 'private', 'exposed', 'refunds', 'profile'] = 'opponent'
    engine: Literal['pillow', 'three'] = 'three'
    shot: Literal['wide', 'opponent', 'cards', 'chips', 'overhead'] = 'wide'
    label: str = Field(default='', max_length=70)
    amount: str = Field(default='', max_length=30)
    detail: str = Field(default='', max_length=100)
    credit: str = Field(default='', max_length=260)
    reveal_at: float = Field(default=1.5, ge=0, le=30, allow_inf_nan=False)
    focus_x: float = Field(default=.5, ge=0, le=1, allow_inf_nan=False)
    focus_y: float = Field(default=.45, ge=0, le=1, allow_inf_nan=False)


@lru_cache(maxsize=30)
def font(size, bold=False):
    suffix = '-Bold' if bold else ''
    return ImageFont.truetype(f'/usr/share/fonts/truetype/dejavu/DejaVuSans{suffix}.ttf', size)


def ease(value):
    x = max(0., min(1., value))
    return x*x*(3-2*x)


def text(draw, point, value, size=32, fill=CREAM, bold=False, anchor=None):
    draw.text(point, value, font=font(size, bold), fill=fill, anchor=anchor,
              stroke_width=1 if size >= 40 else 0, stroke_fill='#10171a')


@lru_cache(maxsize=3)
def room():
    radial = Image.radial_gradient('L').resize((W, H))
    image = ImageOps.colorize(radial, '#263b3b', '#080d14').convert('RGB')
    noise = Image.frombytes('L', (W, H), Random(91).randbytes(W * H)).convert('RGB')
    image = Image.blend(image, noise, .025)
    d = ImageDraw.Draw(image)
    # A physical oval, rim, shadows and felt establish space for every event.
    d.ellipse((110, 240, 1810, 1130), fill='#080c10')
    d.ellipse((96, 200, 1824, 1080), fill='#5b3b26', outline='#b18a56', width=7)
    d.ellipse((124, 226, 1796, 1050), fill='#18201f', outline='#090e10', width=24)
    d.ellipse((153, 253, 1767, 1020), fill='#163f3d', outline='#2e6460', width=4)
    d.arc((225, 310, 1695, 950), 190, 352, fill='#89a298', width=3)
    return image


@lru_cache(maxsize=24)
def card(rank='A', suit='♠', back=False):
    tile = Image.new('RGBA', (160, 222))
    d = ImageDraw.Draw(tile)
    d.rounded_rectangle((6, 8, 154, 216), 13, fill='#03090c88')
    d.rounded_rectangle((0, 0, 148, 208), 12, fill='#e9e2d4', outline='#c5beaf', width=2)
    if back:
        d.rounded_rectangle((8, 8, 140, 200), 7, fill='#19354f', outline='#afbdc1', width=2)
        for x in range(-180, 300, 16):
            d.line((max(10, x), max(10, 10-x), min(138, x+188), min(198, 198+x)), fill='#3b6176', width=2)
        d.ellipse((44, 75, 104, 135), outline='#a3b2b7', width=3)
    else:
        color = '#b24739' if suit in ('♥', '♦') else '#1b2934'
        text(d, (15, 9), rank, 42, color, True)
        text(d, (15, 51), suit, 33, color)
        text(d, (74, 113), suit, 85, color, anchor='mm')
        text(d, (128, 190), rank, 30, color, True, 'rs')
    return tile


def paste_card(image, at, rank='A', suit='♠', back=False, angle=0, flip=1):
    tile = card(rank, suit, back)
    width = max(2, round(tile.width * max(.015, abs(flip))))
    if width != tile.width:
        tile = tile.resize((width, tile.height), Image.Resampling.BICUBIC)
    if angle:
        tile = tile.rotate(angle, Image.Resampling.BICUBIC, expand=True)
    x, y = at
    image.paste(tile, (round(x-tile.width/2), round(y-tile.height/2)), tile)


def chips(d, x, y, count=6, color='#a54e41', scale=1.):
    for i in range(count):
        cy = y - i * 8 * scale
        box = (x-44*scale, cy-15*scale, x+44*scale, cy+15*scale)
        d.ellipse(box, fill=color, outline='#e3d7bd', width=max(1, round(3*scale)))
        d.arc((box[0]+10, box[1]+4, box[2]-10, box[3]-4), 0, 360, fill='#dccbb8', width=2)


def table_frame(data: CinemaData, t: float, duration: float):
    frame = room().copy()
    d = ImageDraw.Draw(frame)
    enter = ease(t/.8)
    # Two distinct players; seats keep their spatial identity across shots.
    d.ellipse((790, 115, 1130, 260), fill='#0b131c', outline='#5d7b7e', width=2)
    text(d, (960, 164), 'NioNio', 44, AMBER, True, 'mm')
    text(d, (960, 210), 'OPPONENT ACCOUNT', 18, '#9dafb6', anchor='mm')
    text(d, (505, 939), 'PAREDES', 28, CREAM, True, 'mm')
    text(d, (1415, 939), 'OTHER PLAYER', 28, CREAM, True, 'mm')
    if data.mode == 'opponent':
        d.ellipse((777, 102, 1143, 276), outline=AMBER, width=3)
    # Illustrated hands, never claimed to be a recorded game.
    for x, rank, suit in ((445, 'A', '♠'), (585, 'K', '♥')):
        paste_card(frame, (x, 792+70*(1-enter)), rank, suit, angle=-8 if x<500 else 7)
    reveal = ease((t-data.reveal_at)/.85) if data.mode=='exposed' else 0
    for x, rank, suit in ((1350, 'Q', '♦'), (1490, '9', '♠')):
        back = reveal < .5
        flip = abs(math.cos(reveal*math.pi)) if data.mode=='exposed' else 1
        paste_card(frame, (x, 792), rank, suit, back=back, angle=-6 if x<1400 else 8, flip=flip)
    for x in (900, 1050):
        paste_card(frame, (x, 364), back=True, angle=6 if x<950 else -5)
    d = ImageDraw.Draw(frame)
    for x, n, col in ((580, 606, '#b14f45'), (1250, 591, '#bbb09b'), (915, 519, '#4d7b9c')):
        shift = ease((t-.5)/1.6) if data.mode=='aggression' else 0
        chips(d, x+(960-x)*shift*.45, n+shift*30, count=7, color=col)
        chips(d, x+89+(960-x)*shift*.30, n+10, count=4, color='#7d8f7d', scale=.8)
    if data.mode in ('private','question','exposed'):
        # Access changes only for the top (privileged) account.
        if reveal:
            glow = Image.new('RGBA', frame.size)
            gd = ImageDraw.Draw(glow)
            gd.line([(1030, 430), (1240, 525), (1420, 663)], fill=(245,173,84,round(180*reveal)), width=12)
            glow = glow.filter(ImageFilter.GaussianBlur(12))
            frame = Image.alpha_composite(frame.convert('RGBA'),glow).convert('RGB')
            d=ImageDraw.Draw(frame)
            d.line([(1030,430),(1240,525),(1420,663)], fill=AMBER, width=3)
            d.rounded_rectangle((1238, 567, 1620, 619), 8, fill='#573d24')
            text(d,(1429,593),'VISIBLE TO ONE ACCOUNT',20,CREAM,True,'mm')
        elif data.mode!='question':
            d.rounded_rectangle((1236, 570, 1612, 624),8,fill='#18272f',outline='#70858c',width=2)
            text(d,(1424,597),'PRIVATE INFORMATION',23,'#b2c0c3',False,'mm')
    if data.amount:
        # Amount remains attached to chips/action, not isolated on a flat slide.
        amount = data.amount
        alpha = ease((t-.35)/.5)
        d.rounded_rectangle((716, 603, 1204, 715), 14, fill='#101b20', outline='#3c5254', width=2)
        text(d,(960,657),amount,64,RED if data.mode=='loss' else AMBER,True,'mm')
        if data.detail:
            text(d,(960,749),data.detail,24,'#c6d0ce',False,'mm')
    # Gentle camera movement affects the table, not external labels.
    progress = t/max(duration,.1)
    zoom = 1.04 + .045*progress
    fw, fh = round(W/zoom), round(H/zoom)
    cx = 960 + (90*progress if data.mode in ('private','exposed') else -45*progress)
    cy = 565 - 15*progress
    box=(int(cx-fw/2),int(cy-fh/2),int(cx+fw/2),int(cy+fh/2))
    frame=frame.crop(box).resize((W,H),Image.Resampling.BICUBIC)
    d=ImageDraw.Draw(frame)
    text(d,(90,65),'ONLINE POKER',24,'#b8c7c6',True)
    text(d,(90,102),'RECONSTRUCTION',17,'#819797')
    if data.label:text(d,(W-90,70),data.label,29,AMBER,True,'ra')
    text(d,(W//2,H-36),'ILLUSTRATION · NOT AN ACTUAL HAND OR ORIGINAL SOFTWARE',19,'#97abaa',anchor='ms')
    return frame


def records_frame(data: CinemaData, t: float, duration: float):
    """Two reports converge on one alias; no invented per-hand history."""
    image = Image.new('RGB',(W,H),'#0c141e')
    d=ImageDraw.Draw(image)
    for x in range(80,W,70):d.line((x,180,x,H-170),fill='#182532',width=1)
    for y in range(180,H-170,70):d.line((80,y,W-80,y),fill='#182532',width=1)
    # Data pulses travel to the actual common account, rather than fabricated rows.
    for left,origin,label in ((True,230,'PAREDES'),(False,1690,'ANOTHER PLAYER')):
        d.ellipse((origin-74,465,origin+74,613),fill='#1c2e3c',outline='#527683',width=3)
        text(d,(origin,540),'01' if left else '02',48,CREAM,True,'mm')
        text(d,(origin,659),label,25,CREAM,True,'mm')
        d.line((origin+(75 if left else -75),540,960,540),fill='#345560',width=3)
        for pulse in range(3):
            q=(t*.3+pulse/3)%1
            x=origin+(960-origin)*q
            d.ellipse((x-7,533,x+7,547),fill=AMBER)
    d.ellipse((807,387,1113,693),fill='#17363d',outline=AMBER,width=4)
    text(d,(960,512),'NioNio',52,CREAM,True,'mm')
    text(d,(960,576),'SAME ACCOUNT',22,AMBER,True,'mm')
    text(d,(100,95),'COMPARE THE ACCOUNTS',29,'#c8d4d8',True)
    if data.amount:
        p=ease((t-data.reveal_at)/1.2)
        length=int(1120*p)
        d.rounded_rectangle((400,779,1520,814),9,fill='#20313f')
        if length>12:d.rounded_rectangle((400,779,400+length,814),9,fill=AMBER)
        text(d,(960,884),data.amount,66,CREAM,True,'mm')
        text(d,(960,950),data.detail,27,'#b9c9d1',anchor='mm')
    else:
        text(d,(960,856),'Two reports. One opponent.',42,CREAM,True,'mm')
    text(d,(W//2,H-35),'REPORTED RELATIONSHIPS · NOT A REPRODUCTION OF HAND HISTORIES',18,'#7f98a5',anchor='ms')
    return image


@lru_cache(maxsize=1)
def photo_shade():
    shade = Image.new('RGBA', (W,H))
    sd = ImageDraw.Draw(shade)
    for y in range(H):
        alpha = round(210*max(0, (y-H*.45)/(H*.55)))
        if alpha:
            sd.line((0,y,W,y), fill=(5,10,16,alpha))
    return shade


def photo_frame(data: CinemaData, t: float, duration: float, original: Image.Image):
    # Camera moves within the real image; no generated person replaces the subject.
    source=original
    zoom=1. + .10*ease(t/max(duration,.1))
    factor=max(W/source.width,H/source.height)*zoom
    cw,ch=W/factor,H/factor
    cx=min(source.width-cw/2,max(cw/2,source.width*data.focus_x))
    cy=min(source.height-ch/2,max(ch/2,source.height*data.focus_y))
    image=source.crop((int(cx-cw/2),int(cy-ch/2),int(cx+cw/2),int(cy+ch/2))).resize((W,H),Image.Resampling.LANCZOS).convert('RGBA')
    image=Image.alpha_composite(image,photo_shade())
    d=ImageDraw.Draw(image)
    if data.detail:text(d,(100,810),data.detail,25,AMBER,True)
    if data.label:text(d,(100,875),data.label,65,CREAM,True)
    if data.credit:text(d,(100,1027),data.credit,18,'#dddace')
    return image.convert('RGB')


def render_cinema(data: CinemaData, kind: str, *, duration: float, width: int, height: int,
                  fps: int, output: Path, settings, encoder, photo: Path|None=None):
    if kind not in {'table','records','photo'} or not .4-1e-6<=duration<=30:
        raise ValueError('Unsupported cinematic scene or duration (maximum30s)')
    if width<320 or height<180 or width%2 or height%2 or not 24<=fps<=60:
        raise ValueError('Invalid cinematic output geometry/FPS')
    if kind=='photo' and photo is None:raise ValueError('Photo composition needs a verified local image')
    project=Path(__file__).resolve().parents[3]
    runtime={}
    if kind=='table' and data.engine=='three':
        runtime={name:file_hash(project/name) for name in
                 ('scripts/cinema3d.mjs','src/kitok/editing/stage3d.js','frontend/package-lock.json')}
    key=hashlib.sha256(json.dumps(dict(version=VERSION,kind=kind,data=data.model_dump(),
        duration=duration,width=width,height=height,fps=fps,encoder=encoder.__dict__,
        photo=file_hash(photo) if photo else None,runtime=runtime),sort_keys=True).encode()).hexdigest()
    receipt=output.with_suffix('.cinema.json')
    if output.is_file() and receipt.is_file():
        prior=json.loads(receipt.read_text())
        if prior.get('key')==key and prior.get('sha256')==file_hash(output):return output
    image=None
    if photo:
        with Image.open(photo) as source:
            image=ImageOps.exif_transpose(source).convert('RGB')
    output.parent.mkdir(parents=True,exist_ok=True)
    pending=output.with_name('.'+output.stem+'.'+uuid4().hex+'.part.mp4')
    if kind=='table' and data.engine=='three':
        spec=output.with_suffix('.stage3d.json')
        write_json_atomic(spec,data.model_dump()|dict(width=width,height=height,fps=fps,duration=duration))
        env=dict(os.environ)
        if (project/'.tools/browsers').is_dir():
            env.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(project/'.tools/browsers'))
        command=['node',str(project/'scripts/cinema3d.mjs'),'--spec',str(spec),'--output',str(pending),
                 '--ffmpeg',settings.ffmpeg_binary]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, env=env, start_new_session=True)
        child_pending = pending.with_name(pending.stem + '.stage3d.part.mp4')
        try:
            stdout, stderr = process.communicate(timeout=900)
            if process.returncode:
                raise RuntimeError('3D render failed: ' + stderr[-1400:])
            info=probe_media(pending,settings.ffprobe_binary)
            if ((info.width, info.height) != (width, height)
                    or abs(info.duration-duration)>1/fps+.02):
                raise RuntimeError('3D scene duration/geometry mismatch')
            pending.replace(output)
            write_json_atomic(receipt,dict(key=key,sha256=file_hash(output),renderer=json.loads(stdout)))
        except BaseException as error:
            # Playwright starts Chromium in its own session. Give Node's
            # Playwright SIGTERM handler time to close it before escalation.
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.communicate(timeout=30)
                except subprocess.TimeoutExpired:
                    # A second TERM asks Playwright to force-kill its own
                    # detached browser group when graceful closure is stuck.
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        process.communicate(timeout=10)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait(timeout=10)
            pending.unlink(missing_ok=True)
            child_pending.unlink(missing_ok=True)
            if isinstance(error, subprocess.TimeoutExpired):
                raise RuntimeError('3D render timed out; inspect the local render before retrying') from None
            raise
        return output
    command=[settings.ffmpeg_binary,'-nostdin','-v','error','-y','-f','rawvideo','-pixel_format','rgb24',
        '-video_size',f'{width}x{height}','-framerate',str(fps),'-i','pipe:0','-an',
        *encoder_arguments(encoder),'-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(pending)]
    # A file-backed stderr avoids deadlock if FFmpeg fails while the pipe is busy.
    with tempfile.TemporaryFile() as error:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=error)
        try:
            for index in range(round(duration*fps)):
                t=index/fps
                frame=(photo_frame(data,t,duration,image) if kind=='photo' else
                       records_frame(data,t,duration) if kind=='records' else table_frame(data,t,duration))
                if frame.size!=(width,height):frame=frame.resize((width,height),Image.Resampling.LANCZOS)
                process.stdin.write(frame.tobytes())
            process.stdin.close()
            if process.wait(timeout=120):raise RuntimeError('Cinematic encoder failed')
            info=probe_media(pending,settings.ffprobe_binary)
            if (info.width,info.height)!=(width,height) or abs(info.duration-duration)>1/fps+.02:
                raise RuntimeError('Cinematic scene duration/geometry mismatch')
            pending.replace(output)
            write_json_atomic(receipt,dict(key=key,sha256=file_hash(output)))
        except BaseException:
            process.kill();process.wait(timeout=10)
            error.seek(0)
            message=error.read().decode(errors='replace')[-1500:]
            pending.unlink(missing_ok=True)
            if message:raise RuntimeError('Cinematic render failed: '+message) from None
            raise
    return output
