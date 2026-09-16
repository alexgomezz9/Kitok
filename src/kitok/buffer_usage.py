"""Parse Buffer's documented structured RateLimit headers; no network calls."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

WINDOW_LABELS = {900: "15m", 86400: "24h", 2592000: "30d"}


def _policies(value: str) -> dict[str, dict[str, int]]:
    result = {}
    for match in re.finditer(r'"([^"\\]+)"([^,]*)', value):
        fields = {}
        for key, number in re.findall(r';\s*(r|t|q|w)\s*=\s*(\d+)', match[2]):
            fields[key] = int(number)
        result[match[1]] = fields
    return result


def parse_rate_limits(headers, previous: dict | None = None, *, now: datetime | None = None) -> dict:
    """Merge actually returned policies; never infer quotas from policy names."""
    now = now or datetime.now(timezone.utc)
    data = dict(previous or {})
    windows = {key: dict(value) for key, value in data.get("windows", {}).items()}
    status = _policies(headers.get("ratelimit", ""))
    policies = _policies(headers.get("ratelimit-policy", ""))
    for name in status.keys() | policies.keys():
        row = windows.setdefault(name, {"policy": name})
        for source, target in (("q", "quota"), ("w", "window_seconds")):
            if source in policies.get(name, {}):
                row[target] = policies[name][source]
        current = status.get(name, {})
        if "r" in current:
            row["remaining"] = current["r"]
            row["observed_at"] = now.isoformat()
        if "t" in current:
            row["reset_at"] = (now + timedelta(seconds=current["t"])).isoformat()
    if status or policies:
        data.update(windows=windows, refreshed_at=now.isoformat())
    return data


def usage_rows(usage: dict) -> list[dict]:
    """Build display rows from known values only; missing values stay unknown."""
    return [{"Window": WINDOW_LABELS.get(row.get("window_seconds"), name),
             "Remaining": row.get("remaining", "unknown"), "Quota": row.get("quota", "unknown"),
             "Reset": row.get("reset_at", "unknown"), "Updated": row.get("observed_at", "unknown")}
            for name, row in sorted(usage.get("windows", {}).items(),
                                    key=lambda pair: pair[1].get("window_seconds", 0))]
