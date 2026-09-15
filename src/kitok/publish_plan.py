from __future__ import annotations
import json
from pathlib import Path
from .models import ContentQueue

def generate_publish_plan(queue:ContentQueue,states:dict,target_dir:Path):
    target_dir.mkdir(parents=True,exist_ok=True)
    rows=[]
    for item in queue.items:
        st=states.get(item.id,{})
        if st.get("status")!="ready": continue
        rows.append({
            "id":item.id,"publish_at":item.publish_at.isoformat(),
            "caption":item.caption,"subject":item.subject,
            "video":Path(st.get("ready_path") or "").name,
            "platforms":item.platforms
        })
    rows.sort(key=lambda x:x["publish_at"])
    jp=target_dir/"publish_plan.json"
    jp.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=[]; current=None
    for row in rows:
        d,t=row["publish_at"].split("T",1)
        if d!=current:
            if lines: lines.append("")
            lines.append(f"=== {d} ==="); current=d
        lines += [f"{t[:5]} - {row['id']}",f"Vídeo: {row['video']}",f"Caption: {row['caption']}",""]
    tp=target_dir/"publish_plan.txt"
    tp.write_text("\n".join(lines).strip()+("\n" if lines else ""),encoding="utf-8")
    return tp,jp
