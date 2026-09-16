"""Local views and confirmed actions shared by the dashboard and Kitok services.

Constructing or rendering a panel only reads local data. Explicit refresh methods
perform service reads. execute() is the sole confirmed action entry point.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from .buffer_client import BufferClient, PLATFORMS
from .cloudinary_usage import CloudinaryUsage
from .config import Settings, PROJECT_ROOT
from .models import ContentItem, ContentQueue
from .mpt_client import MPTClient
from .pipeline import Pipeline, load_preset
from .publisher import Publisher, PublishPlan
from .queue_editor import add_item, delete_item, edit_item, queue_digest, reorder_item, set_editorial_status
from .regeneration import ReadyRegenerator, skip_reason
from .service_cache import buffer_cache, cloudinary_cache
from .state import StateStore


def disclosure(settings: Settings) -> dict:
    """Return explicit user choices; no policy or legal classification."""
    return {"AI assisted": settings.content_ai_assisted, "TikTok AI generated": settings.tiktok_ai_generated,
            "YouTube AI generated": settings.youtube_ai_generated, "Instagram AI generated": settings.instagram_ai_generated}


def recommendation(message: str) -> str:
    """Explain recovery steps without performing automatic repairs."""
    message = message.lower()
    if "past" in message:
        return "Choose a future publish time for an unpublished item."
    if any(word in message for word in ("unknown", "ambiguous", "unresolved", "creating")):
        return "Sync state and inspect the saved remote IDs. Do not blindly republish."
    if any(word in message for word in ("rate", "budget", "cooldown", "quota")):
        return "Wait until the reported reset time, then refresh usage once."
    if "cloudinary" in message:
        return "Inspect Cloudinary status and refresh usage; preserve existing asset IDs."
    if any(word in message for word in ("video", "mp4", "audio", "media", "file")):
        return "Inspect the local MP4 and validation. Regenerate only if publishing has not started."
    return "Review the item and its platform status before retrying."


@dataclass
class PendingAction:
    kind: str
    content_id: str | None
    revision: str
    queue_revision: str
    summary: dict
    rows: list[dict] = field(default_factory=list)
    changes: dict = field(default_factory=dict)


class ControlPanel:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or Settings()
        self.cache = buffer_cache(self.s)
        self.cloud_usage = CloudinaryUsage(self.s, cache=cloudinary_cache(self.s))

    def load(self) -> tuple[ContentQueue, StateStore]:
        """Read queue/state only; no directory creation, logging or remote requests."""
        return ContentQueue.load(self.s.queue_path), StateStore(self.s.state_path, create_parent=False)

    def client(self, *, refresh_channels=False, persist=True) -> BufferClient:
        """Construct the existing client; HTTP begins only on an explicit method call."""
        return BufferClient(self.s.buffer_api_key.get_secret_value(), publish_enabled=self.s.publish_enabled,
                            timeout=self.s.buffer_request_timeout_seconds,
                            cache=buffer_cache(self.s, persist=persist),
                            discovery_ttl=0 if refresh_channels else self.s.buffer_discovery_ttl_seconds)

    def preview(self, content_id: str | None = None) -> PublishPlan:
        """Produce a truly offline publishing plan using local media and cached occupancy."""
        queue, state = self.load()
        publisher = Publisher(self.s, queue, state, cache=self.cache)
        return publisher.plan_one(content_id) if content_id else publisher.plan()

    def refresh_buffer(self, *, sync=False) -> dict:
        """Read Buffer on explicit request; sync may update local publishing status only."""
        queue, state = self.load()
        if sync:
            state.path.parent.mkdir(parents=True, exist_ok=True)
        client = self.client(refresh_channels=True)
        try:
            publisher = Publisher(self.s, queue, state, client, cache=self.cache)
            if sync:
                return publisher.sync()
            publisher.snapshot()
            return {"refreshed_at": self.cache.get("snapshot").get("refreshed_at")}
        finally:
            client.close()

    def settings_view(self) -> dict:
        """Return only allowlisted, non-secret settings for display."""
        url = urlsplit(self.s.mpt_base_url)
        host = url.hostname or ""
        if url.port:
            host += f":{url.port}"
        return {"PUBLISH_ENABLED": self.s.publish_enabled,
                "BUFFER_MAX_SCHEDULED_PER_CHANNEL": self.s.buffer_max_scheduled_per_channel,
                **disclosure(self.s), "READY_DIR": str(self.s.ready_dir),
                "MPT URL": urlunsplit((url.scheme, host, url.path, "", "")), "Timezone": self.s.timezone,
                "Cloudinary usage guard": self.s.cloudinary_usage_guard,
                "Cloudinary safety threshold": self.s.cloudinary_usage_threshold}

    def view(self, *, include_archived: bool = False) -> dict:
        """Assemble overview, upcoming rows and attention from local data only."""
        queue, state = self.load()
        rows, issues = [], []
        counters = Counter()
        local_posts = {}
        now = datetime.now(timezone.utc)
        for item in sorted(queue.items, key=lambda value: value.publish_at):
            if item.editorial_status == "archived" and not include_archived:
                continue
            record = state.get(item.id)
            publishing = record.get("publishing") or {}
            buffer = publishing.get("buffer", {})
            local = item.publish_at.astimezone(ZoneInfo(self.s.timezone))
            status = record.get("status", "pending")
            counters["ready"] += status == "ready" and item.editorial_status == "active"
            row = {"ID": item.id, "Content": item.subject, "Date": local.strftime("%Y-%m-%d"),
                   "Time": local.strftime("%H:%M"), "Generation": status,
                   "Editorial": item.editorial_status,
                   "Cloudinary": publishing.get("cloudinary", {}).get("status", "not uploaded")}
            item_issues = []
            if record.get("last_error"):
                item_issues.append(("generation", record["last_error"]))
            if status == "ready":
                try:
                    Publisher(self.s, queue, state)._video_path(item, record)
                except ValueError as error:
                    item_issues.append(("media", str(error)))
                if record.get("validation", {}).get("ok") is False:
                    item_issues.append(("media", "Invalid MP4: " + "; ".join(record["validation"].get("errors", []))))
            for platform in PLATFORMS:
                post = buffer.get(platform, {})
                value = post.get("status", "skipped" if item.editorial_status == "skipped" else
                                 ("ready" if status == "ready" else "pending"))
                row[platform.title()] = value
                counters["scheduled"] += value in {"scheduled", "sending"}
                counters["published"] += value == "sent"
                if post.get("post_id"):
                    local_posts[post["post_id"]] = {"id": post["post_id"], "status": value,
                                                  "dueAt": post.get("due_at"), "text": post.get("request", {}).get("text", item.caption),
                                                  "channelId": post.get("channel_id") or self.s.buffer_channel_ids[platform]}
                if post.get("last_error") or value in {"unknown", "creating", "error", "needs_attention", "needs_approval"}:
                    item_issues.append((platform, post.get("last_error") or f"Publishing status: {value}"))
                if (item.editorial_status == "active" and item.publish_at <= now
                        and not post.get("post_id") and platform in item.platforms):
                    item_issues.append((platform, "publish_at is in the past"))
            cloud = publishing.get("cloudinary", {})
            if cloud.get("last_error") or cloud.get("status") in {"unknown", "uploading"}:
                item_issues.append(("Cloudinary", cloud.get("last_error") or "Cloudinary upload unresolved"))
            for platform, message in item_issues:
                issues.append({"Content ID": item.id, "Platform": platform, "What happened": message,
                               "Recommended action": recommendation(message)})
            row["Attention"] = "; ".join(message for _, message in item_issues)
            rows.append(row)
        snapshot = self.cache.get("snapshot")
        remote = {p["id"]: p for p in snapshot.get("posts", [])}
        remote.update(local_posts)
        publisher = Publisher(self.s, queue, state, cache=self.cache)
        counts, _ = publisher.occupancy(publisher.snapshot())
        occupancy = {platform: counts.get(platform, 0) for platform in PLATFORMS}
        usage = self.cache.get("usage")
        if usage.get("retry_at") and datetime.fromisoformat(usage["retry_at"]) > now:
            issues.append({"Content ID": "—", "Platform": "Buffer", "What happened": f"Rate-limit cooldown until {usage['retry_at']}",
                           "Recommended action": "Wait before making another Buffer request."})
        cloud_report = self.cloud_usage.cached()
        for metric in ("credits", "storage", "bandwidth", "transformations"):
            values = cloud_report.get("data", {}).get(metric, {})
            if (isinstance(values, dict) and isinstance(values.get("limit"), (int, float))
                    and isinstance(values.get("usage"), (int, float)) and values["limit"] > 0):
                if values.get("usage", 0) >= values["limit"] * self.s.cloudinary_usage_threshold:
                    issues.append({"Content ID": "—", "Platform": "Cloudinary",
                                   "What happened": f"Cloudinary {metric} reached the upload safety threshold",
                                   "Recommended action": "Stop new uploads and review the cached usage report."})
        scheduled = sorted((p for p in remote.values() if p.get("status") in {"scheduled", "sending"}),
                           key=lambda p: p.get("dueAt") or "")
        counters["scheduled"] = len(scheduled)
        counters["uploaded"] = sum(row["Cloudinary"] == "uploaded" for row in rows)
        sync_times = [post.get("synced_at") for record in state.all().values()
                      for post in record.get("publishing", {}).get("buffer", {}).values() if post.get("synced_at")]
        return {"rows": rows, "issues": issues, "counts": dict(counters), "occupancy": occupancy,
                "snapshot": snapshot, "buffer_usage": usage, "cloudinary_usage": cloud_report,
                "scheduled_posts": scheduled, "last_sync": max(sync_times, default="never")}

    def _revision(self) -> str:
        queue, state = self.load()
        files = []
        for record in state.all().values():
            path = Path(record.get("ready_path") or "/nonexistent")
            if path.is_file():
                stat = path.stat()
                files.append((str(path), stat.st_size, stat.st_mtime_ns))
        payload = [queue_digest(self.s.queue_path), state.all(), self.settings_view(), files,
                   self.cache.scope, self.cloud_usage.cache.scope]
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    def prepare_action(self, kind: str, content_id: str | None = None, *, changes=None) -> PendingAction:
        """Prepare a reviewable action; never performs remote requests or writes."""
        queue, state = self.load()
        changes = changes or {}
        if kind != "add" and content_id is not None and content_id not in queue.by_id():
            raise ValueError(f"Unknown content ID: {content_id}")
        rows = []
        summary = {"Action": kind, "Content ID": content_id}
        if kind in {"fill", "publish"}:
            if not self.s.publish_enabled:
                raise ValueError("Publishing disabled: set PUBLISH_ENABLED=true in .env")
            plan = self.preview(content_id if kind == "publish" else None)
            rows = plan.rows
            ids = {row["id"] for row in rows}
            uploads = sum(not state.get(cid).get("publishing", {}).get("cloudinary", {}).get("url") for cid in ids)
            summary.update(videos=len(ids), posts=len(rows), uploads=uploads,
                           platforms=dict(Counter(row["platform"] for row in rows)),
                           disclosure=disclosure(self.s), occupancy=plan.occupancy_source,
                           estimated_requests=plan.estimated_requests,
                           after_estimated={platform: plan.counts.get(platform, 0) +
                                            sum(row["platform"] == platform for row in rows)
                                            for platform in PLATFORMS},
                           issues=plan.issues, note="Up to these counts; live occupancy will be checked on confirmation.")
        elif kind == "regenerate":
            reason = skip_reason(state.get(content_id))
            if reason:
                raise ValueError(reason)
            summary["MPT tasks"] = 1
        elif kind == "generate":
            if queue.by_id()[content_id].editorial_status != "active":
                raise ValueError("Restore this item before generation")
            status = state.get(content_id).get("status", "pending")
            if status not in {"pending", "failed", "submitted", "generating"}:
                raise ValueError(f"Cannot generate an item in {status} state")
            summary["MPT tasks"] = "Resume saved task or submit one new task"
        elif kind == "reset":
            summary["publishing state to clear"] = state.get(content_id).get("publishing", {})
            summary["Reminder"] = "Use only after manually deleting the social posts."
        elif kind == "edit":
            if state.get(content_id).get("publishing"):
                raise ValueError("Publishing metadata exists; cannot edit safely")
            current = queue.by_id()[content_id]
            generation = state.get(content_id)
            if any(key in changes and changes[key] != getattr(current, key) for key in ("script", "keywords")):
                if generation.get("status", "pending") != "pending" or generation.get("attempts", 0) or generation.get("mpt_task_id"):
                    raise ValueError("Script and video terms can only change before generation starts")
            summary["changes"] = changes
            ContentItem.model_validate({**queue.by_id()[content_id].model_dump(mode="json"), **changes})
        elif kind == "add":
            item = ContentItem.model_validate(changes)
            if not item.caption:
                raise ValueError("A caption is required for new content")
            if item.id in queue.by_id():
                raise ValueError(f"Content ID already exists: {item.id}")
            if state.get(item.id):
                raise ValueError("This content ID has saved history and cannot be reused")
            if any(existing.publish_at == item.publish_at for existing in queue.items):
                raise ValueError("Another item already uses that publish time")
            summary.update({"Content ID": item.id, "Topic": item.subject,
                            "Publish time": item.publish_at.isoformat(), "Generation": "Pending; no video is generated"})
        elif kind in {"move_earlier", "move_later"}:
            active = sorted((item for item in queue.items if item.editorial_status == "active"),
                            key=lambda item: item.publish_at)
            index = next((index for index, item in enumerate(active) if item.id == content_id), None)
            target = (index - 1 if kind == "move_earlier" else index + 1) if index is not None else -1
            if not 0 <= target < len(active):
                raise ValueError("No item in that direction")
            neighbor = active[target]
            if state.get(content_id).get("publishing") or state.get(neighbor.id).get("publishing"):
                raise ValueError("Publishing metadata exists; remote rescheduling requires a separate action")
            summary.update({"Swap with": neighbor.subject, "Current time": queue.by_id()[content_id].publish_at.isoformat(),
                            "New time": neighbor.publish_at.isoformat(),
                            "Note": "Only the two local publish times will be exchanged."})
        elif kind in {"skip", "archive", "restore"}:
            if kind == "skip" and state.get(content_id).get("publishing"):
                raise ValueError("Publishing metadata exists; scheduled posts need a separate remote action")
            summary["Note"] = ("Hide this item from active views; preserve its history and remote posts."
                               if kind == "archive" else
                               "Exclude it from future publishing; preserve its media and queue entry."
                               if kind == "skip" else "Return this item to active views and publishing plans.")
        elif kind == "delete":
            if state.get(content_id).get("publishing"):
                raise ValueError("Publishing metadata exists; this item cannot be deleted")
            summary["Note"] = "Remove only this queue entry. Existing local media and state history stay on disk."
        else:
            raise ValueError("Unknown action")
        if kind not in {"fill", "add"} and content_id is None:
            raise ValueError("Select exactly one content item")
        return PendingAction(kind, content_id, self._revision(), queue_digest(self.s.queue_path),
                             summary, rows, changes)

    def execute(self, action: PendingAction, *, confirmed: bool = False) -> dict:
        """Execute one explicitly confirmed action through existing services."""
        if not confirmed:
            raise ValueError("Explicit confirmation is required")
        if action.revision != self._revision():
            raise ValueError("Content, media or state changed since preview; review a fresh preview")
        queue, state = self.load()
        state.path.parent.mkdir(parents=True, exist_ok=True)
        if action.kind == "reset":
            with state.publishing_lock():
                if action.revision != self._revision():
                    raise ValueError("State changed; preview again")
                state.clear_publishing(action.content_id)
            return {"reset": action.content_id}
        if action.kind == "edit":
            edited = edit_item(self.s.queue_path, state, action.content_id, action.changes,
                               expected_revision=action.queue_revision)
            return {"edited": edited.id}
        if action.kind == "add":
            item = add_item(self.s.queue_path, state, action.changes, expected_revision=action.queue_revision)
            return {"added": item.id}
        if action.kind in {"move_earlier", "move_later"}:
            first, second = reorder_item(self.s.queue_path, state, action.content_id,
                                         -1 if action.kind == "move_earlier" else 1,
                                         expected_revision=action.queue_revision)
            return {"moved": first.id, "swapped_with": second.id}
        if action.kind in {"skip", "archive", "restore"}:
            status = {"skip": "skipped", "archive": "archived", "restore": "active"}[action.kind]
            item = set_editorial_status(self.s.queue_path, state, action.content_id, status,
                                        expected_revision=action.queue_revision)
            return {"editorial_status": item.editorial_status, "id": item.id}
        if action.kind == "delete":
            delete_item(self.s.queue_path, state, action.content_id, expected_revision=action.queue_revision)
            return {"deleted_from_queue": action.content_id}
        if action.kind == "regenerate":
            self.s.ensure_directories()
            path = self.s.mpt_preset_path
            preset = load_preset(path if path.is_absolute() else PROJECT_ROOT / path)
            client = MPTClient(self.s.mpt_base_url, self.s.mpt_api_key, self.s.mpt_request_timeout_seconds,
                               self.s.http_retry_attempts, self.s.http_retry_base_seconds)
            try:
                result = ReadyRegenerator(self.s, queue, state, client, preset).run(ids={action.content_id})
                return vars(result)
            finally:
                client.close()
        if action.kind == "generate":
            self.s.ensure_directories()
            path = self.s.mpt_preset_path
            preset = load_preset(path if path.is_absolute() else PROJECT_ROOT / path)
            client = MPTClient(self.s.mpt_base_url, self.s.mpt_api_key, self.s.mpt_request_timeout_seconds,
                               self.s.http_retry_attempts, self.s.http_retry_base_seconds)
            try:
                Pipeline(self.s, queue, state, client, preset).process(
                    ids={action.content_id}, retry_failed=True)
                result = state.get(action.content_id)
                return {"id": action.content_id, "generation_status": result.get("status", "pending"),
                        "last_error": result.get("last_error")}
            finally:
                client.close()
        if action.kind not in {"fill", "publish"}:
            raise ValueError("Unknown action")
        if not action.rows:
            raise ValueError("No posts were approved in this preview")
        def signature(row):
            return json.dumps({key: row.get(key) for key in
                               ("id", "platform", "dueAt", "caption", "title", "video_path", "disclosure")}, sort_keys=True)
        allowed = {signature(row) for row in action.rows}
        def check_plan(plan):
            if queue_digest(self.s.queue_path) != action.queue_revision or any(signature(row) not in allowed for row in plan.rows):
                raise ValueError("Live plan differs from the approved preview; review a fresh preview")
        client = self.client()
        try:
            publisher = Publisher(self.s, queue, state, client, cache=self.cache)
            if action.kind == "publish":
                return publisher.publish_one(action.content_id, before_execute=check_plan)
            return publisher.publish(ids={row["id"] for row in action.rows}, maintain=True, before_execute=check_plan)
        finally:
            client.close()
