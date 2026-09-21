from __future__ import annotations
import json, shutil
from pathlib import Path
from .models import ContentItem

def output_filename(item:ContentItem)->str:
    prefix = item.publish_at.strftime('%Y-%m-%d_%H-%M') if item.publish_at else "unscheduled"
    return f"{prefix}__{item.id}.mp4"

def copy_atomic(source:Path,destination:Path)->Path:
    destination.parent.mkdir(parents=True,exist_ok=True)
    tmp=destination.with_suffix(destination.suffix+".part")
    shutil.copyfile(source,tmp); tmp.replace(destination)
    return destination

def write_metadata_sidecar(item:ContentItem,video_path:Path)->Path:
    sidecar=video_path.with_suffix(".json")
    data={"id":item.id,"subject":item.subject,"caption":item.caption,
          "publish_at":item.publish_at.isoformat() if item.publish_at else None,"keywords":item.keywords,
          "platforms":item.platforms,"video_file":video_path.name}
    sidecar.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    return sidecar
