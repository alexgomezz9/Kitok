"""Deterministic, lock-held closing of an already prepared editorial handoff."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from .delivery import _cache_locks, _compact_delivery_locked, sha256, publication_metadata
from .files import local_file, replace_state, write
from .final_paths import final_video, delivery_episode
from .workspace import _organize_locked


def accepted_narration(episode: Path) -> tuple[dict, Path]:
    """Load the prepared voice only; no ASR, cuts, provider or receipt rewriting."""
    from .pipeline import current
    from .voice_cleaning import cleaned_paths
    plan, config, _ = current(episode)
    audio, srt, alignment = cleaned_paths(episode, config.voice.transcript_verification)
    receipt = local_file(episode, '.stickman/narration.json')
    if audio != episode / 'voz.mp3':
        active = json.loads(local_file(episode, '.stickman/voice-cleaning/active.json').read_text())
        receipt = local_file(episode, active['files']['narration']['path'])
    result = json.loads(receipt.read_text())
    if (result.get('audio_path') != str(audio) or result.get('srt_path') != str(srt)
            or result.get('audio_sha256') != plan.audio_sha256
            or result.get('srt_sha256') != plan.srt_sha256
            or result.get('script_sha256') != plan.script_sha256
            or result.get('alignment_sha256') != sha256(alignment)
            or not result.get('words')
            or abs(result.get('duration', 0) - plan.narration_duration) > .001):
        raise ValueError('Prepared narration receipt and real word alignment must match the current plan before handoff')
    return result, receipt


def handoff_inputs(episode: Path) -> dict[str, str]:
    """Freeze sources and editorial decisions, excluding regenerable render state."""
    from .pipeline import current
    from .voice_cleaning import cleaned_paths
    plan, config, batch = current(episode)
    status = batch.status()
    if not plan.direction_complete or not status['render_images_ready']:
        raise ValueError('Handoff requires a complete visual plan and all supplied images')
    if not (status['style_approved'] or status['assembly_authorized']):
        raise ValueError('Handoff requires reviewed style or explicit supplied-image assembly authorization')
    if config.description is None or (plan.duration >= 30 and config.chapters is None):
        raise ValueError('Supply editorial description and chapter titles in configuracion.json before handoff')
    publication = publication_metadata(episode)
    if config.pacing_policy and not publication:
        raise ValueError('Trazo dynamic handoff requires editorial/publicacion_youtube.json with final Studio texts')
    # Validate packaging without modifying immutable files or generating media.
    metadata = json.loads(local_file(episode, 'metadata_youtube.json').read_text())
    if metadata.get('title') != plan.title:
        raise ValueError('Prepared metadata title differs from the current visual plan')
    thumbnail = local_file(episode, 'miniaturas/miniatura_final.png')
    with Image.open(thumbnail) as image:
        image.load()
        if image.format != 'PNG' or image.size != (1280, 720):
            raise ValueError('Selected thumbnail must be a reviewed 1280x720 PNG')
    paths = {local_file(episode, name) for name in (
        'guion_final.txt', 'titulo.txt', 'configuracion.json', 'plan_imagenes.json',
        'metadata_youtube.json', 'descripcion_youtube.txt', 'capitulos.txt',
        'miniaturas/miniatura_final.png', 'voz.mp3', 'voz.srt', 'voz.alignment.json')}
    effective = cleaned_paths(episode, config.voice.transcript_verification)
    paths.update(effective)
    _, narration_receipt = accepted_narration(episode)
    paths.add(narration_receipt)
    if config.voice.transcript_verification != 'off' and effective[0] == episode / 'voz.mp3':
        from .voice_fidelity import require_reviewed
        candidates = []
        for report_path in episode.glob('.stickman/voice-fidelity/**/report*.json'):
            report = json.loads(report_path.read_text())
            identity = report.get('identity', {})
            if (identity.get('audio_sha256') == plan.audio_sha256
                    and identity.get('script_sha256') == plan.script_sha256):
                try:
                    if report.get('uncovered_activity'):
                        continue
                    require_reviewed(report, episode)
                    candidates.append(report_path)
                except ValueError:
                    pass
        if not candidates:
            raise ValueError('Voice must have existing accepted ASR evidence before background handoff; no ASR acceptance or correction runs in the queue')
    paths.update(local_file(episode, scene.image_file) for scene in plan.scenes)
    paths.update(local_file(episode, ref.path) for ref in config.references)
    for name in ('direccion_visual.json', 'plan_visual.json', '.stickman/word_timing.json',
                 '.stickman/provided_images.json', '.stickman/images.json', 'miniaturas/conceptos.json',
                 'editorial/revision_voz.json', 'editorial/publicacion_youtube.json'):
        path = local_file(episode, name, exists=False)
        if path.is_file():
            paths.add(path)
    # Review, corrected voice manifests and batch receipts remain immutable inputs.
    for pattern in ('.stickman/voice-fidelity/**/*.json', '.stickman/voice-cleaning/**/*.json',
                    '.stickman/*approval*.json', '.stickman/*batch*.json',
                    'planificacion_visual/lotes_imagenes/*/manifest.json'):
        paths.update(episode.glob(pattern))
    return {str(p.relative_to(episode)): sha256(local_file(episode, str(p.relative_to(episode))))
            for p in sorted(paths)}


def verify_handoff(episode: Path, expected: dict[str, str]):
    actual = handoff_inputs(episode)
    if actual != expected:
        changed = sorted(name for name in actual.keys() | expected.keys()
                         if actual.get(name) != expected.get(name))
        raise ValueError('Handoff inputs changed; preserve this job and prepare a new handoff: ' + ', '.join(changed[:12]))


def verify_videos(episode: Path) -> dict:
    records = {}
    for suffix, filename in (('', 'video_final.mp4'), ('_subtitulado', 'video_subtitulado.mp4')):
        qa = json.loads(local_file(episode, 'qa' + suffix + '.json').read_text())
        digest = sha256(final_video(episode, filename))
        if qa.get('technical_status') != 'passed' or qa.get('video_sha256') != digest:
            raise ValueError('Both videos require matching passed QA before cleanup: ' + filename)
        records[filename] = digest
    base_receipt = json.loads(local_file(episode, 'video_final.editorial.json').read_text())
    receipt = json.loads(local_file(episode, '.stickman/subtitles.json').read_text())
    qa = json.loads(local_file(episode, 'qa_subtitulado.json').read_text())
    if (base_receipt.get('output_sha256') != records['video_final.mp4']
            or receipt.get('status') != 'complete'
            or receipt.get('identity', {}).get('base_video_sha256') != records['video_final.mp4']
            or receipt.get('output_sha256') != records['video_subtitulado.mp4']
            or receipt.get('qa_sha256') != sha256(local_file(episode, 'qa_subtitulado.json'))
            or qa.get('copied_audio_identical') is not True):
        raise ValueError('Both video receipts and identical caption audio evidence are required before cleanup')
    return records


def complete_locked(root: Path, episode: Path, *, expected: dict[str, str], on_stage=None) -> dict:
    """Caller holds episode_lock across render, packaging and safe cleanup."""
    emit = on_stage or (lambda message: None)
    emit('Entrega: verificando inputs, ambos QA y recibos antes del empaquetado')
    verify_handoff(episode, expected)
    videos = verify_videos(episode)
    metadata = json.loads(local_file(episode, 'metadata_youtube.json').read_text())
    metadata.update(technical_status='passed', normal_video='video_final.mp4',
                    captioned_video='video_subtitulado.mp4', human_review_required=True,
                    final_video_ready=False, publishing_automated=False,
                    audio_fidelity_status='reviewed_at_handoff',
                    audio_fidelity_note='Entradas aceptadas antes del montaje; escucha humana final pendiente.')
    # Texts are assembled from supplied editorial metadata and actual mix credits.
    credits = local_file(episode, 'CREDITS.md').read_text()
    description = local_file(episode, 'descripcion_youtube.txt').read_text()
    final_description = description.rstrip() + '\n\n' + credits.rstrip() + '\n'
    if len(final_description) > 5000:
        raise ValueError('Final description with music credits exceeds 5000 characters; shorten supplied description in a new revision')
    write(local_file(episode, 'descripcion_youtube_final.txt', exists=False), final_description)
    write(local_file(episode, 'creditos_finales.txt', exists=False), credits)
    write(local_file(episode, 'metadata_youtube_final.json', exists=False), metadata)
    with _cache_locks(episode):
        bundle = _compact_delivery_locked(root, episode)
    target_episode = delivery_episode(episode)
    report = json.loads(local_file(target_episode, '.stickman/delivery.json').read_text())
    # Absolute paths remain private audit data; parent-delivered historical
    # revisions may legitimately own their canonical files outside this revision.
    protected = {str(local_file(episode, name)): digest for name, digest in expected.items()}
    protected.update({str(local_file(target_episode, 'entrega/' + name)): digest for name, digest in report['sha256'].items()})
    protected[str(local_file(target_episode, '.stickman/delivery.json'))] = sha256(local_file(target_episode, '.stickman/delivery.json'))
    for name in ('qa.json', 'qa_subtitulado.json',
                 '.stickman/subtitles.json', 'metadata_youtube_final.json', 'creditos_finales.txt',
                 'descripcion_youtube_final.txt'):
        protected[str(local_file(episode, name))] = sha256(local_file(episode, name))
    for name, digest in protected.items():
        if sha256(Path(name)) != digest:
            raise ValueError('Protected delivery changed before cleanup: ' + name)
    emit('Limpieza: calculando sólo derivados regenerables; originales y revisiones conservados')
    dry_run = _organize_locked(root, episode, apply=False, archive_revisions=False)
    # Durable deletion audit precedes the first unlink; retain this on interruptions.
    receipt_path = local_file(episode, '.stickman/completion-cleanup.json', exists=False)
    previous = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    if previous and previous.get('inputs') != expected:
        raise ValueError('Cleanup receipt belongs to a different handoff')
    history = previous.get('attempts', []) if previous else []
    record = {'status': 'planned', 'inputs': expected, 'protected': protected,
              'attempts': history + [dry_run]}
    replace_state(receipt_path, record)
    removed = _organize_locked(root, episode, apply=True, archive_revisions=False)
    for name, digest in protected.items():
        if sha256(Path(name)) != digest:
            raise ValueError('Protected file changed during cleanup: ' + name)
    record.update(status='complete', result=removed, protected_hashes_verified=True)
    replace_state(receipt_path, record)
    count = len(removed['removed'])
    size = sum(item['bytes'] for item in removed['removed'])
    emit(f'Terminado: entrega verificada; limpieza {count} archivos / {size} bytes lógicos')
    return {'status': 'technical_complete', 'delivery': bundle, 'cleanup_files': count,
            'cleanup_logical_bytes': size, 'human_review_required': True,
            'publishing_automated': False, 'protected_hashes_verified': True}
