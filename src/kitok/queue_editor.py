"""Explicit, atomic edits to unpublished queue items; no external calls."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from .models import ContentItem, ContentQueue
from .batch_import import validate_batch
from .state import StateStore, write_json_atomic

GENERATION_FIELDS = {"script", "keywords", "content_format", "voice_profile", "dialogue",
                     "dialogue_preset", "visual_profile", "background_seed", "visual_seed", "background_file", "character_profile"}


def _schedule_key(row: dict):
    if row.get("schedule_enabled", row.get("publish_at") is not None) and row.get("publish_at"):
        return (0, datetime.fromisoformat(row["publish_at"]).astimezone(timezone.utc))
    return (1, datetime.max.replace(tzinfo=timezone.utc))


def queue_digest(path: Path) -> str:
    """Identify a queue revision without editing it."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def edit_item(path: Path, state: StateStore, content_id: str, changes: dict,
              *, expected_revision: str) -> ContentItem:
    """Edit unpublished editorial fields atomically; never touches remote state."""
    if not changes or set(changes) - ({"publish_at", "schedule_enabled", "platforms", "subject", "caption", "youtube_title"} | GENERATION_FIELDS):
        raise ValueError("Only editorial fields can be edited here")
    with state.publishing_lock():
        if queue_digest(path) != expected_revision:
            raise ValueError("Queue changed since preview; review the edit again")
        if state.get(content_id).get("publishing"):
            raise ValueError("Publishing metadata exists; review remote posts before editing this item")
        raw = json.loads(path.read_text(encoding="utf-8"))
        index = next((i for i, row in enumerate(raw) if row["id"] == content_id), None)
        if index is None:
            raise ValueError(f"Unknown content ID: {content_id}")
        generation = state.get(content_id)
        current = ContentItem.model_validate(raw[index])
        if any(key in changes and changes[key] != getattr(current, key) for key in GENERATION_FIELDS):
            if generation.get("status", "pending") != "pending" or generation.get("attempts", 0) or generation.get("mpt_task_id"):
                raise ValueError("Generation settings can only change before generation starts")
        candidate = ContentItem.model_validate({**raw[index], **changes})
        if candidate.schedule_enabled and {"publish_at", "schedule_enabled", "platforms"}.intersection(changes) and any(
                row["id"] != content_id and row.get("schedule_enabled", row.get("publish_at") is not None) and row.get("publish_at") and
                set(row.get("platforms", ["tiktok", "instagram", "youtube"])) & set(candidate.platforms) and
                datetime.fromisoformat(row["publish_at"]).astimezone(timezone.utc) ==
                candidate.publish_at.astimezone(timezone.utc) for row in raw):
            raise ValueError("Another item already uses that publish time")
        values = candidate.model_dump(mode="json")
        raw[index].update({key: values[key] for key in changes})
        ContentQueue(items=[ContentItem.model_validate(row) for row in raw])
        raw.sort(key=_schedule_key)
        write_json_atomic(path, raw)
        return candidate


def suggested_id(topic: str, existing: set[str]) -> str:
    """Suggest a short ASCII ID; the user may replace it before saving."""
    folded = unicodedata.normalize("NFKD", topic).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "_", folded).strip("_")[:48].strip("_") or "content"
    candidate, number = base, 2
    while candidate in existing:
        candidate, number = f"{base}_{number}", number + 1
    return candidate


def _load_for_change(path: Path, expected_revision: str) -> list[dict]:
    if queue_digest(path) != expected_revision:
        raise ValueError("Queue changed since preview; review the action again")
    return json.loads(path.read_text(encoding="utf-8"))


def add_item(path: Path, state: StateStore, values: dict, *, expected_revision: str) -> ContentItem:
    """Add one validated item in chronological order; no generation or remote calls."""
    with state.publishing_lock():
        raw = _load_for_change(path, expected_revision)
        item = ContentItem.model_validate(values)
        if not item.caption:
            raise ValueError("A caption is required for new content")
        if any(row["id"] == item.id for row in raw):
            raise ValueError(f"Content ID already exists: {item.id}")
        if state.get(item.id):
            raise ValueError("This content ID has saved history and cannot be reused")
        if item.schedule_enabled and item.publish_at and any(row.get("schedule_enabled", row.get("publish_at") is not None) and row.get("publish_at") and
               set(row.get("platforms", ["tiktok", "instagram", "youtube"])) & set(item.platforms) and
               datetime.fromisoformat(row["publish_at"]).astimezone(timezone.utc) ==
               item.publish_at.astimezone(timezone.utc) for row in raw):
            raise ValueError("Another item already uses that publish time")
        raw.append(item.model_dump(mode="json"))
        ContentQueue(items=[ContentItem.model_validate(row) for row in raw])
        raw.sort(key=_schedule_key)
        write_json_atomic(path, raw)
        return item


