"""Read-only, ID-addressed local motion gallery. No render/provider action on navigation."""
from pathlib import Path
import json
import re
import math

from .config import PROJECT_ROOT

FILES = frozenset({'preview.mp4', 'baseline.mp4', 'contact.jpg', 'CREDITS.md', 'qa.json'})


class MotionStudio:
    def __init__(self, application):
        self.root = (application.s.data_root or PROJECT_ROOT).resolve()
        self.folder = self.root / 'outputs' / 'motion-gallery'

    def _path(self, item_id, name):
        if not isinstance(item_id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,99}', item_id):
            raise ValueError('Muestra no encontrada')
        path = self.folder / item_id / name
        cursor = self.root
        for part in path.relative_to(self.root).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError('La galería no admite enlaces simbólicos')
        if not path.resolve().is_relative_to(self.folder.resolve()) or not path.is_file():
            raise ValueError('Archivo de muestra no encontrado')
        return path

    def file(self, item_id, name):
        if name not in FILES:
            raise ValueError('Archivo de muestra no permitido')
        return self._path(item_id, name)

    def list(self):
        result = []
        if not self.folder.is_dir() or self.folder.is_symlink():
            return result
        for folder in sorted(self.folder.iterdir()):
            try:
                data = json.loads(self._path(folder.name, 'item.json').read_text())
                if data.get('id') != folder.name or data.get('kind') not in {'effect', 'sample'}:
                    continue
                if (not isinstance(data.get('duration'), (int,float)) or not math.isfinite(data['duration'])
                        or not 0 < data['duration'] <= 60 or not isinstance(data.get('title'), str)
                        or len(data['title']) > 180 or not isinstance(data.get('family'), str)):
                    continue
                files = {}
                for name in sorted(FILES):
                    try:
                        self.file(folder.name, name)
                        files[name] = f'/api/motion/{folder.name}/files/{name}'
                    except ValueError:
                        pass
                if 'preview.mp4' not in files:
                    continue
                result.append({k: data.get(k) for k in ('id','title','family','duration','kind','review','preset')} | {'files': files})
            except (ValueError, OSError, TypeError, AttributeError):
                continue
        return result
