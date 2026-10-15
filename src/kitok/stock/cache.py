from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Callable

from .models import SelectedStock, StockAsset


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class SearchCache:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, query: str, orientation: str, per_page: int, page: int) -> Path:
        identity = json.dumps(
            [query.strip().casefold(), orientation, per_page, page],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return self.root / "searches" / f"{digest}.json"

    def load(self, query: str, orientation: str, per_page: int, page: int) -> list[StockAsset] | None:
        path = self._path(query, orientation, per_page, page)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("query") != query or payload.get("orientation") != orientation:
                return None
            return [StockAsset.from_dict(item) for item in payload["assets"]]
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def store(
        self, query: str, orientation: str, per_page: int, page: int, assets: list[StockAsset]
    ) -> Path:
        path = self._path(query, orientation, per_page, page)
        _atomic_json(
            path,
            {
                "query": query,
                "orientation": orientation,
                "per_page": per_page,
                "page": page,
                "assets": [asset.to_dict() for asset in assets],
            },
        )
        return path

    def clear(self) -> None:
        shutil.rmtree(self.root / "searches", ignore_errors=True)


class AssetCache:
    def __init__(self, root: Path):
        self.root = root

    def video_path(self, asset_id: int) -> Path:
        return self.root / "videos" / f"{asset_id}.mp4"

    def metadata_path(self, asset_id: int) -> Path:
        return self.root / "videos" / f"{asset_id}.json"

    def get(
        self,
        asset_id: int,
        validator: Callable[[Path], bool],
        expected: SelectedStock | None = None,
    ) -> Path | None:
        path = self.video_path(asset_id)
        metadata = self.metadata_path(asset_id)
        if not metadata.is_file() or not validator(path):
            return None
        try:
            payload = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if payload.get("asset_id") != asset_id:
            return None
        if expected is not None and (
            payload.get("width") != expected.variant.width
            or payload.get("height") != expected.variant.height
        ):
            return None
        return path

    def part_path(self, asset_id: int) -> Path:
        path = self.video_path(asset_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.with_suffix(".mp4.part")

    def commit(self, selection: SelectedStock, part: Path) -> Path:
        destination = self.video_path(selection.asset.asset_id)
        if not part.is_file() or part.stat().st_size == 0:
            raise ValueError("Cannot cache an empty Pexels asset")
        part.replace(destination)
        _atomic_json(
            self.metadata_path(selection.asset.asset_id),
            {
                "asset_id": selection.asset.asset_id,
                "query": selection.asset.query,
                "duration": selection.asset.duration,
                "width": selection.variant.width,
                "height": selection.variant.height,
                "fps": selection.variant.fps,
                "url": selection.variant.url,
                "local_cache_path": str(destination),
            },
        )
        return destination

    def clear(self) -> None:
        shutil.rmtree(self.root / "videos", ignore_errors=True)
