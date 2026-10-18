"""Bounded official Data / Analytics / Reporting reads with provenance.

References: developers.google.com/youtube/{v3/docs,analytics/channel_reports,
reporting/v1/reference/rest}. No generic URL fetching or remote write methods.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import math
import re
from zoneinfo import ZoneInfo

import httpx

from .oauth import AuthorizationError, PrivateStore, YouTubeError, access_token

DATA = "https://www.googleapis.com/youtube/v3/"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
REPORTING = "https://youtubereporting.googleapis.com/v1/"
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")


def parse_table(payload: dict) -> dict:
    """Column names are authoritative; missing rows stay missing, never zero."""
    headers = payload.get("columnHeaders")
    if not isinstance(headers, list) or not all(isinstance(h, dict) and isinstance(h.get("name"), str) for h in headers):
        raise YouTubeError("Analytics devolvió columnas inválidas.")
    names = [h["name"] for h in headers]
    if len(names) != len(set(names)):
        raise YouTubeError("Analytics devolvió columnas duplicadas.")
    rows = payload.get("rows", [])
    if not isinstance(rows, list) or any(not isinstance(row, list) or len(row) != len(names) for row in rows):
        raise YouTubeError("Analytics devolvió filas inválidas.")
    for row in rows:
        for value in row:
            if isinstance(value, (dict, list)) or (isinstance(value, float) and not math.isfinite(value)):
                raise YouTubeError("Analytics devolvió valores inválidos.")
    return {"status": "available" if rows else "no_data", "columns": headers,
            "rows": [dict(zip(names, row)) for row in rows]}


class YouTubeReadOnly:
    def __init__(self, store: PrivateStore, *, client: httpx.Client | None = None):
        self.store = store
        self.client = client or httpx.Client(trust_env=False)
        self._owns_client = client is None

    def close(self):
        if self._owns_client:
            self.client.close()

    def _get(self, url: str, params: dict) -> dict:
        allowed = {DATA + name for name in ("channels", "playlistItems", "videos")}
        allowed |= {ANALYTICS, REPORTING + "jobs", REPORTING + "reportTypes"}
        report_path = re.fullmatch(re.escape(REPORTING) + r"jobs/[A-Za-z0-9_-]+/reports", url)
        if url not in allowed and not report_path:
            raise YouTubeError("Endpoint de lectura no permitido.")
        token = access_token(self.store, self.client)
        try:
            response = self.client.get(url, params=params, headers={"Authorization": "Bearer " + token},
                                       timeout=25, follow_redirects=False)
        except httpx.HTTPError:
            raise YouTubeError("La lectura de Google falló o agotó su tiempo. Conservamos el estado previo.") from None
        if response.status_code != 200:
            # Do not include Google's response/request in errors: it may include private data.
            if response.status_code == 401:
                raise AuthorizationError("Google no acepta la autorización actual. Vuelve a conectar.")
            raise YouTubeError(f"Lectura de Google rechazada (HTTP {response.status_code}).")
        try:
            result = response.json()
        except ValueError:
            raise YouTubeError("Google devolvió JSON inválido.") from None
        if not isinstance(result, dict):
            raise YouTubeError("Google devolvió una respuesta inválida.")
        return result

    def _items(self, url: str, params: dict, key: str, *, limit: int = 500) -> dict:
        items, seen, pages = [], set(), 0
        query = dict(params)
        while True:
            page = self._get(url, query)
            pages += 1
            values = page.get(key, [])
            if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
                raise YouTubeError("Google devolvió una lista inválida.")
            items.extend(values)
            next_page = page.get("nextPageToken")
            if not next_page or len(items) >= limit or pages >= 20:
                return {"items": items[:limit], "truncated": bool(next_page) or len(items) > limit}
            if not isinstance(next_page, str) or next_page in seen:
                raise YouTubeError("Google devolvió una paginación repetida o inválida.")
            seen.add(next_page)
            query["pageToken"] = next_page

    def _analytics(self, start: str, end: str, *, dimensions: str, metrics: str, video: str | None = None) -> dict:
        params = {"ids": "channel==MINE", "startDate": start, "endDate": end,
                  "dimensions": dimensions, "metrics": metrics}
        if video:
            params["filters"] = "video==" + video
        try:
            table = parse_table(self._get(ANALYTICS, params))
        except AuthorizationError:
            raise
        except YouTubeError as exc:
            return {"status": "unavailable", "reason": str(exc), "query": params}
        return {**table, "query": params, "source": ANALYTICS,
                "date_timezone": "America/Los_Angeles", "missing_is_zero": False}

    def _reporting(self) -> dict:
        try:
            types = self._items(REPORTING + "reportTypes", {}, "reportTypes")
            jobs = self._items(REPORTING + "jobs", {}, "jobs", limit=20)
            reports = {}
            for job in jobs["items"]:
                job_id = job.get("id", "")
                if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
                    raise YouTubeError("Reporting devolvió un identificador inválido.")
                reports[job_id] = self._items(REPORTING + "jobs/" + job_id + "/reports", {}, "reports", limit=100)
            return {"status": "available", "report_types": types, "jobs": jobs, "reports": reports,
                    "source": REPORTING, "creates_jobs": False, "downloads_reports": False,
                    "reach_metrics": "No importadas; no se calculan CTR o impresiones a partir de vistas."}
        except AuthorizationError:
            raise
        except YouTubeError as exc:
            return {"status": "unavailable", "reason": str(exc), "source": REPORTING}

    def sync(self, *, start: str, end: str, video: str | None = None, limit: int = 100) -> dict:
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError:
            raise YouTubeError("Las fechas deben tener formato AAAA-MM-DD.") from None
        if first > last or (last - first).days > 3660 or last > datetime.now(ZoneInfo("America/Los_Angeles")).date():
            raise YouTubeError("El intervalo de fechas es inválido o supera diez años.")
        start, end = first.isoformat(), last.isoformat()
        if not 1 <= limit <= 500:
            raise YouTubeError("El límite de catálogo debe estar entre 1 y 500.")
        if video and not VIDEO_ID.fullmatch(video):
            raise YouTubeError("Identificador de vídeo inválido.")
        with self.store.lock():
            channels = self._items(DATA + "channels", {"mine": "true", "part": "snippet,contentDetails,statistics"}, "items")
            if len(channels["items"]) != 1:
                raise YouTubeError("La autorización debe identificar exactamente un canal. No se elige por nombre.")
            channel = channels["items"][0]
            channel_id = channel.get("id")
            if not isinstance(channel_id, str) or not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", channel_id):
                raise YouTubeError("Google no devolvió una identidad de canal válida.")
            tokens = self.store.read("tokens.json")
            if tokens.get("channel_id") and tokens["channel_id"] != channel_id:
                raise YouTubeError("La identidad cambió. Usa un directorio independiente para otro canal.")
            tokens["channel_id"] = channel_id
            self.store.write("tokens.json", tokens)
            playlist = channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
            if not playlist:
                raise YouTubeError("El canal no devolvió su lista de subidas.")
            uploads = self._items(DATA + "playlistItems", {"playlistId": playlist, "part": "contentDetails", "maxResults": 50}, "items", limit=limit)
            ids = [item.get("contentDetails", {}).get("videoId") for item in uploads["items"]]
            if any(not isinstance(value, str) or not VIDEO_ID.fullmatch(value) for value in ids):
                raise YouTubeError("El catálogo contiene identificadores inválidos.")
            if video and video not in ids:
                ids.append(video)
            videos = []
            for offset in range(0, len(ids), 50):
                batch = self._get(DATA + "videos", {"id": ",".join(ids[offset:offset+50]), "part": "snippet,contentDetails,statistics,status"})
                batch_items = batch.get("items", [])
                if not isinstance(batch_items, list) or any(not isinstance(item, dict) for item in batch_items):
                    raise YouTubeError("Google devolvió metadatos inválidos.")
                videos.extend(batch_items)
            if any(item.get("snippet", {}).get("channelId") != channel_id for item in videos):
                raise YouTubeError("Un vídeo no pertenece al canal conectado.")
            if video and not any(item.get("id") == video for item in videos):
                raise YouTubeError("No se pudo verificar el vídeo solicitado en este canal.")
            snapshot = {
                "version": 1, "fetched_at": datetime.now(timezone.utc).isoformat(),
                "channel_id": channel_id, "channel": channel, "videos": videos,
                "catalog_truncated": uploads["truncated"], "catalog_limit": limit,
                "period": {"start": start, "end": end, "date_timezone": "America/Los_Angeles"},
                "daily": self._analytics(start, end, dimensions="day", metrics="views,estimatedMinutesWatched,averageViewDuration"),
                "traffic": self._analytics(start, end, dimensions="insightTrafficSourceType", metrics="views,estimatedMinutesWatched"),
                "retention": self._analytics(start, end, dimensions="elapsedVideoTimeRatio", metrics="audienceWatchRatio,relativeRetentionPerformance", video=video) if video else {"status": "not_requested", "reason": "Selecciona un vídeo para consultar su retención."},
                "reporting": self._reporting(), "api_writes": False,
                "source": {"data": DATA, "analytics": ANALYTICS, "reporting": REPORTING},
                "limits": ["Snapshot local, no dashboard.", "Reporting sólo lista informes existentes: no crea trabajos ni importa CSV.",
                           "Las métricas sin filas o sin permiso permanecen ausentes.",
                           "No se clasifica Shorts por duración ni se deduce CTR de vistas."],
            }
            self.store.write("snapshot.json", snapshot)
            return snapshot
