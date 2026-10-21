"""Fail-closed, local-only recovery of confirmed paid Native narration.

Auditing reads files only. A confirmed recovery never constructs a Fish client,
nor a network-capable stock provider, and never falls back to new synthesis.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .editing.manifest import load_or_create_manifest
from .editing.motion import provider_sections
from .media.ffprobe import probe_media, valid_video
from .stock.cache import AssetCache, SearchCache
from .stock.selector import StockSelector


def digest(path: Path) -> str:
    with path.open('rb') as handle:
        result = hashlib.file_digest(handle, 'sha256').hexdigest()
    return result


def identity(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def regular(path: Path, root: Path) -> Path:
    """Reject symlinks at every level, including directories, before reading."""
    root = root.absolute()
    path = path.absolute()
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise ValueError('Recovery input is outside the controlled workspace') from None
    for candidate in (root, *(root / Path(*relative.parts[:i]) for i in range(1, len(relative.parts) + 1))):
        if candidate.is_symlink():
            raise ValueError('Recovery does not follow symlinks')
    if not path.is_file():
        raise ValueError(f'Recovery input is missing: {relative}')
    return path


@dataclass(frozen=True)
class ConfirmedNarration:
    root: Path
    output: Path
    narration: Path
    duration: float
    sha256: str
    fingerprint: str
    files: tuple[tuple[Path, str], ...]
    definition_identity: str

    def verify(self, definition, output):
        if output != self.output or definition_identity(definition) != self.definition_identity:
            raise ValueError('Recovery definition changed after confirmation')
        ensure_no_output(output)
        for path, expected in self.files:
            if digest(regular(path, self.root)) != expected:
                raise ValueError(f'Recovery input changed after confirmation: {path.name}')

    def public(self):
        return {'narration_sha256': self.sha256, 'audit_fingerprint': self.fingerprint,
                'duration': self.duration, 'narration_path': str(self.narration),
                'fish_reused': True, 'network_allowed': False,
                'note': 'Reutiliza la voz confirmada. Sólo caché local; si falta un recurso, se detiene sin sintetizar.'}


def definition_identity(definition):
    value = {'script': definition.item.script, 'voice': definition.voice_name,
                     'rate': definition.voice_rate, 'id': definition.item.id,
                     'keywords': definition.item.keywords,
                     'music_mode': definition.music_mode, 'music_track': definition.music_track,
                     'mounting_style': definition.mounting_style}
    plan = getattr(definition, 'visual_plan', None)
    if plan is not None:
        value['visual_plan'] = plan.model_dump(mode='json') if hasattr(plan, 'model_dump') else plan
        value['visual_root'] = str(getattr(definition, 'visual_root', None))
    if getattr(definition, 'source_narration_id', None) is not None:
        value['source_narration_id'] = definition.source_narration_id
    return identity(value)


def ensure_no_output(output):
    for path in (output, output.with_suffix('.editorial.json'), output.with_suffix('.native.json'),
                 output.with_suffix('.credits.md')):
        if path.exists() or path.is_symlink():
            raise ValueError('Recovery output already exists; preserve and review it before continuing')


def inspect_narration(settings, definition, output: Path, *, source_files=(), _allow_existing_output=False,
                      _validate_visual_assets=True) -> ConfirmedNarration:
    """Read-only audit. Requires exact successful Fish operation identity + edit/audio."""
    root = settings.data_root
    if root is None:
        from .config import PROJECT_ROOT
        root = PROJECT_ROOT
    root = root.absolute()
    if output.parent != root / 'outputs' / 'longform':
        raise ValueError('Recovery output is outside the controlled directory')
    if not _allow_existing_output:
        ensure_no_output(output)
    narration = regular(output.parent / '.native-work' / definition.item.id / 'narration.mp3', root)
    alignment = regular(narration.with_suffix('.alignment.json'), root)
    edit = regular(output.with_suffix('.edit.json'), root)
    audio_hash = digest(narration)
    info = probe_media(narration, settings.ffprobe_binary)
    if not info.audio_codec or info.duration <= 0:
        raise ValueError('Confirmed narration cannot be decoded')
    from .rendering.native import fish_reference_id
    body = {'text': definition.item.script, 'reference_id': fish_reference_id(definition.voice_name),
            'format': 'mp3', 'temperature': .8, 'top_p': .7,
            'prosody': {'speed': definition.voice_rate}}
    # This is the exact documented cache v2 identity, not a call into FishVoiceClient.
    request_hash = identity({'version': 2, 'model': settings.fish_model, 'body': body})
    folder = settings.audio_cache_dir / request_hash[:2] / request_hash
    ledger = regular(folder / 'operation.json', root)
    cache_audio = regular(folder / 'audio.mp3', root)
    operation = json.loads(ledger.read_text())
    if (operation.get('status') != 'succeeded' or operation.get('request_hash') != request_hash
            or operation.get('model') != settings.fish_model
            or operation.get('audio_sha256') != audio_hash or digest(cache_audio) != audio_hash):
        raise ValueError('Fish receipt does not confirm this script, voice, model, rate and audio')
    manifest = load_or_create_manifest(edit, definition.item.script, info.duration,
                                       definition.item.keywords, audio_sha256=audio_hash)
    words = json.loads(alignment.read_text())
    if provider_sections(manifest.sections, words, info.duration) is None:
        raise ValueError('Recovery word alignment does not match the narration transcript or duration')
    visual_files = _visual_input_files(definition, root) if _validate_visual_assets else ()
    paths = (narration, alignment, edit, ledger, cache_audio, *source_files, *visual_files)
    files = tuple((regular(path, root), digest(path)) for path in paths)
    definition_hash = definition_identity(definition)
    fingerprint = identity({'definition': definition_hash, 'files': [(str(p.relative_to(root)), h) for p, h in files]})
    return ConfirmedNarration(root, output, narration, info.duration, audio_hash, fingerprint, files, definition_hash)


def _visual_input_files(definition, root):
    from .editing.visual_cues import validate_visual_plan, visual_file
    plan = getattr(definition, 'visual_plan', None)
    if plan is None:
        return ()
    visual_root = getattr(definition, 'visual_root', None)
    plan = validate_visual_plan(plan, definition.item.script, root, visual_root)
    return tuple(visual_file(root, visual_root, cue.asset) for cue in plan.visual_cues if cue.asset)


def inspect_remount_narration(settings, source_definition, source_output: Path,
                              new_definition, new_output: Path, *, source_files=()) -> ConfirmedNarration:
    """Audit an existing paid voice for a separate cut, preserving the original.

    No output, alignment or receipt is copied or written by this operation. The
    returned confirmation is bound to the new montage and all input hashes.
    """
    if getattr(new_definition, 'source_narration_id', None) not in (None, source_definition.item.id):
        raise ValueError('The selected narration source does not match the target draft')
    if source_definition.item.id == new_definition.item.id or source_output == new_output:
        raise ValueError('A new montage requires a distinct content ID and output')
    if (source_definition.item.script, source_definition.voice_name, source_definition.voice_rate) != (
            new_definition.item.script, new_definition.voice_name, new_definition.voice_rate):
        raise ValueError('Remount narration requires the same script, voice and rate')
    ensure_no_output(new_output)
    audit = inspect_narration(settings, source_definition, source_output,
                               source_files=source_files, _allow_existing_output=True, _validate_visual_assets=False)
    if new_output.parent != audit.root / 'outputs' / 'longform':
        raise ValueError('Remount output is outside the controlled directory')
    extras = _visual_input_files(new_definition, audit.root)
    if source_output.exists():
        extras = (*extras, source_output)
    files = (*audit.files, *((regular(path, audit.root), digest(path)) for path in extras))
    definition_hash = definition_identity(new_definition)
    fingerprint = identity({'definition': definition_hash,
                            'files': [(str(p.relative_to(audit.root)), h) for p,h in files]})
    return ConfirmedNarration(audit.root, new_output, audit.narration, audit.duration,
                             audit.sha256, fingerprint, files, definition_hash)


class CachedStock:
    """No HTTP client exists in this adapter. Missing cache is a hard stop."""
    def __init__(self, root: Path, *, ffprobe='ffprobe'):
        self.root = root
        self.ffprobe = ffprobe
        self.search_cache = SearchCache(root)
        self.asset_cache = AssetCache(root)

    def search_videos(self, query, *, orientation, per_page=80, page=1):
        regular(self.search_cache._path(query, orientation, per_page, page), self.root)
        result = self.search_cache.load(query, orientation, per_page, page)
        if result is None:
            raise ValueError(f'Offline recovery is missing cached stock search: {query}')
        return result

    def preflight_searches(self, queries, *, orientation):
        for query in dict.fromkeys(queries):
            self.search_videos(query, orientation=orientation)

    def select_candidate(self, assets, **kwargs):
        return StockSelector().select_candidate(assets, **kwargs)

    def download_asset(self, selection):
        regular(self.asset_cache.video_path(selection.asset.asset_id), self.root)
        regular(self.asset_cache.metadata_path(selection.asset.asset_id), self.root)
        path = self.asset_cache.get(selection.asset.asset_id, lambda p: valid_video(p, self.ffprobe), selection)
        if path is None:
            raise ValueError(f'Offline recovery is missing valid cached stock: {selection.asset.asset_id}')
        return path

    def close(self):
        pass
