"""Direct Fish TTS: one POST per attempt, durable uncertainty and reusable audio."""
from __future__ import annotations

import base64
from contextlib import contextmanager, ExitStack
import fcntl
import hashlib
import json
import math
from pathlib import Path
import shutil
import uuid

import httpx

from .state import write_json_atomic


class FishVoiceError(RuntimeError):
    pass


def _looks_like_mp3(data: bytes) -> bool:
    return data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == destination.resolve():
        return
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.part")
    try:
        shutil.copyfile(source, temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _locked(path: Path):
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise FishVoiceError("This Fish request is already running; no second POST was sent") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class FishVoiceClient:
    def __init__(self, api_key: str, model: str = "s2.1-pro-free", *,
                 timeout: float = 180, attempts: int = 1, client: httpx.Client | None = None,
                 cache_dir: Path | None = None, timestamps: bool = False, ffprobe: str = "ffprobe"):
        self.api_key, self.model = api_key, model
        # attempts is accepted for source compatibility, never used to retry paid POSTs.
        self.attempts = 1
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.timestamps = timestamps
        self.ffprobe = ffprobe
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=timeout, write=30.0, pool=10.0)
        )
        self._owns_client = client is None
        self.last_cache_hit = False

    def close(self):
        if self._owns_client:
            self.client.close()

    def synthesize(self, text: str, reference_id: str, destination: Path, *,
                   speed: float | None = None, temperature: float | None = None,
                   top_p: float | None = None, normalize_loudness: bool | None = None) -> Path:
        if not text.strip() or not reference_id:
            raise FishVoiceError("Fish synthesis needs text and a reference ID")
        # Unknown models can fall back to a different paid model at the provider.
        if self.model not in {"s1", "s2-pro", "s2.1-pro", "s2.1-pro-free", "drama-3"}:
            raise FishVoiceError("Unsupported Fish model; choose an explicitly documented model")
        body = {"text": text, "reference_id": reference_id, "format": "mp3"}
        if temperature is not None:
            body["temperature"] = _bounded_number(temperature, "temperature", 0.0, 1.0)
        if top_p is not None:
            body["top_p"] = _bounded_number(top_p, "top_p", 0.0, 1.0)
        if speed is not None or normalize_loudness is not None:
            prosody = {}
            if speed is not None:
                prosody["speed"] = _bounded_number(speed, "speed", 0.5, 2.0)
            if normalize_loudness is not None:
                if not isinstance(normalize_loudness, bool):
                    raise FishVoiceError("Fish normalize_loudness must be true or false")
                prosody["normalize_loudness"] = normalize_loudness
            body["prosody"] = prosody
        self.last_cache_hit = False
        if self.cache_dir is None:
            # Callers without a cache still never retry a mutating request.
            self._request(body, Path(destination))
            return Path(destination)
        def fingerprint_for(identity):
            return hashlib.sha256(json.dumps(
                identity, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
            ).encode()).hexdigest()

        # Timestamps affect response metadata, not the identity of paid speech.
        fingerprint = fingerprint_for({"version": 2, "model": self.model, "body": body})
        folder = self.cache_dir / fingerprint[:2] / fingerprint
        folder.mkdir(parents=True, exist_ok=True)
        audio, ledger = folder / "audio.mp3", folder / "operation.json"
        legacy_folders = []
        for timestamps in (self.timestamps, not self.timestamps):
            old_hash = fingerprint_for({"version": 1, "model": self.model,
                                        "timestamps": timestamps, "body": body})
            old_folder = self.cache_dir / old_hash[:2] / old_hash
            if old_folder.exists():
                legacy_folders.append(old_folder)
        with ExitStack() as locks:
            locks.enter_context(_locked(folder / "request.lock"))
            # Also respect a request started by the previous cache implementation.
            for old_folder in sorted(legacy_folders):
                locks.enter_context(_locked(old_folder / "request.lock"))
            cached = None
            needs_review = False
            uncertain = False
            for candidate in (folder, *legacy_folders):
                candidate_audio, candidate_ledger = candidate / "audio.mp3", candidate / "operation.json"
                record = json.loads(candidate_ledger.read_text()) if candidate_ledger.exists() else {}
                if not candidate_audio.is_file():
                    uncertain |= record.get("status") in {"submitted", "unknown", "succeeded"}
                    continue
                # Complete atomic audio may survive a crash before ledger confirmation.
                try:
                    from .media.ffprobe import probe_media
                    info = probe_media(candidate_audio, self.ffprobe)
                    valid = bool(info.audio_codec and info.duration > 0)
                except RuntimeError:
                    valid = False
                if not valid or (record.get("audio_sha256") and record["audio_sha256"] != _digest(candidate_audio)):
                    needs_review = True
                    continue
                cached = candidate_audio
                break
            if cached is not None:
                if cached != audio:
                    _copy(cached, audio)
                    alignment = cached.with_suffix(".alignment.json")
                    if alignment.exists():
                        _copy(alignment, audio.with_suffix(".alignment.json"))
                self.last_cache_hit = True
                write_json_atomic(ledger, {"status": "succeeded", "request_hash": fingerprint,
                                          "audio_sha256": _digest(audio), "model": self.model})
            elif needs_review or uncertain:
                if needs_review:
                    raise FishVoiceError("Cached Fish audio needs review; it will not be synthesized again automatically")
                raise FishVoiceError(
                    "Fish result is uncertain or its audio is missing. Review the provider and audio cache; "
                    "no new POST was sent. Do not erase the operation to force a retry."
                )
            else:
                if not self.api_key:
                    raise FishVoiceError("FISH_API_KEY is required for new audio")
                write_json_atomic(ledger, {"status": "submitted", "request_hash": fingerprint, "model": self.model})
                try:
                    self._request(body, audio)
                    from .media.ffprobe import probe_media
                    if not probe_media(audio, self.ffprobe).audio_codec:
                        raise FishVoiceError("Fish returned audio that could not be decoded")
                    write_json_atomic(ledger, {"status": "succeeded", "request_hash": fingerprint,
                                              "audio_sha256": _digest(audio), "model": self.model})
                except Exception:
                    # A transport error, bad response or local commit failure can follow a charge.
                    write_json_atomic(ledger, {"status": "unknown", "request_hash": fingerprint, "model": self.model})
                    raise
            _copy(audio, Path(destination))
            alignment = audio.with_suffix(".alignment.json")
            if alignment.exists():
                _copy(alignment, Path(destination).with_suffix(".alignment.json"))
        return Path(destination)

    def _request(self, body: dict, destination: Path) -> None:
        if not self.api_key:
            raise FishVoiceError("FISH_API_KEY is required for new audio")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.part")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                   "model": self.model}
        endpoint = "https://api.fish.audio/v1/tts"
        try:
            if self.timestamps:
                alignment = self._stream(endpoint + "/stream/with-timestamp", headers, body, temporary)
            else:
                response = self.client.post(endpoint, headers=headers, json=body)
                if response.status_code >= 400:
                    raise FishVoiceError(f"Fish TTS returned HTTP {response.status_code}; not retried")
                if not _looks_like_mp3(response.content):
                    raise FishVoiceError("Fish TTS returned no valid audio; not retried")
                temporary.write_bytes(response.content)
                alignment = None
            temporary.replace(destination)
            if alignment is not None:
                write_json_atomic(destination.with_suffix(".alignment.json"), alignment)
        except (httpx.TimeoutException, httpx.TransportError):
            raise FishVoiceError("Fish TTS result is uncertain after a network failure; not retried") from None
        finally:
            temporary.unlink(missing_ok=True)

    def _stream(self, endpoint, headers, body, temporary) -> dict:
        snapshots = {}
        with self.client.stream("POST", endpoint, headers=headers, json=body) as response:
            if response.status_code >= 400:
                raise FishVoiceError(f"Fish TTS returned HTTP {response.status_code}; not retried")
            with temporary.open("wb") as target:
                event_lines = []
                for line in response.iter_lines():
                    if line.startswith("data:"):
                        event_lines.append(line[5:].lstrip())
                    elif not line and event_lines:
                        self._consume_event("\n".join(event_lines), target, snapshots)
                        event_lines = []
                if event_lines:
                    self._consume_event("\n".join(event_lines), target, snapshots)
        if not temporary.is_file() or not _looks_like_mp3(temporary.read_bytes()[:3]):
            raise FishVoiceError("Fish stream returned no valid audio; not retried")
        words = [word for seq in sorted(snapshots) for word in snapshots[seq]]
        return {"method": "fish_provider_timestamps" if words else "missing_provider_timestamps",
                "precision": "unmeasured", "confidence": None, "words": words}

    @staticmethod
    def _consume_event(data: str, target, snapshots: dict) -> None:
        if data.strip() == "[DONE]":
            return
        try:
            event = json.loads(data)
            if event.get("error"):
                raise ValueError("provider error")
            if event.get("audio_base64"):
                target.write(base64.b64decode(event["audio_base64"], validate=True))
            alignment = event.get("alignment")
            if alignment is not None:
                seq = int(event["chunk_seq"])
                offset = float(event["chunk_audio_offset_sec"])
                if not math.isfinite(offset) or offset < 0 or seq < 0:
                    raise ValueError("invalid offset")
                rows = []
                for segment in alignment["segments"]:
                    start, end = offset + float(segment["start"]), offset + float(segment["end"])
                    if not math.isfinite(start + end) or start < offset or end < start:
                        raise ValueError("invalid alignment")
                    rows.append({"word": str(segment["text"]), "start": start, "end": end})
                snapshots[seq] = rows
        except (ValueError, KeyError, TypeError):
            raise FishVoiceError("Invalid Fish timestamp stream; result requires review, not retry") from None


def _bounded_number(value: float, label: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FishVoiceError(f"Fish {label} must be a number") from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise FishVoiceError(f"Fish {label} must be between {minimum:g} and {maximum:g}")
    return number
