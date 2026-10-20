from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx

from ..media.ffprobe import valid_video
from ..stock.cache import AssetCache, SearchCache
from ..stock.models import SelectedStock, StockAsset, StockVariant
from ..stock.selector import OutputGeometry, StockSelector

log = logging.getLogger("kitok.providers.pexels")


class PexelsError(RuntimeError):
    pass


class PexelsProvider:
    API_URL = "https://api.pexels.com/videos/search"

    def __init__(
        self,
        api_key: str,
        cache_root: Path,
        *,
        ffprobe: str = "ffprobe",
        timeout: float = 30,
        attempts: int = 3,
        client: httpx.Client | None = None,
        asset_validator=None,
    ):
        self.api_key = api_key
        self.ffprobe = ffprobe
        self.attempts = attempts
        self.search_cache = SearchCache(cache_root)
        self.asset_cache = AssetCache(cache_root)
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._owns_client = client is None
        self.asset_validator = asset_validator or (lambda path: valid_video(path, self.ffprobe))

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _request(self, url: str, **kwargs) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.attempts):
            try:
                response = self.client.get(url, **kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    raise PexelsError(f"Pexels returned HTTP {response.status_code}")
                response.raise_for_status()
                return response
            except (httpx.HTTPError, PexelsError) as exc:
                last = exc
                if attempt + 1 < self.attempts:
                    time.sleep(min(2**attempt, 4))
        raise PexelsError(f"Pexels request failed after retries: {last}")

    def search_videos(
        self, query: str, *, orientation: str, per_page: int = 80, page: int = 1
    ) -> list[StockAsset]:
        query = query.strip()
        if not query:
            raise PexelsError("Pexels query must not be blank")
        log.debug(
            "Pexels search query=%r orientation=%s page=%d per_page=%d",
            query, orientation, page, per_page,
        )
        cached = self.search_cache.load(query, orientation, per_page, page)
        if cached is not None:
            log.debug("Pexels search cache hit query=%r candidates=%d", query, len(cached))
            return cached
        log.debug("Pexels search cache miss query=%r", query)
        if not self.api_key:
            raise PexelsError("PEXELS_API_KEY is required for an uncached native stock search")
        response = self._request(
            self.API_URL,
            headers={"Authorization": self.api_key, "User-Agent": "kitok-native/0.1"},
            params={
                "query": query,
                "orientation": orientation,
                "per_page": per_page,
                "page": page,
            },
        )
        try:
            videos = response.json().get("videos", [])
            assets = [self._parse_asset(item, query) for item in videos]
        except (ValueError, TypeError, KeyError) as exc:
            raise PexelsError("Pexels returned malformed search metadata") from exc
        assets = [asset for asset in assets if asset.variants and asset.duration > 0]
        self.search_cache.store(query, orientation, per_page, page, assets)
        return assets

    def preflight_searches(
        self, queries: list[str] | tuple[str, ...], *, orientation: str,
        per_page: int = 80, page: int = 1,
    ) -> None:
        """Fail before expensive Fish synthesis when neither credentials nor cache can serve."""
        if self.api_key:
            return
        missing = [
            query for query in dict.fromkeys(queries)
            if self.search_cache.load(query, orientation, per_page, page) is None
        ]
        if missing:
            raise PexelsError(
                "PEXELS_API_KEY is required before Native Fish synthesis; uncached queries: "
                + ", ".join(missing[:3])
                + ("..." if len(missing) > 3 else "")
            )

    @staticmethod
    def _parse_asset(item: dict, query: str) -> StockAsset:
        variants = tuple(
            StockVariant(
                url=str(value.get("link") or ""),
                width=int(value.get("width") or 0),
                height=int(value.get("height") or 0),
                fps=float(value["fps"]) if value.get("fps") else None,
                file_type=str(value.get("file_type") or "video/mp4"),
            )
            for value in item.get("video_files", [])
            if value.get("link") and value.get("width") and value.get("height")
        )
        return StockAsset(
            asset_id=int(item["id"]),
            query=query,
            duration=float(item["duration"]),
            variants=variants,
            page_url=item.get("url"),
            author=(item.get("user") or {}).get("name"),
            author_url=(item.get("user") or {}).get("url"),
        )

    def select_candidate(
        self,
        assets: list[StockAsset],
        *,
        target: OutputGeometry,
        minimum_duration: float,
        used_ids: set[int] | None = None,
    ) -> SelectedStock:
        return StockSelector().select_candidate(
            assets,
            target=target,
            minimum_duration=minimum_duration,
            used_ids=used_ids,
        )

    def download_asset(self, selection: SelectedStock) -> Path:
        asset_id = selection.asset.asset_id
        cached = self.asset_cache.get(asset_id, self.asset_validator, selection)
        if cached is not None:
            log.debug("Pexels asset cache hit asset_id=%s path=%s", asset_id, cached)
            return cached
        log.debug(
            "Pexels asset cache miss asset_id=%s source=%dx%d",
            asset_id, selection.variant.width, selection.variant.height,
        )
        part = self.asset_cache.part_path(asset_id)
        part.unlink(missing_ok=True)
        try:
            last: Exception | None = None
            for attempt in range(self.attempts):
                try:
                    with self.client.stream("GET", selection.variant.url) as response:
                        if response.status_code == 429 or response.status_code >= 500:
                            raise PexelsError(f"Pexels asset returned HTTP {response.status_code}")
                        response.raise_for_status()
                        with part.open("wb") as handle:
                            for chunk in response.iter_bytes():
                                handle.write(chunk)
                    break
                except (httpx.HTTPError, PexelsError, OSError) as exc:
                    last = exc
                    part.unlink(missing_ok=True)
                    if attempt + 1 >= self.attempts:
                        raise PexelsError(f"Pexels asset download failed after retries: {last}") from exc
                    time.sleep(min(2**attempt, 4))
            if not self.asset_validator(part):
                raise PexelsError(f"Downloaded Pexels asset {asset_id} is not a valid video")
            return self.asset_cache.commit(selection, part)
        except (OSError, PexelsError):
            part.unlink(missing_ok=True)
            raise
