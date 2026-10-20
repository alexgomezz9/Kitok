"""Small licensed music library and local speech-first audio production.

Only audited Incompetech sources can be downloaded. Licenses, source
evidence, hashes, selection receipts and mix measurements remain traceable.
Nothing in this module synthesizes speech or contacts generation APIs.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import random
import shutil
import subprocess
import tempfile
from urllib.parse import quote
from typing import Literal
import wave

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .media.ffmpeg import parse_loudnorm_measurement
from .media.ffprobe import measure_loudness, probe_media


class AudioLibraryError(RuntimeError):
    pass


BASE = "https://incompetech.com/music/royalty-free/"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"
AUDITED = {
    "long_note_two": ("USUAN1100420", "Long Note Two"),
    "echoes_of_time_v2": ("USUAN1300030", "Echoes of Time v2"),
    "dreams_become_real": ("USUAN1500027", "Dreams Become Real"),
    "darkest_child": ("USUAN1100783", "Darkest Child"),
    "night_vigil": ("USUAN1900047", "Night Vigil"),
    "floating_cities": ("USUAN1600018", "Floating Cities"),
    "crypto": ("USUAN1600013", "Crypto"),
    "despair_and_triumph": ("USUAN1400012", "Despair and Triumph"),
    "ghost_story": ("USUAN1300034", "Ghost Story"),
    "the_descent": ("USUAN1200094", "The Descent"),
    "deep_haze": ("USUAN1100886", "Deep Haze"),
    "lightless_dawn": ("USUAN1100655", "Lightless Dawn"),
    "dark_walk": ("USUAN1100468", "Dark Walk"),
    "anxiety": ("USUAN1100328", "Anxiety"),
    "immersed": ("USUAN1600010", "Immersed"),
    "mesmerize": ("USUAN1500005", "Mesmerize"),
    "anguish": ("USUAN1400047", "Anguish"),
    "clean_soul": ("USUAN1300033", "Clean Soul"),
    "on_the_ground": ("USUAN1400030", "On the Ground"),
    "deliberate_thought": ("USUAN1100261", "Deliberate Thought"),
}
ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}\Z")
SFX_KINDS = ("soft_tick", "low_pulse", "air_swish", "paper_texture", "key_click", "ui_ping")
# Editorial affinities are separate from the source/license receipt. They are
# judgments based on the author's stored instrument/feel descriptions, not claims
# that the author assigned a business/history genre or that Kitok auditioned them.
AUDIO_AFFINITIES = {
    "technology": {"floating_cities", "deep_haze", "deliberate_thought"},
    "business": {"crypto", "on_the_ground", "deep_haze"},
    "history": {"night_vigil", "despair_and_triumph", "anguish", "echoes_of_time_v2"},
    "revelation": {"the_descent", "lightless_dawn", "crypto"},
}


def infer_audio_mood(script: str, *, channel: str = "loose_thread") -> str:
    """Conservative whole-transcript heuristic; never reads the video title.

    Two distinct supporting terms are required. Profiles constrain horror;
    ambiguous prose keeps the channel's neutral documentary/ambient bed.
    These are editorial hints, not semantic understanding or emotion detection.
    Each returned mood has at least two catalog choices in its supported profile.
    """
    default = "horror" if channel == "horror" else "ambient" if channel == "science" else "investigation"
    if not isinstance(script, str):
        raise AudioLibraryError("Audio mood requires the full narration text")
    words = re.findall(r"\w+", script.casefold())
    if len(words) < 12:
        return default
    vocabulary = {
        "investigation": {"evidence", "investigation", "fraud", "scandal", "audit", "records", "cheating", "stolen",
                          "pruebas", "investigación", "fraude", "escándalo", "auditoría", "registros"},
        "reflective": {"aftermath", "grief", "legacy", "survivors", "mourning", "remembrance", "memories", "loss",
                       "consecuencias", "duelo", "legado", "supervivientes", "recuerdos", "pérdida"},
        "resolution": {"rebuilding", "recovery", "restored", "reconciliation", "healing", "renewal", "recovered",
                       "reconstrucción", "recuperación", "restaurado", "reconciliación", "sanación"},
        "ambient": {"galaxies", "orbit", "planets", "forest", "ocean", "ecosystem", "species", "biodiversity",
                    "galaxias", "órbita", "planetas", "bosque", "océano", "ecosistema", "especies", "biodiversidad"},
        "horror": {"haunted", "ghost", "nightmare", "supernatural", "apparition", "curse", "dread",
                   "embrujado", "fantasma", "pesadilla", "sobrenatural", "aparición", "maldición"},
        "technology": {"software", "server", "network", "encryption", "cyber", "digital", "hacker", "exploit",
                       "servidor", "redes", "cifrado", "cibernético", "informático", "hackeo"},
        "business": {"profit", "market", "investors", "revenue", "debt", "bank", "shares", "corporate",
                     "beneficio", "mercado", "inversores", "ingresos", "deuda", "banco", "acciones", "empresa"},
        "history": {"historical", "century", "empire", "archaeology", "medieval", "ancient", "archives", "revolution",
                    "histórico", "siglo", "imperio", "arqueología", "antiguo", "archivos", "revolución"},
        "revelation": {"revelation", "exposed", "unmasked", "uncovered", "breakthrough", "revelación", "desenmascarado", "revelado"},
    }
    counts = {word: min(2, count) for word, count in Counter(words).items()}
    scores = {}
    for mood, terms in vocabulary.items():
        if channel == "horror" and mood != "horror":
            continue
        if mood == "horror" and channel not in {"horror", "lore"}:
            continue
        matched = terms & counts.keys()
        if len(matched) >= 2:
            scores[mood] = sum(counts[word] for word in matched)
    if not scores:
        return default
    highest = max(scores.values())
    winners = [mood for mood, score in scores.items() if score == highest]
    return winners[0] if len(winners) == 1 else default


def _narrative_profile(script: str, channel: str) -> dict:
    if not isinstance(script, str) or not script.strip():
        raise AudioLibraryError("Narrative music requires the full narration text")
    words = re.sub(r"\[[^\]\n]{1,80}\]", "", script).split()
    if len(words) < 36:
        opening = closing = script
        reason = "Short narration: retain the full-script mood for both distinct tracks."
    else:
        opening = " ".join(words[:max(12, math.ceil(len(words)*.45))])
        closing = " ".join(words[-max(12, math.ceil(len(words)*.35)):])
        reason = "Opening 45% and closing 35% of narration words; conservative independent mood inference."
    return {"opening_mood": infer_audio_mood(opening, channel=channel),
            "closing_mood": infer_audio_mood(closing, channel=channel), "reason": reason,
            "script_sha256": hashlib.sha256(script.encode()).hexdigest()}


def narrative_transition(script: str, duration: float, *, sections: list[dict] | None = None,
                         channel: str = "loose_thread") -> dict:
    """Choose a verified sentence/mood boundary, or label a central estimate.

    sections must contain the complete transcript and validated provider timing,
    expressed as text/start/end. No word-level claim is made from estimated data.
    """
    if not math.isfinite(duration) or duration < 3:
        raise AudioLibraryError("Narrative transition needs at least three measured seconds")
    profile = _narrative_profile(script, channel)
    fallback = {"transition_at": duration/2, "method": "fallback-central-estimated",
                "reason": "No validated aligned section boundary; central crossfade is an estimate."}
    if not sections:
        return fallback
    token = lambda text: re.findall(r"\w+", re.sub(r"\[[^\]\n]{1,80}\]", "", text).casefold())
    try:
        if token(script) != [word for section in sections for word in token(section["text"])]:
            raise ValueError
        previous = 0.
        for section in sections:
            start, end = float(section["start"]), float(section["end"])
            if not math.isfinite(start+end) or start < previous-.02 or not 0 <= start < end <= duration+.05:
                raise ValueError
            previous = end
        candidates = []
        for index in range(1, len(sections)):
            at = (float(sections[index-1]["end"])+float(sections[index]["start"]))/2
            if not max(.75, duration*.15) <= at <= min(duration-.75, duration*.85):
                continue
            before = infer_audio_mood(" ".join(section["text"] for section in sections[:index]), channel=channel)
            after = infer_audio_mood(" ".join(section["text"] for section in sections[index:]), channel=channel)
            candidates.append((before == after, after != profile["closing_mood"], abs(at-duration*.62), at))
        if not candidates:
            return fallback
        no_change, _, _, at = min(candidates)
        return {"transition_at": at,
                "method": "validated-section-boundary" if no_change else "validated-mood-boundary",
                "reason": "Aligned transcript boundary nearest the narrative turn; " + (
                    "no distinct mood change was detected." if no_change else "opening/closing moods differ.")}
    except (ValueError, TypeError, KeyError, AttributeError):
        return {**fallback, "reason": "Section transcript/timing validation failed; central crossfade is an estimate."}


class MusicSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    isrc: str
    title: str
    author: str = "Kevin MacLeod"
    filename: str
    source_url: str
    download_url: str
    license_id: str = "CC-BY-4.0"
    license_url: str = LICENSE
    attribution: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    moods: list[str] = Field(min_length=1)
    channels: list[str] = Field(min_length=1)
    content_id: str = "unknown"
    verified_on: str
    source_feel: str | None = None
    instruments: str | None = None

    @model_validator(mode="after")
    def audited_source(self):
        if self.id not in AUDITED or AUDITED[self.id] != (self.isrc, self.title):
            raise ValueError("Source must be one of the audited tracks")
        if self.author != "Kevin MacLeod" or self.filename != self.title + ".mp3":
            raise ValueError("Unexpected author or filename")
        if self.download_url != BASE + "mp3-royaltyfree/" + quote(self.filename):
            raise ValueError("Only the audited author's exact download URL is accepted")
        if self.source_url != BASE + "index.html?Search=Search&isrc=" + self.isrc:
            raise ValueError("Expected the track's official ISRC source page")
        if self.license_id != "CC-BY-4.0" or self.license_url != LICENSE or self.content_id != "unknown":
            raise ValueError("License must permit commercial use with attribution; Content ID is unverified")
        if not self.attribution or self.title not in self.attribution or self.author not in self.attribution or LICENSE not in self.attribution:
            raise ValueError("Missing attribution or license reference")
        return self


class SoundEvent(BaseModel):
    """A deliberate editorial cue; timing is relative to the requested mix."""
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    time: float = Field(ge=0)
    kind: Literal["soft_tick", "low_pulse", "air_swish", "paper_texture", "key_click", "ui_ping"] = "soft_tick"


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict, *, replace: bool = True) -> tuple[int, int]:
    fd, temporary = tempfile.mkstemp(prefix=".receipt-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
            identity = os.fstat(handle.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError:
                raise AudioLibraryError("A receipt appeared during mixing; it was preserved") from None
        return identity.st_dev, identity.st_ino
    finally:
        Path(temporary).unlink(missing_ok=True)


class AudioLibrary:
    def __init__(self, catalog: Path, cache: Path, *, ffmpeg="ffmpeg", ffprobe="ffprobe", client: httpx.Client | None = None):
        try:
            payload = json.loads(Path(catalog).read_text())
            if payload.get("version") != 1:
                raise ValueError("Unsupported catalog version")
            self.sources = {source.id: source for source in (MusicSource.model_validate(item) for item in payload["sources"])}
            if len(self.sources) != len(payload["sources"]):
                raise ValueError("Duplicate track ID")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, ValidationError) as exc:
            raise AudioLibraryError("Invalid or unapproved music catalog") from exc
        raw_cache = Path(cache).absolute()
        if any(p.is_symlink() for p in (raw_cache, *raw_cache.parents)):
            raise AudioLibraryError("Library directories cannot be symlinks")
        raw_cache.mkdir(parents=True, exist_ok=True)
        self.cache, self.ffmpeg, self.ffprobe = raw_cache, ffmpeg, ffprobe
        self.client = client or httpx.Client(trust_env=False)
        self._owns_client = client is None
        self._pieces = None

    def close(self):
        if self._owns_client:
            self.client.close()

    @contextmanager
    def _lock(self):
        fd = os.open(self.cache / ".library.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise AudioLibraryError("Another audio-library operation is in progress") from None
            yield
        finally:
            os.close(fd)

    def _directory(self, track_id: str) -> Path:
        if track_id not in self.sources:
            raise AudioLibraryError("Unknown track ID")
        directory = self.cache / track_id
        if directory.is_symlink():
            raise AudioLibraryError("Track directories cannot be symlinks")
        directory.mkdir(exist_ok=True)
        if any(path.is_symlink() for path in directory.iterdir()):
            raise AudioLibraryError("Track files cannot be symlinks")
        return directory

    def _get(self, url: str, *, maximum: int) -> bytes:
        allowed = {BASE + "pieces.json"}
        allowed |= {source.source_url for source in self.sources.values()}
        allowed |= {source.download_url for source in self.sources.values()}
        if url not in allowed:
            raise AudioLibraryError("Download URL is not in the audited catalog")
        request = self.client.build_request("GET", url, timeout=40)
        request.headers.pop("authorization", None)
        request.headers.pop("cookie", None)
        try:
            response = self.client.send(request, stream=True, auth=None, follow_redirects=False)
            with closing(response):
                if response.status_code != 200:
                    raise AudioLibraryError(f"Music source returned HTTP {response.status_code}; no redirect or automatic retry")
                length = response.headers.get("content-length")
                if length and (not length.isdigit() or int(length) > maximum):
                    raise AudioLibraryError("Music source exceeds the download size limit")
                result = bytearray()
                for block in response.iter_bytes():
                    result.extend(block)
                    if len(result) > maximum:
                        raise AudioLibraryError("Music source exceeds the download size limit")
                return bytes(result)
        except httpx.HTTPError:
            raise AudioLibraryError("Music download failed; no automatic retry") from None

    def _cached(self, track_id: str) -> dict | None:
        if not (self.cache / track_id).exists():
            return None
        directory, source = self._directory(track_id), self.sources[track_id]
        try:
            receipt = json.loads((directory / "receipt.json").read_text())
            valid = receipt.get("sha256") == source.sha256 and _hash(directory / "music.mp3") == source.sha256
            valid = valid and receipt.get("source") == source.model_dump(exclude_none=True)
            valid = valid and _hash(directory / "license.html") == receipt.get("license_evidence_sha256")
            valid = valid and _hash(directory / "source.json") == receipt.get("track_evidence_sha256")
            if valid:
                return receipt
        except (OSError, ValueError, AttributeError):
            pass
        return None

    def available(self, *, channel: str | None = None, mood: str | None = None) -> list[dict]:
        """Read verified local choices without downloading or changing selections."""
        return [self.describe(source) for source in self.sources.values()
                if (channel is None or channel in source.channels)
                and (mood is None or self._matches_mood(source, mood)) and self._cached(source.id)]

    def preview(self, track_id: str) -> Path:
        """Return one verified local track for an ID-only HTTP route, without writes."""
        if not isinstance(track_id, str) or track_id not in self.sources or not self._cached(track_id):
            raise AudioLibraryError("Music preview missing or changed; fetch the audited source before listening")
        return self.cache / track_id / "music.mp3"

    def narrative_options(self, script: str, *, channel: str = "loose_thread") -> dict:
        """Read eligible opening/closing pools without creating a selection or downloading."""
        if not isinstance(channel, str) or not ID.fullmatch(channel):
            raise AudioLibraryError("Invalid narrative channel ID")
        profile = _narrative_profile(script, channel)
        tracks = self.available(channel=channel)
        opening = [row["id"] for row in tracks if profile["opening_mood"] in row["moods"]]
        closing = [row["id"] for row in tracks if profile["closing_mood"] in row["moods"]]
        eligible = any(a != b for a in opening for b in closing)
        return {**profile, "eligible": eligible, "opening_candidates": opening, "closing_candidates": closing}

    def select_narrative(self, job_id: str, script: str, *, channel: str = "loose_thread") -> dict:
        """Fix two distinct licensed tracks for the opening and closing narrative moods."""
        if not isinstance(job_id, str) or not ID.fullmatch(job_id):
            raise AudioLibraryError("Invalid narrative job ID")
        with self._lock():
            options = self.narrative_options(script, channel=channel)
            state = self._state()
            request = {"channel": channel, "mood": options["opening_mood"], "closing_mood": options["closing_mood"],
                       "count": 2, "method": "narrative-v1", "script_sha256": options["script_sha256"]}
            if job_id in state["jobs"]:
                selection = self._selection(state, job_id)
                if any(selection.get(key) != value for key, value in request.items()):
                    raise AudioLibraryError("This job already has a different audio selection; use a new revision ID")
                if not all(self._cached(track_id) for track_id in selection["tracks"]):
                    raise AudioLibraryError("A selected narrative track is missing or corrupted")
                return selection
            if not options["eligible"]:
                raise AudioLibraryError("Not enough distinct cached licensed tracks for the opening and closing moods")
            previous = state["last"].get(channel)
            pairs = [(a, b) for a in options["opening_candidates"] for b in options["closing_candidates"] if a != b]
            pairs.sort(key=lambda pair: (pair[0] == previous,
                                        hashlib.sha256(f"{job_id}:{channel}:{pair[0]}:{pair[1]}".encode()).hexdigest()))
            tracks = list(pairs[0])
            selection = {"job_id": job_id, **request, "tracks": tracks,
                         "selected_at": datetime.now(timezone.utc).isoformat(),
                         "credits": [self.sources[track].attribution for track in tracks],
                         "changes_notice": "Music trimmed, crossfaded at a declared narrative boundary, mixed and ducked under narration.",
                         "reason": options["reason"], "content_id": "unknown"}
            state["jobs"][job_id] = selection
            state["last"][channel] = tracks[0]
            _atomic_json(self.cache / "selection.json", state)
            return selection

    @staticmethod
    def _matches_mood(source: MusicSource, mood: str) -> bool:
        return mood in source.moods or source.id in AUDIO_AFFINITIES.get(mood, set())

    @staticmethod
    def describe(source: MusicSource) -> dict:
        affinities = [mood for mood, tracks in AUDIO_AFFINITIES.items() if source.id in tracks]
        return {**source.model_dump(exclude_none=True), "moods": list(dict.fromkeys([*source.moods, *affinities])),
                "editorial_affinities": affinities}

    def select_manual(self, job_id: str, track_id: str, *, channel: str = "loose_thread") -> dict:
        """Persist an explicit cached choice with the same revision/lock rules as auto."""
        if not all(isinstance(value, str) and ID.fullmatch(value) for value in (job_id, track_id, channel)):
            raise AudioLibraryError("Expected validated job/channel/track IDs")
        if track_id not in self.sources or channel not in self.sources[track_id].channels:
            raise AudioLibraryError("Unknown track or incompatible channel")
        with self._lock():
            state = self._state()
            if not self._cached(track_id):
                raise AudioLibraryError("The selected track is missing or corrupted")
            if job_id in state["jobs"]:
                selection = self._selection(state, job_id)
                if selection.get("channel") != channel or selection.get("mood") != "manual" or selection["tracks"] != [track_id]:
                    raise AudioLibraryError("This job already has a different audio selection; use a new revision ID")
                return selection
            selection = {"job_id": job_id, "channel": channel, "mood": "manual", "count": 1,
                         "tracks": [track_id], "selected_at": datetime.now(timezone.utc).isoformat(),
                         "credits": [self.sources[track_id].attribution],
                         "changes_notice": "Music trimmed, mixed and dynamically ducked under narration.",
                         "content_id": "unknown"}
            state["jobs"][job_id] = selection
            state["last"][channel] = track_id
            _atomic_json(self.cache / "selection.json", state)
            return selection

    def fetch(self, track_id: str, *, local_file: Path | None = None) -> dict:
        """Download or import a hash-pinned file, verifying current per-track evidence.

        local_file can reuse an already downloaded exact file; it never bypasses
        hash, media, licensing or provenance checks.
        """
        with self._lock():
            cached = self._cached(track_id)
            if cached:
                return {**cached, "cache_hit": True}
            source, directory = self.sources[track_id], self._directory(track_id)
            html = self._get(source.source_url, maximum=512 * 1024)
            if b"By Attribution 4.0 License" not in html or b"creativecommons.org/licenses/by/4.0/" not in html:
                raise AudioLibraryError("The source page no longer confirms the audited CC BY 4.0 license")
            if self._pieces is None:
                try:
                    self._pieces = json.loads(self._get(BASE + "pieces.json", maximum=4 * 1024 * 1024))
                except ValueError:
                    raise AudioLibraryError("The official track catalog is invalid") from None
            if not isinstance(self._pieces, list):
                raise AudioLibraryError("The official track catalog is invalid")
            matches = [item for item in self._pieces if isinstance(item, dict) and item.get("isrc") == source.isrc]
            if len(matches) != 1 or matches[0].get("title") != source.title or matches[0].get("filename") != source.filename:
                raise AudioLibraryError("Official track identity does not match the audited source")
            fd, temporary = tempfile.mkstemp(prefix=".download-", suffix=".mp3", dir=directory)
            os.close(fd)
            temporary = Path(temporary)
            try:
                if local_file is not None:
                    if Path(local_file).stat().st_size > 32 * 1024 * 1024:
                        raise AudioLibraryError("Local music file exceeds size limit")
                    shutil.copyfile(local_file, temporary)
                else:
                    temporary.write_bytes(self._get(source.download_url, maximum=32 * 1024 * 1024))
                if _hash(temporary) != source.sha256:
                    raise AudioLibraryError("Music hash changed; review the source instead of accepting new bytes silently")
                media = probe_media(temporary, self.ffprobe)
                if not media.audio_codec or not 1 <= media.duration <= 1800:
                    raise AudioLibraryError("Downloaded file is not a bounded audio track")
                evidence = json.dumps(matches[0], sort_keys=True).encode()
                (directory / "license.html").write_bytes(html)
                (directory / "source.json").write_bytes(evidence)
                temporary.replace(directory / "music.mp3")
                receipt = {"version": 1, "source": source.model_dump(exclude_none=True), "sha256": source.sha256,
                           "duration": media.duration, "bytes": (directory / "music.mp3").stat().st_size,
                           "fetched_at": datetime.now(timezone.utc).isoformat(),
                           "license_evidence_sha256": hashlib.sha256(html).hexdigest(),
                           "track_evidence_sha256": hashlib.sha256(evidence).hexdigest(),
                           "content_id": "unknown", "commercial_use": "permitted with attribution under CC BY 4.0"}
                _atomic_json(directory / "receipt.json", receipt)
                return {**receipt, "cache_hit": False}
            finally:
                temporary.unlink(missing_ok=True)

    def _state(self) -> dict:
        path = self.cache / "selection.json"
        if path.is_symlink():
            raise AudioLibraryError("Selection state cannot be a symlink")
        try:
            state = json.loads(path.read_text()) if path.exists() else {"version": 1, "jobs": {}, "last": {}}
            if state.get("version") != 1 or not isinstance(state.get("jobs"), dict) or not isinstance(state.get("last"), dict):
                raise ValueError
            return state
        except (OSError, ValueError, AttributeError):
            raise AudioLibraryError("Selection state is invalid; preserve and inspect it") from None

    def select(self, job_id: str, *, channel: str, mood: str, count: int = 2) -> dict:
        if not all(isinstance(value, str) and ID.fullmatch(value) for value in (job_id, channel, mood)) or count not in (1, 2):
            raise AudioLibraryError("Expected validated job/channel/mood IDs and one or two tracks")
        with self._lock():
            state = self._state()
            request = {"channel": channel, "mood": mood, "count": count}
            if job_id in state["jobs"]:
                selection = self._selection(state, job_id)
                if any(selection.get(key) != value for key, value in request.items()):
                    raise AudioLibraryError("This job already has a different audio selection; use a new revision ID")
                if any(not self._cached(track_id) for track_id in selection["tracks"]):
                    raise AudioLibraryError("A selected track is missing or corrupted")
                return selection
            candidates = [source.id for source in self.sources.values()
                          if channel in source.channels and self._matches_mood(source, mood) and self._cached(source.id)]
            if len(candidates) < count:
                raise AudioLibraryError("Not enough cached licensed tracks for this channel and mood; fetch matching tracks first")
            previous = state["last"].get(channel)
            ordered = sorted(candidates, key=lambda value: hashlib.sha256(f"{job_id}:{channel}:{mood}:{value}".encode()).hexdigest())
            if previous in ordered and len(ordered) > 1:
                ordered.remove(previous)
                ordered.append(previous)
            selection = {"job_id": job_id, **request, "tracks": ordered[:count],
                         "selected_at": datetime.now(timezone.utc).isoformat(),
                         "credits": [self.sources[track].attribution for track in ordered[:count]],
                         "changes_notice": "Music trimmed, crossfaded, mixed and dynamically ducked under narration.",
                         "content_id": "unknown"}
            if mood in AUDIO_AFFINITIES:
                selection["mood_basis"] = "Kitok editorial affinity based on the author's instrument/feel descriptions; audition pending."
            state["jobs"][job_id] = selection
            state["last"][channel] = ordered[0]
            _atomic_json(self.cache / "selection.json", state)
            return selection

    def _selection(self, state: dict, job_id: str) -> dict:
        selection = state["jobs"].get(job_id)
        valid = isinstance(selection, dict) and selection.get("job_id") == job_id
        tracks = selection.get("tracks") if valid else None
        valid = valid and isinstance(tracks, list) and len(tracks) in (1, 2)
        valid = valid and all(isinstance(track, str) and track in self.sources for track in tracks)
        if not valid or selection.get("credits") != [self.sources[track].attribution for track in tracks]:
            raise AudioLibraryError("Audio selection is missing or invalid; preserve and inspect its state")
        return selection

    def mix(self, job_id: str, narration: Path, output: Path, *, duration: float,
            offset: float = 0, crossfade: float = 1.5, sfx_events: list[dict] | None = None,
            transition_at: float | None = None) -> dict:
        """Render a separate mix; narration and existing outputs are never overwritten."""
        if not ID.fullmatch(job_id) or not all(math.isfinite(value) for value in (duration, offset, crossfade)):
            raise AudioLibraryError("Invalid audio request")
        if not 3 <= duration <= 7200 or offset < 0 or not .1 <= crossfade <= min(5, duration / 2):
            raise AudioLibraryError("Invalid duration, offset or crossfade")
        if transition_at is not None and (not math.isfinite(transition_at) or not crossfade/2 <= transition_at <= duration-crossfade/2):
            raise AudioLibraryError("Music transition must fit the duration and crossfade")
        try:
            events = [SoundEvent.model_validate(event).model_dump() for event in (sfx_events or [])]
        except (ValidationError, TypeError):
            raise AudioLibraryError("Invalid sound effect event") from None
        if len(events) > 24 or any(event["time"] + .22 > duration for event in events):
            raise AudioLibraryError("Sound effect events must fit inside the mix; maximum 24")
        times = sorted(event["time"] for event in events)
        if any(right - left < 1.5 for left, right in zip(times, times[1:])):
            raise AudioLibraryError("Keep at least 1.5 seconds between discreet sound cues")
        narration, output = Path(narration).resolve(), Path(output).absolute()
        if not narration.is_file() or output.exists() or output.is_symlink() or output.resolve() == narration:
            raise AudioLibraryError("Narration must exist and output must be a new separate file")
        if output.suffix.lower() not in {".m4a", ".wav"}:
            raise AudioLibraryError("Use .m4a or .wav for the separate mix")
        info = probe_media(narration, self.ffprobe)
        if not info.audio_codec or offset + duration > info.duration + .02:
            raise AudioLibraryError("Narration does not cover the requested interval")
        output.parent.mkdir(parents=True, exist_ok=True)
        receipt_path = output.with_suffix(output.suffix + ".json")
        if receipt_path.exists() or receipt_path.is_symlink():
            raise AudioLibraryError("Output receipt already exists")
        narration_sha256 = _hash(narration)
        with self._lock(), tempfile.TemporaryDirectory(prefix=".audio-mix-", dir=output.parent) as workspace:
            selection = self._selection(self._state(), job_id)
            if not all(self._cached(track_id) for track_id in selection["tracks"]):
                raise AudioLibraryError("Select verified cached tracks before mixing")
            inputs = [self.ffmpeg, "-nostdin", "-hide_banner", "-y", "-ss", f"{offset:.6f}", "-i", str(narration)]
            for track_id in selection["tracks"]:
                inputs += ["-stream_loop", "-1", "-i", str(self._directory(track_id) / "music.mp3")]
            effect_receipts = []
            for index, event in enumerate(events):
                path = Path(workspace) / f"sfx-{index}.wav"
                effect_receipts.append({**synthesize_sfx(path, kind=event["kind"]), "time": event["time"]})
                inputs += ["-i", str(path)]
            if transition_at is not None and len(selection["tracks"]) != 2:
                raise AudioLibraryError("A narrative transition requires two selected tracks")
            chain = self._mix_filter(duration, crossfade, len(selection["tracks"]), events, transition_at)
            analysis_filter = chain + ";[mixed]loudnorm=I=-16:LRA=7:TP=-1.8:print_format=json[analysis]"
            analysis = self._run(inputs + ["-filter_complex", analysis_filter, "-map", "[analysis]", "-vn", "-t", str(duration), "-f", "null", "-"], "mix analysis")
            measured = parse_loudnorm_measurement(analysis.stderr)
            if not all(math.isfinite(value) for value in (measured.input_i, measured.input_lra, measured.input_tp, measured.input_thresh, measured.target_offset)):
                raise AudioLibraryError("Cannot normalize silent or non-finite audio")
            normalize = (f"loudnorm=I=-16:LRA=7:TP=-1.8:measured_I={measured.input_i}:"
                         f"measured_LRA={measured.input_lra}:measured_TP={measured.input_tp}:"
                         f"measured_thresh={measured.input_thresh}:offset={measured.target_offset}:linear=true")
            temporary = Path(workspace) / ("mixed" + output.suffix.lower())
            codec = ["-c:a", "aac", "-b:a", "192k"] if output.suffix.lower() == ".m4a" else ["-c:a", "pcm_s16le"]
            self._run(inputs + ["-filter_complex", chain + ";[mixed]" + normalize + "[out]", "-map", "[out]", "-vn", "-t", str(duration),
                                "-ar", "48000", "-ac", "2", *codec, str(temporary)], "audio mix")
            final_info, loudness = probe_media(temporary, self.ffprobe), measure_loudness(temporary, self.ffmpeg)
            if abs(final_info.duration - duration) > .08 or not all(isinstance(loudness.get(key), (int, float)) and math.isfinite(loudness[key])
                    for key in ("integrated_lufs", "true_peak_dbtp", "loudness_range_lu")):
                raise AudioLibraryError("Audio duration or loudness validation failed")
            if abs(loudness["integrated_lufs"] + 16) > 1 or loudness["true_peak_dbtp"] > -1.5:
                raise AudioLibraryError("Measured mix does not meet -16 LUFS / -1.5 dBTP")
            if _hash(narration) != narration_sha256:
                raise AudioLibraryError("Narration changed during mixing; no output was promoted")
            source_receipts = [self._cached(track_id) for track_id in selection["tracks"]]
            if not all(source_receipts):
                raise AudioLibraryError("A music source changed during mixing; no output was promoted")
            receipt = {"version": 1, "job_id": job_id, "selection": selection,
                       "narration_sha256": narration_sha256, "narration_offset": offset,
                       "duration": final_info.duration, "crossfade_seconds": crossfade if len(selection["tracks"]) == 2 else 0,
                       "transition_at": (duration/2 if transition_at is None else transition_at) if len(selection["tracks"]) == 2 else None,
                       "ducking": {"threshold": .012, "ratio": 8, "attack_ms": 15, "release_ms": 300},
                       "target_lufs": -16, "target_true_peak_dbtp": -1.5, "encoding_headroom_db": .3,
                       "measured": loudness, "output_sha256": _hash(temporary),
                       "sources": source_receipts,
                       "sound_effects": effect_receipts,
                       "filter": chain, "created_at": datetime.now(timezone.utc).isoformat()}
            owned_receipt = _atomic_json(receipt_path, receipt, replace=False)
            try:
                # Prevent replacing a result that appeared while FFmpeg was running.
                os.link(temporary, output)
            except FileExistsError:
                try:
                    present = receipt_path.lstat()
                    if (present.st_dev, present.st_ino) == owned_receipt:
                        receipt_path.unlink()
                except FileNotFoundError:
                    pass
                raise AudioLibraryError("Output appeared during mixing; it was preserved") from None
            return receipt

    @staticmethod
    def _mix_filter(duration: float, crossfade: float, count: int, events: list[dict] | None = None,
                    transition_at: float | None = None) -> str:
        filters = [f"[0:a]atrim=duration={duration:.6f},asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
                   "loudnorm=I=-19:LRA=7:TP=-3,aresample=48000,asplit=2[voice][key]"]
        for index in range(count):
            center = duration/2 if transition_at is None else transition_at
            segment = (center if index == 0 else duration-center) + crossfade/2 if count == 2 else duration
            filters.append(f"[{index+1}:a]atrim=duration={segment:.6f},asetpts=PTS-STARTPTS,"
                           "aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=60,lowpass=f=6500,"
                           f"loudnorm=I=-29:LRA=11:TP=-8,aresample=48000[m{index}]")
        filters.append(f"[m0][m1]acrossfade=d={crossfade:.6f}:c1=tri:c2=tri[bed]" if count == 2 else "[m0]anull[bed]")
        filters += ["[bed][key]sidechaincompress=threshold=0.012:ratio=8:attack=15:release=300:makeup=1[ducked]",
                    f"[ducked]afade=t=in:d=0.08,afade=t=out:st={duration-.4:.6f}:d=0.4[bedfaded]"]
        labels = "[voice][bedfaded]"
        for index, event in enumerate(events or []):
            filters.append(f"[{count+index+1}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                           f"volume=0.65,adelay={round(event['time']*1000)}:all=1[sfx{index}]")
            labels += f"[sfx{index}]"
        filters.append(labels + f"amix=inputs={2+len(events or [])}:duration=first:normalize=0[mixed]")
        return ";".join(filters)

    @staticmethod
    def _run(command: list[str], label: str) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(command, capture_output=True, text=True, check=True, timeout=3600)
        except (OSError, subprocess.SubprocessError) as exc:
            raise AudioLibraryError(f"FFmpeg failed during {label}") from exc


def synthesize_sfx(output: Path, *, kind: str = "soft_tick", duration: float = .22) -> dict:
    """A quiet original Kitok sound, independent of external recordings/models."""
    import struct
    if kind not in SFX_KINDS or not math.isfinite(duration) or not .05 <= duration <= 1:
        raise AudioLibraryError("Unknown or excessive sound effect")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    rate, frequency = 48000, (900 if kind == "soft_tick" else 90)
    noise = random.Random(76129)
    low = 0.0
    fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    with os.fdopen(fd, "wb") as raw, wave.open(raw, "wb") as writer:
        writer.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        frames = bytearray()
        for index in range(round(duration * rate)):
            t = index / rate
            envelope = math.sin(math.pi * min(1, t / .008) / 2) ** 2 * math.exp(-7 * t / duration)
            if kind in {"soft_tick", "low_pulse"}:
                value = .07 * envelope * math.sin(2 * math.pi * frequency * t)
            elif kind == "ui_ping":
                value = .055 * envelope * (.65 * math.sin(2*math.pi*660*t) + .25*math.sin(2*math.pi*990*t)
                                            + .1*math.sin(2*math.pi*1320*t))
            else:
                sample = noise.uniform(-1, 1)
                low += .12 * (sample - low)
                high = sample - low
                if kind == "air_swish":
                    value = .045 * math.sin(math.pi*t/duration)**2 * (.65*high + .35*low)
                elif kind == "paper_texture":
                    bursts = sum(math.exp(-((t/duration-center)/.085)**2) for center in (.2,.5,.78))
                    value = .04 * min(1,bursts) * high
                else:  # key_click: a quiet contact transient, not a recording of a keyboard.
                    value = .055 * envelope * (.55*high + .3*math.sin(2*math.pi*700*t)
                                               + .15*math.sin(2*math.pi*1800*t))
            # All families finish at zero; the historical tick/pulse waveforms stay unchanged.
            if kind not in {"soft_tick", "low_pulse"}:
                value *= min(1, max(0, (duration-t)/.008))
            frames.extend(struct.pack("<h", round(value * 32767)))
        writer.writeframes(frames)
    return {"author": "Kitok", "origin": "original procedural synthesis", "kind": kind,
            "duration": duration, "sha256": _hash(output), "external_samples": False}
