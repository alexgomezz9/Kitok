"""Optional, bounded Buffer scheduling. Never invoked by generation."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .buffer_client import BufferError, PLATFORMS, POST_STATUSES
from .cloudinary_host import CloudinaryHost, HostingError, require_https
from .file_manager import output_filename
from .video_validator import validate_for_publishing


def utc_due_at(value: datetime) -> str:
    """Convert an aware time to Buffer UTC text; no side effects."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("publish_at must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_caption(caption: str, fixed_hashtags: str) -> str:
    """Append missing configured tags without rewriting supplied text; pure."""
    # Preserve supplied wording and existing tags; append only missing fixed tags.
    text = caption.strip()
    existing = {word.casefold() for word in text.split()}
    for tag in fixed_hashtags.split():
        if tag.casefold() not in existing:
            text = f"{text} {tag}".strip()
            existing.add(tag.casefold())
    return text


def post_content(item, platform: str, fixed_hashtags: str, *, ai_assisted: bool = True,
                 tiktok_ai_generated: bool = True, youtube_ai_generated: bool = True,
                 instagram_ai_generated: bool = True) -> dict:
    """Build supported platform payloads; pure function, no requests or writes."""
    if platform not in PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform}")
    text = build_caption(item.caption, fixed_hashtags)
    if platform == "tiktok" and len(text) > 150:
        raise ValueError(f"TikTok caption is {len(text)} characters; maximum is 150")
    if platform == "instagram" and len(text) > 2200:
        raise ValueError("Instagram caption plus hashtags exceeds 2200 characters")
    youtube_title = item.youtube_title or item.subject
    if platform == "youtube" and len(youtube_title) > 100:
        raise ValueError("YouTube title exceeds 100 characters")
    metadata = {}
    if platform == "tiktok":
        metadata["isAiGenerated"] = tiktok_ai_generated
    if platform == "instagram":
        metadata.update(type="reel", shouldShareToFeed=True, isAiGenerated=instagram_ai_generated)
    elif platform == "youtube":
        metadata.update(title=youtube_title, categoryId="27", madeForKids=False,
                        privacy="public", notifySubscribers=True, isAiGenerated=youtube_ai_generated)
    return {"text": text, "metadata": {platform: metadata}, "aiAssisted": ai_assisted,
            "schedulingType": "automatic", "mode": "customScheduled", "needsApproval": False}


def available_slots(scheduled_count: int, maximum: int = 9) -> int:
    """Calculate local capacity; never reads or modifies Buffer."""
    if not 1 <= maximum <= 9:
        raise ValueError("Buffer queue target must be between 1 and 9")
    return max(0, maximum - max(0, scheduled_count))


def already_created(record: dict) -> bool:
    """Treat saved IDs and ambiguous intents as protected; no side effects."""
    return bool(record.get("post_id")) or record.get("status") in {
        "unknown", "creating", "scheduled", "sending", "sent", "draft", "needs_approval"}


@dataclass
class PublishPlan:
    rows: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    offline: bool = False
    deferred: int = 0
    occupancy_source: str = "LOCAL"
    refreshed_at: str | None = None
    estimated_requests: int = 0


