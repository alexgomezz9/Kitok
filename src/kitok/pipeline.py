"""Generate shorts natively, validate media and atomically copy READY files."""
from __future__ import annotations
import json, logging, tempfile
from pathlib import Path
from .config import Settings
from .file_manager import copy_atomic, output_filename, write_metadata_sidecar
from .models import ContentQueue
from .publish_plan import generate_publish_plan
from .state import StateStore
from .video_validator import VideoValidator
from .generation import GenerationService
from .locks import generation_lock, GenerationBusy

log=logging.getLogger("kitok.pipeline")

def load_preset(path:Path)->dict:
    """Read current MPT defaults; does not change the preset or contact MPT."""
    raw=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw,dict): raise ValueError("preset must be a JSON object")
    forbidden={"video_subject","video_script","video_terms"}
    if forbidden.intersection(raw): raise ValueError("preset contains content-specific fields")
    return raw

class Pipeline:
    def __init__(self,settings:Settings,queue:ContentQueue,state:StateStore,client=None,preset:dict|None=None):
        self.s=settings; self.q=queue; self.state=state; self.client=client; self.preset=preset
        self.validator=VideoValidator(settings.ffprobe_binary,settings.min_video_seconds,
                                      settings.max_video_seconds,settings.min_vertical_width,
                                      settings.min_vertical_height)
        self.generator=GenerationService(settings,preset or {})

    def process(self,ids:set[str]|None=None,retry_failed:bool=False) -> None:
        """Generate selected drafts; historical remote tasks require explicit review."""
        for item in self.q.items:
            if ids is not None and item.id not in ids: continue
            cur=self.state.get(item.id); status=cur.get("status","pending")
            if status=="ready":
                log.info("SKIP %s already ready",item.id); continue
            if status=="failed" and not retry_failed:
                log.info("SKIP %s failed; use --retry-failed",item.id); continue
            if cur.get("generation_renderer") == "native" and status in {"generating", "generated", "submitted"} and not retry_failed:
                log.warning("SKIP %s interrupted native generation; review paid work before --retry-failed", item.id)
                continue
            try:
                self._process_item(item)
            except GenerationBusy as error:
                log.warning("SKIP %s: %s", item.id, error)
                continue
            except KeyboardInterrupt: raise
            except Exception as e:
                self.state.upsert(item.id,status="failed",last_error=str(e))
                log.exception("FAILED %s: %s",item.id,e)
            self.refresh_plans()

    def _process_item(self,item):
        with generation_lock(self.s, item.id), tempfile.TemporaryDirectory(prefix=".generate-", dir=self.s.generated_dir) as temp:
            self._generate_and_prepare(item,Path(temp))

    def _generate_and_prepare(self,item,workspace):
        cur=self.state.get(item.id)
        if cur.get("mpt_task_id") and cur.get("generation_renderer") != "native":
            raise RuntimeError(
                f"Historical MPT task {cur['mpt_task_id']} requires review; native generation does not resume or resubmit it. "
                "Preserve this record and create a new draft ID after reviewing its result."
            )
        self.state.increment_attempts(item.id)
        self.state.upsert(item.id, generation_renderer="native", status="generating", last_error=None)
        self.generator.on_stage = lambda label, event, elapsed=None: self.state.upsert(item.id, generation_stage=label) if event == "start" else None
        self.state.upsert(item.id, generation_stage="Preparing audio")
        plan=self.generator.plan(item,workspace)
        source=None
        name=output_filename(item)
        generated=self.s.generated_dir/name
        self.generator.finish(item,plan,source,generated,workspace)
        self.state.upsert(item.id,status="generated",last_error=None)
        self.state.upsert(item.id, generation_stage="Validating")
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
                          last_error=None,validation=result.model_dump(),
                          generation_warnings=self.generator.last_warnings,
                          generation_debug=self.generator.last_metadata)
        log.info("READY %s -> %s",item.id,external)

    def refresh_plans(self) -> None:
        """Write local handoff plans; never schedules remote posts."""
        states=self.state.all()
        generate_publish_plan(self.q,states,self.s.local_ready_dir)
        if self.s.ready_dir.expanduser().resolve()!=self.s.local_ready_dir.resolve():
            generate_publish_plan(self.q,states,self.s.ready_dir.expanduser())
