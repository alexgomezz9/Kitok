"""Atomic local state and locks; never contacts external services."""
from __future__ import annotations
import json, os, tempfile
import fcntl
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def utc_now_iso() -> str: return datetime.now(timezone.utc).isoformat()

def write_json_atomic(path: Path, data: Any) -> None:
    """Replace one local JSON file atomically; caller supplies the appropriate lock."""
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(prefix=".state.", suffix=".tmp", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

class StateStore:
    def __init__(self, path: Path, *, create_parent: bool = True):
        self.path = path
        if create_parent:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self):
        if not self.path.exists():
            return {"version":1,"items":{}}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw,dict) or not isinstance(raw.get("items",{}),dict):
            raise ValueError(f"Invalid state file: {self.path}")
        raw.setdefault("version",1); raw.setdefault("items",{})
        return raw

    def get(self, cid: str) -> dict: return deepcopy(self._data["items"].get(cid,{}))
    def all(self) -> dict[str, dict]: return deepcopy(self._data["items"])

    def cache_get(self, key: str) -> dict:
        """Read a cached service response without changing state or files."""
        return deepcopy(self._data.get("cache", {}).get(key, {}))

    def cache_put(self, key: str, value: dict) -> None:
        """Atomically save a service response locally; no external writes."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._write_lock():
            self._data = self._load()
            self._data.setdefault("cache", {})[key] = deepcopy(value)
            self._atomic_write()

    def upsert(self, cid: str, **changes) -> dict:
        """Merge and atomically persist one local record; no external calls."""
        # Merge from disk while locked so generation and publishing preserve
        # each other's fields, including when their StateStores predate a write.
        with self._write_lock():
            self._data = self._load()
            return self._upsert(cid, **changes)

    def _upsert(self, cid, **changes):
        now = utc_now_iso()
        row = self._data["items"].setdefault(cid,{
            "content_id":cid,"status":"pending","attempts":0,
            "created_at":now,"updated_at":now,"mpt_task_id":None,
            "output_path":None,"ready_path":None,"last_error":None
        })
        row.update(changes); row["updated_at"] = now
        self._atomic_write()
        return deepcopy(row)

    def update_publishing(self, cid: str, section: str, platform: str | None = None, **changes) -> dict:
        """Persist publishing intent/outcome locally; never calls publishing APIs."""
        with self._write_lock():
            self._data = self._load()
            publishing = self.get(cid).get("publishing", {})
            target = publishing.setdefault(section, {})
            if platform is not None:
                target = target.setdefault(platform, {})
            target.update(changes)
            return self._upsert(cid, publishing=publishing)

    def clear_publishing(self, cid: str) -> dict | None:
        """Remove only one item's publishing subtree from the latest state."""
        with self._write_lock():
            self._data = self._load()
            row = self._data["items"].get(cid)
            if row is None or "publishing" not in row:
                return None
            removed = deepcopy(row.pop("publishing"))
            self._atomic_write()
            return removed

    @contextmanager
    def _write_lock(self):
        with self.path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    @contextmanager
    def publishing_lock(self):
        """Serialize maintenance runs, including remote uploads/mutations (WSL/Linux)."""
        with self.path.with_suffix(".publishing.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Another Kitok publishing operation is running") from None
            try:
                self._data = self._load()
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def increment_attempts(self,cid: str) -> int:
        """Increment a local generation counter; never submits tasks."""
        n = int(self.get(cid).get("attempts",0))+1
        self.upsert(cid, attempts=n); return n

    def reset_failed(self,cid: str) -> None:
        """Clear failed generation recovery fields locally; preserve publishing state."""
        if self.get(cid).get("status") == "failed":
            self.upsert(cid,status="pending",mpt_task_id=None,output_path=None,ready_path=None,last_error=None)

    def _atomic_write(self):
        write_json_atomic(self.path, self._data)
