"""Submit/recover MPT tasks, normalize media, then atomically copy READY files.

Generation writes MPT tasks and local state. It never uploads or schedules posts.
"""
from __future__ import annotations
import json, logging, time
from pathlib import Path
from .config import Settings
from .file_manager import copy_atomic, output_filename, write_metadata_sidecar
from .models import ContentQueue
from .mpt_client import MPTClient, TASK_STATE_COMPLETE, TASK_STATE_FAILED
from .publish_plan import generate_publish_plan
from .state import StateStore
from .video_validator import VideoValidator

log=logging.getLogger("kitok.pipeline")

def load_preset(path:Path)->dict:
    """Read current MPT defaults; does not change the preset or contact MPT."""
    raw=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw,dict): raise ValueError("preset must be a JSON object")
    forbidden={"video_subject","video_script","video_terms"}
    if forbidden.intersection(raw): raise ValueError("preset contains content-specific fields")
    return raw

class Pipeline:
    def __init__(self,settings:Settings,queue:ContentQueue,state:StateStore,client:MPTClient,preset:dict):
        self.s=settings; self.q=queue; self.state=state; self.client=client; self.preset=preset
        self.validator=VideoValidator(settings.ffprobe_binary,settings.min_video_seconds,
                                      settings.max_video_seconds,settings.min_vertical_width,
                                      settings.min_vertical_height)

    def process(self,ids:set[str]|None=None,retry_failed:bool=False) -> None:
        """Submit/recover selected MPT tasks; writes generation state and local files."""
        for item in self.q.items:
            if ids is not None and item.id not in ids: continue
            cur=self.state.get(item.id); status=cur.get("status","pending")
            if status=="ready":
                log.info("SKIP %s already ready",item.id); continue
            if status=="failed" and not retry_failed:
                log.info("SKIP %s failed; use --retry-failed",item.id); continue
            if status=="failed" and retry_failed:
                self.state.reset_failed(item.id)
            try:
                self._process_item(item)
            except KeyboardInterrupt: raise
            except Exception as e:
                latest=self.state.get(item.id)
                if latest.get("mpt_task_id") and latest.get("status") in {"submitted","generating"}:
                    self.state.upsert(item.id,last_error=str(e))
                else:
                    self.state.upsert(item.id,status="failed",last_error=str(e))
                log.exception("FAILED %s: %s",item.id,e)
            self.refresh_plans()

    def _process_item(self,item):
        cur=self.state.get(item.id); task_id=cur.get("mpt_task_id")
        if task_id:
            log.info("RECOVER %s task=%s",item.id,task_id)
        else:
            self.state.increment_attempts(item.id)
            task_id=self.client.submit_video(item,self.preset)
            self.state.upsert(item.id,status="submitted",mpt_task_id=task_id,last_error=None)
            log.info("SUBMITTED %s task=%s",item.id,task_id)

        task=self._wait(item,task_id)
        if task.state==TASK_STATE_FAILED:
            detail=task.error or "MoneyPrinterTurbo task failed"
            if task.failed_stage: detail+=f" (stage: {task.failed_stage})"
            self.state.upsert(item.id,status="failed",last_error=detail); return
        if not task.videos:
            self.state.upsert(item.id,status="failed",last_error="MPT completed without video artifacts"); return

        name=output_filename(item)
        generated=self.s.generated_dir/name
        self.client.download_artifact(task.videos[0],generated)
        result=self.validator.prepare(generated,item.platforms,self.s.ffmpeg_binary)
        if not result.ok:
            copy_atomic(generated,self.s.failed_dir/name)
            self.state.upsert(item.id,status="failed",output_path=str(generated),
                              last_error="; ".join(result.errors)); return

        local=self.s.local_ready_dir/name; copy_atomic(generated,local)
        external=self.s.ready_dir.expanduser()/name
        if external.resolve()!=local.resolve(): copy_atomic(generated,external)
        else: external=local

        if self.s.copy_metadata_sidecars:
            write_metadata_sidecar(item,local)
            if external.resolve()!=local.resolve(): write_metadata_sidecar(item,external)

        self.state.upsert(item.id,status="ready",output_path=str(generated),ready_path=str(external),
                          last_error=None,validation=result.model_dump())
        log.info("READY %s -> %s",item.id,external)

    def _wait(self,item,task_id):
        started=time.monotonic(); timeout=self.s.task_timeout_minutes*60
        while True:
            task=self.client.get_task(task_id)
            if task.state==TASK_STATE_COMPLETE:
                self.state.upsert(item.id,status="generated",last_error=None); return task
            if task.state==TASK_STATE_FAILED: return task
            self.state.upsert(item.id,status="generating",mpt_progress=task.progress,last_error=None)
            if time.monotonic()-started>timeout:
                raise TimeoutError(f"Timed out waiting for {task_id}; task id retained for recovery")
            log.info("WAIT %s state=%s progress=%s",item.id,task.state,task.progress)
            time.sleep(self.s.poll_interval_seconds)

    def refresh_plans(self) -> None:
        """Write local handoff plans; never schedules remote posts."""
        states=self.state.all()
        generate_publish_plan(self.q,states,self.s.local_ready_dir)
        if self.s.ready_dir.expanduser().resolve()!=self.s.local_ready_dir.resolve():
            generate_publish_plan(self.q,states,self.s.ready_dir.expanduser())
