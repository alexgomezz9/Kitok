"""Small episode-scoped filesystem boundary; no HTTP paths or global queue writes."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile


def digest(data) -> str:
    if isinstance(data, Path):
        return hashlib.sha256(data.read_bytes()).hexdigest()
    def canonical(value):
        # Pydantic defaults can be 0 while validated JSON yields 0.0. These
        # represent identical scene decisions and must survive process restart.
        if isinstance(value,float) and value.is_integer():
            return int(value)
        if isinstance(value,dict):
            return {key:canonical(item) for key,item in value.items()}
        if isinstance(value,(list,tuple)):
            return [canonical(item) for item in value]
        return value
    return hashlib.sha256(json.dumps(canonical(data), sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()


def episode_path(root: Path, episode: Path) -> Path:
    root = root.resolve()
    candidate = episode if episode.is_absolute() else root/episode
    # Reject links before resolve: operator media is never redirected by a link.
    if not candidate.absolute().is_relative_to(root):
        raise ValueError('Episode must remain inside the Kitok workspace')
    path = root
    for part in candidate.absolute().relative_to(root).parts:
        if part in {'.', '..'}:
            raise ValueError('Invalid episode path')
        path /= part
        if path.is_symlink():
            raise ValueError('Episode paths cannot contain symlinks')
    if not path.is_dir() or path == root:
        raise ValueError('Choose an existing episode folder inside Kitok')
    return path


def local_file(episode: Path, value: str, *, exists: bool = True) -> Path:
    relative = Path(value)
    if relative.is_absolute() or any(p in {'.', '..'} for p in relative.parts) or not relative.parts:
        raise ValueError('Expected an episode-relative resource path')
    path = episode
    for part in relative.parts:
        path /= part
        if path.is_symlink():
            raise ValueError('Episode resources cannot be symlinks')
    if not path.resolve().is_relative_to(episode.resolve()):
        raise ValueError('Episode resource escaped its folder')
    if exists and not path.is_file():
        raise ValueError(f'Missing episode resource: {value}')
    return path


def write(path: Path, data, *, identical_ok: bool = True):
    """Exclusive publication; changed operator outputs require another revision."""
    content = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n'
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Output cannot be a symlink')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if identical_ok and path.read_text(encoding='utf-8') == content:
            return
        raise FileExistsError(f'Preserve {path.name}; choose a new episode or revision')
    fd, temporary = tempfile.mkstemp(prefix='.publish-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(content)
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def replace_state(path: Path, value):
    from ..state import write_json_atomic
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('State cannot be a symlink')
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, value)


@contextmanager
def episode_lock(episode: Path):
    folder = episode/'.stickman'
    if folder.is_symlink():
        raise ValueError('Episode state cannot be a symlink')
    folder.mkdir(exist_ok=True)
    path = folder/'production.lock'
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('This stickman episode is already being processed') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
