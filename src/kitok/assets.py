"""Local asset registry and explicit mutations; large videos are imported by path."""
from __future__ import annotations
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote

from PIL import Image, UnidentifiedImageError
from . import profiles
from .dialogue_video import CharacterAssetRegistry, VIDEO_EXTENSIONS
from .state import write_json_atomic


def identifier(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Use letters, numbers, hyphens or underscores for the ID')
    return value


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError('Invalid asset path')
    return path


class AssetService:
    def __init__(self, settings, catalog_path=None):
        self.s = settings
        self.catalog_path = catalog_path or profiles.CATALOG_PATH
        self._probe_cache = {}

    def metadata(self):
        catalog = profiles.load_catalog(self.catalog_path)
        formats = [{'id': 'classic', 'name': 'Clásico', 'content_format': 'explainer', 'voice_profile': 'alvaro'}]
        formats += [{'id': key, 'name': value.display_name, 'content_format': 'explainer', 'voice_profile': key}
                    for key, value in profiles.VOICES.items() if value.provider == 'fish']
        formats += [{'id': key, 'name': ' + '.join(profiles.VOICES[s].display_name.replace(' ES', '') for s in speakers),
                     'content_format': 'dialogue', 'dialogue_preset': key, 'speakers': list(speakers),
                     'character_profile': key if key in profiles.CHARACTER_PROFILES else None}
                    for key, speakers in profiles.DIALOGUE_PRESETS.items()]
        return {'voices': [{'id': key, **asdict(value)} for key, value in profiles.VOICES.items()],
                'visual_profiles': list(profiles.VISUAL_PROFILES), 'formats': formats,
                'character_profiles': catalog['character_profiles'], 'timezone': self.s.timezone,
                'default_visual_profile': self.s.default_visual_profile}

    def characters(self):
        root = self.s.character_root
        names = set(profiles.CHARACTERS)
        if root.exists():
            names.update(path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith('.'))
        result = []
        for name in sorted(names):
            registry = CharacterAssetRegistry(root)
            poses = registry.discover(name)
            info = profiles.CHARACTERS.get(name, {})
            result.append({'id': name, 'display_name': info.get('display_name', name.title()),
                           'side': info.get('side', 'left'), 'scale': info.get('scale', 1.0),
                           'poses': [{'name': pose.pose, 'filename': pose.path.name,
                                      'url': f'/api/assets/characters/{quote(name)}/poses/{quote(pose.path.name)}'} for pose in poses],
                           'warnings': registry.warnings})
        return result

    def inspect_video(self, path):
        stat = path.stat()
        key = (str(path), stat.st_size, stat.st_mtime_ns)
        if key not in self._probe_cache:
            result = subprocess.run([self.s.ffprobe_binary, '-v', 'error', '-show_streams', '-show_format',
                                     '-of', 'json', str(path)], capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(result.stdout)
            video = next((stream for stream in data.get('streams', []) if stream.get('codec_type') == 'video'), None)
            if not video:
                raise ValueError('The file has no video stream')
            duration = float(data['format']['duration'])
            if duration <= 0:
                raise ValueError('The video has no usable duration')
            self._probe_cache[key] = {'duration': duration, 'width': video['width'], 'height': video['height'],
                                      'codec': video['codec_name'], 'size': stat.st_size, 'compatible': True}
        return self._probe_cache[key]

    def backgrounds(self):
        result = []
        for pool in sorted({v for v in profiles.VISUAL_PROFILES.values() if v}):
            directory = self.s.background_root / pool
            for path in sorted(directory.glob('*')):
                if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
                    continue
                row = {'pool': pool, 'filename': path.name, 'id': f'{pool}/{path.name}'}
                try:
                    row.update(self.inspect_video(path))
                except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                    row.update(compatible=False, error='No se puede leer este vídeo. Revisa el archivo y ffprobe.')
                result.append(row)
        return result

    def _save_catalog(self, catalog):
        # Validate the complete candidate before touching the catalog.
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', dir=self.catalog_path.parent, delete=False) as file:
            json.dump(catalog, file, ensure_ascii=False)
            temporary = Path(file.name)
        try:
            profiles.reload_catalog(temporary)
            write_json_atomic(self.catalog_path, catalog)
        finally:
            temporary.unlink(missing_ok=True)
            profiles.reload_catalog(self.catalog_path)

    def add_character(self, character_id, display_name, side='left', scale=1.0):
        identifier(character_id)
        if side not in {'left', 'right'} or not 0.3 <= scale <= 1.4:
            raise ValueError('Invalid character side or scale')
        catalog = profiles.load_catalog(self.catalog_path)
        if character_id in catalog.get('characters', {}):
            raise ValueError('Character already exists')
        catalog.setdefault('characters', {})[character_id] = {'display_name': display_name, 'side': side, 'scale': scale}
        self._save_catalog(catalog)
        (self.s.character_root / character_id).mkdir(parents=True, exist_ok=True)
        return {'id': character_id}

    def save_voice(self, voice_id, display_name, provider, value, character=None):
        identifier(voice_id)
        catalog = profiles.load_catalog(self.catalog_path)
        if voice_id in catalog['voices']:
            raise ValueError('Voice ID already exists; use a new ID to preserve existing jobs')
        catalog['voices'][voice_id] = {'display_name': display_name, 'provider': provider, 'value': value}
        if character:
            identifier(character)
            if character not in catalog.get('characters', {}):
                raise ValueError('Select a known character')
            if provider != 'fish':
                raise ValueError('Character dialogue requires a Fish voice')
            catalog['character_profiles'].setdefault('custom_cast', {})[voice_id] = {
                'character': character, 'side': catalog['characters'][character].get('side', 'left')}
            catalog['dialogue_presets']['custom_cast'] = list(catalog['character_profiles']['custom_cast'])
        self._save_catalog(catalog)
        return {'id': voice_id}

    def save_pose(self, character, name, stream):
        identifier(character)
        filename = name if name.lower().endswith('.png') else name + '.png'
        if Path(filename).name != filename or not filename.strip('. '):
            raise ValueError('Invalid pose filename')
        directory = inside(self.s.character_root, character)
        directory.mkdir(parents=True, exist_ok=True)
        target = inside(directory, filename)
        if target.exists():
            raise ValueError('Pose already exists; choose a different name')
        data = stream.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise ValueError('PNG must be smaller than 20 MB')
        import io
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                if image.format != 'PNG' or ('A' not in image.getbands() and 'transparency' not in image.info):
                    raise ValueError('Upload a PNG with transparency')
                alpha = image.convert('RGBA').getchannel('A')
                if not alpha.getbbox() or alpha.getextrema()[0] == 255:
                    raise ValueError('PNG must have visible pixels and actual transparency')
        except (OSError, UnidentifiedImageError) as error:
            raise ValueError('Upload a valid PNG with transparency') from error
        with target.open('xb') as file:
            file.write(data)
        return {'name': target.stem}

    def rename_pose(self, character, filename, new_name):
        directory = inside(self.s.character_root, identifier(character))
        old = inside(directory, filename)
        new = inside(directory, new_name if new_name.lower().endswith('.png') else new_name + '.png')
        if new.exists():
            raise ValueError('Pose already exists')
        if not old.is_file() or old.suffix.lower() != '.png' or new.parent != directory:
            raise ValueError('Pose not found')
        old.rename(new)
        return {'name': new.stem}

    def delete_pose(self, character, filename):
        path = inside(self.s.character_root / identifier(character), filename)
        if not path.is_file() or path.suffix.lower() != '.png':
            raise ValueError('Pose not found')
        path.unlink()

    def import_background(self, source, pool):
        identifier(pool)
        if pool not in profiles.VISUAL_PROFILES.values():
            raise ValueError('Unknown background pool')
        source = Path(source).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError('Choose a local MP4, MOV, MKV or WebM video')
        info = self.inspect_video(source)
        directory = inside(self.s.background_root, pool)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / source.name
        if target.exists():
            raise ValueError('Background filename already exists')
        # Hard-link on the same filesystem; bounded-memory copy otherwise.
        try:
            os.link(source, target)
        except OSError:
            with source.open('rb') as reader, target.open('xb') as writer:
                try:
                    shutil.copyfileobj(reader, writer, 1024 * 1024)
                except Exception:
                    target.unlink(missing_ok=True)
                    raise
        return {'filename': target.name, **info}
