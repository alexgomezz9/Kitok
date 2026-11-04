"""Resolve completed videos without recreating duplicate names outside entrega."""
from __future__ import annotations

import json
from pathlib import Path

from .files import local_file, digest

UPLOAD_FILES = {'video_final.mp4', 'video_subtitulado.mp4', 'voz.srt', 'miniatura.png',
                'titulo.txt', 'descripcion.txt', 'etiquetas.txt', 'ajustes_youtube.txt'}


def interrupted_delivery_backup(episode: Path) -> Path | None:
    """Read-only recovery evidence for the gap between two directory renames."""
    transaction = local_file(episode, '.stickman/delivery-transaction.json', exists=False)
    if not transaction.is_file():
        return None
    record = json.loads(transaction.read_text())
    if record.get('status') != 'planned':
        return None
    relative = Path(record.get('backup', ''))
    if (len(relative.parts) != 3 or relative.parts[:2] != ('.stickman', 'delivery-history')
            or len(relative.name) != 20 or any(c not in '0123456789abcdef' for c in relative.name)):
        raise ValueError('Invalid interrupted delivery backup location')
    backup = local_file(episode, str(relative), exists=False)
    if not backup.is_dir():
        raise ValueError('Interrupted delivery backup is unavailable; preserve state for review')
    pending = local_file(episode, '.stickman/delivery-pending.json')
    if digest(pending) != record.get('pending_sha256'):
        raise ValueError('Interrupted delivery pending receipt changed; backup preserved')
    previous = record.get('previous', {})
    identities = previous.get('sha256', {})
    legacy_files = {'video.mp4', 'miniatura.png', 'descripcion.txt', 'creditos.txt'}
    if set(identities) == legacy_files:
        expected = legacy_files | {'informe.json', 'LEEME.txt'}
        receipt = local_file(backup, 'informe.json')
    elif set(identities) == UPLOAD_FILES:
        expected = UPLOAD_FILES
        receipt = local_file(episode, '.stickman/delivery.json')
    else:
        raise ValueError('Interrupted delivery previous receipt has unexpected assets')
    if json.loads(receipt.read_text()) != previous:
        raise ValueError('Interrupted delivery previous receipt changed; backup preserved')
    if {path.name for path in backup.iterdir()} != expected:
        raise ValueError('Interrupted delivery backup contents changed; preserved for review')
    if any(digest(local_file(backup, name)) != value for name, value in identities.items()):
        raise ValueError('Interrupted delivery backup hashes changed; preserved for review')
    return backup


def delivery_episode(episode: Path) -> Path:
    marker = local_file(episode, '.stickman/delivery-location.json', exists=False)
    if not marker.is_file():
        return episode
    scope = json.loads(marker.read_text()).get('scope')
    if scope == 'episode':
        return episode
    if scope == 'parent_episode' and episode.parent.name == 'revisiones':
        parent = episode.parent.parent
        # Validate every component again, including the destination directory.
        local_file(parent, 'entrega', exists=False)
        return parent
    raise ValueError('Invalid canonical delivery location')


def final_video(episode: Path, filename: str, *, exists: bool = True) -> Path:
    """Production writes its original name; a completed bundle owns the only copy.

    Render receipts retain their historical names and hashes. No arbitrary path
    can be supplied by the marker; a revision may use only its own parent episode.
    """
    if Path(filename).name != filename or not filename.endswith('.mp4'):
        raise ValueError('Expected a final video filename')
    legacy = local_file(episode, filename, exists=False)
    target = delivery_episode(episode)
    canonical = local_file(target, 'entrega/' + filename, exists=False)
    path = legacy if legacy.exists() or not canonical.exists() else canonical
    if not path.exists() and not local_file(target, 'entrega', exists=False).exists():
        backup = interrupted_delivery_backup(target)
        if backup:
            path = local_file(backup, filename, exists=False)
    if exists and not path.is_file():
        raise ValueError('Missing final video: ' + filename)
    return path
