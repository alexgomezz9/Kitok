"""Explicit Cloudinary Admin API usage reads and a local upload safety guard."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

from .service_cache import cloudinary_cache


class CloudinaryUsage:
    def __init__(self, settings, *, cache=None, fetch=None):
        self.s = settings
        self.cache = cache or cloudinary_cache(settings)
        self.fetch = fetch

    def cached(self) -> dict:
        """Read last usage without contacting Cloudinary or writing files."""
        return self.cache.get("usage")

    def refresh(self) -> dict:
        """Perform one Admin usage read and cache it; never uploads or changes plans."""
        from .cloudinary_host import HostingError
        if self.fetch is None:
            if not (self.s.cloudinary_cloud_name and self.s.cloudinary_api_key.get_secret_value()
                    and self.s.cloudinary_api_secret.get_secret_value()):
                raise HostingError("Configure Cloudinary credentials before refreshing usage")
            import cloudinary.api
            fetch = lambda: cloudinary.api.usage(
                cloud_name=self.s.cloudinary_cloud_name,
                api_key=self.s.cloudinary_api_key.get_secret_value(),
                api_secret=self.s.cloudinary_api_secret.get_secret_value(), secure=True)
        else:
            fetch = self.fetch
        try:
            response = fetch()
            if not isinstance(response, dict):
                raise ValueError("Unexpected usage response")
        except Exception:
            raise HostingError("Cloudinary usage refresh failed; check credentials or Admin API quota") from None
        # Store only documented usage categories, never credentials or arbitrary fields.
        data = {key: response[key] for key in
                ("plan", "last_updated", "credits", "storage", "bandwidth", "transformations",
                 "requests", "resources", "rate_limit_allowed", "rate_limit_remaining", "rate_limit_reset_at")
                if key in response}
        report = {"data": data, "refreshed_at": datetime.now(timezone.utc).isoformat()}
        self.cache.put("usage", report)
        return report

    def require_upload_budget(self, path: Path) -> None:
        """Block new uploads at known limits, or unknown/stale usage when guard is on."""
        from .cloudinary_host import HostingError
        report = self.cached()
        if self.s.cloudinary_usage_guard:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(report["refreshed_at"])).total_seconds()
                if age < 0 or age > self.s.cloudinary_usage_max_age_seconds:
                    raise ValueError
            except (KeyError, ValueError, TypeError):
                raise HostingError("Cloudinary usage is unknown or stale. Refresh Cloudinary usage before uploading.") from None
        known_limit = False
        for name in ("credits", "storage", "bandwidth", "transformations"):
            metric = report.get("data", {}).get(name, {})
            if not isinstance(metric, dict):
                continue
            try:
                usage, limit = float(metric["usage"]), float(metric["limit"])
                if not math.isfinite(usage) or not math.isfinite(limit) or limit <= 0:
                    continue
            except (KeyError, TypeError, ValueError):
                continue
            known_limit = True
            if name == "storage":
                usage += path.stat().st_size + report.get("reserved_upload_bytes", 0)
            if usage >= limit * self.s.cloudinary_usage_threshold:
                raise HostingError(f"Cloudinary {name} is at the {self.s.cloudinary_usage_threshold:.0%} safety threshold; new uploads stopped")
        if self.s.cloudinary_usage_guard and not known_limit:
            raise HostingError("Cloudinary did not return a usable usage limit; inspect usage before uploading")

    def reserve_upload(self, path: Path) -> None:
        """Check limits and reserve local bytes until the next explicit usage refresh."""
        self.require_upload_budget(path)
        report = self.cached()
        if report:
            report["reserved_upload_bytes"] = report.get("reserved_upload_bytes", 0) + path.stat().st_size
            self.cache.put("usage", report)