def add_batch(path: Path, state: StateStore, values: list[dict], *, expected_revision: str) -> list[ContentItem]:
    """Commit a fully valid batch with one locked atomic queue replacement."""
    with state.publishing_lock():
        raw = _load_for_change(path, expected_revision)
        queue = ContentQueue(items=[ContentItem.model_validate(row) for row in raw])
        items, errors = validate_batch(values, queue, state)
        if errors:
            raise ValueError("Batch import rejected: " + "; ".join(errors))
        raw.extend(item.model_dump(mode="json") for item in items)
        ContentQueue(items=[ContentItem.model_validate(row) for row in raw])
        raw.sort(key=_schedule_key)
        write_json_atomic(path, raw)
        return items


def reorder_item(path: Path, state: StateStore, content_id: str, direction: int,
                 *, expected_revision: str) -> tuple[ContentItem, ContentItem]:
    """Swap neighboring active items' times atomically; remote schedules stay untouched."""
    if direction not in {-1, 1}:
        raise ValueError("Direction must be -1 or 1")
    with state.publishing_lock():
        raw = _load_for_change(path, expected_revision)
        active = sorted((row for row in raw if row.get("editorial_status", "active") == "active"
                         and row.get("schedule_enabled", row.get("publish_at") is not None)
                         and row.get("publish_at")),
                        key=lambda row: datetime.fromisoformat(row["publish_at"]).astimezone(timezone.utc))
        index = next((i for i, row in enumerate(active) if row["id"] == content_id), None)
        if index is None:
            raise ValueError("Unknown or inactive content ID")
        neighbor = index + direction
        if not 0 <= neighbor < len(active):
            raise ValueError("No item in that direction")
        first, second = active[index], active[neighbor]
        if state.get(first["id"]).get("publishing") or state.get(second["id"]).get("publishing"):
            raise ValueError("Publishing metadata exists; remote rescheduling requires a separate action")
        first["publish_at"], second["publish_at"] = second["publish_at"], first["publish_at"]
        ContentQueue(items=[ContentItem.model_validate(row) for row in raw])
        raw.sort(key=_schedule_key)
        write_json_atomic(path, raw)
        return ContentItem.model_validate(first), ContentItem.model_validate(second)


def set_editorial_status(path: Path, state: StateStore, content_id: str, status: str,
                         *, expected_revision: str) -> ContentItem:
    """Skip/archive locally; preserved files and remote posts are never changed."""
    if status not in {"active", "skipped", "archived"}:
        raise ValueError("Invalid editorial status")
    with state.publishing_lock():
        raw = _load_for_change(path, expected_revision)
        row = next((row for row in raw if row["id"] == content_id), None)
        if row is None:
            raise ValueError(f"Unknown content ID: {content_id}")
        if status == "skipped" and state.get(content_id).get("publishing"):
            raise ValueError("Publishing metadata exists; scheduled posts need separate remote action")
        row["editorial_status"] = status
        item = ContentItem.model_validate(row)
        write_json_atomic(path, raw)
        return item


def delete_item(path: Path, state: StateStore, content_id: str, *, expected_revision: str) -> None:
    """Remove only queue entry; never deletes media, state history or remote assets."""
    with state.publishing_lock():
        raw = _load_for_change(path, expected_revision)
        if not any(row["id"] == content_id for row in raw):
            raise ValueError(f"Unknown content ID: {content_id}")
        if state.get(content_id).get("publishing"):
            raise ValueError("Publishing metadata exists; this content cannot be deleted")
        raw = [row for row in raw if row["id"] != content_id]
        ContentQueue(items=[ContentItem.model_validate(row) for row in raw])
        write_json_atomic(path, raw)
