"""Compact local handoff and conservative removal of regenerable visual caches.

No providers, encoding, publishing or automatic deletion during production.
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
    video = local_file(episode, 'video_subtitulado.mp4')
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
    """Create six files atomically; video hardlink avoids duplicating large bytes.

    Text and thumbnail are independent copies. Video is a production artifact: do
    not modify it in place; export an edited version to a new file.
    """
    episode = episode_path(root, episode)
    with episode_lock(episode):
        video, qa = _approved(episode)
        sources = {
            'video.mp4': video,
            'miniatura.png': local_file(episode, 'miniaturas/miniatura_final.png'),
            'descripcion.txt': local_file(episode, 'descripcion_youtube_final.txt'),
            'creditos.txt': local_file(episode, 'creditos_finales.txt'),
        }
        identities = {name: sha256(path) for name, path in sources.items()}
        metadata_path = local_file(episode, 'metadata_youtube_final.json', exists=False)
        metadata_sha = sha256(metadata_path) if metadata_path.exists() else None
        metadata = json.loads(metadata_path.read_text()) if metadata_sha else {}
        fidelity = metadata.get('audio_fidelity_status', 'unverified')
        fidelity_note = metadata.get('audio_fidelity_note', 'Independent audio fidelity review remains unverified.')
        report = {
            'version': 1, 'technical_status': qa['technical_status'],
            'duration_seconds': qa.get('duration'), 'frames': qa.get('decoded_frames'),
            'audio_listened_by_tool': False, 'human_review_required': True,
            'sha256': identities, 'publishing_automated': False,
            'source_episode': str(episode.relative_to(root.resolve())),
            'source_qa_sha256': sha256(episode / 'qa_subtitulado.json'),
            'video_storage': 'hardlink; preserve immutable bytes, export edits to a new file',
            'audio_fidelity_status': fidelity, 'audio_fidelity_note': fidelity_note,
            'final_video_ready': False,
            'source_metadata_sha256': metadata_sha,
        }
        report_text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
        readme = ('Entrega local: vídeo, miniatura, descripción y créditos.\n'
                  'informe.json conserva hashes y QA técnico. Revisar escucha completa y estilo antes de publicar.\n'
                  'Los originales, alineación, imágenes y diagnósticos siguen fuera de esta carpeta.\n'
                  'El vídeo comparte bytes con el máster: para editarlo exporta a un archivo nuevo.\n'
                  f'Fidelidad de audio: {fidelity}. {fidelity_note}\n'
                  'Este paquete técnico no acredita que el episodio esté listo para publicar.\n')
        destination = local_file(episode, 'entrega', exists=False)
        if destination.exists():
            expected = set(sources) | {'informe.json', 'LEEME.txt'}
            if (not destination.is_dir() or {p.name for p in destination.iterdir()} != expected
                    or any(p.is_symlink() or not p.is_file() for p in destination.iterdir())
                    or any(sha256(destination / name) != digest for name, digest in identities.items())
                    or (destination / 'informe.json').read_text() != report_text
                    or (destination / 'LEEME.txt').read_text() != readme):
                raise ValueError('Existing entrega differs; preserve it and choose a new episode revision')
        else:
            staged = Path(tempfile.mkdtemp(prefix='.delivery-', dir=episode))
            try:
                for name, source in sources.items():
                    if name == 'video.mp4':
                        os.link(source, staged / name)
                    else:
                        shutil.copy2(source, staged / name)
                    if sha256(staged / name) != identities[name] or sha256(source) != identities[name]:
                        raise ValueError('A delivery source changed during copying')
                (staged / 'informe.json').write_text(report_text, encoding='utf-8')
                (staged / 'LEEME.txt').write_text(readme, encoding='utf-8')
                if metadata_sha and sha256(metadata_path) != metadata_sha:
                    raise ValueError('Editorial audio status changed during delivery preparation')
                # Under the episode lock another cooperative writer cannot race.
                # Refuse any existing destination, including a dangling symlink.
                if destination.exists() or destination.is_symlink():
                    raise FileExistsError('Delivery destination appeared; preserved existing path')
                staged.rename(destination)
            finally:
                if staged.exists():
                    shutil.rmtree(staged)
        return {'delivery': str(destination.relative_to(root.resolve())), 'files': 6,
                'technical_status': 'passed', 'new_provider_requests': 0,
                'audio_fidelity_status': fidelity, 'final_video_ready': False,
                'human_review_required': True}


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
