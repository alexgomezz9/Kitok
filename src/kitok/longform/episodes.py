"""Numbered episode directories and compatibility with immutable historical paths."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from ..locks import generation_lock


CHANNELS = ('loose_thread', 'trazo_maldito')
EPISODE_ID = r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}'
EPISODE_NUMBER = re.compile(r'([0-9]{3,})_[a-z0-9][a-z0-9_-]*')
EPISODE_PATH = Path('content/longform')
STUDIO_DRAFTS = Path('state/longform/drafts')
LEGACY_STUDIO_DRAFTS = EPISODE_PATH / 'studio'
MOVES_PATH = Path('state/longform-episode-moves.json')


@dataclass(frozen=True)
class EpisodeMoves:
    root: Path
    pairs: tuple[tuple[Path, Path], ...] = ()

    @classmethod
    def load(cls, root: Path) -> EpisodeMoves:
        root = root.absolute()
        path = root / MOVES_PATH
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError('Episode move history cannot be a symlink')
        if not path.exists():
            return cls(root)
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Invalid episode move history')
        pairs = tuple((Path(old), Path(new)) for old, new in data.items())
        for old, new in pairs:
            if (not old.is_relative_to(EPISODE_PATH) or len(old.parts) not in (3, 4)
                    or len(new.parts) != 4 or new.parts[:2] != EPISODE_PATH.parts
                    or new.parts[2] not in CHANNELS or not EPISODE_NUMBER.fullmatch(new.name)
                    or any(part == '..' for part in (*old.parts, *new.parts))):
                raise ValueError('Invalid historical episode path')
        if len({new for _, new in pairs}) != len(pairs) or {old for old, _ in pairs} & {new for _, new in pairs}:
            raise ValueError('Conflicting episode move history')
        return cls(root, pairs)

    def path(self, value: Path, *, reverse: bool = False) -> Path:
        if value.is_absolute() and not value.is_relative_to(self.root):
            return value
        relative = value.relative_to(self.root) if value.is_absolute() else value
        if '..' in relative.parts or not relative.is_relative_to(EPISODE_PATH):
            return value
        if (not reverse and relative.parent == LEGACY_STUDIO_DRAFTS
                and re.fullmatch(r'lf_[0-9a-f]{32}\.(json|txt)', relative.name)):
            historical = self.root / relative
            current = self.root / STUDIO_DRAFTS / relative.name
            if (not (historical.exists() or historical.is_symlink()) and current.is_file()
                    and not any(path.is_symlink() for path in (current, *current.parents))):
                return current if value.is_absolute() else current.relative_to(self.root)
        for old, new in self.pairs:
            source, destination = (new, old) if reverse else (old, new)
            if relative.is_relative_to(source):
                if not reverse:
                    prior = self.root / old
                    if prior.exists() or prior.is_symlink():
                        raise ValueError(f'Conflicting old and new episode paths: {old.name}')
                result = destination / relative.relative_to(source)
                return self.root / result if value.is_absolute() else result
        return value

    def data(self, value, *, reverse: bool = False):
        """Translate path-valued JSON strings for comparison. Preserve original bytes."""
        if isinstance(value, str):
            if value.startswith((str(EPISODE_PATH) + '/', str(self.root / EPISODE_PATH) + '/')):
                return str(self.path(Path(value), reverse=reverse))
        elif isinstance(value, list):
            return [self.data(item, reverse=reverse) for item in value]
        elif isinstance(value, dict):
            return {key: self.data(item, reverse=reverse) for key, item in value.items()}
        return value


def moves_for_episode(path: Path) -> EpisodeMoves | None:
    for parent in path.absolute().parents:
        if parent.parts[-2:] == EPISODE_PATH.parts:
            return EpisodeMoves.load(parent.parent.parent)
    return None


def resolve_episode_path(episode: Path, value: Path) -> Path:
    moves = moves_for_episode(episode)
    return moves.path(value) if moves else value


def reserve_episode(root: Path, settings, channel: str, slug: str) -> Path:
    """Reserve a visible number for an episode; filesystem state is the index."""
    if channel not in CHANNELS or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,69}', slug):
        raise ValueError('Choose a supported channel and a short lowercase episode slug')
    root = root.absolute()
    folder = root / EPISODE_PATH / channel
    if any(path.is_symlink() for path in (root, root / 'content', folder.parent, folder)):
        raise ValueError('Episode directories cannot be symlinks')
    with generation_lock(settings, f'episode-number-{channel}'):
        folder.mkdir(parents=True, exist_ok=True)
        existing = []
        for child in folder.iterdir():
            if child.is_symlink():
                raise ValueError('Channel contains an unexpected episode symlink')
            match = EPISODE_NUMBER.fullmatch(child.name)
            if child.is_dir() and match:
                existing.append((int(match[1]), child))
        matches = [path for _, path in existing if path.name.split('_', 1)[1] == slug]
        if len(matches) > 1:
            raise ValueError('Multiple episodes have the same slug')
        if matches:
            return matches[0]
        number = max((n for n, _ in existing), default=0) + 1
        path = folder / f'{number:03d}_{slug}'
        path.mkdir()
        return path
