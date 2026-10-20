"""Incremental editorial scenes over the existing FFmpeg renderer; no provider calls."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import uuid4

from ..longform.models import TimelineClip, TimelineSlot
from ..media.ffmpeg import FFmpegNativeEngine, RenderSpec, choose_encoder, encoder_arguments
from ..media.ffprobe import probe_media, stream_durations
from ..state import write_json_atomic
from .ass import filter_path
from .graphics import render_graphic
from .storyboard import EditorialPlan, file_hash, project_file

RENDER_VERSION = 2


def _run(command: list[str], timeout: int = 900):
    try:
        return subprocess.run(command, capture_output=True, text=True, check=True, timeout=timeout)
    except subprocess.CalledProcessError as error:
        # Commands contain local paths and user text, never provider credentials.
        raise RuntimeError("Editorial FFmpeg failed: " + error.stderr[-1800:]) from None


@contextmanager
def _plan_lock(workspace: Path):
    with (workspace / "render.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("This editorial render is already running") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _ass_text(text: str) -> str:
    return text.replace("\\", " ").replace("{", "(").replace("}", ")").replace("\n", " ")


def _caption(scene, path, plan):
    scale = plan.height / 1080
    x, y = round(plan.width * .07), round(plan.height * .72)
    headline_size = round((100 if scene.headline_style == "impact" else 57)*scale)
    end = scene.end - scene.start
    # Captions are intentional plan fields, not inferred names or numbers.
    def stamp(t):
        cs = round(t * 100)
        return f"{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}"
    fg = "&H00FFFFFF"
    events = []
    if scene.headline:
        # Short, semantic titles; keep them below 70% width at mobile scale.
        lines = []
        current = ""
        for word in scene.headline.split():
            if len(current + " " + word) > 30 and current:
                lines.append(current)
                current = word
            else:
                current = (current + " " + word).strip()
        if current:
            lines.append(current)
        if any(len(word)>30 for word in scene.headline.split()) or len(lines)>3:
            raise ValueError("Caption is too long for its safe area")
        y = min(y, round(plan.height*.92 - (len(lines)*headline_size*1.22 + 60*scale)))
        text = r"\N".join(_ass_text(line) for line in lines)
        events.append(f"Dialogue: 1,0:00:00.15,{stamp(end-.15)},Default,,0,0,0,,"
                      f"{{\\an7\\pos({x},{y+round(49*scale)})\\fs{headline_size}\\1c{fg}\\fad(160,160)}}{text}")
    if scene.kicker:
        events.append(f"Dialogue: 0,0:00:00.15,{stamp(end-.15)},Default,,0,0,0,,"
                      f"{{\\an7\\pos({x},{y})\\fs{round(29*scale)}\\1c&H0068EAB7\\fad(160,160)}}{_ass_text(scene.kicker)}")
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {plan.width}
PlayResY: {plan.height}
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,DejaVu Sans,48,&H00FFFFFF,&H00FFFFFF,&H00201812,&H90000000,-1,0,0,0,100,100,0,0,1,2,1,7,50,50,50,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def render_editorial_plan(plan: EditorialPlan, *, root: Path, output: Path, settings,
                          encoder_name: str = "auto", on_stage=None) -> dict:
    """Compile approved scene decisions and deliver without synthesizing or downloading."""
    started = time.monotonic()
    root, output = root.resolve(), output.resolve()
    if not output.is_relative_to(root):
        raise ValueError("Editorial output must remain inside the project workspace")
    audio = project_file(root, plan.audio_source)
    audio_info = probe_media(audio, settings.ffprobe_binary)
    _, source_audio_duration = stream_durations(audio, settings.ffprobe_binary)
    if source_audio_duration is None and audio_info.video_codec is None:
        source_audio_duration = audio_info.duration
    if (not audio_info.audio_codec or source_audio_duration is None
            or source_audio_duration + .05 < plan.audio_offset + plan.duration):
        raise ValueError("Existing audio does not cover this edit plan")
    # Validate every local input before creating outputs.
    assets = {key: project_file(root, asset.path) for key, asset in plan.assets.items()}
    inputs = {audio: file_hash(audio)}
    if any(scene.motion_design for scene in plan.scenes):
        for code in (Path(__file__),Path(__file__).with_name('motion_components.py')):
            inputs[code]=file_hash(code)
    if plan.alignment.get('audio_sha256', inputs[audio]) != inputs[audio]:
        raise ValueError('Approved audio changed after preparing the plan')
    for key, source in assets.items():
        digest = file_hash(source)
        if plan.assets[key].sha256 is not None and plan.assets[key].sha256 != digest:
            raise ValueError(f'Approved resource changed after preparing the plan: {key}')
        inputs[source] = digest
    if output in assets.values() or output == audio:
        raise ValueError("Editorial output cannot replace an input")
    manifest = output.with_suffix('.editorial.json')
    if output.exists() or manifest.exists() or manifest.is_symlink():
        raise ValueError("Editorial output or receipt exists; choose a new output to preserve the previous cut")
    output.parent.mkdir(parents=True, exist_ok=True)
    workspace = output.parent / ".editorial-work" / plan.episode_id
    workspace.mkdir(parents=True, exist_ok=True)
    encoder = choose_encoder(settings.ffmpeg_binary, requested=encoder_name, nvenc_preset="p5")
    spec = RenderSpec(width=plan.width, height=plan.height, fps=plan.fps,
                      fade_in=0, fade_out=0, chunk_size=4)
    rendered, reused, clips = [], [], []
    with _plan_lock(workspace):
        for index, scene in enumerate(plan.scenes):
            if on_stage:
                on_stage(f"Scene {index+1}/{len(plan.scenes)}: {scene.intention}")
            scene_start = time.monotonic()
            duration = scene.end - scene.start
            image = bool(scene.graphic)
            if scene.composition:
                from .cinema import CinemaData, render_cinema
                source = workspace / f'{scene.id}.composition.mp4'
                render_cinema(CinemaData.model_validate(scene.composition_data), scene.composition,
                              duration=duration, width=plan.width, height=plan.height,
                              fps=plan.fps, output=source, settings=settings, encoder=encoder,
                              photo=assets[scene.asset] if scene.asset else None)
                source_identity = file_hash(source)
            elif scene.graphic == 'motion':
                from .motion_components import background_plate
                source = workspace / f'{scene.id}.png'
                background_plate(scene.motion_design, source, plan.width, plan.height)
                source_identity = file_hash(source)
            elif image:
                source = workspace / f"{scene.id}.png"
                render_graphic(scene.graphic, scene.graphic_data, source,
                               width=plan.width, height=plan.height,
                               style={"palette": scene.palette or plan.palette, "accent": plan.accent})
                source_identity = file_hash(source)
            else:
                source = assets[scene.asset]
                image = source.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                info = None if image else probe_media(source, settings.ffprobe_binary)
                if not image and (not info.video_codec or info.duration + .05 < scene.source_start + duration):
                    raise ValueError(f"Stock does not cover scene {scene.id}; choose another asset or shorten the scene")
                source_identity = file_hash(source)
            caption = workspace / f"{scene.id}.ass"
            _caption(scene, caption, plan)
            filters = [
                f"scale={plan.width}:{plan.height}:force_original_aspect_ratio=increase:force_divisible_by=2",
                f"crop={plan.width}:{plan.height}", f"fps={plan.fps}", "setsar=1", "format=yuv420p",
            ]
            frames = max(1, round(duration * plan.fps))
            if scene.motion == "push":
                filters.append(f"zoompan=z='1+0.035*min(on/{frames},1)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={plan.width}x{plan.height}:fps={plan.fps}")
            elif scene.motion == "pan":
                sw, sh = round(plan.width*1.035/2)*2, round(plan.height*1.035/2)*2
                filters.extend([f"scale={sw}:{sh}",f"crop={plan.width}:{plan.height}:x='(iw-ow)*min(t/{duration:.6f},1)':y='(ih-oh)/2'"])
            if scene.motion_design:
                from .motion_components import write_motion_ass, treatment_filters
                motion_ass = workspace / f'{scene.id}.motion.ass'
                has_text = write_motion_ass(scene.motion_design, motion_ass, duration=duration,
                                            width=plan.width, height=plan.height, over_stock=bool(scene.asset))
                filters.extend(treatment_filters(scene.motion_design, duration=duration,
                                                 width=plan.width, height=plan.height, fps=plan.fps))
                if has_text:
                    filters.append(f"ass='{filter_path(motion_ass)}'")
            if scene.headline or scene.kicker:
                filters.append(f"ass='{filter_path(caption)}'")
            if scene.transition == "fade":
                filters.append("fade=t=in:st=0:d=0.14")
            target = workspace / f"{scene.id}.mp4"
            receipt = workspace / f"{scene.id}.json"
            scene_key = scene.model_dump(exclude={"palette", "headline_style"})
            key_data = {"version":RENDER_VERSION, "scene":scene_key, "source_hash":source_identity,
                        "filters":filters,"encoder":encoder.__dict__,"caption":caption.read_text(),
                        "motion_ass":motion_ass.read_text() if scene.motion_design else None,
                        "motion_code":inputs[Path(__file__).with_name('motion_components.py')] if scene.motion_design else None,
                        "previous":file_hash(clips[-1].source) if clips and scene.transition in {'dissolve','wipe'} else None}
            import hashlib
            fingerprint = hashlib.sha256(json.dumps(key_data,sort_keys=True).encode()).hexdigest()
            hit = False
            if target.exists() and receipt.exists():
                prior = json.loads(receipt.read_text())
                if prior.get("fingerprint") == fingerprint:
                    info = probe_media(target,settings.ffprobe_binary)
                    hit = (abs(info.duration-duration) <= 1/plan.fps+.02
                           and (info.width,info.height)==(plan.width,plan.height)
                           and prior.get("media_sha256")==file_hash(target))
            if not hit:
                temp = target.with_name(f".{target.stem}.part.mp4")
                command = [settings.ffmpeg_binary,"-nostdin","-v","error","-y","-threads","2"]
                if image:
                    command += ["-loop","1","-framerate",str(plan.fps)]
                else:
                    command += ["-ss",f"{scene.source_start:.6f}"]
                command += ["-i",str(source),"-an","-t",f"{duration:.6f}","-vf",",".join(filters),
                            "-filter_threads","1",*encoder_arguments(encoder),"-pix_fmt","yuv420p","-threads","2",str(temp)]
                _run(command)
                if clips and scene.transition in {'dissolve', 'wipe'}:
                    # Borrow only the preceding final frame. Incoming frames keep their
                    # timestamps, so a transition never shifts narration or shot boundaries.
                    prior = clips[-1]
                    still = workspace / f'{scene.id}.previous.png'
                    _run([settings.ffmpeg_binary,'-nostdin','-v','error','-y',
                          '-ss',str(max(0, prior.slot.duration-1/plan.fps)), '-i',str(prior.source),
                          '-frames:v','1',str(still)])
                    transitioned = temp.with_name(temp.stem+'.transition.mp4')
                    blend = min(.28, duration/3)
                    mode = 'fade' if scene.transition == 'dissolve' else 'wipeleft'
                    _run([settings.ffmpeg_binary,'-nostdin','-v','error','-y',
                          '-loop','1','-framerate',str(plan.fps),'-t',f'{blend:.6f}','-i',str(still),'-i',str(temp),
                          '-filter_complex_threads','1','-filter_complex',
                          f'[0:v]format=yuv420p,settb=AVTB[a];[1:v]format=yuv420p,settb=AVTB[b];[a][b]xfade=transition={mode}:duration={blend:.6f}:offset=0[v]',
                          '-map','[v]','-an','-t',f'{duration:.6f}',*encoder_arguments(encoder),'-threads','2',str(transitioned)])
                    transitioned.replace(temp)
                info = probe_media(temp,settings.ffprobe_binary)
                if abs(info.duration-duration) > 1/plan.fps+.05:
                    raise RuntimeError(f"Scene duration mismatch: {scene.id}")
                temp.replace(target)
                write_json_atomic(receipt,{"fingerprint":fingerprint,"media_sha256":file_hash(target)})
            (reused if hit else rendered).append(scene.id)
            clips.append(TimelineClip(TimelineSlot(index,"editorial",scene.start,duration),index,target,0))
            if on_stage:
                on_stage(f"{scene.id}: {'cached' if hit else 'rendered'} in {time.monotonic()-scene_start:.2f}s")
        # Existing engine owns normalization, concat, encoder fallback and audio mixing.
        engine = FFmpegNativeEngine(ffmpeg=settings.ffmpeg_binary,ffprobe=settings.ffprobe_binary,
                                   encoder=encoder,spec=spec)
        assembled = workspace / "assembled.mp4"
        if plan.audio_is_final_mix:
            # All scene files already share geometry/codec/timebase. Joining them
            # by stream copy avoids a redundant encode and never normalizes an
            # approved mix (including intentionally silent gallery audio).
            concat_file = workspace / 'scenes.ffconcat'
            lines = ['ffconcat version 1.0']
            for clip in clips:
                escaped = str(clip.source.resolve()).replace("'", "'\\''")
                lines.append(f"file '{escaped}'")
            concat_file.write_text('\n'.join(lines)+'\n',encoding='utf-8')
            _run([settings.ffmpeg_binary,'-nostdin','-v','error','-y','-f','concat','-safe','0',
                  '-i',str(concat_file),'-map','0:v:0','-c:v','copy','-an',str(assembled)])
        else:
            engine.render(clips,audio,plan.duration,assembled,workspace/"assembly",
                          music=None,music_volume=0,loudness_target=-16,lra_target=20,true_peak_target=-1.5)
        pending = output.with_name(f".{output.stem}.{uuid4().hex}.part.mp4")
        if plan.audio_is_final_mix:
            # Exactly the approved mix. Rendering visuals must not alter its gain/music.
            seek = ["-ss",str(plan.audio_offset)] if plan.audio_offset else []
            _run([settings.ffmpeg_binary,"-nostdin","-v","error","-y","-i",str(assembled),
                  *seek,"-i",str(audio),"-map","0:v:0","-map","1:a:0",
                  "-t",str(plan.duration),"-c","copy","-movflags","+faststart",str(pending)])
        else:
            if plan.audio_offset:
                raise ValueError("An unmixed narration plan currently requires audio_offset=0")
            assembled.replace(pending)
        final = probe_media(pending,settings.ffprobe_binary)
        video_duration, audio_duration = stream_durations(pending,settings.ffprobe_binary)
        if (abs(final.duration-plan.duration)>.15 or not final.audio_codec
                or video_duration is None or abs(video_duration-plan.duration)>1/plan.fps+.02
                or audio_duration is None or audio_duration<plan.duration-.05):
            raise RuntimeError("Editorial final validation failed")
        result = {"version":1,"episode_id":plan.episode_id,"channel_id":plan.channel_id,
                  "output":str(output.relative_to(root)),"duration":final.duration,
                  "audio_stream_duration":audio_duration,"video_stream_duration":video_duration,
                  "encoder":encoder.codec,"elapsed_seconds":time.monotonic()-started,
                  "rendered_scenes":rendered,"reused_scenes":reused,"audio_source":plan.audio_source,
                  "audio_source_sha256":file_hash(audio),"audio_is_final_mix":plan.audio_is_final_mix,
                  "alignment":plan.alignment,"provider_requests":0,"scenes":[s.model_dump() for s in plan.scenes],
                  "assets":{key:asset.model_dump() for key,asset in plan.assets.items()}}
        if any(file_hash(path) != digest for path, digest in inputs.items()):
            raise ValueError('An editorial input changed during rendering; delivery was blocked')
        _publish_new(pending, output, manifest, result)
        return result


def _publish_new(pending: Path, output: Path, manifest: Path, result: dict):
    """Exclusive promotion across independent episode locks, preserving racing files."""
    fd, name = tempfile.mkstemp(prefix='.editorial-receipt-', dir=output.parent)
    temporary = Path(name)
    owned_receipt = None
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(result, handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
            stat = os.fstat(handle.fileno())
            identity = (stat.st_dev, stat.st_ino)
        os.link(temporary, manifest)
        owned_receipt = identity
        os.link(pending, output)
    except BaseException:
        if owned_receipt is not None:
            try:
                stat = manifest.lstat()
                if (stat.st_dev, stat.st_ino) == owned_receipt:
                    manifest.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        temporary.unlink(missing_ok=True)
        pending.unlink(missing_ok=True)
