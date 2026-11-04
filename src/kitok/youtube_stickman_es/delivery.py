"""Upload handoff, verified final-video deduplication and visual-cache cleanup.

No providers, encoding or publishing.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from .files import episode_lock, episode_path, local_file


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def inventory(episode: Path) -> dict:
    """Count hardlinked files once for allocated bytes; never follow symlinks."""
    seen = set()
    logical = allocated = count = 0
    for folder, directories, filenames in os.walk(episode, followlinks=False):
        directories[:] = [name for name in directories if not (Path(folder) / name).is_symlink()]
        for name in filenames:
            path = Path(folder) / name
            if path.is_symlink() or not path.is_file():
                continue
            stat = path.stat()
            count += 1
            logical += stat.st_size
            inode = stat.st_dev, stat.st_ino
            if inode not in seen:
                allocated += stat.st_blocks * 512
                seen.add(inode)
    return {'files': count, 'unique_inodes': len(seen), 'logical_bytes': logical,
            'allocated_bytes': allocated,
            'allocated_note': 'Unique inodes inside this tree; external hardlinks may retain blocks.'}


def _approved(episode: Path) -> tuple[Path, dict]:
    from .final_paths import final_video
    video = final_video(episode, 'video_subtitulado.mp4')
    qa_path = local_file(episode, 'qa_subtitulado.json')
    receipt = json.loads(local_file(episode, '.stickman/subtitles.json').read_text())
    qa = json.loads(qa_path.read_text())
    video_sha = sha256(video)
    if (qa.get('technical_status') != 'passed' or qa.get('video_sha256') != video_sha
            or receipt.get('status') != 'complete' or receipt.get('output_sha256') != video_sha
            or receipt.get('qa_sha256') != sha256(qa_path)):
        raise ValueError('Compact delivery requires passed caption QA and a matching complete receipt')
    return video, qa


def compact_delivery(root: Path, episode: Path) -> dict:
    """Publish only Studio upload assets, then retain one name per final MP4."""
    episode = episode_path(root, episode)
    from .final_paths import delivery_episode
    with ExitStack() as stack:
        stack.enter_context(episode_lock(episode))
        target = delivery_episode(episode)
        if target != episode:
            stack.enter_context(episode_lock(target))
        stack.enter_context(_cache_locks(episode))
        return _compact_delivery_locked(root, episode)


def publication_metadata(episode):
    path = local_file(episode, 'editorial/publicacion_youtube.json', exists=False)
    if not path.exists():
        return {}
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('Editorial YouTube publication metadata must be an object')
    title, description, tags = value.get('title'), value.get('description'), value.get('tags')
    if not isinstance(title, str) or not title.strip() or len(title) > 100 or '\n' in title or '\r' in title:
        raise ValueError('Editorial YouTube title must contain 1-100 characters on one line')
    if not isinstance(description, str) or not description.strip() or len(description) > 5000:
        raise ValueError('Editorial YouTube description must contain 1-5000 characters')
    if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
        raise ValueError('Editorial YouTube tags must be a list of nonempty strings')
    if 'settings' in value and not isinstance(value['settings'], (dict, str)):
        raise ValueError('Editorial Studio settings must be an object or text')
    if 'music_changes_notice' in value and (not isinstance(value['music_changes_notice'], str) or not value['music_changes_notice'].strip()):
        raise ValueError('Editorial music changes notice must be nonempty text')
    return value


def _require_music_attribution(episode, description, editorial):
    """Bind public attribution to the actual mixed audio, not generic CREDITS."""
    render = json.loads(local_file(episode, 'video_final.editorial.json').read_text())
    if not render.get('audio_is_final_mix'):
        return
    audio_name = Path(render.get('audio_source', '')).name
    mix_path = local_file(episode, '.stickman/' + audio_name, exists=False)
    receipt_path = local_file(episode, '.stickman/' + audio_name + '.json', exists=False)
    if not mix_path.is_file() or not receipt_path.is_file():
        raise ValueError('Mixed video requires its existing audio and license receipt before delivery')
    mix = json.loads(receipt_path.read_text())
    if (mix.get('output_sha256') != render.get('audio_source_sha256')
            or sha256(mix_path) != render.get('audio_source_sha256')):
        raise ValueError('Music receipt does not match the audio used in the final video')
    required = set(mix.get('selection', {}).get('credits', []))
    for row in mix.get('sources', []):
        source = row.get('source', {})
        if source.get('attribution'):
            required.add(source['attribution'])
        elif source.get('license_id', '').startswith('CC-BY'):
            raise ValueError('CC BY source has no recorded required attribution')
    def normalized(value):
        return ' '.join(value.replace('—', '-').replace('–', '-').split()).casefold()
    public_text = normalized(description)
    for credit in required:
        if normalized(credit) not in public_text:
            raise ValueError('Description is missing required music attribution: ' + credit.split('.')[0])
    # Legacy generated CREDITS contain attribution but did not include this
    # notice. Preserve those immutable descriptions; an editorial replacement
    # must retain the notice when it replaces the complete public description.
    if required and editorial and mix.get('selection', {}).get('changes_notice'):
        notices = [mix['selection']['changes_notice'],
                   'Música recortada, enlazada y mezclada bajo la narración.',
                   'Música editada y mezclada para acompañar la narración.']
        if editorial.get('music_changes_notice'):
            notices.append(editorial['music_changes_notice'])
        if not any(normalized(notice) in public_text for notice in notices):
            raise ValueError('Description must retain a notice of the edits and mix made to attributed music')


def _delivery_materials(episode):
    from .completion import verify_videos
    from .final_paths import final_video
    verify_videos(episode)
    _, qa = _approved(episode)
    metadata_path = local_file(episode, 'metadata_youtube_final.json', exists=False)
    if not metadata_path.exists():
        metadata_path = local_file(episode, 'metadata_youtube.json', exists=False)
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    editorial_path = local_file(episode, 'editorial/publicacion_youtube.json', exists=False)
    editorial = publication_metadata(episode)
    metadata = {**metadata, **editorial}
    title_path = local_file(episode, 'titulo.txt', exists=False)
    title = metadata.get('title') or (title_path.read_text().strip() if title_path.exists() else None)
    if not isinstance(title, str) or not title.strip() or len(title) > 100 or '\n' in title or '\r' in title:
        raise ValueError('Delivery requires an explicit YouTube title of 1-100 characters')
    tags = metadata.get('tags', [])
    if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
        raise ValueError('YouTube tags must be a list of nonempty strings')
    sources = {
        'video_final.mp4': final_video(episode, 'video_final.mp4'),
        'video_subtitulado.mp4': final_video(episode, 'video_subtitulado.mp4'),
        'miniatura.png': local_file(episode, 'miniaturas/miniatura_final.png'),
        'descripcion.txt': local_file(episode, 'descripcion_youtube_final.txt'),
    }
    # A cleaned narration may have a different clock; use its actual SRT.
    from .voice_cleaning import cleaned_paths
    config_path = local_file(episode, 'configuracion.json', exists=False)
    config = json.loads(config_path.read_text()) if config_path.is_file() else {}
    mode = config.get('voice', {}).get('transcript_verification', 'off')
    sources['voz.srt'] = cleaned_paths(episode, mode)[1]
    sources['voz.srt'] = local_file(episode, str(sources['voz.srt'].relative_to(episode)))
    texts = {'titulo.txt': title.strip() + '\n', 'etiquetas.txt': ', '.join(tags) + '\n',
             'ajustes_youtube.txt': (
                 'Idioma del vídeo y del título/descripción: español.\n'
                 'Categoría sugerida: entretenimiento.\n'
                 'Audiencia: no creado para niños (relato de terror).\n'
                 'Comentarios: moderación básica sugerida; revisar preferencia del canal.\n'
                 'Visibilidad inicial: privado; programar sólo cuando lo decidas.\n'
                 'Selecciona miniatura.png y, si subes el vídeo normal, voz.srt con tiempos.\n'
                 'Contenido alterado/sintético y restricciones: responder tras revisar el vídeo '
                 'y las preguntas actuales de Studio; no se han contestado automáticamente.\n')}
    if 'description' in editorial:
        description = editorial['description']
        if not isinstance(description, str) or not description.strip() or len(description) > 5000:
            raise ValueError('Editorial YouTube description must contain 1-5000 characters')
        sources.pop('descripcion.txt')
        texts['descripcion.txt'] = description.rstrip() + '\n'
    if 'settings' in editorial:
        settings = editorial['settings']
        if not isinstance(settings, (dict, str)):
            raise ValueError('Editorial Studio settings must be an object or text')
        if isinstance(settings, dict):
            settings = '\n'.join(f'{key}: {value}' for key, value in settings.items())
        texts['ajustes_youtube.txt'] += '\nAjustes editoriales del episodio:\n' + settings.strip() + '\n'
    description = texts.get('descripcion.txt') or sources['descripcion.txt'].read_text()
    _require_music_attribution(episode, description, editorial)
    identities = {name: sha256(path) for name, path in sources.items()}
    identities.update({name: hashlib.sha256(content.encode()).hexdigest() for name, content in texts.items()})
    report = {'version': 2, 'technical_status': qa['technical_status'],
              'duration_seconds': qa.get('duration'), 'frames': qa.get('decoded_frames'),
              'audio_listened_by_tool': False, 'human_review_required': True,
              'sha256': identities, 'publishing_automated': False,
              'source_episode': str(episode),
              'source_qa_sha256': sha256(episode / 'qa_subtitulado.json'),
              'audio_fidelity_status': metadata.get('audio_fidelity_status', 'unverified'),
              'audio_fidelity_note': metadata.get('audio_fidelity_note', 'Independent audio review remains unverified.'),
              'final_video_ready': False,
              'source_metadata_sha256': sha256(metadata_path) if metadata_path.exists() else None}
    if editorial_path.exists():
        report['source_publication_sha256'] = sha256(editorial_path)
    return sources, texts, report


def _existing_delivery(destination, *, allow_legacy=False):
    """Validate known receipts before migration; never discard operator edits."""
    if not destination.exists() or not any(destination.iterdir()):
        return None
    if not destination.is_dir() or any(p.is_symlink() or not p.is_file() for p in destination.iterdir()):
        raise ValueError('Existing entrega differs; preserve it and inspect its contents')
    names = {p.name for p in destination.iterdir()}
    if allow_legacy and names == {'video.mp4', 'miniatura.png', 'descripcion.txt', 'creditos.txt', 'informe.json', 'LEEME.txt'}:
        report = json.loads((destination / 'informe.json').read_text())
        if set(report.get('sha256', {})) != {'video.mp4', 'miniatura.png', 'descripcion.txt', 'creditos.txt'}:
            raise ValueError('Existing legacy entrega has no complete hash register')
        if any(sha256(destination / name) != digest for name, digest in report['sha256'].items()):
            raise ValueError('Existing entrega differs from its receipt; operator edits preserved')
        return report
    report_path = local_file(destination.parent, '.stickman/delivery.json', exists=False)
    pending_path = local_file(destination.parent, '.stickman/delivery-pending.json', exists=False)
    # A migration can publish its directory and crash before replacing an older
    # final receipt. Prefer the pending transaction only when every file matches;
    # otherwise try the previous receipt, without accepting unregistered edits.
    for candidate in (pending_path, report_path):
        if not candidate.is_file():
            continue
        report = json.loads(candidate.read_text())
        if names == set(report.get('sha256', {})) and all(sha256(destination / name) == digest for name, digest in report['sha256'].items()):
            return report
    raise ValueError('Existing entrega differs from its receipt; operator edits preserved')


def _duplicate_final_videos(episode, canonical, identities):
    videos = {name: local_file(canonical, name) for name in ('video_final.mp4', 'video_subtitulado.mp4')}
    digests = {identities[name] for name in videos}
    sizes = {path.stat().st_size for path in videos.values()}
    rows = []
    for path in sorted(episode.rglob('*.mp4')):
        local_file(episode, str(path.relative_to(episode)))
        if path in videos.values() or path.stat().st_size not in sizes:
            continue
        digest = sha256(path)
        if digest in digests:
            rows.append({'path': str(path.relative_to(episode)), 'sha256': digest, 'bytes': path.stat().st_size})
    return rows


def _compact_delivery_locked(root: Path, episode: Path, *, destination_episode=None, migrate=False) -> dict:
    """Caller holds source and (when different) destination episode leases."""
    from .files import replace_state
    from .final_paths import delivery_episode, interrupted_delivery_backup
    target_episode = destination_episode or delivery_episode(episode)
    destination = local_file(target_episode, 'entrega', exists=False)
    if not destination.exists():
        backup = interrupted_delivery_backup(target_episode)
        if backup:
            backup.rename(destination)
    sources, texts, report = _delivery_materials(episode)
    report['source_episode'] = str(episode.relative_to(root.resolve()))
    if destination.exists() and not destination.is_dir():
        raise ValueError('Existing entrega must be a directory')
    previous = _existing_delivery(destination, allow_legacy=migrate)
    same = previous == report and {p.name for p in destination.iterdir()} == set(report['sha256']) if previous else False
    if previous and not same and not migrate:
        raise ValueError('Existing entrega differs; preserve it and choose a new episode revision')
    if previous and not same:
        old_videos = {digest for name, digest in previous['sha256'].items() if name.endswith('.mp4')}
        new_videos = {report['sha256'][name] for name in ('video_final.mp4', 'video_subtitulado.mp4')}
        if not old_videos.issubset(new_videos):
            raise ValueError('Existing entrega contains a distinct video; preserve it before migrating')
    report_path = local_file(target_episode, '.stickman/delivery.json', exists=False)
    pending_path = local_file(target_episode, '.stickman/delivery-pending.json', exists=False)
    transaction_path = local_file(target_episode, '.stickman/delivery-transaction.json', exists=False)
    if not same:
        staged = Path(tempfile.mkdtemp(prefix='.delivery-', dir=target_episode))
        backup = None
        try:
            for name, source in sources.items():
                if name.endswith('.mp4'):
                    os.link(source, staged / name)
                else:
                    shutil.copy2(source, staged / name)
            for name, content in texts.items():
                (staged / name).write_text(content, encoding='utf-8')
            if any(sha256(staged / name) != digest for name, digest in report['sha256'].items()):
                raise ValueError('A delivery source changed during copying')
            if any(sha256(source) != report['sha256'][name] for name, source in sources.items()):
                raise ValueError('A delivery source changed during preparation')
            metadata_name = 'metadata_youtube_final.json' if local_file(episode, 'metadata_youtube_final.json', exists=False).exists() else 'metadata_youtube.json'
            for name, key in ((metadata_name, 'source_metadata_sha256'),
                              ('editorial/publicacion_youtube.json', 'source_publication_sha256')):
                path = local_file(episode, name, exists=False)
                if path.exists() and report.get(key) and sha256(path) != report[key]:
                    raise ValueError('Editorial metadata changed during delivery preparation')
            # Allows a retry after publishing the directory but before publishing
            # its final receipt, without accepting arbitrary unregistered files.
            replace_state(pending_path, report)
            if destination.exists():
                if previous:
                    history = local_file(target_episode, '.stickman/delivery-history', exists=False)
                    history.mkdir(parents=True, exist_ok=True)
                    backup = history / hashlib.sha256(json.dumps(previous, sort_keys=True).encode()).hexdigest()[:20]
                    if backup.exists():
                        raise ValueError('Prior migration backup exists; inspect before continuing')
                    replace_state(transaction_path, {'version': 1, 'status': 'planned',
                                  'backup': str(backup.relative_to(target_episode)), 'previous': previous,
                                  'pending_sha256': sha256(pending_path)})
                    destination.rename(backup)
                else:
                    destination.rmdir()
            try:
                staged.rename(destination)
            except OSError:
                if backup and backup.exists() and not destination.exists():
                    backup.rename(destination)
                raise
            replace_state(report_path, report)
            if backup:
                # Keep prior text/report history, but never a second large MP4.
                for path in backup.glob('*.mp4'):
                    digest = sha256(path)
                    if digest not in {report['sha256']['video_final.mp4'], report['sha256']['video_subtitulado.mp4']}:
                        raise ValueError('Prior delivery contains a distinct video; preserved in migration history')
                    path.unlink()
        finally:
            if staged.exists():
                shutil.rmtree(staged)
    marker = local_file(episode, '.stickman/delivery-location.json', exists=False)
    scope = 'episode' if target_episode == episode else 'parent_episode'
    replace_state(marker, {'version': 1, 'scope': scope})
    # A durable record precedes unlink. Rerunning after interruption is harmless.
    # Includes transient caption-work hardlinks, so production ends with exactly
    # one pathname per final video, rather than merely shared disk blocks.
    removals = _duplicate_final_videos(episode, destination, report['sha256'])
    canonicalization_path = local_file(episode, '.stickman/video-canonicalization.json', exists=False)
    prior = json.loads(canonicalization_path.read_text()) if canonicalization_path.exists() else {}
    history = prior.get('attempts', [])
    record = {'status': 'planned', 'removed': removals, 'attempts': history + [removals],
              'delivery': str(destination.relative_to(root.resolve()))}
    replace_state(canonicalization_path, record)
    for item in removals:
        path = local_file(episode, item['path'])
        if sha256(path) != item['sha256'] or item['sha256'] not in {
                sha256(destination / 'video_final.mp4'), sha256(destination / 'video_subtitulado.mp4')}:
            raise ValueError('Final video changed before canonicalization; preserved duplicate')
        path.unlink()
    replace_state(canonicalization_path, {**record, 'status': 'complete'})
    replace_state(report_path, report)
    if transaction_path.exists():
        transaction = json.loads(transaction_path.read_text())
        replace_state(transaction_path, {**transaction, 'status': 'complete'})
    pending_path.unlink(missing_ok=True)
    return {'delivery': str(destination.relative_to(root.resolve())), 'files': len(report['sha256']),
            'technical_status': 'passed', 'new_provider_requests': 0,
            'audio_fidelity_status': report['audio_fidelity_status'], 'final_video_ready': False,
            'human_review_required': True}


def normalize_delivery(root: Path, episode: Path, *, apply=False, destination_episode=None):
    """Reviewed migration plus hash-identical video deduplication; no encodes."""
    from .files import replace_state
    from .final_paths import delivery_episode
    root = root.resolve()
    episode = episode_path(root, episode)
    target = episode_path(root, destination_episode) if destination_episode else delivery_episode(episode)
    if target != episode and not (episode.parent.name == 'revisiones' and target == episode.parent.parent):
        raise ValueError('A revision can deliver only to itself or its parent episode')
    with ExitStack() as stack:
        stack.enter_context(episode_lock(episode))
        if target != episode:
            stack.enter_context(episode_lock(target))
        # Hold every nested revision lease before scanning duplicate names.
        scopes = {episode, target}
        for path in sorted((target / 'revisiones').glob('*')):
            if path.is_symlink():
                raise ValueError('Revision symlinks block normalization')
            if path.is_dir() and path != episode:
                stack.enter_context(episode_lock(path))
                scopes.add(path)
        for scope in sorted(scopes):
            stack.enter_context(_cache_locks(scope))
        sources, texts, report = _delivery_materials(episode)
        previous = _existing_delivery(local_file(target, 'entrega', exists=False), allow_legacy=True)
        if previous:
            old_videos = {digest for name, digest in previous['sha256'].items() if name.endswith('.mp4')}
            new_videos = {report['sha256'][name] for name in ('video_final.mp4', 'video_subtitulado.mp4')}
            if not old_videos.issubset(new_videos):
                raise ValueError('Existing entrega contains a distinct video; preserve it before migrating')
        digests = {report['sha256'][name] for name in ('video_final.mp4', 'video_subtitulado.mp4')}
        sizes = {sources[name].stat().st_size for name in ('video_final.mp4', 'video_subtitulado.mp4')}
        candidates, distinct = [], []
        destination = target / 'entrega'
        for path in sorted(target.rglob('*.mp4')):
            local_file(target, str(path.relative_to(target)))
            if path.parent == destination and path.name in ('video_final.mp4', 'video_subtitulado.mp4'):
                continue
            digest = sha256(path) if path.stat().st_size in sizes else None
            if digest in digests:
                candidates.append({'path': str(path.relative_to(target)), 'sha256': digest, 'bytes': path.stat().st_size})
            else:
                distinct.append(str(path.relative_to(target)))
        result = {'mode': 'applied' if apply else 'dry_run', 'episode': str(episode.relative_to(root)),
                  'destination': str(destination.relative_to(root)), 'duplicate_videos': candidates,
                  'distinct_videos_preserved': distinct, 'provider_requests': 0}
        if not apply:
            return result
        # Persist exact deletions outside entrega, including any prior duplicate bundle.
        audit = local_file(target, '.stickman/delivery-normalization.json', exists=False)
        replace_state(audit, {**result, 'status': 'planned'})
        result['bundle'] = _compact_delivery_locked(root, episode, destination_episode=target, migrate=True)
        for row in candidates:
            path = local_file(target, row['path'], exists=False)
            if path.exists():
                if sha256(path) != row['sha256']:
                    raise ValueError('Duplicate changed during normalization; remaining copies preserved')
                # The verified canonical output must still exist before each unlink.
                if not any(sha256(destination / name) == row['sha256'] for name in ('video_final.mp4', 'video_subtitulado.mp4')):
                    raise ValueError('Canonical video changed; duplicate preserved')
                path.unlink()
        replace_state(audit, {**result, 'status': 'complete'})
        return result


@contextmanager
def _cache_locks(episode: Path):
    """Respect the renderer's independent locks as well as the episode lock."""
    with ExitStack() as stack:
        locked_folders = []
        workspace = local_file(episode, '.editorial-work', exists=False)
        if workspace.exists():
            if not workspace.is_dir():
                raise ValueError('Editorial workspace must be a directory')
            for folder in sorted(workspace.iterdir()):
                if folder.is_symlink() or not folder.is_dir():
                    raise ValueError('Unexpected editorial workspace entry')
                lock = local_file(episode, str((folder / 'render.lock').relative_to(episode)), exists=False)
                handle = stack.enter_context(lock.open('a'))
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError('An editorial render is running; cleanup blocked') from None
                locked_folders.append(folder)
        # Renderers may create another workspace after enumeration. Such folders
        # were never locked by us and must never become cleanup candidates.
        yield tuple(locked_folders)


