"""Official local YouTube integration. Reading by default; explicit management CLI and OAuth profiles."""

from .oauth import SCOPES, PrivateStore, YouTubeError, connect
from .client import YouTubeReadOnly

__all__ = ["SCOPES", "PrivateStore", "YouTubeError", "YouTubeReadOnly", "connect"]
