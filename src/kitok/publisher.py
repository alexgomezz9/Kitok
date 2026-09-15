"""Optional, bounded Buffer scheduling. Never invoked by generation."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .buffer_client import BufferError, PLATFORMS, POST_STATUSES
from .cloudinary_host import CloudinaryHost, HostingError, require_https
from .file_manager import output_filename
from .video_validator import validate_for_publishing


def utc_due_at(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("publish_at must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_caption(caption, fixed_hashtags):
    # Preserve supplied wording and existing tags; append only missing fixed tags.
    text = caption.strip()
    existing = {word.casefold() for word in text.split()}
    for tag in fixed_hashtags.split():
        if tag.casefold() not in existing:
            text = f"{text} {tag}".strip()
            existing.add(tag.casefold())
    return text


def post_content(item, platform, fixed_hashtags):
    if platform not in PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform}")
    text = build_caption(item.caption, fixed_hashtags)
    if platform == "tiktok" and len(text) > 150:
        raise ValueError(f"TikTok caption is {len(text)} characters; maximum is 150")
    if platform == "instagram" and len(text) > 2200:
        raise ValueError("Instagram caption plus hashtags exceeds 2200 characters")
    if platform == "youtube" and len(item.subject) > 100:
        raise ValueError("YouTube title exceeds 100 characters")
    metadata = {"isAiGenerated": True}
    if platform == "instagram":
        metadata.update(type="reel", shouldShareToFeed=True)
    elif platform == "youtube":
        metadata.update(title=item.subject, categoryId="27", madeForKids=False,
                        privacy="public", notifySubscribers=True)
    return {"text": text, "metadata": {platform: metadata}, "aiAssisted": True,
            "schedulingType": "automatic", "mode": "customScheduled", "needsApproval": False}


def available_slots(scheduled_count, maximum=9):
    if not 1 <= maximum <= 9:
        raise ValueError("Buffer queue target must be between 1 and 9")
    return max(0, maximum - max(0, scheduled_count))


def already_created(record):
    return bool(record.get("post_id")) or record.get("status") in {
        "unknown", "creating", "scheduled", "sending", "sent", "draft", "needs_approval"}


@dataclass
class PublishPlan:
    rows: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    offline: bool = False
    deferred: int = 0


class Publisher:
    def __init__(self, settings, queue, state, client=None, host=None,
                 *, validator=validate_for_publishing, now=None):
        self.s, self.q, self.state, self.client = settings, queue, state, client
        self.host = host or CloudinaryHost(settings, state)
        self.validator = validator
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _buffer_records(self):
        for cid, record in self.state.all().items():
            for platform, post in record.get("publishing", {}).get("buffer", {}).items():
                yield cid, platform, post

    def snapshot(self):
        if self.client is None:
            return None, {p: {"id": self.s.buffer_channel_ids[p] or p, "service": p}
                          for p in PLATFORMS}, None
        org, _, channels = self.client.discover(self.s.buffer_organization_id, self.s.buffer_channel_ids)
        posts = self.client.posts(org, [c["id"] for c in channels.values()], ["scheduled", "sending"]) if channels else []
        return org, channels, posts

    def plan(self, ids=None, snapshot=None):
        org, channels, remote = snapshot if snapshot is not None else self.snapshot()
        plan = PublishPlan(offline=remote is None)
        occupied = Counter()
        remote_ids = set()
        if remote is not None:
            for post in remote:
                if post["id"] not in remote_ids and post["status"] in {"scheduled", "sending"}:
                    occupied[post["channelId"]] += 1
                    remote_ids.add(post["id"])
        blocked = set()
        for _, platform, post in self._buffer_records():
            channel_id = post.get("channel_id") or channels.get(platform, {}).get("id")
            if post.get("status") in {"unknown", "creating"}:
                blocked.add(channel_id)
            if post.get("status") in {"scheduled", "sending"} and post.get("post_id") not in remote_ids:
                # Conservative reservation if a just-created post is not yet visible.
                occupied[channel_id] += 1
        slots = {}
        for platform, channel in channels.items():
            plan.counts[platform] = occupied[channel["id"]]
            slots[platform] = available_slots(occupied[channel["id"]], self.s.buffer_max_scheduled_per_channel)
            if channel["id"] in blocked or any(channel.get(k) for k in ("isDisconnected", "isLocked", "isQueuePaused")):
                slots[platform] = 0
                plan.issues.append({"id": None, "platform": platform,
                                    "error": "Channel unavailable or has an unresolved creation; reconcile before filling"})
        for item in sorted(self.q.items, key=lambda i: (i.publish_at, i.id)):
            if ids is not None and item.id not in ids:
                continue
            record = self.state.get(item.id)
            if record.get("status") != "ready":
                continue
            for platform in dict.fromkeys(item.platforms):
                post = record.get("publishing", {}).get("buffer", {}).get(platform, {})
                if already_created(post):
                    continue
                try:
                    due_at = utc_due_at(item.publish_at)
                    if item.publish_at <= self.now():
                        raise ValueError("publish_at is in the past; choose a new future time")
                    content = post_content(item, platform, self.s.fixed_hashtags)
                    if platform not in channels:
                        raise ValueError(f"No connected {platform} channel")
                    retry_at = post.get("retry_at")
                    if retry_at and datetime.fromisoformat(retry_at) > self.now():
                        raise ValueError(f"Buffer cooldown until {retry_at}")
                    if slots.get(platform, 0) <= 0:
                        plan.deferred += 1
                        continue
                    path = self._video_path(item, record)
                    errors = self.validator(path, [platform], self.s.ffprobe_binary)
                    if errors:
                        raise ValueError("; ".join(errors))
                except (ValueError, OSError) as error:
                    plan.issues.append({"id": item.id, "platform": platform, "error": str(error)})
                    continue
                slots[platform] -= 1
                plan.rows.append({"id": item.id, "platform": platform, "dueAt": due_at,
                                  "caption": content["text"],
                                  "title": item.subject if platform == "youtube" else None,
                                  "video_path": str(path), "organization_id": org,
                                  "input": {**content, "dueAt": due_at,
                                            "channelId": (self.s.buffer_channel_ids[platform] or None)
                                            if plan.offline else channels[platform]["id"]}})
        return plan

    def _video_path(self, item, record):
        paths = [Path(record["ready_path"]).expanduser()] if record.get("ready_path") else []
        paths.append(self.s.local_ready_dir / output_filename(item))
        for path in paths:
            if not path.is_absolute():
                from .config import PROJECT_ROOT
                path = PROJECT_ROOT / path
            if path.is_file():
                return path
        raise ValueError("ready MP4 is missing from ready_path and outputs/ready")

    def _save_post(self, cid, platform, post, error=None):
        status = post.get("status", "unknown")
        if status not in POST_STATUSES:
            error = error or "Unrecognized Buffer status; inspect post"
            status = "unknown"
        if status in {"error", "needs_approval", "draft"}:
            error = error or f"Buffer post is {status}; review it in Buffer (no automatic recreation)"
        self.state.update_publishing(cid, "buffer", platform, post_id=post["id"], status=status,
                                     channel_id=post.get("channelId"), due_at=post.get("dueAt"),
                                     last_error=error, synced_at=utc_due_at(self.now()))

    def _sync(self, snapshot):
        org, channels, remote = snapshot
        if self.client is None:
            raise BufferError("BUFFER_API_KEY is required for synchronization")
        by_id = {p["id"]: p for p in remote}
        claimed = {post.get("post_id") for _, _, post in self._buffer_records() if post.get("post_id")}
        summary = {"synced": 0, "reconciled": 0, "attention": []}
        for cid, platform, record in list(self._buffer_records()):
            post_id = record.get("post_id")
            if record.get("status") == "sent":
                continue
            try:
                if post_id:
                    post = by_id.get(post_id) or self.client.post(post_id)
                    if post.get("id") != post_id:
                        raise BufferError("Buffer returned a different post ID")
                    self._save_post(cid, platform, post)
                    summary["synced"] += 1
                    if post.get("status") in {"draft", "error", "needs_approval"}:
                        summary["attention"].append(f"{cid}/{platform}: Buffer status {post['status']}")
                elif record.get("status") in {"unknown", "creating"}:
                    request = record.get("request") or {}
                    due = datetime.fromisoformat(request["dueAt"])
                    candidates = self.client.posts(
                        record.get("organization_id") or org, [request["channelId"]], sorted(POST_STATUSES),
                        due_at={"start": utc_due_at(due - timedelta(minutes=5)),
                                "end": utc_due_at(due + timedelta(minutes=5))})
                    matches = [p for p in candidates if p["channelId"] == request["channelId"]
                               and p.get("text") == request["text"] and p.get("dueAt")
                               and datetime.fromisoformat(p["dueAt"]) == due]
                    if len(matches) == 1 and matches[0]["id"] not in claimed:
                        self._save_post(cid, platform, matches[0])
                        claimed.add(matches[0]["id"])
                        summary["reconciled"] += 1
                    else:
                        raise BufferError(f"Unknown creation: {len(matches)} matches; inspect Buffer manually")
            except (BufferError, KeyError, ValueError) as error:
                message = str(error) if isinstance(error, BufferError) else "Missing reconciliation data; inspect Buffer manually"
                self.state.update_publishing(cid, "buffer", platform, last_error=message)
                summary["attention"].append(f"{cid}/{platform}: {message}")
                if isinstance(error, BufferError) and error.retry_after:
                    raise
        return summary

    def sync(self):
        with self.state.publishing_lock():
            return self._sync(self.snapshot())

    def publish(self, ids=None, *, maintain=False):
        if not self.s.publish_enabled:
            raise BufferError("Publishing disabled: set PUBLISH_ENABLED=true")
        if self.client is None:
            raise BufferError("BUFFER_API_KEY is required for publishing")
        with self.state.publishing_lock():
            snapshot = self.snapshot()
            summary = self._sync(snapshot) if maintain else {"synced": 0, "reconciled": 0, "attention": []}
            plan = self.plan(ids, snapshot)
            summary.update(created=0, deferred=plan.deferred, counts=plan.counts)
            for issue in plan.issues:
                summary["attention"].append(f"{issue['id'] or 'channel'}/{issue['platform']}: {issue['error']}")
                if issue["id"]:
                    self.state.update_publishing(issue["id"], "buffer", issue["platform"],
                                                 status="needs_attention", last_error=issue["error"])
            blocked_channels = set()
            for row in plan.rows:
                cid, platform, inputs = row["id"], row["platform"], row["input"]
                if inputs["channelId"] in blocked_channels:
                    summary["deferred"] += 1
                    continue
                current = self.state.get(cid).get("publishing", {}).get("buffer", {}).get(platform, {})
                if already_created(current):
                    continue
                try:
                    media = self.host.ensure_video(cid, Path(row["video_path"]))
                    if datetime.fromisoformat(row["dueAt"]) <= self.now():
                        raise ValueError("publish_at passed during preparation; choose a future time")
                    inputs = {**inputs, "assets": [{"video": {"url": require_https(media["url"])}}]}
                except (HostingError, ValueError, OSError) as error:
                    self.state.update_publishing(cid, "buffer", platform, status="needs_attention", last_error=str(error))
                    summary["attention"].append(f"{cid}/{platform}: {error}")
                    continue
                # Durable intent BEFORE the mutation protects process-crash recovery.
                self.state.update_publishing(cid, "buffer", platform, status="unknown", last_error=None,
                                             channel_id=inputs["channelId"], due_at=row["dueAt"],
                                             organization_id=row["organization_id"], request=inputs)
                try:
                    post = self.client.create_post(inputs)
                except BufferError as error:
                    if error.post and error.post.get("id"):
                        self._save_post(cid, platform, error.post, str(error))
                        summary["created"] += 1
                    else:
                        changes = {"status": "unknown" if error.ambiguous else "error", "last_error": str(error)}
                        if error.retry_after:
                            changes["retry_at"] = utc_due_at(self.now() + timedelta(seconds=error.retry_after))
                        self.state.update_publishing(cid, "buffer", platform, **changes)
                    summary["attention"].append(f"{cid}/{platform}: {error}")
                    blocked_channels.add(inputs["channelId"])
                    if error.retry_after:
                        break
                else:
                    # First action after receiving success is atomic ID persistence.
                    self._save_post(cid, platform, post)
                    summary["created"] += 1
                    if post.get("status") != "scheduled":
                        summary["attention"].append(f"{cid}/{platform}: Buffer status {post.get('status')}")
            return summary
