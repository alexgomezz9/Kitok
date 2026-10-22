"""Restartable image requests for Codex's real built-in tool, not a paid API client.

All mutations are called under the episode lock by the public pipeline interface.
An interrupted request is never reissued automatically: its claim remains visible.
"""
from __future__ import annotations

import io
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from PIL import Image, ImageOps

from .files import digest, local_file, replace_state
from .models import Config, IllustrationPlan
from .planner import combined_prompt, reference_records


class ImageBatch:
    def __init__(self, episode: Path, plan: IllustrationPlan, config: Config):
        self.episode, self.plan, self.config = episode, plan, config
        if not plan.direction_complete:
            raise ValueError('Complete the scene directions before requesting illustrations')
        if plan.references != reference_records(episode, config):
            raise ValueError('Style reference changed after planning')
        if plan.config_sha256 != digest(config.model_dump()):
            raise ValueError('Production configuration changed; preserve this episode and use a new revision')
        self.state_path = local_file(episode, '.stickman/images.json', exists=False)
        self.approval_path = local_file(episode, '.stickman/style_approval.json', exists=False)
        self.jobs = {}
        for scene in plan.scenes:
            self.jobs[scene.id] = {'id':scene.id, 'kind':'scene', 'image_file':scene.image_file,
                                   'prompt':combined_prompt(scene, config), 'references':scene.reference_files}
        concepts_path = local_file(episode, 'miniaturas/conceptos.json')
        concepts=json.loads(concepts_path.read_text())
        self.plan_key=digest(plan.model_dump())
        self.key=digest({'illustration_plan':plan.model_dump(),'thumbnail_concepts':concepts})
        for concept in concepts['concepts']:
            ident = 'thumb_'+concept['id']
            self.jobs[ident] = {'id':ident, 'kind':'thumbnail', 'image_file':concept['background_file'],
                                'prompt':config.style_prompt+'\n\n'+concept['prompt'],
                                'references':[r['path'] for r in plan.references if r['role'] in {'interior','thumbnail','character'}]}
        indices = sorted({0, len(plan.scenes)//2, len(plan.scenes)-1})
        self.samples = [plan.scenes[i].id for i in indices]

    def _read(self):
        if not self.state_path.exists():
            return {'version':1, 'plan_sha256':self.plan_key, 'batch_sha256':self.key, 'jobs':{}}
        state = json.loads(self.state_path.read_text())
        if (state.get('plan_sha256') != self.plan_key or state.get('batch_sha256') != self.key
                or not isinstance(state.get('jobs'), dict)):
            raise ValueError('Image batch belongs to different inputs; preserve it and use another revision')
        for ident,row in state['jobs'].items():
            if (ident not in self.jobs or not isinstance(row,dict)
                    or row.get('status') not in {'pending','claimed','unknown','failed','complete'}
                    or type(row.get('attempts')) is not int or not 1<=row['attempts']<=3):
                raise ValueError('Image state is invalid; preserve it for review')
        return state

    def _write(self, state):
        replace_state(self.state_path, state)

    def _job(self, ident):
        if ident not in self.jobs:
            raise ValueError('Unknown planned image ID')
        return self.jobs[ident]

    @staticmethod
    def inspect(path: Path) -> dict:
        if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= 40*1024**2:
            raise ValueError('Image missing, symlinked or larger than 40MB')
        try:
            with Image.open(path) as image:
                width, height = image.size
                if image.getexif().get(274) in {5,6,7,8}:
                    width,height=height,width
                if (image.format not in {'PNG','JPEG','WEBP'} or width*height > 40_000_000
                        or width < 1280 or height < 720 or abs(width/height-16/9) > .02):
                    raise ValueError('Image needs landscape 16:9, at least 1280x720 and at most 40MP')
                image.load()
                return {'width':width,'height':height,'sha256':digest(path),'format':image.format}
        except (OSError, Image.DecompressionBombError) as error:
            raise ValueError('Image is corrupt or unsafe to decode') from error

    def _valid(self, ident, row):
        if not isinstance(row, dict) or row.get('status') != 'complete':
            return False
        path = local_file(self.episode, self._job(ident)['image_file'], exists=False)
        info = self.inspect(path)
        if info['sha256'] != row.get('sha256'):
            raise ValueError(f'Previously accepted image changed: {ident}')
        return True

    def approval(self):
        if not self.approval_path.exists():
            return None
        data = json.loads(self.approval_path.read_text())
        if data.get('plan_sha256') != self.plan_key or data.get('batch_sha256') != self.key:
            raise ValueError('Style approval is stale for the current plan')
        state = self._read()
        if set(data.get('sample_hashes',{})) != set(self.samples):
            raise ValueError('Style approval does not cover the representative sample')
        for ident, value in data['sample_hashes'].items():
            row = state['jobs'].get(ident)
            if not self._valid(ident,row) or row['sha256'] != value or not row.get('reviewed'):
                raise ValueError('Approved style sample changed or lacks visual review')
        return data

    def status(self):
        state, approved = self._read(), self.approval()
        provided = self.provided_authorization()
        rows = []
        for ident, job in self.jobs.items():
            row = state['jobs'].get(ident, {})
            valid = self._valid(ident,row)
            rows.append({'id':ident,'kind':job['kind'],'file':job['image_file'],
                         'status':row.get('status','pending'),'valid':valid,
                         'reviewed':bool(row.get('reviewed')),'attempts':row.get('attempts',0),
                         'attempt_id':row.get('attempt_id'),
                         'eligible':not valid and row.get('status','pending') == 'pending'
                                    and (bool(approved) or ident in self.samples)})
        attempts = [attempt for row in state['jobs'].values() for attempt in [*row.get('history',[]),row]]
        costs = [attempt.get('reported_cost') for attempt in attempts if attempt.get('attempt_id')]
        return {'sample_ids':self.samples,'style_approved':bool(approved),'jobs':rows,
                'completed':sum(r['valid'] for r in rows),'planned':len(rows),
                'generation_cost':sum(costs) if costs and all(c is not None for c in costs) else None,
                'cost_note':'Unknown until the actual generation tool reports a cost; never treated as zero.',
                'assembly_authorized':bool(provided),
                'render_images_ready':all(r['valid'] and (r['reviewed'] or bool(provided)) for r in rows if r['kind']=='scene')}

    def provided_authorization(self):
        """Explicit operator permission to assemble supplied files; never visual QA."""
        path = local_file(self.episode,'.stickman/provided_images.json',exists=False)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        expected = {s.id:digest(local_file(self.episode,s.image_file)) for s in self.plan.scenes}
        if (data.get('plan_sha256') != self.plan_key or data.get('batch_sha256') != self.key
                or data.get('image_hashes') != expected):
            raise ValueError('Provided image authorization changed; preserve it and use another revision')
        return data

    def adopt_provided(self):
        """Register existing originals without normalization, renaming or fake review."""
        state = self._read()
        hashes = {}
        for scene in self.plan.scenes:
            info = self.inspect(local_file(self.episode,scene.image_file))
            old = state['jobs'].get(scene.id)
            if old and (old.get('source_kind') != 'provided_collection'
                        or old.get('sha256') != info['sha256'] or old.get('status') != 'complete'):
                raise ValueError('Existing image attempt cannot be replaced by provided resources')
            hashes[scene.id] = info['sha256']
        # All files are validated before either state or authorization is published.
        for scene in self.plan.scenes:
            state['jobs'].setdefault(scene.id,{'status':'complete','attempts':1,
                'sha256':hashes[scene.id],'source_kind':'provided_collection',
                'reviewed':False,'reported_cost':None})
        from .files import write
        self._write(state)
        write(local_file(self.episode,'.stickman/provided_images.json',exists=False),{
            'version':1,'plan_sha256':self.plan_key,'batch_sha256':self.key,
            'image_hashes':hashes,'authorization':'operator --reuse-images',
            'review_scope':'Assembly of supplied resources only; no new visual/style review asserted.'})
        return self.status()

    def claim(self, ident: str) -> dict:
        job = self._job(ident)
        approved = self.approval()
        if not approved and ident not in self.samples:
            raise ValueError('Approve the representative style sample before generating the full batch')
        state = self._read()
        old = state['jobs'].get(ident,{})
        if self._valid(ident,old):
            raise ValueError('This valid image is already complete; resume will reuse it')
        if old.get('status','pending') != 'pending':
            raise ValueError('Previous attempt needs review; import its result or explicitly authorize retry')
        attempts = old.get('attempts',0)+1
        if attempts > 3:
            raise ValueError('Image retry limit reached; preserve attempts and review manually')
        token = uuid4().hex
        state['jobs'][ident] = {'status':'claimed','attempt_id':token,'attempts':attempts,
                                'history':old.get('history',[]),'reported_cost':None}
        self._write(state)
        references = [str(local_file(self.episode, p)) for p in job['references']]
        if approved:
            references = [str(local_file(self.episode,self.jobs[i]['image_file'])) for i in self.samples]+references
        tool_args = {'prompt':job['prompt'],'transparent_background':False}
        if references:
            tool_args['referenced_image_paths'] = list(dict.fromkeys(references))
        return {'id':ident,'attempt_id':token,'tool':'image_gen.imagegen','arguments':tool_args,
                'destination':job['image_file'],
                'instruction':'Codex calls the real built-in image tool, then registers the chosen output. '
                              'There is no shell imagegen command or automatic paid API fallback.'}

    def import_image(self, ident: str, source: Path, *, attempt_id: str, reviewed: bool,
                     reported_cost: float | None = None, source_kind: str = 'provided') -> dict:
        job, state = self._job(ident), self._read()
        row = state['jobs'].get(ident,{})
        if row.get('attempt_id') != attempt_id or row.get('status') not in {'claimed','unknown'}:
            raise ValueError('Image result must match its active attempt; do not consume a stale result')
        if reported_cost is not None and (not math.isfinite(reported_cost) or reported_cost < 0):
            raise ValueError('Reported cost must be nonnegative and actually supplied by the tool')
        if source_kind not in {'builtin_imagegen','provided','technical_fixture'}:
            raise ValueError('Identify the real image origin; importing a file is not proof of AI generation')
        source = Path(source)
        original = self.inspect(source)
        target = local_file(self.episode,job['image_file'],exists=False)
        with Image.open(source) as image:
            buffer = io.BytesIO()
            ImageOps.exif_transpose(image).convert('RGB').save(buffer,format='PNG')
            content = buffer.getvalue()
        incoming_hash = hashlib.sha256(content).hexdigest()
        adopting = target.exists() and source.resolve() == target.resolve()
        if adopting:
            incoming_hash = original['sha256']
            if original['format'] != 'PNG':
                raise ValueError('A file placed directly at its PNG destination must really be PNG')
        if any(r.get('sha256') == incoming_hash for key,r in state['jobs'].items() if key != ident):
            raise ValueError('A different scene already uses this exact image; generate a distinct illustration')
        if target.exists():
            # A result may already have been copied at the prescribed path by the
            # agent before its bookkeeping was interrupted. Adoption is explicit.
            if source.resolve() != target.resolve():
                raise FileExistsError('Image destination exists; preserved without overwriting')
        else:
            target.parent.mkdir(parents=True,exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix='.image-',suffix='.png',dir=target.parent)
            try:
                with os.fdopen(fd,'wb') as stream:
                    stream.write(content)
                os.link(temporary,target)
            finally:
                Path(temporary).unlink(missing_ok=True)
        info = self.inspect(target)
        row.update(status='complete',sha256=info['sha256'],original=original,
                   reviewed=bool(reviewed),reported_cost=reported_cost,source_kind=source_kind)
        self._write(state)
        return {**row,'file':job['image_file']}

    def mark_unknown(self, ident: str, *, attempt_id: str, reason: str):
        state = self._read()
        row = state['jobs'].get(ident,{})
        if row.get('attempt_id') != attempt_id or row.get('status') != 'claimed':
            raise ValueError('Unknown-result receipt does not match an active request')
        row.update(status='unknown',reason=reason)
        self._write(state)

    def retry(self, ident: str, *, reason: str):
        self._job(ident)
        state = self._read()
        row = state['jobs'].get(ident,{})
        if not reason.strip() or row.get('status') not in {'claimed','unknown','failed'} or row.get('attempts',0)>=3:
            raise ValueError('Retry needs a reviewed failed/uncertain attempt, reason and remaining attempt budget')
        row.setdefault('history',[]).append({k:v for k,v in row.items() if k!='history'})
        row.update(status='pending',reason=reason,attempt_id=None,reported_cost=None)
        self._write(state)

    def reject(self, ident: str, *, reason: str):
        job, state = self._job(ident), self._read()
        row = state['jobs'].get(ident,{})
        if row.get('source_kind') == 'provided_collection':
            raise ValueError('Provided collection is immutable; preserve it and create another revision')
        if not reason.strip() or row.get('status')!='complete':
            raise ValueError('Reject a completed image with a concrete review reason')
        if self.approval() and ident in self.samples:
            raise ValueError('An approved style sample is immutable; create another episode/style revision')
        source = local_file(self.episode,job['image_file'],exists=False)
        archive = local_file(self.episode,f'.stickman/rejected/{ident}-{row["attempt_id"]}.png',exists=False)
        observed = None
        if source.exists():
            observed = digest(source)
            archive.parent.mkdir(parents=True,exist_ok=True)
            if not archive.exists():
                os.link(source,archive)
            if digest(source) != observed or digest(archive) != observed:
                raise ValueError('Image changed during rejection; preserved for review')
            source.unlink()
        row.update(status='failed',reviewed=False,rejection_reason=reason,rejected_sha256=observed,
                   rejected_file=str(archive.relative_to(self.episode)) if archive.exists() else None)
        self._write(state)

    def review(self, ident: str, *, reviewer: str):
        self._job(ident)
        state=self._read()
        row=state['jobs'].get(ident,{})
        if not reviewer.strip() or not self._valid(ident,row):
            raise ValueError('Review needs an existing valid image and an identified reviewer')
        row.update(reviewed=True,reviewer=reviewer)
        self._write(state)
        return row

    def approve_style(self, *, reviewer: str):
        if not reviewer.strip():
            raise ValueError('Style approval requires an identified reviewer')
        if not any(r['role']=='interior' for r in self.plan.references):
            raise ValueError('Interior-frame references are required; thumbnails alone cannot establish production style')
        state = self._read()
        hashes = {}
        for ident in self.samples:
            row = state['jobs'].get(ident,{})
            if not self._valid(ident,row) or not row.get('reviewed'):
                raise ValueError('Review every representative image before approving the style')
            hashes[ident] = row['sha256']
        receipt = {'version':1,'plan_sha256':self.plan_key,'batch_sha256':self.key,
                   'sample_hashes':hashes,'reviewer':reviewer,
                   'review_scope':'visual sample; final audio and all episode images still require review'}
        from .files import write
        write(self.approval_path,receipt)
        return receipt
