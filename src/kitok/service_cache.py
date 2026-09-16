"""Account-scoped service caches using StateStore's atomic persistence."""
from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path

from .state import StateStore


class ServiceCache:
    def __init__(self, path: Path, scope: str, *, persist: bool = True):
        self.path, self.scope, self.persist = path, scope, persist
        self.memory: dict[str, dict] = {}

    def get(self, name: str) -> dict:
        """Read a snapshot; no directories, network requests or writes."""
        if name in self.memory:
            return deepcopy(self.memory[name])
        return StateStore(self.path, create_parent=False).cache_get(f"{self.scope}:{name}")

    def put(self, name: str, data: dict) -> None:
        """Save locally, or only in memory for read-only live previews."""
        if self.persist:
            StateStore(self.path, create_parent=False).cache_put(f"{self.scope}:{name}", data)
        else:
            self.memory[name] = deepcopy(data)


def buffer_cache(settings, *, persist: bool = True, path: Path | None = None) -> ServiceCache:
    """Scope cache to credentials and channel configuration, without storing secrets."""
    identity = repr((settings.buffer_api_key.get_secret_value(), settings.buffer_organization_id,
                     settings.buffer_channel_ids))
    scope = "buffer-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
    return ServiceCache(path or settings.cache_path, scope, persist=persist)


def cloudinary_cache(settings, *, path: Path | None = None) -> ServiceCache:
    """Use a separate namespace for each Cloudinary product environment."""
    identity = settings.cloudinary_cloud_name + settings.cloudinary_api_key.get_secret_value()
    return ServiceCache(path or settings.cache_path,
                        "cloudinary-" + hashlib.sha256(identity.encode()).hexdigest()[:24])
