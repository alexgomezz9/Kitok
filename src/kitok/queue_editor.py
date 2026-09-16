"""Explicit, atomic edits to unpublished queue items; no external calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import ContentItem, ContentQueue
from .state import StateStore, write_json_atomic


def queue_digest(path: Path) -> str:
    """Identify a queue revision without editing it."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def edit_item(path: Path, state: StateStore, content_id: str, changes: dict,
              *, expected_revision: str) -> ContentItem:
    """Edit time/title/caption only if still unpublished and the preview is current."""
    if not changes or set(changes) - {"publish_at", "subject", "caption"}:
        raise ValueError("Only publish time, title and caption can be edited here")
    with state.publishing_lock():
        if queue_digest(path) != expected_revision:
            raise ValueError("Queue changed since preview; review the edit again")
        if state.get(content_id).get("publishing"):
            raise ValueError("Publishing metadata exists; review remote posts before editing this item")
        raw = json.loads(path.read_text(encoding="utf-8"))
        index = next((i for i, row in enumerate(raw) if row["id"] == content_id), None)
        if index is None:
            raise ValueError(f"Unknown content ID: {content_id}")
        candidate = ContentItem.model_validate({**raw[index], **changes})
        values = candidate.model_dump(mode="json")
        raw[index].update({key: values[key] for key in changes})
        ContentQueue(items=[ContentItem.model_validate(row) for row in raw])
        write_json_atomic(path, raw)
        return candidate
