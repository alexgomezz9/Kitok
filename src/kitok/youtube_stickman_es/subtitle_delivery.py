"""Separate, immutable captioned delivery from an already approved base render."""
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, replace
from pathlib import Path
import re
import subprocess
import tempfile

from ..editing.ass import filter_path
from ..editing.quality import decoded_audio_hash
from ..media.ffmpeg import choose_encoder, encoder_arguments
from ..media.ffprobe import probe_media, probe_video_clock, stream_durations
from .audio import prepare_narration
from .files import digest, episode_path, local_file, write
from .quality import QA_VERSION, inspect_delivery


def _check_media(video, *, settings, plan, audio_duration):
    info = probe_media(video, settings.ffprobe_binary)
    clock = probe_video_clock(video, settings.ffprobe_binary)
    expected = round(plan.duration * 30)
    if ((info.width, info.height) != (1920, 1080) or info.fps is None
            or abs(info.fps - 30) > 1e-6 or info.pixel_format != 'yuv420p'
            or clock.frames != expected or abs(clock.start_time) > 1e-5
            or abs(clock.duration - expected / 30) > 1e-5):
        raise ValueError('Caption delivery requires the exact 1920x1080, 30 fps narration frame clock')
    duration = stream_durations(video, settings.ffprobe_binary)[1]
    if (info.audio_codec != 'aac' or duration is None or not math.isfinite(duration)
            or abs(duration - audio_duration) > .08):
        raise ValueError('Caption delivery requires complete AAC audio matching the narration')
    result = subprocess.run(
        [settings.ffmpeg_binary, '-nostdin', '-v', 'error', '-xerror', '-threads', '2',
         '-i', str(video), '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'],
        capture_output=True, text=True, check=True, timeout=1800)
    if result.stderr.strip():
        raise ValueError('Caption delivery full decode reported errors: ' + result.stderr[-1000:])
    return {'frames': clock.frames, 'audio_codec': info.audio_codec,
            'audio_duration': duration, 'full_decode': 'passed'}


def _recover_encoded(episode: Path, identity: dict):
    """Find a completed encoding with exact input identity; never trust a bare MP4.

    The tiny receipts are persisted before/after encoding so interruptions during
    expensive QA can resume without spending another encode or probing the GPU.
    Older work without these receipts remains untouched for explicit review.
    """
    parent = local_file(episode, '.stickman/caption-work', exists=False)
    if not parent.exists():
        return None
    matches = []
    for folder in sorted(parent.iterdir()):
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError('Caption work cannot contain symlinks or unexpected files')
        request = local_file(episode, str((folder / 'request.json').relative_to(episode)), exists=False)
        encoded = local_file(episode, str((folder / 'encoded.json').relative_to(episode)), exists=False)
        if not request.exists() or not encoded.exists():
            continue
        recorded = json.loads(request.read_text())
        encoder = recorded.get('encoder') if isinstance(recorded, dict) else None
        if (not isinstance(encoder, dict) or encoder.get('codec') not in {'libx264', 'h264_nvenc'}
                or recorded != {**identity, 'encoder': encoder}):
            continue
        staged = local_file(episode, str((folder / 'video_subtitulado.mp4').relative_to(episode)))
        receipt = json.loads(encoded.read_text())
        if receipt != {'status': 'encoded', 'video_sha256': digest(staged)}:
            raise ValueError('Preserved caption encoding changed; review it before retrying')
        matches.append((staged, recorded))
    if len({digest(path) for path, _ in matches}) > 1:
        raise ValueError('Multiple caption encodings match; choose a reviewed revision')
    return matches[0] if matches else None


