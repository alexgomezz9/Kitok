"""Host a finished video once; retain public media indefinitely."""
from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse


class HostingError(RuntimeError):
    pass


def require_https(url: str) -> str:
    """Validate a public asset URL without requesting it."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HostingError("Cloudinary must return a public HTTPS URL")
    return url


class CloudinaryHost:
    def __init__(self, settings, state, *, uploader=None, lookup=None, usage=None):
        self.s, self.state = settings, state
        self._upload, self._lookup = uploader, lookup
        from .cloudinary_usage import CloudinaryUsage
        from .service_cache import cloudinary_cache
        self.usage = usage or CloudinaryUsage(settings, cache=cloudinary_cache(
            settings, path=state.path.with_name("services.json")))

    def _sdk(self):
        if self._upload is not None and self._lookup is not None:
            return
        if not (self.s.cloudinary_cloud_name and self.s.cloudinary_api_key.get_secret_value()
                and self.s.cloudinary_api_secret.get_secret_value()):
            raise HostingError("Configure CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET")
        try:
            import cloudinary.uploader
            import cloudinary.api
        except ImportError:
            raise HostingError('Install dependencies: pip install -e ".[dev]"') from None
        options = {"cloud_name": self.s.cloudinary_cloud_name,
                   "api_key": self.s.cloudinary_api_key.get_secret_value(),
                   "api_secret": self.s.cloudinary_api_secret.get_secret_value(), "secure": True}
        self._upload = lambda path, **kw: cloudinary.uploader.upload_large(path, **options, **kw)
        self._lookup = lambda public_id, **kw: cloudinary.api.resource(public_id, **options, **kw)

    def ensure_video(self, content_id: str, path: Path) -> dict:
        """Reuse or reconcile an asset; new uploads require publishing and usage permission."""
        if not self.s.publish_enabled:
            raise HostingError("Publishing disabled: Cloudinary upload forbidden")
        current = self.state.get(content_id).get("publishing", {}).get("cloudinary", {})
        if current.get("url") and current.get("public_id"):
            require_https(current["url"])
            return current
        self._sdk()
        if current.get("status") in {"uploading", "unknown"}:
            # A crash/timeout may follow a completed upload. Read back the saved
            # deterministic ID; never resend the bytes automatically.
            try:
                result = self._lookup(current["public_id"], resource_type="video", type="upload")
            except Exception:
                raise HostingError("Cloudinary upload unresolved; inspect the saved public_id before retrying") from None
        else:
            self.usage.reserve_upload(path)
            with path.open("rb") as video:
                digest = hashlib.file_digest(video, "sha256").hexdigest()
            public_id = f"kitok/{content_id}-{digest}"
            self.state.update_publishing(content_id, "cloudinary", public_id=public_id,
                                         status="uploading", sha256=digest, last_error=None)
            try:
                result = self._upload(str(path), resource_type="video", type="upload",
                                      public_id=public_id, overwrite=False)
            except Exception:
                self.state.update_publishing(content_id, "cloudinary", status="unknown",
                                             last_error="Upload outcome unknown; reconcile public_id")
                raise HostingError("Cloudinary upload outcome unknown; no automatic upload retry") from None
        try:
            url = require_https(result["secure_url"])
            public_id = result["public_id"]
            if public_id != self.state.get(content_id)["publishing"]["cloudinary"]["public_id"]:
                raise ValueError
        except (KeyError, TypeError, ValueError, HostingError):
            self.state.update_publishing(content_id, "cloudinary", status="unknown",
                                         last_error="Invalid Cloudinary response; reconcile public_id")
            raise HostingError("Cloudinary returned incomplete or unexpected media details") from None
        self.state.update_publishing(content_id, "cloudinary", public_id=public_id, url=url,
                                     secure_url=url, status="uploaded", last_error=None)
        return self.state.get(content_id)["publishing"]["cloudinary"]
