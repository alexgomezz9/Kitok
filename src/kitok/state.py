from __future__ import annotations
import json, os, tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def utc_now_iso(): return datetime.now(timezone.utc).isoformat()

class StateStore:
    def __init__(self, path: Path):
        self.path = path
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

    def get(self, cid): return deepcopy(self._data["items"].get(cid,{}))
    def all(self): return deepcopy(self._data["items"])

    def upsert(self, cid, **changes):
        now = utc_now_iso()
        row = self._data["items"].setdefault(cid,{
            "content_id":cid,"status":"pending","attempts":0,
            "created_at":now,"updated_at":now,"mpt_task_id":None,
            "output_path":None,"ready_path":None,"last_error":None
        })
        row.update(changes); row["updated_at"] = now
        self._atomic_write()
        return deepcopy(row)

    def increment_attempts(self,cid):
        n = int(self.get(cid).get("attempts",0))+1
        self.upsert(cid, attempts=n); return n

    def reset_failed(self,cid):
        if self.get(cid).get("status") == "failed":
            self.upsert(cid,status="pending",mpt_task_id=None,output_path=None,ready_path=None,last_error=None)

    def _atomic_write(self):
        payload = json.dumps(self._data,ensure_ascii=False,indent=2)
        fd,tmp = tempfile.mkstemp(prefix=".state.",suffix=".tmp",dir=str(self.path.parent),text=True)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as f:
                f.write(payload); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
