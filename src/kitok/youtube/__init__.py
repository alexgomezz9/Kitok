"""Official local YouTube integration. Read-only APIs, no uploading capability."""

from .oauth import SCOPES, PrivateStore, YouTubeError, connect
from .client import YouTubeReadOnly

__all__ = ["SCOPES", "PrivateStore", "YouTubeError", "YouTubeReadOnly", "connect"]
