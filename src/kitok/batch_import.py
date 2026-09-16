"""Validate a complete editorial import before any queue write."""
from __future__ import annotations

import json
from datetime import timezone

from pydantic import ValidationError

from .models import ContentItem, ContentQueue


def parse_batch(text: str) -> list[dict]:
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Malformed JSON at line {error.lineno}, column {error.colno}: {error.msg}") from error
    if not isinstance(rows, list) or not rows:
        raise ValueError("Import must be a non-empty JSON array of content objects")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Every entry in the JSON array must be an object")
    return rows


def validate_batch(rows: list[dict], queue: ContentQueue, state) -> tuple[list[ContentItem], list[str]]:
    """Accept queue fields plus topic/video_terms aliases; report all local conflicts."""
    if not rows:
        return [], ["Import must contain at least one content item"]
    errors: list[str] = []
    items: list[ContentItem] = []
    ids = set(queue.by_id())
    slots = {item.publish_at.astimezone(timezone.utc) for item in queue.items}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"Item {index}: expected a JSON object")
            continue
        values = dict(row)
        if "subject" not in values and "topic" in values:
            values["subject"] = values.pop("topic")
        if "keywords" not in values and "video_terms" in values:
            values["keywords"] = values.pop("video_terms")
        if "topic" in values or "video_terms" in values:
            errors.append(f"Item {index}: use either queue fields or their aliases, not both")
            continue
        if not values.get("caption") or not str(values["caption"]).strip():
            errors.append(f"Item {index}: missing caption")
        if values.get("editorial_status", "active") != "active":
            errors.append(f"Item {index}: imported content must be active")
        try:
            item = ContentItem.model_validate(values)
        except ValidationError as error:
            for detail in error.errors():
                field = ".".join(map(str, detail["loc"])) or "item"
                errors.append(f"Item {index}: {field}: {detail['msg']}")
            continue
        if item.id in ids:
            errors.append(f"Item {index}: duplicate ID {item.id}")
        if state.get(item.id):
            errors.append(f"Item {index}: ID {item.id} has saved history")
        slot = item.publish_at.astimezone(timezone.utc)
        if slot in slots:
            errors.append(f"Item {index}: occupied scheduling slot {item.publish_at.isoformat()}")
        ids.add(item.id)
        slots.add(slot)
        items.append(item)
    return items, errors
