"""Application boundary shared by CLI and HTTP: durable jobs over the existing engine."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import threading
from uuid import uuid4

from .app_settings import configured
from .config import PROJECT_ROOT
from .models import ContentItem, ContentQueue
from .mpt_client import MPTClient
from .pipeline import Pipeline, load_preset
from .regeneration import ReadyRegenerator, skip_reason
from .state import StateStore, write_json_atomic
from .queue_editor import add_item, edit_item, delete_item, queue_digest, suggested_id

log = logging.getLogger('kitok.application')


def run_generation(settings, queue, state, client, preset, *, ids=None, retry_failed=False, regenerate=False):
    """One execution boundary used by CLI, API jobs and the existing engine."""
    if regenerate:
        return ReadyRegenerator(settings, queue, state, client, preset).run(ids=ids)
    return Pipeline(settings, queue, state, client, preset).process(ids=ids, retry_failed=retry_failed)


def user_error(error):
    text = str(error)
    patterns = [
        ('FISH_API_KEY', 'Configura FISH_API_KEY en .env para generar las voces.'),
        ('network request', 'No se pudo conectar con Fish. Comprueba la conexión y vuelve a intentarlo.'),
        ('HTTP 429', 'Fish ha limitado las solicitudes. Espera un momento antes de reintentar.'),
        ('timeout', 'El servicio tardó demasiado. Revisa System y los logs antes de reintentar.'),
        ('No gameplay', 'Añade un fondo de gameplay válido en Assets.'),
        ('at least', 'No hay un fondo suficientemente largo para este diálogo.'),
        ('between 5', 'El vídeo dura menos de 5 segundos. Amplía el texto del diálogo.'),
        ('ffmpeg', 'FFmpeg no pudo completar el vídeo. Comprueba la instalación y los recursos.'),
        ('publishing', 'Este vídeo tiene historial de publicación. Gestiona el cambio en Buffer.'),
        ('already', 'Esta operación ya está en curso o el contenido ya existe.'),
    ]
    for key, message in patterns:
        if key.lower() in text.lower():
            return message
    return text[:500]


class Application:
    def __init__(self, settings=None):
        self.s = configured(settings)
        self.s.ensure_directories()
        if not self.s.queue_path.exists():
            write_json_atomic(self.s.queue_path, [])
        self._mutex = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='kitok-video')
        self._pending = set()
        # Interrupted jobs require an explicit retry; never restart paid work on boot.
        state = StateStore(self.s.state_path)
        from .locks import generation_lock
        for cid, record in state.all().items():
            if record.get('job', {}).get('status') in {'queued', 'running'}:
                try:
                    with generation_lock(self.s, cid):
                        state.upsert(cid, job={**record['job'], 'status': 'failed',
                                              'error': 'Kitok se cerró durante el trabajo. Puedes reintentarlo.'})
                except RuntimeError:
                    pass

    def close(self):
        self._executor.shutdown(wait=True)

    def load(self):
        return ContentQueue.load(self.s.queue_path), StateStore(self.s.state_path)

    def content(self, cid=None):
        queue, state = self.load()
        rows = []
        for item in queue.items:
            if cid is not None and item.id != cid:
                continue
            record = state.get(item.id)
            posts = record.get('publishing', {}).get('buffer', {})
            states = {p.get('status') for p in posts.values()}
            status = record.get('status', 'pending')
            publishing_status = ('published' if states and states <= {'sent'} else
                                 'attention' if states & {'unknown', 'creating', 'needs_attention'} else
                                 'scheduled' if states & {'scheduled', 'sending', 'sent'} else None)
            job = record.get('job', {})
            if job.get('status') in {'queued', 'running'}:
                status = 'generating'
            elif job.get('status') == 'failed' and status != 'ready':
                status = 'failed'
            media = record.get('ready_path') or record.get('output_path')
            has_preview = bool(media and Path(media).is_file() and record.get('status') == 'ready')
            scheduled_at = item.publish_at.isoformat() if item.schedule_enabled and item.publish_at else None
            schedule_status = ('published' if publishing_status == 'published' else
                               'scheduled' if publishing_status or scheduled_at else
                               'queued' if record.get('schedule_status') == 'queued' else
                               'unscheduled')
            rows.append({'item': item.model_dump(mode='json'), 'status': status,
                         'generation_status': status, 'schedule_status': schedule_status,
                         'publishing_status': publishing_status,
                         'queue_position': record.get('queue_position'),
                         'stage': record.get('generation_stage'), 'job': job,
                         'error': user_error(record['last_error']) if record.get('last_error') else job.get('error'),
                         'technical_error': record.get('last_error'),
                         'preview_url': f'/api/content/{item.id}/video' if has_preview else None,
                         'thumbnail_url': f'/api/content/{item.id}/thumbnail' if has_preview else None,
                         'duration': record.get('validation', {}).get('duration'),
                         'scheduled_at': scheduled_at,
                         'buffer': {platform: {k: p.get(k) for k in ('post_id', 'status', 'due_at', 'last_error')}
                                    for platform, p in posts.items()},
                         'remote_locked': bool(record.get('publishing')),
                         'warnings': record.get('generation_warnings', [])})
        if cid is not None:
            if not rows:
                raise ValueError('Content ID not found')
            return rows[0]
        return rows

    def create(self, values):
        with self._mutex:
            queue, state = self.load()
            values = dict(values)
            values.setdefault('id', suggested_id(values['subject'], set(queue.by_id()) | set(state.all())))
            values.setdefault('schedule_enabled', values.get('publish_at') is not None)
            values.setdefault('caption', values['subject'])
            created = add_item(self.s.queue_path, state, values, expected_revision=queue_digest(self.s.queue_path))
            return self.content(created.id)

    def _assert_idle(self, cid, state):
        from .locks import generation_lock
        with generation_lock(self.s, cid):
            pass
        if cid in self._pending or state.get(cid).get('job', {}).get('status') in {'queued', 'running'}:
            raise ValueError('This video is already being generated')

    def edit(self, cid, changes):
        with self._mutex:
            _, state = self.load()
            self._assert_idle(cid, state)
            edit_item(self.s.queue_path, state, cid, changes, expected_revision=queue_digest(self.s.queue_path))
            return self.content(cid)

    def duplicate(self, cid):
        values = self.content(cid)['item']
        values.pop('id')
        values['subject'] += ' · copia'
        values['publish_at'] = None
        values['schedule_enabled'] = False
        return self.create(values)

    def delete(self, cid):
        with self._mutex:
            _, state = self.load()
            self._assert_idle(cid, state)
            delete_item(self.s.queue_path, state, cid, expected_revision=queue_digest(self.s.queue_path))

    def start_job(self, cid, action='generate'):
        with self._mutex:
            queue, state = self.load()
            if cid not in queue.by_id():
                raise ValueError('Content ID not found')
            self._assert_idle(cid, state)
            record = state.get(cid)
            if record.get('publishing'):
                raise ValueError('Publishing history exists; duplicate this video before changing it')
            if action in {'regenerate', 'background'}:
                reason = skip_reason(record)
                if reason:
                    raise ValueError(reason)
                if action == 'background':
                    item = queue.by_id()[cid]
                    if item.content_format != 'dialogue':
                        raise ValueError('New background is available for dialogue videos')
                    # This explicit action changes only the visual seed of an unpublished READY item.
                    with state.publishing_lock():
                        import json
                        raw = json.loads(self.s.queue_path.read_text())
                        for row in raw:
                            if row['id'] == cid:
                                row['background_seed'] = uuid4().hex[:12]
                        write_json_atomic(self.s.queue_path, raw)
            elif record.get('status') == 'ready':
                raise ValueError('Video already ready; choose Regenerate')
            job = {'id': uuid4().hex, 'status': 'queued', 'action': action,
                   'created_at': datetime.now(timezone.utc).isoformat(), 'error': None}
            state.upsert(cid, job=job, generation_stage='En cola')
            self._pending.add(cid)
            self._executor.submit(self._run_job, cid, job)
            return job

    def _run_job(self, cid, job):
        state = StateStore(self.s.state_path)
        client = None
        try:
            state.upsert(cid, job={**job, 'status': 'running'}, last_error=None)
            settings = configured(self.s)
            queue = ContentQueue.load(settings.queue_path)
            preset = load_preset(settings.mpt_preset_path if settings.mpt_preset_path.is_absolute()
                                 else PROJECT_ROOT / settings.mpt_preset_path)
            client = MPTClient(settings.mpt_base_url, settings.mpt_api_key,
                               settings.mpt_request_timeout_seconds, settings.http_retry_attempts,
                               settings.http_retry_base_seconds)
            result = run_generation(settings, queue, state, client, preset, ids={cid}, retry_failed=True,
                                    regenerate=job['action'] in {'regenerate', 'background'})
            record = StateStore(settings.state_path).get(cid)
            if record.get('status') != 'ready' or (result is not None and result.failed):
                raise RuntimeError(record.get('last_error') or 'Generation did not produce a valid video')
            state.upsert(cid, job={**job, 'status': 'succeeded'}, generation_stage='Ready')
        except Exception as error:
            log.exception('Generation job failed: %s', cid)
            state.upsert(cid, job={**job, 'status': 'failed', 'error': user_error(error)}, last_error=str(error))
        finally:
            if client:
                client.close()
            with self._mutex:
                self._pending.discard(cid)

    def video_path(self, cid):
        self.content(cid)
        record = StateStore(self.s.state_path).get(cid)
        path = Path(record.get('ready_path') or '')
        if record.get('status') != 'ready' or not path.is_file():
            raise ValueError('The video is not ready yet')
        return path.resolve()