def _source_documents(episode: Path) -> list[Path]:
    """Current input contracts and named revisions, never per-scene cache receipts."""
    documents = set()
    for pattern in ('montaje*.json', 'plan*.json', 'configuracion*.json',
                    'video*.editorial.json', 'direccion_visual*.json'):
        documents.update(episode.glob(pattern))
    prevoice = local_file(episode, 'planificacion_visual', exists=False)
    if prevoice.is_dir():
        documents.update(prevoice.glob('plan*.json'))
    return sorted(local_file(episode, str(path.relative_to(episode))) for path in documents)


def clean_visual_cache(root: Path, episode: Path, *, apply: bool = False) -> dict:
    """Dry-run by default. Preserve narration, sources, receipts and all final MP4s.

    Only renderer scene MP4s, generated source plates and contact JPEGs qualify.
    Removing these sacrifices fast rerender reuse, never the source illustrations.
    """
    episode = episode_path(root, episode)
    with episode_lock(episode), _cache_locks(episode) as locked_folders:
        video, _ = _approved(episode)
        protected_video = sha256(video)
        # Any explicit resource reference into a cache is an input, not disposable.
        protected_paths = set()
        for path in _source_documents(episode):
            def collect(value):
                if isinstance(value, str):
                    for base in (root.resolve(), episode):
                        candidate = (base / value).resolve()
                        if candidate.is_relative_to(episode):
                            protected_paths.add(candidate)
                elif isinstance(value, dict):
                    for child in value.values(): collect(child)
                elif isinstance(value, list):
                    for child in value: collect(child)
            collect(json.loads(path.read_text()))
        candidates = []
        for folder in locked_folders:
            for path in sorted(folder.iterdir()):
                if re.fullmatch(r's\d+_\d+(?:\.handle)?\.mp4|s\d+_\d+\.source\.png|assembled\.mp4', path.name):
                    candidates.append(path)
        # QA frames are diagnostic derivatives; contacts themselves remain.
        for name in ('.qa.contact-frames',):
            frames = local_file(episode, name, exists=False)
            if frames.is_dir():
                candidates.extend(sorted(frames.glob('[0-9][0-9][0-9].jpg')))
        records = []
        all_links = {}
        for path in candidates:
            local_file(episode, str(path.relative_to(episode)))
            if path.resolve() in protected_paths:
                continue
            stat = path.stat()
            key = stat.st_dev, stat.st_ino
            all_links.setdefault(key, {'count': 0, 'links': stat.st_nlink, 'bytes': stat.st_blocks * 512})['count'] += 1
            records.append({'path': str(path.relative_to(episode)), 'sha256': sha256(path),
                            'bytes': stat.st_size, 'inode': [stat.st_dev, stat.st_ino]})
        reclaimable = sum(item['bytes'] for item in all_links.values() if item['count'] == item['links'])
        report = {'version': 1, 'mode': 'applied' if apply else 'dry_run', 'files': records,
                  'logical_bytes': sum(r['bytes'] for r in records),
                  'reclaimable_allocated_bytes': reclaimable,
                  'preserved': ['narration and original audio', 'source images and atlases',
                                'plans, captions and receipts', 'final videos', 'licenses and references'],
                  'tradeoff': 'Deleted scene caches must be rendered again if the edit changes.'}
        if apply:
            # Recheck every candidate before deleting any, under both lock layers.
            if sha256(video) != protected_video:
                raise ValueError('Final video changed; cleanup blocked')
            for item in records:
                path = local_file(episode, item['path'])
                stat = path.stat()
                if [stat.st_dev, stat.st_ino] != item['inode'] or sha256(path) != item['sha256']:
                    raise ValueError('A cleanup candidate changed; no files deleted')
            for item in records:
                local_file(episode, item['path']).unlink()
        return report
