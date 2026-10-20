"""Read-only verified Fish metadata and local, reusable voice preferences.

No speech endpoint, model creation, cloning or sample download is used here.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re

import httpx

from .state import write_json_atomic


DEFAULT_REFERENCE = "e686ae649ee44f219a108aacba206c1a"
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}\Z")


class VoiceLibraryError(RuntimeError):
    pass


def discover_fish_voices(api_key: str, *, language: str = "en", limit: int = 10,
                         reference_id: str | None = None, client: httpx.Client | None = None) -> list[dict]:
    """One bounded official GET, with no retry, synthesis, cloning or catalog mutation."""
    if not api_key or not re.fullmatch(r"[a-z]{2}", language) or not 1 <= limit <= 100:
        raise VoiceLibraryError("Expected an API key, two-letter language and limit 1–100")
    if reference_id is not None and not re.fullmatch(r"[a-f0-9]{32}", reference_id):
        raise VoiceLibraryError("Invalid Fish reference ID")
    own_client = client is None
    client = client or httpx.Client(trust_env=False)
    url = "https://api.fish.audio/model" + ("/" + reference_id if reference_id else "")
    params = None if reference_id else {"licensed": "true", "language": language, "page_size": limit, "page_number": 1}
    try:
        with client.stream("GET", url, params=params, headers={"Authorization": "Bearer " + api_key},
                           timeout=30, follow_redirects=False) as response:
            if response.status_code != 200:
                raise VoiceLibraryError(f"Fish metadata HTTP {response.status_code}; no redirect or retry")
            data = bytearray()
            for block in response.iter_bytes():
                data.extend(block)
                if len(data) > 2 * 1024 * 1024:
                    raise VoiceLibraryError("Fish metadata exceeds size limit")
        payload = json.loads(data)
        models = [payload] if reference_id else payload["items"]
        result = []
        for model in models:
            if not reference_id and model.get("licensed") is not True:
                continue
            result.append({"reference_id": model["_id"], "display_name": model["title"],
                           "languages": model.get("languages", []), "tags": model.get("tags", []),
                           "api_licensed": model.get("licensed") is True, "state": model.get("state"),
                           "taken_down": model.get("dmca_taken_down"), "release_state": model.get("pvc_release_state"),
                           "requires_editorial_review": True})
        return result
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise VoiceLibraryError("Fish metadata request or response failed; no synthesis was requested") from None
    finally:
        if own_client:
            client.close()


class VoiceLibrary:
    def __init__(self, catalog: Path, preferences: Path):
        try:
            payload = json.loads(Path(catalog).read_text())
            voices = payload["voices"]
            if payload["version"] != 1 or not isinstance(voices, list):
                raise ValueError
            self.voices = {voice["id"]: voice for voice in voices}
            if len(self.voices) != len(voices):
                raise ValueError
            for slug, voice in self.voices.items():
                if not _ID.fullmatch(slug) or not re.fullmatch(r"[0-9a-f]{32}", voice["reference_id"]):
                    raise ValueError
                if voice["selectable"] != (voice["api_licensed"] is True or voice["reference_id"] == DEFAULT_REFERENCE):
                    raise ValueError
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise VoiceLibraryError("Invalid voice catalog") from None
        self.preferences = Path(preferences).absolute()
        if any(path.is_symlink() for path in (self.preferences, *self.preferences.parents)):
            raise VoiceLibraryError("Voice preferences cannot use symlinks")

    def _state(self) -> dict:
        try:
            if self.preferences.is_symlink():
                raise ValueError
            state = json.loads(self.preferences.read_text()) if self.preferences.exists() else {
                "version": 1, "favorites": [], "assignments": {"loose_thread": "baseline"}}
            if state["version"] != 1 or not isinstance(state["favorites"], list) or not isinstance(state["assignments"], dict):
                raise ValueError
            if any(slug not in self.voices for slug in state["favorites"]):
                raise ValueError
            for channel, slug in state["assignments"].items():
                if not _ID.fullmatch(channel) or slug not in self.voices or not self.voices[slug]["selectable"]:
                    raise ValueError
            return state
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise VoiceLibraryError("Invalid voice preferences; preserve and inspect the file") from None

    @contextmanager
    def _lock(self):
        self.preferences.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.preferences.with_suffix(".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise VoiceLibraryError("Another voice preference operation is in progress") from None
            yield
        finally:
            os.close(fd)

    def list(self) -> list[dict]:
        state = self._state()
        return [{**voice, "favorite": slug in state["favorites"],
                 "assigned_channels": [channel for channel, value in state["assignments"].items() if value == slug]}
                for slug, voice in self.voices.items()]

    def favorite(self, slug: str, enabled: bool = True) -> None:
        if slug not in self.voices:
            raise VoiceLibraryError("Unknown voice ID")
        with self._lock():
            state = self._state()
            state["favorites"] = sorted((set(state["favorites"]) | {slug}) if enabled else (set(state["favorites"]) - {slug}))
            write_json_atomic(self.preferences, state)

    def assign(self, channel: str, slug: str) -> None:
        if not isinstance(channel, str) or not _ID.fullmatch(channel) or slug not in self.voices:
            raise VoiceLibraryError("Unknown voice or invalid channel ID")
        if not self.voices[slug]["selectable"]:
            raise VoiceLibraryError("New assignments require Fish licensed metadata or the existing operator default")
        with self._lock():
            state = self._state()
            state["assignments"][channel] = slug
            write_json_atomic(self.preferences, state)

    def assigned(self, channel: str) -> dict | None:
        slug = self._state()["assignments"].get(channel)
        return self.voices[slug] if slug else None

    def sample(self, slug: str, index: int, *, root: Path) -> Path:
        """Resolve a catalogued, hash-pinned preview for an ID-based HTTP route."""
        try:
            if index < 0:
                raise ValueError
            sample = self.voices[slug]["samples"][index]
            root = Path(root).resolve()
            path = root / sample["path"]
            if any(parent.is_symlink() for parent in (path, *path.parents)):
                raise ValueError
            resolved = path.resolve()
            allowed = (root / "outputs/voice-tests", root / "cache/voice-library")
            if not any(resolved.is_relative_to(directory) for directory in allowed) or resolved.suffix != ".mp3":
                raise ValueError
            if not resolved.is_file() or hashlib.sha256(resolved.read_bytes()).hexdigest() != sample["sha256"]:
                raise ValueError
            return resolved
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            raise VoiceLibraryError("Voice preview missing, changed or outside controlled library directories") from None
