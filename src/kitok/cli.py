from __future__ import annotations
import argparse
from rich.console import Console
from rich.table import Table
from .config import PROJECT_ROOT, Settings
from .logging_setup import configure_logging
from .models import ContentQueue
from .mpt_client import MPTClient, MPTError
from .pipeline import Pipeline, load_preset
from .publish_plan import generate_publish_plan
from .state import StateStore
from .video_validator import VideoValidator

console=Console()

def parser():
    p=argparse.ArgumentParser(description="Kitok -> MoneyPrinterTurbo pipeline")
    p.add_argument("--id",action="append",dest="ids")
    p.add_argument("--dry-run",action="store_true")
    p.add_argument("--retry-failed",action="store_true")
    p.add_argument("--status",action="store_true")
    p.add_argument("--check-mpt",action="store_true")
    p.add_argument("--plan",action="store_true")
    p.add_argument("-v","--verbose",action="store_true")
    return p

def load_all():
    s=Settings(); s.ensure_directories()
    q=ContentQueue.load(s.queue_path); st=StateStore(s.state_path)
    pp=s.mpt_preset_path if s.mpt_preset_path.is_absolute() else (PROJECT_ROOT/s.mpt_preset_path).resolve()
    return s,q,st,load_preset(pp)

def show_status(q,st):
    t=Table(title="Kitok status")
    for c in ["ID","Publish","Status","Attempts","MPT %","Last error"]: t.add_column(c)
    for item in sorted(q.items,key=lambda x:x.publish_at):
        r=st.get(item.id)
        t.add_row(item.id,item.publish_at.strftime("%Y-%m-%d %H:%M"),r.get("status","pending"),
                  str(r.get("attempts",0)),str(r.get("mpt_progress","")),str(r.get("last_error") or ""))
    console.print(t)

def main(argv=None):
    a=parser().parse_args(argv)
    try: s,q,st,preset=load_all()
    except Exception as e:
        console.print(f"[red]Startup error:[/red] {e}"); return 2
    configure_logging(s.logs_dir,a.verbose)

    if a.dry_run:
        v=VideoValidator(s.ffprobe_binary)
        console.print(f"[green]Queue OK[/green]: {len(q.items)} items")
        console.print(f"[green]Preset OK[/green]: {len(preset)} fields")
        console.print(f"MPT: {s.mpt_base_url}")
        console.print(f"READY_DIR: {s.ready_dir.expanduser()}")
        console.print("ffprobe: "+("OK" if v.ffprobe_available() else "NOT FOUND"))
        return 0 if v.ffprobe_available() else 1

    if a.status: show_status(q,st); return 0
    if a.plan:
        generate_publish_plan(q,st.all(),s.local_ready_dir)
        if s.ready_dir.expanduser().resolve()!=s.local_ready_dir.resolve():
            generate_publish_plan(q,st.all(),s.ready_dir.expanduser())
        console.print("[green]Plan regenerated[/green]"); return 0

    client=MPTClient(s.mpt_base_url,s.mpt_api_key,s.mpt_request_timeout_seconds,
                     s.http_retry_attempts,s.http_retry_base_seconds)
    try:
        if a.check_mpt:
            console.print("[green]MPT reachable[/green]")
            console.print(client.check()); return 0
        ids=set(a.ids) if a.ids else None
        if ids:
            missing=ids-set(q.by_id())
            if missing:
                console.print(f"[red]Unknown ids:[/red] {', '.join(sorted(missing))}"); return 2
        Pipeline(s,q,st,client,preset).process(ids=ids,retry_failed=a.retry_failed)
        show_status(q,st); return 0
    except MPTError as e:
        console.print(f"[red]MPT error:[/red] {e}"); return 3
    finally:
        client.close()