def caption_video(episode: Path, *, root: Path, settings, on_stage=None,
                  revision: str | None = None) -> dict:
    """Caller holds episode_lock; never render the base or request providers.

    Interrupted outputs and work directories are preserved. Only a complete
    receipt with identical inputs and output bytes allows reuse.
    """
    from .captions import write_captions
    from .pipeline import current

    root = root.resolve()
    episode = episode_path(root, episode)
    emit = on_stage or (lambda message: None)
    if revision is not None and not re.fullmatch('[a-z0-9][a-z0-9_-]{0,39}', revision):
        raise ValueError('Render revision must be a short lowercase ID')
    suffix = '__' + revision if revision else ''
    plan, config, _ = current(episode)
    base = local_file(episode, 'video_final' + suffix + '.mp4')
    base_qa_path = local_file(episode, 'qa' + suffix + '.json')
    base_sha = digest(base)
    base_qa = json.loads(base_qa_path.read_text())
    if base_qa.get('technical_status') != 'passed' or base_qa.get('video_sha256') != base_sha:
        raise ValueError('Base video requires passed QA matching its current SHA256')
    emit('Subtítulos: comprobando vídeo aprobado y alineación existente; sin generar voz')
    narration = prepare_narration(episode, root=root, settings=settings,
                                 voice=config.voice.model_dump(), generate=False, on_stage=on_stage)
    if not narration.get('words') or not narration.get('alignment_sha256'):
        raise ValueError('Subtitles require existing validated word alignment; no estimated timestamps')
    source_media = _check_media(base, settings=settings, plan=plan,
                                audio_duration=narration['duration'])
    ass = local_file(episode, 'subtitles' + suffix + '.ass', exists=False)
    output = local_file(episode, 'video_subtitulado' + suffix + '.mp4', exists=False)
    qa_path = local_file(episode, 'qa_subtitulado' + suffix + '.json', exists=False)
    receipt_path = local_file(episode, '.stickman/subtitles' + suffix + '.json', exists=False)
    # The helper uses immutable publication too, so an existing changed ASS is
    # rejected before either video or receipt is touched.
    metadata = write_captions(local_file(episode, 'guion_final.txt').read_text(encoding='utf-8-sig'),
                              narration['words'], ass, width=1920, height=1080, words_per_group=3)
    identity = {'version': 1, 'base_video_sha256': base_sha,
                'plan_sha256': digest(plan.model_dump()), 'script_sha256': narration['script_sha256'],
                'narration_sha256': narration['audio_sha256'],
                'alignment_sha256': narration['alignment_sha256'],
                'words_sha256': digest(narration['words']), 'ass_sha256': digest(ass),
                'qa_version': QA_VERSION}
    if receipt_path.exists() or output.exists() or qa_path.exists():
        if not all(path.is_file() for path in (receipt_path, output, qa_path)):
            raise ValueError('Incomplete caption delivery preserved; inspect it and choose another revision')
        receipt = json.loads(receipt_path.read_text())
        qa = json.loads(qa_path.read_text())
        # Encoder availability is relevant only when making new bytes. Reuse
        # retains the encoder that actually created the verified delivery,
        # even if this process cannot currently access its GPU.
        recorded_identity = receipt.get('identity', {})
        recorded_encoder = recorded_identity.get('encoder') if isinstance(recorded_identity, dict) else None
        expected_identity = {**identity, 'encoder': recorded_encoder}
        if (receipt.get('status') != 'complete' or receipt.get('identity') != expected_identity
                or not isinstance(recorded_encoder, dict)
                or recorded_encoder.get('codec') not in {'libx264', 'h264_nvenc'}
                or receipt.get('output_sha256') != digest(output)
                or receipt.get('qa_sha256') != digest(qa_path)
                or qa.get('technical_status') != 'passed'
                or qa.get('video_sha256') != digest(output)):
            raise ValueError('Existing caption delivery differs; preserve it and choose another revision')
        _check_media(output, settings=settings, plan=plan, audio_duration=source_media['audio_duration'])
        emit('Subtítulos existentes: identidad, reloj y decodificación comprobados')
    else:
        recovered = _recover_encoded(episode, identity)
        if recovered:
            staged, identity = recovered
            work = staged.parent
            emit('Subtítulos: recuperando codificación terminada; repitiendo QA sin recodificar')
        else:
            encoder = choose_encoder(settings.ffmpeg_binary, nvenc_preset='p5')
            if not encoder.is_nvenc:
                encoder = replace(encoder, preset='fast', cq=20)
            identity['encoder'] = {**asdict(encoder), 'arguments': encoder_arguments(encoder), 'threads': 2,
                                   'audio': 'copy', 'width': 1920, 'height': 1080, 'fps': 30}
            work_parent = local_file(episode, '.stickman/caption-work', exists=False)
            work_parent.mkdir(parents=True, exist_ok=True)
            work = Path(tempfile.mkdtemp(prefix='delivery-', dir=work_parent))
            staged = work / 'video_subtitulado.mp4'
            write(work / 'request.json', identity)
            emit(f'Subtítulos: incrustando ASS con {encoder.codec} ({encoder.preset}); audio AAC copiado')
            subprocess.run(
                [settings.ffmpeg_binary, '-nostdin', '-v', 'error', '-n', '-threads', '2',
                 '-i', str(base), '-map', '0:v:0', '-map', '0:a:0',
                 '-vf', "ass=filename='" + filter_path(ass) + "'", *encoder_arguments(encoder),
                 '-threads', '2', '-pix_fmt', 'yuv420p',
                 '-c:a', 'copy', '-movflags', '+faststart', str(staged)],
                capture_output=True, text=True, check=True, timeout=7200)
            write(work / 'encoded.json', {'status': 'encoded', 'video_sha256': digest(staged)})
        media = _check_media(staged, settings=settings, plan=plan,
                             audio_duration=source_media['audio_duration'])
        if decoded_audio_hash(base, settings.ffmpeg_binary) != decoded_audio_hash(staged, settings.ffmpeg_binary):
            raise ValueError('Captioned audio differs from base; staged video preserved')
        emit('Calidad: comprobando entrega subtitulada y preservación del audio')
        qa = inspect_delivery(staged, work / 'qa.json', plan=plan, settings=settings,
                              narration=local_file(episode, 'voz.mp3'),
                              fade_in=config.fade_in, fade_out=config.fade_out)
        if qa['technical_status'] != 'passed':
            raise ValueError('Caption delivery QA rejected; staged video and report preserved')
        # Recheck source identities immediately before exclusive publication.
        if (digest(base) != base_sha or digest(ass) != identity['ass_sha256']
                or digest(local_file(episode, 'voz.alignment.json')) != identity['alignment_sha256']
                or digest(local_file(episode, 'voz.mp3')) != identity['narration_sha256']
                or digest(local_file(episode, 'guion_final.txt')) != identity['script_sha256']):
            raise ValueError('Caption inputs changed during rendering; staged output preserved')
        qa.update(video=str(output), video_sha256=digest(staged), caption_media=media,
                  copied_audio_identical=True)
        os.link(staged, output)
        write(qa_path, qa)
        write(receipt_path, {'status': 'complete', 'identity': identity,
                             'output_sha256': digest(output), 'qa_sha256': digest(qa_path),
                             'captions': metadata})
    return {'pipeline': 'youtube_stickman_es', 'technical_status': qa['technical_status'],
            'video': str(output.relative_to(root)), 'base_video': str(base.relative_to(root)),
            'subtitles': str(ass.relative_to(root)), 'qa': str(qa_path.relative_to(root)),
            'receipt': str(receipt_path.relative_to(root)), 'human_review_required': True,
            'human_review': ['caption placement, readability and word synchronization',
                             'complete video playback and audio listening'],
            'provider_requests': 0, 'new_voice_requested': False, 'publishing_automated': False}
