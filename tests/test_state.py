import json
from pathlib import Path
from kitok.state import StateStore

def test_persistence(tmp_path:Path):
    p=tmp_path/"state.json"; s=StateStore(p)
    s.upsert("abc",status="submitted",mpt_task_id="task-1")
    r=StateStore(p).get("abc")
    assert r["status"]=="submitted" and r["mpt_task_id"]=="task-1"
    json.loads(p.read_text())

def test_reset_failed(tmp_path:Path):
    p=tmp_path/"state.json"; s=StateStore(p)
    s.upsert("abc",status="failed",attempts=2,mpt_task_id="old")
    s.reset_failed("abc"); r=s.get("abc")
    assert r["status"]=="pending" and r["attempts"]==2 and r["mpt_task_id"] is None
