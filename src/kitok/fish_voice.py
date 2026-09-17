"""Direct Fish TTS for dialogue turns; never exposes credentials in errors."""
from __future__ import annotations

import time
from pathlib import Path
import httpx


class FishVoiceError(RuntimeError):
    pass


def _looks_like_mp3(data: bytes) -> bool:
    return data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0)


class FishVoiceClient:
    def __init__(self, api_key: str, model: str = "s2.1-pro-free", *,
                 timeout: float = 45, attempts: int = 3, client: httpx.Client | None = None):
        self.api_key, self.model, self.attempts = api_key, model, attempts
        self.client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def close(self):
        if self._owns_client:
            self.client.close()

    def synthesize(self, text: str, reference_id: str, destination: Path) -> Path:
        if not self.api_key:
            raise FishVoiceError("FISH_API_KEY is required for dialogue audio")
        if not text.strip() or not reference_id:
            raise FishVoiceError("Fish synthesis needs text and a reference ID")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                   "model": self.model}
        body = {"text": text, "reference_id": reference_id, "format": "mp3"}
        try:
            for attempt in range(self.attempts):
                try:
                    response = self.client.post("https://api.fish.audio/v1/tts", headers=headers, json=body)
                    if (response.status_code == 429 or 500 <= response.status_code <= 599) and attempt + 1 < self.attempts:
                        time.sleep(min(2 ** attempt, 4))
                        continue
                    if response.status_code >= 400:
                        raise FishVoiceError(f"Fish TTS returned HTTP {response.status_code}")
                    if not _looks_like_mp3(response.content):
                        raise FishVoiceError("Fish TTS returned no valid audio")
                    temporary.write_bytes(response.content)
                    temporary.replace(destination)
                    return destination
                except (httpx.TimeoutException, httpx.TransportError) as error:
                    if attempt + 1 >= self.attempts:
                        raise FishVoiceError("Fish TTS network request failed after retries") from None
                    time.sleep(min(2 ** attempt, 4))
            raise FishVoiceError("Fish TTS request failed")
        finally:
            temporary.unlink(missing_ok=True)
