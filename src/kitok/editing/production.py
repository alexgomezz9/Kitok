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
from ..media.ffprobe import probe_media, stream_durations, measured_video_duration, probe_video_clock
from ..state import write_json_atomic
from .ass import filter_path
from .graphics import render_graphic
from .storyboard import EditorialPlan, file_hash, project_file
from .camera import IMAGE_EXTENSIONS, CameraMotion, camera_filters, image_plate

RENDER_VERSION = 5
MOVING_TRANSITIONS = {'dissolve', 'wipe', 'slide', 'fade_black', 'focus'}


class EditorialValidationError(RuntimeError):
    pass


def _clock_matches(clock, frames: int, fps: int) -> bool:
    return (clock.frames == frames and abs(clock.start_time) <= 1e-6
            and abs(clock.duration - frames / fps) <= 1e-5)


def _blend_frames(previous_frames: int, incoming_frames: int, fps: int) -> int:
    return max(2, min(round(.28*fps), incoming_frames//3, previous_frames))


def _require_clock(path, frames, fps, diagnostics, *, ffprobe="ffprobe"):
    clock = probe_video_clock(path, ffprobe)
    report = {"media": str(path), "expected_frames": frames, "actual_frames": clock.frames,
              "expected_duration": frames / fps, "video_duration": clock.duration,
              "video_start_time": clock.start_time,
              "status": "validated" if _clock_matches(clock, frames, fps) else "rejected"}
    write_json_atomic(diagnostics, report)
    if report["status"] != "validated":
        raise EditorialValidationError(
            f"Editorial frame validation failed: {Path(path).name}; video_frames={clock.frames} expected={frames}; "
            f"video_start={clock.start_time:.6f}s expected=0; video_duration={clock.duration:.6f}s "
            f"expected={frames / fps:.6f}s; diagnostics preserved: {diagnostics}")
    return clock


def validate_stock_coverage(plan, assets: dict[str, Path], *, ffprobe="ffprobe") -> dict[Path, float]:
    """Check every stock window before rendering even the first scene."""
    durations = {}
    for scene in plan.scenes:
        if scene.graphic or scene.composition:
            continue
        source = assets[scene.asset]
        if source.suffix.lower() in IMAGE_EXTENSIONS:
            continue
        if source not in durations:
            durations[source] = measured_video_duration(source, ffprobe)
        end = scene.source_start + scene.end - scene.start
        if end > durations[source] + .05:
            raise ValueError(
                f"Stock does not cover scene {scene.id}: asset={scene.asset} "
                f"source_start={scene.source_start:.6f}s required_end={end:.6f}s "
                f"video_duration={durations[source]:.6f}s; choose another asset or shorten the scene")
    return durations


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
    stock_durations = validate_stock_coverage(plan, assets, ffprobe=settings.ffprobe_binary)
    output.parent.mkdir(parents=True, exist_ok=True)
    workspace = output.parent / ".editorial-work" / plan.episode_id
    workspace.mkdir(parents=True, exist_ok=True)
    encoder = choose_encoder(settings.ffmpeg_binary, requested=encoder_name, nvenc_preset="p5")
    spec = RenderSpec(width=plan.width, height=plan.height, fps=plan.fps,
                      fade_in=0, fade_out=0, chunk_size=4)
    rendered, reused, clips, handles, transition_decisions = [], [], [], [], []
    with _plan_lock(workspace):
        for index, scene in enumerate(plan.scenes):
            if on_stage:
                on_stage(f"Scene {index+1}/{len(plan.scenes)}: {scene.intention}")
            scene_start = time.monotonic()
            duration = scene.end - scene.start
            frames = round(scene.end * plan.fps) - round(scene.start * plan.fps)
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
                if scene.graphic_data.get('background') == 'black':
                    from PIL import Image
                    Image.new('RGB', (plan.width, plan.height), 'black').save(source)
                elif scene.graphic_data.get('background') in (None, 'automatic_stock'):
                    background_plate(scene.motion_design, source, plan.width, plan.height)
                else:
                    raise ValueError('Unknown motion plate background')
                source_identity = file_hash(source)
            elif image:
                source = workspace / f"{scene.id}.png"
                render_graphic(scene.graphic, scene.graphic_data, source,
                               width=plan.width, height=plan.height,
                               style={"palette": scene.palette or plan.palette, "accent": plan.accent})
                source_identity = file_hash(source)
            else:
                source = assets[scene.asset]
                image = source.suffix.lower() in IMAGE_EXTENSIONS
                source_identity = file_hash(source)
                if image:
                    plate = workspace / f'{scene.id}.source.png'
                    image_plate(source, plate, width=plan.width, height=plan.height,
                                fit=scene.image_fit,
                                highlight_box=scene.motion_design.highlight_box if scene.motion_design else None)
                    source = plate
                elif scene.motion_design and scene.motion_design.highlight_box:
                    raise ValueError('An authentic document highlight requires a photograph or scan')
            caption = workspace / f"{scene.id}.ass"
            _caption(scene, caption, plan)
            # A transition consumes future frames from the outgoing shot rather
            # than replaying its already displayed tail. Handles are optional:
            # insufficient stock coverage produces an explicit safe cut.
            handle_frames = 0
            if index+1 < len(plan.scenes) and plan.scenes[index+1].transition in MOVING_TRANSITIONS:
                following = plan.scenes[index+1]
                count = round(following.end*plan.fps)-round(following.start*plan.fps)
                wanted = _blend_frames(frames, count, plan.fps)
                coverage = image or (not scene.composition and
                    stock_durations.get(source, 0) >= scene.source_start+(frames+wanted+1)/plan.fps)
                if coverage:
                    handle_frames = wanted
            handle = workspace / f'{scene.id}.handle.mp4' if handle_frames else None
            render_frames = frames+handle_frames
            # Fractional input seeks can leave the first source PTS above zero.
            # Reset it before fps; otherwise per-scene time limits silently lose
            # frames, accumulating a short video beneath the full-length audio.
            filters = [
                "setpts=PTS-STARTPTS",
                f"scale={plan.width}:{plan.height}:force_original_aspect_ratio=increase:force_divisible_by=2",
                f"crop={plan.width}:{plan.height}", f"fps={plan.fps}", "setsar=1", "format=yuv420p",
            ]
            camera = scene.camera
            if camera is None and image and scene.asset and not scene.composition and scene.motion == 'none':
                camera = CameraMotion(preset='slow_push_in')
            if camera is not None:
                filters.extend(camera_filters(camera, width=plan.width, height=plan.height,
                                              frames=render_frames, fps=plan.fps))
            elif scene.motion == "push":
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
            # Apply fades at global visual time, including fades that span more
            # than one short scene. Audio is never fed through these filters.
            if plan.fade_in or plan.fade_out:
                filters.append(f'setpts=PTS+{scene.start:.9f}/TB')
                if plan.fade_in:
                    filters.append(f'fade=t=in:st=0:d={min(plan.fade_in, plan.duration):.9f}')
                if plan.fade_out:
                    fade = min(plan.fade_out, plan.duration)
                    # Last displayed frame reaches black within the frame grid.
                    start = max(0, plan.duration-fade-1/plan.fps)
                    filters.append(f'fade=t=out:st={start:.9f}:d={fade:.9f}')
                filters.append('setpts=PTS-STARTPTS')
            target = workspace / f"{scene.id}.mp4"
            receipt = workspace / f"{scene.id}.json"
            scene_key = scene.model_dump(exclude={"palette", "headline_style"})
            key_data = {"version":RENDER_VERSION, "scene":scene_key, "source_hash":source_identity,
                        "filters":filters,"encoder":encoder.__dict__,"caption":caption.read_text(),
                        "camera_code":file_hash(Path(__file__).with_name('camera.py')),
                        "handle_frames":handle_frames,
                        "motion_ass":motion_ass.read_text() if scene.motion_design else None,
                        "motion_code":inputs[Path(__file__).with_name('motion_components.py')] if scene.motion_design else None,
                        "previous":file_hash(handles[-1]) if handles and handles[-1] and scene.transition in MOVING_TRANSITIONS else None}
            import hashlib
            fingerprint = hashlib.sha256(json.dumps(key_data,sort_keys=True).encode()).hexdigest()
            hit = False
            if target.exists() and receipt.exists():
                prior = json.loads(receipt.read_text())
                if prior.get("fingerprint") == fingerprint:
                    info = probe_media(target,settings.ffprobe_binary)
                    hit = (abs(info.duration-duration) <= 1/plan.fps+.02
                           and (info.width,info.height)==(plan.width,plan.height)
                           and prior.get("media_sha256")==file_hash(target)
                           and _clock_matches(probe_video_clock(target, settings.ffprobe_binary), frames, plan.fps))
                    if hit and handle is not None:
                        hit = (handle.is_file() and prior.get('handle_sha256') == file_hash(handle)
                               and _clock_matches(probe_video_clock(handle, settings.ffprobe_binary), handle_frames, plan.fps))
            if not hit:
                temp = target.with_name(f".{target.stem}.part.mp4")
                command = [settings.ffmpeg_binary,"-nostdin","-v","error","-y","-threads","2"]
                if image:
                    command += ["-loop","1","-framerate",str(plan.fps)]
                else:
                    command += ["-ss",f"{scene.source_start:.6f}"]
                command += ['-i',str(source)]
                if handle is not None:
                    # Split one continuous filtered stream at the exact boundary;
                    # both files retain zero PTS and independent H.264 headers.
                    graph = (f"[0:v]{','.join(filters)},split=2[base][continuation];"
                             f'[base]trim=end_frame={frames},setpts=PTS-STARTPTS[v];'
                             f'[continuation]trim=start_frame={frames}:end_frame={render_frames},setpts=PTS-STARTPTS[h]')
                    command += ['-filter_complex_threads','1','-filter_complex',graph,
                                '-map','[v]','-an','-frames:v',str(frames),*encoder_arguments(encoder),
                                '-pix_fmt','yuv420p','-threads','2',str(temp),
                                '-map','[h]','-an','-frames:v',str(handle_frames),*encoder_arguments(encoder),
                                '-pix_fmt','yuv420p','-threads','2',str(handle)]
                else:
                    command += ["-an","-frames:v",str(frames),"-vf",",".join(filters),
                                "-filter_threads","1",*encoder_arguments(encoder),"-pix_fmt","yuv420p","-threads","2",str(temp)]
                _run(command)
                if handle is not None:
                    _require_clock(handle, handle_frames, plan.fps,
                                   workspace / f'{scene.id}.handle.validation.json',ffprobe=settings.ffprobe_binary)
                if clips and scene.transition in MOVING_TRANSITIONS and handles[-1] is not None:
                    prior = clips[-1]
                    transitioned = temp.with_name(temp.stem+'.transition.mp4')
                    blend_frames = _blend_frames(round(prior.slot.duration*plan.fps), frames, plan.fps)
                    blend = blend_frames/plan.fps
                    mode = {'dissolve':'fade', 'wipe':'wipeleft', 'slide':'slideleft',
                            'fade_black':'fadeblack', 'focus':'fade'}[scene.transition]
                    focus = (",gblur=sigma=6:enable='lt(t,0.10)',gblur=sigma=2:enable='between(t,0.10,0.20)'"
                             if scene.transition == 'focus' else '')
                    _run([settings.ffmpeg_binary,'-nostdin','-v','error','-y',
                          '-i',str(handles[-1]),'-i',str(temp),
                          '-filter_complex_threads','1','-filter_complex',
                          # xfade negotiates a planar 4:4:4 working format even
                          # when both inputs are 4:2:0. Convert AFTER the filter:
                          # otherwise a concatenated avc1 MP4 can switch from
                          # High/4:2:0 to High 4:4:4 midstream while ffprobe's
                          # stream summary still reports its first frame only.
                          f'[0:v]format=yuv420p,setpts=PTS-STARTPTS,settb=AVTB[a];[1:v]format=yuv420p,setpts=PTS-STARTPTS,settb=AVTB[b];[a][b]xfade=transition={mode}:duration={blend:.9f}:offset=0{focus},format=yuv420p[v]',
                          '-map','[v]','-an','-frames:v',str(frames),*encoder_arguments(encoder),
                          '-pix_fmt','yuv420p','-threads','2',str(transitioned)])
                    transitioned.replace(temp)
                info = probe_media(temp,settings.ffprobe_binary)
                _require_clock(temp, frames, plan.fps, workspace / f"{scene.id}.validation.json",
                               ffprobe=settings.ffprobe_binary)
                temp.replace(target)
                write_json_atomic(receipt,{"fingerprint":fingerprint,"media_sha256":file_hash(target),
                                           'handle_sha256':file_hash(handle) if handle else None})
            applied = scene.transition
            reason = None
            if index and scene.transition in MOVING_TRANSITIONS and handles[-1] is None:
                applied, reason = 'cut', 'Outgoing source lacks continuation coverage'
            if scene.transition == 'match_cut':
                reason = 'Direct cut; visual match is an explicit editorial decision'
            transition_decisions.append({'scene_id':scene.id,'requested':scene.transition,
                                         'applied':applied,'reason':reason})
            (reused if hit else rendered).append(scene.id)
            clips.append(TimelineClip(TimelineSlot(index,"editorial",scene.start,duration),index,target,0))
            handles.append(handle)
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
        if plan.audio_is_final_mix:
            _require_clock(assembled, round(plan.duration * plan.fps), plan.fps,
                           workspace / "assembly-validation.json", ffprobe=settings.ffprobe_binary)
        pending = output.with_name(f".{output.stem}.{uuid4().hex}.part.mp4")
        if plan.audio_is_final_mix:
            # Preserve approved AAC bit-for-bit. PCM is a valid production master,
            # but an MP4 delivery needs broadly supported AAC instead of copying
            # the WAV codec into an MP4. Never normalize an approved mix twice.
            seek = ["-ss",str(plan.audio_offset)] if plan.audio_offset else []
            audio_encoding = (["-c:a","copy"] if audio_info.audio_codec == 'aac' else
                              ["-c:a","aac","-b:a","192k"])
            _run([settings.ffmpeg_binary,"-nostdin","-v","error","-y","-i",str(assembled),
                  *seek,"-i",str(audio),"-map","0:v:0","-map","1:a:0",
                  "-t",str(plan.duration),"-c:v","copy",*audio_encoding,"-movflags","+faststart",str(pending)])
        else:
            if plan.audio_offset:
                raise ValueError("An unmixed narration plan currently requires audio_offset=0")
            assembled.replace(pending)
        final = probe_media(pending,settings.ffprobe_binary)
        video_duration, audio_duration = stream_durations(pending,settings.ffprobe_binary)
        final_clock = probe_video_clock(pending, settings.ffprobe_binary)
        failures = []
        if abs(final.duration-plan.duration)>.15:
            failures.append(f"container_duration={final.duration:.6f}s expected={plan.duration:.6f}s tolerance=0.15s")
        if not final.audio_codec:
            failures.append("missing audio codec")
        if video_duration is None or abs(video_duration-plan.duration)>1/plan.fps+.02:
            failures.append(f"video_duration={video_duration!r}s expected={plan.duration:.6f}s")
        if not _clock_matches(final_clock, round(plan.duration * plan.fps), plan.fps):
            failures.append(f"video_frames={final_clock.frames} expected={round(plan.duration * plan.fps)} "
                            f"video_start={final_clock.start_time:.6f}s expected=0")
        if audio_duration is None or audio_duration<plan.duration-.05:
            failures.append(f"audio_duration={audio_duration!r}s minimum={plan.duration-.05:.6f}s")
        diagnostics = workspace / f"{pending.stem}.validation.json"
        write_json_atomic(diagnostics, {"media": str(pending), "expected_duration": plan.duration,
                          "expected_frames": round(plan.duration * plan.fps), "video_frames": final_clock.frames,
                          "video_start_time": final_clock.start_time, "container_duration": final.duration,
                          "video_duration": video_duration, "audio_duration": audio_duration,
                          "failures": failures, "status": "rejected" if failures else "validated"})
        if failures:
            raise EditorialValidationError("Editorial final validation failed: " + "; ".join(failures)
                                           + f"; diagnostics preserved: {diagnostics}")
        result = {"version":1,"episode_id":plan.episode_id,"channel_id":plan.channel_id,
                  "output":str(output.relative_to(root)),"duration":final.duration,
                  "audio_stream_duration":audio_duration,"video_stream_duration":video_duration,
                  "video_frames":final_clock.frames,"validation_report":str(diagnostics.relative_to(root)),
                  "encoder":encoder.codec,"elapsed_seconds":time.monotonic()-started,
                  "rendered_scenes":rendered,"reused_scenes":reused,"audio_source":plan.audio_source,
                  "audio_source_sha256":file_hash(audio),"audio_is_final_mix":plan.audio_is_final_mix,
                  "audio_delivery": 'copied-aac' if plan.audio_is_final_mix and audio_info.audio_codec=='aac' else
                                    'encoded-aac-without-normalization' if plan.audio_is_final_mix else 'engine-mix',
                  "alignment":plan.alignment,"provider_requests":0,"scenes":[s.model_dump() for s in plan.scenes],
                  "assets":{key:asset.model_dump() for key,asset in plan.assets.items()}}
        result['transitions'] = transition_decisions
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