class Publisher:
    def __init__(self, settings, queue, state, client=None, host=None,
                 *, validator=None, now=None, cache=None):
        self.s, self.q, self.state, self.client = settings, queue, state, client
        self.host = host or CloudinaryHost(settings, state)
        self.validator = validator or validate_for_publishing
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.cache = cache

    def _buffer_records(self):
        for cid, record in self.state.all().items():
            for platform, post in record.get("publishing", {}).get("buffer", {}).items():
                yield cid, platform, post

    def snapshot(self) -> tuple:
        """Read one paginated occupancy snapshot; never creates remote posts."""
        if self.client is None:
            cached = self.cache.get("snapshot") if self.cache else {}
            if cached:
                return cached["organization_id"], cached["channels"], cached["posts"]
            channels = {}
            for platform in PLATFORMS:
                known = {post["channel_id"] for _, service, post in self._buffer_records()
                         if service == platform and post.get("channel_id")}
                channel_id = self.s.buffer_channel_ids[platform] or (next(iter(known)) if len(known) == 1 else platform)
                channels[platform] = {"id": channel_id, "service": platform}
            return None, channels, None
        org, _, channels = self.client.discover(self.s.buffer_organization_id, self.s.buffer_channel_ids)
        posts = self.client.posts(org, [c["id"] for c in channels.values()], ["scheduled", "sending"]) if channels else []
        if self.cache:
            self.cache.put("snapshot", {"organization_id": org, "channels": channels, "posts": posts,
                                       "refreshed_at": utc_due_at(self.now())})
        return org, channels, posts

    def occupancy(self, snapshot: tuple) -> tuple[dict, set]:
        """Combine a supplied snapshot with local reservations; no reads or writes."""
        _, channels, remote = snapshot
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
        return {platform: occupied[channel["id"]] for platform, channel in channels.items()}, blocked

    def plan(self, ids: set[str] | None = None, snapshot: tuple | None = None,
             *, platforms=None, require_all: bool = False) -> PublishPlan:
        """Validate a plan; client=None is offline. No uploads or post mutations."""
        snapshot = snapshot if snapshot is not None else self.snapshot()
        org, channels, remote = snapshot
        cached = self.cache.get("snapshot") if self.cache else {}
        counts, blocked = self.occupancy(snapshot)
        plan = PublishPlan(offline=self.client is None, counts=counts,
                           occupancy_source="LIVE" if self.client else ("CACHED" if remote is not None else "LOCAL"),
                           refreshed_at=cached.get("refreshed_at"))
        slots = {}
        for platform, channel in channels.items():
            slots[platform] = available_slots(plan.counts[platform], self.s.buffer_max_scheduled_per_channel)
            if channel["id"] in blocked or any(channel.get(k) for k in ("isDisconnected", "isLocked", "isQueuePaused")):
                slots[platform] = 0
                plan.issues.append({"id": None, "platform": platform,
                                    "error": "Channel unavailable or has an unresolved creation; reconcile before filling"})
        for item in sorted(self.q.items, key=lambda i: (i.publish_at, i.id)):
            if ids is not None and item.id not in ids:
                continue
            if item.editorial_status != "active":
                continue
            record = self.state.get(item.id)
            if record.get("status") != "ready":
                continue
            for platform in dict.fromkeys(platforms or item.platforms):
                post = record.get("publishing", {}).get("buffer", {}).get(platform, {})
                if already_created(post):
                    continue
                try:
                    due_at = utc_due_at(item.publish_at)
                    if item.publish_at <= self.now():
                        raise ValueError("publish_at is in the past; choose a new future time")
                    content = post_content(item, platform, self.s.fixed_hashtags,
                                           ai_assisted=self.s.content_ai_assisted,
                                           tiktok_ai_generated=self.s.tiktok_ai_generated,
                                           instagram_ai_generated=self.s.instagram_ai_generated,
                                           youtube_ai_generated=self.s.youtube_ai_generated)
                    if platform not in channels:
                        raise ValueError(f"No connected {platform} channel")
                    retry_at = post.get("retry_at")
                    if retry_at and datetime.fromisoformat(retry_at) > self.now():
                        raise ValueError(f"Buffer cooldown until {retry_at}")
                    if slots.get(platform, 0) <= 0:
                        if require_all:
                            plan.issues.append({"id": item.id, "platform": platform,
                                                "error": "No Buffer queue slot is available for this channel"})
                        else:
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
                                  "local_publish_at": item.publish_at.astimezone(ZoneInfo(self.s.timezone)).isoformat(),
                                  "disclosure": {"aiAssisted": content["aiAssisted"],
                                                 **{k: v for k, v in content["metadata"][platform].items()
                                                    if k == "isAiGenerated"}},
                                  "caption": content["text"],
                                  "title": (item.youtube_title or item.subject) if platform == "youtube" else None,
                                  "video_path": str(path), "organization_id": org,
                                  "input": {**content, "dueAt": due_at,
                                            "channelId": (self.s.buffer_channel_ids[platform] or None)
                                            if plan.offline else channels[platform]["id"]}})
        plan.estimated_requests = len(plan.rows)
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

    def sync(self) -> dict:
        """Read Buffer and reconcile local state; never creates remote posts."""
        with self.state.publishing_lock():
            return self._sync(self.snapshot())

    def publish(self, ids=None, *, maintain=False, platforms=None,
                require_all=False, before_execute=None) -> dict:
        """Schedule a checked batch. May upload media and create Buffer posts once."""
        if not self.s.publish_enabled:
            raise BufferError("Publishing disabled: set PUBLISH_ENABLED=true")
        if self.client is None:
            raise BufferError("BUFFER_API_KEY is required for publishing")
        started_requests = self.client.request_count
        with self.state.publishing_lock():
            snapshot = self.snapshot()
            if maintain:
                remote_ids = {post["id"] for post in snapshot[2]}
                sync_reads = sum(record.get("status") != "sent" and
                                 ((record.get("post_id") and record["post_id"] not in remote_ids)
                                  or (not record.get("post_id") and record.get("status") in {"unknown", "creating"}))
                                 for _, _, record in self._buffer_records())
                if sync_reads:
                    self.client.ensure_budget(sync_reads, reserve=self.s.buffer_request_reserve)
            summary = self._sync(snapshot) if maintain else {"synced": 0, "reconciled": 0, "attention": []}
            plan = self.plan(ids, snapshot, platforms=platforms, require_all=require_all)
            if isinstance(started_requests, int):
                plan.estimated_requests += self.client.request_count - started_requests
            summary.update(created=0, deferred=plan.deferred, counts=plan.counts)
            summary.update(before=dict(plan.counts), created_by_platform={p: 0 for p in PLATFORMS},
                           after_estimated=dict(plan.counts), estimated_requests=plan.estimated_requests)
            if before_execute is not None:
                before_execute(plan)
            # Snapshot/sync reads have completed; headers now describe the budget
            # available for the entire mutation batch, before any media upload.
            if plan.rows:
                self.client.ensure_budget(len(plan.rows), reserve=self.s.buffer_request_reserve)
            if require_all and plan.issues:
                summary["attention"].extend(
                    f"{issue['id'] or 'channel'}/{issue['platform']}: {issue['error']}"
                    for issue in plan.issues
                )
                return summary
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
                        summary["created_by_platform"][platform] += 1
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
                    summary["created_by_platform"][platform] += 1
                    if post.get("status") != "scheduled":
                        summary["attention"].append(f"{cid}/{platform}: Buffer status {post.get('status')}")
            summary["after_estimated"] = {p: n + summary["created_by_platform"].get(p, 0)
                                          for p, n in plan.counts.items()}
            return summary

    def publish_one(self, content_id: str, *, before_execute=None) -> dict:
        """Publish only this ready item; may upload and create supported-platform posts."""
        self._require_ready_item(content_id)
        return self.publish(
            ids={content_id},
            platforms=PLATFORMS,
            require_all=True,
            before_execute=before_execute,
        )

    def plan_one(self, content_id: str) -> PublishPlan:
        """Preview only this ready item; no uploads or remote mutations."""
        self._require_ready_item(content_id)
        return self.plan(ids={content_id}, platforms=PLATFORMS, require_all=True)

    def _require_ready_item(self, content_id):
        if content_id not in self.q.by_id():
            raise ValueError(f"Unknown content ID: {content_id}")
        if self.state.get(content_id).get("status") != "ready":
            raise ValueError(f"Content item {content_id} is not ready")
