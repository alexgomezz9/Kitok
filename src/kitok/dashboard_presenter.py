"""Pure, local presentation rules for Kitok's daily dashboard."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PLATFORMS = ("tiktok", "instagram", "youtube")
NAMES = {"tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube"}
STATUS = {
    "pending": "Draft", "submitted": "Generating", "generating": "Generating",
    "generated": "Generating", "ready": "Ready", "scheduled": "Scheduled",
    "sending": "Scheduled", "sent": "Published", "failed": "Failed",
    "error": "Failed", "unknown": "Needs attention", "creating": "Needs attention",
    "needs_attention": "Needs attention", "needs_approval": "Needs attention",
    "draft": "Draft", "skipped": "Skipped", "archived": "Archived",
}
STATUS_ICON = {"Draft": "○", "Generating": "◌", "Ready": "●", "Scheduled": "◷",
               "Published": "✓", "Skipped": "↷", "Archived": "□", "Failed": "!", "Needs attention": "!"}


def status_label(value: str | None) -> str:
    """Translate backend states into the small public status vocabulary."""
    return STATUS.get(value or "pending", "Needs attention")


def content_status(item, record: dict, row: dict | None = None) -> str:
    """Summarize one item's editorial, generation and platform state locally."""
    if item.editorial_status != "active":
        return status_label(item.editorial_status)
    publishing = record.get("publishing") or {}
    posts = publishing.get("buffer") or {}
    platform_states = [posts.get(name, {}).get("status") for name in item.platforms]
    if (row or {}).get("Attention") or any(value in {"unknown", "creating", "needs_attention", "needs_approval"}
                                             for value in platform_states):
        return "Needs attention"
    if record.get("status") == "failed" or any(value == "error" for value in platform_states):
        return "Failed"
    if platform_states and all(value == "sent" for value in platform_states):
        return "Published"
    if platform_states and all(value in {"scheduled", "sending", "sent"} for value in platform_states):
        return "Scheduled"
    return status_label(record.get("status"))


def _due(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except ValueError:
        return None


def coverage(data: dict, channel_ids: dict, timezone_name: str, *, now: datetime | None = None) -> dict:
    """Describe known future posts; shared coverage ends at the least covered channel."""
    now = now or datetime.now(timezone.utc)
    future = [(_due(post.get("dueAt")), post.get("channelId")) for post in data.get("scheduled_posts", [])]
    future = [(due, channel) for due, channel in future if due and due > now]
    latest = max((due for due, _ in future), default=None)
    channels = data.get("snapshot", {}).get("channels", {})
    ids = {name: channels.get(name, {}).get("id") or channel_ids.get(name) for name in PLATFORMS}
    shared = None
    if all(ids.values()):
        last_by_channel = {name: max((due for due, channel in future if channel == cid), default=None)
                           for name, cid in ids.items()}
        if all(last_by_channel.values()):
            shared = min(last_by_channel.values())
    until = shared or latest
    local = until.astimezone(ZoneInfo(timezone_name)) if until else None
    if shared:
        text = f"Scheduled across your channels through {local:%a %d %b, %H:%M}"
    elif latest:
        text = f"Latest known scheduled post: {local:%a %d %b, %H:%M}"
    else:
        text = "No upcoming scheduled posts are known locally."
    source = "Cached Buffer snapshot" if data.get("snapshot") else "Local records only"
    return {"until": until, "shared": bool(shared), "text": text, "source": source}


def grouped_issues(data: dict) -> list[dict]:
    """Collapse per-platform duplicates so Attention reads like an inbox."""
    groups = defaultdict(list)
    for issue in data.get("issues", []):
        message = str(issue.get("What happened", ""))
        category = "past" if "past" in message.lower() else "other"
        key = (issue.get("Content ID"), category) if category == "past" else (
            issue.get("Content ID"), issue.get("Platform"), message)
        groups[key].append(issue)
    result = []
    for entries in groups.values():
        first = entries[0]
        result.append({**first, "platforms": [entry.get("Platform", "") for entry in entries],
                       "count": len(entries)})
    return result


@dataclass(frozen=True)
class Recommendation:
    kind: str
    title: str
    detail: str
    action: str | None = None


def recommendations(data: dict, queue, state, settings, *, now: datetime | None = None) -> list[Recommendation]:
    """Prioritize local attention, limits and coverage; never contacts a service."""
    now = now or datetime.now(timezone.utc)
    issues = grouped_issues(data)
    active = [item for item in queue.items if item.editorial_status == "active"]
    pending = [item for item in active if state.get(item.id).get("status", "pending") == "pending"]
    ready = [item for item in active if state.get(item.id).get("status") == "ready"
             and any(not state.get(item.id).get("publishing", {}).get("buffer", {}).get(name, {}).get("post_id")
                     for name in item.platforms)]
    capacity = sum(max(0, settings.buffer_max_scheduled_per_channel - data.get("occupancy", {}).get(name, 0))
                   for name in PLATFORMS)
    known = bool(data.get("snapshot"))
    report = coverage(data, settings.buffer_channel_ids, settings.timezone, now=now)
    usage = data.get("buffer_usage") or {}
    quota_low = bool(_due(usage.get("retry_at")) and _due(usage.get("retry_at")) > now)
    quota_low |= any(row.get("window_seconds") == 900 and isinstance(row.get("remaining"), int)
                     and row["remaining"] <= settings.buffer_request_reserve + 1
                     and (_due(row.get("reset_at")) or now) > now
                     for row in usage.get("windows", {}).values())
    result = []
    content_issues = [issue for issue in issues if issue.get("Content ID") in queue.by_id()]
    if content_issues:
        first = content_issues[0]
        result.append(Recommendation("fix", f"{len(content_issues)} things need your attention",
                                     f"Review {queue.by_id()[first['Content ID']].subject}" +
                                     (" and the other flagged items." if len(content_issues) > 1 else "."),
                                     "Review issues"))
    if any(issue.get("Platform") == "Cloudinary" for issue in issues):
        result.append(Recommendation("cloudinary", "Video hosting needs attention",
                                     "Review the cached usage warning before uploading more videos.", "Review system"))
    if quota_low:
        result.append(Recommendation("budget", "Publishing requests are limited",
                                     "Wait for Buffer's next available window before scheduling.", "Review system"))
    if not known:
        result.append(Recommendation("refresh", "Check your schedule",
                                     "The current Buffer schedule has not been cached yet.", "Refresh publishing status"))
    elif capacity > 0 and settings.publish_enabled and ready and not quota_low:
        result.append(Recommendation("fill", "Schedule has room",
                                     f"Up to {capacity} social post slots are open. Ready videos can fill them.",
                                     "Fill schedule"))
    if pending:
        result.append(Recommendation("generate", f"{len(pending)} videos are still drafts",
                                     "Review the next draft and start its video when ready.", "Generate video"))
    if not active:
        result.append(Recommendation("prepare", "Prepare your next content",
                                     "Add a topic and script to start your editorial queue.", "Add content"))
    if not result:
        detail = report["text"] if report["until"] else "Your active queue has no known issues."
        result.append(Recommendation("none", "Everything is ready", detail))
    return result
