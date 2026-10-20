"""Local long-form drafts/jobs, independent of the shorts queue and publishing.

The existing CLI config and renderers remain authoritative. No external work is
performed by save/preview/list. A paid render always requires an explicit start.
"""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
from functools import lru_cache
import json
import logging
from pathlib import Path
import re
import shutil
from uuid import uuid4

from .config import PROJECT_ROOT
from .locks import generation_lock, GenerationBusy
from .models import ContentItem
from .state import write_json_atomic

log = logging.getLogger('kitok.longform_studio')


@lru_cache(maxsize=1)
def runner():
    """Use the shared package CLI without importing a root script dynamically."""
    from .longform import cli
    return cli


class LongformStudio:
    def __init__(self, application):
        self.application = application
        self.s = application.s
        self.root = self.s.data_root or PROJECT_ROOT
        self.folder = self.root / 'content' / 'longform' / 'studio'
        self.records = self.s.state_path.parent / 'longform'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.records.mkdir(parents=True, exist_ok=True)
        # Never replay paid work after a restart. A live worker owns the flock.
        for path in self.records.glob('*.json'):
            record = json.loads(path.read_text(encoding='utf-8'))
            cid = record['id']
            self._valid_id(cid)
            if record['status'] in {'queued', 'running'}:
                try:
                    with generation_lock(self.s, f'longform-{cid}'):
                        # The live worker may have completed between the first
                        # read and acquiring the lock. Preserve that result.
                        current = self._read(cid)
                        if current['status'] in {'queued', 'running'}:
                            current['status'] = 'interrupted'
                            current['error'] = 'El trabajo se interrumpió. Revisa los logs antes de generar otra copia; la voz puede haberse cobrado.'
                            self._write(current)
                except GenerationBusy:
                    pass

    @staticmethod
    def _valid_id(cid):
        # Only server-issued IDs can address drafts or files through HTTP.
        if not isinstance(cid, str) or not re.fullmatch(r'lf_[0-9a-f]{32}', cid):
            raise ValueError('Vídeo largo no encontrado')
        return cid

    def _write(self, record):
        write_json_atomic(self.records / f"{self._valid_id(record['id'])}.json", record)

    def _read(self, cid):
        path = self.records / f'{self._valid_id(cid)}.json'
        if not path.is_file():
            raise ValueError('Vídeo largo no encontrado')
        return json.loads(path.read_text(encoding='utf-8'))

    def _definition_values(self, body, cid='lf_preview'):
        r = runner()
        item = ContentItem(id=cid, subject=body.subject, script=body.script,
                           keywords=body.keywords, platforms=['youtube'], schedule_enabled=False)
        r.validate_tts_script(item.script)
        config = {
            'id': cid, 'subject': item.subject, 'keywords': item.keywords,
            'narrator_voice': body.narrator_voice or r.DEFAULT_NARRATOR_VOICE,
            'music_enabled': body.music_enabled if body.music_mode is None else body.music_mode != 'off',
        }
        # Keep historical draft configs byte-compatible for tamper detection.
        if body.music_mode is not None:
            config.update(music_mode=body.music_mode, music_track=body.music_track)
        if body.mounting_style != 'basic':
            config['mounting_style'] = body.mounting_style
        if body.music_mode == 'manual' and not body.music_track:
            raise ValueError('Selecciona una pista de la biblioteca para la música manual.')
        if body.mounting_style == 'documentary' and body.music_mode is None and body.music_enabled:
            raise ValueError('Para el montaje documental elige música automática, manual o desactivada.')
        if body.music_mode != 'manual' and body.music_track is not None:
            raise ValueError('La pista sólo se elige en modo de música manual.')
        return item, config

    @staticmethod
    def _native_only(renderer):
        if renderer != 'native':
            raise ValueError('Los vídeos nuevos usan el motor nativo. MPT se conserva sólo para recuperar una tarea histórica con el CLI y --resume TASK_ID.')

    def preview(self, body):
        self._native_only(body.renderer)
        item, config = self._definition_values(body)
        r = runner()
        from .rendering.native import fish_reference_id
        fish_reference_id(config['narrator_voice'])
        checks = [
            {'label': 'FFmpeg instalado', 'ok': bool(shutil.which(self.s.ffmpeg_binary))},
            {'label': 'ffprobe instalado', 'ok': bool(shutil.which(self.s.ffprobe_binary))},
        ]
        checks += [
            {'label': 'FISH_API_KEY configurada en .env', 'ok': bool(self.s.fish_api_key.get_secret_value())},
            {'label': 'PEXELS_API_KEY configurada en .env', 'ok': bool(self.s.pexels_api_key.get_secret_value())},
        ]
        if body.music_mode in {'auto', 'manual'}:
            if body.music_mode == 'auto':
                ready = self.music_narrative_options(item.script)['eligible']
            else:
                ready = any(row['id'] == body.music_track for row in self.music_options())
            checks.append({'label': 'Música de biblioteca verificada en caché local', 'ok': ready})
        elif body.music_mode is None and body.music_enabled:
            checks.append({'label': 'Música local disponible (assets/music/loose_thread/level.mp3)',
                           'ok': (self.root / r.DEFAULT_BACKGROUND_MUSIC_FILE).is_file()})
        return {'valid': True, 'can_generate': all(check['ok'] for check in checks),
                'renderer': body.renderer, 'words': len(item.script.split()),
                'checks': checks, 'format': '16:9 · 1920×1080 · sin subtítulos',
                'note': 'Comprobación local: no verifica credenciales ni conexión. Generar usa Fish y Pexels; puede consumir saldo.',
                'output_directory': str(self.root / 'outputs' / 'longform')}

    def music_options(self):
        from .audio_library import AudioLibrary
        cache = self.root / 'cache' / 'audio-library'
        catalog = self.root / 'presets' / 'music_sources.json'
        if not cache.is_dir() or not catalog.is_file():
            return []
        library = AudioLibrary(catalog, cache, ffmpeg=self.s.ffmpeg_binary, ffprobe=self.s.ffprobe_binary)
        try:
            return library.available(channel='loose_thread')
        finally:
            library.close()

    def music_narrative_options(self, script):
        from .audio_library import AudioLibrary
        cache = self.root / 'cache' / 'audio-library'
        catalog = self.root / 'presets' / 'music_sources.json'
        if not cache.is_dir() or not catalog.is_file():
            return {'eligible': False, 'reason': 'No hay biblioteca musical local verificada.'}
        library = AudioLibrary(catalog, cache, ffmpeg=self.s.ffmpeg_binary, ffprobe=self.s.ffprobe_binary)
        try:
            return library.narrative_options(script, channel='loose_thread')
        finally:
            library.close()

    def music_preview(self, track_id):
        from .audio_library import AudioLibrary
        cache = self.root / 'cache' / 'audio-library'
        catalog = self.root / 'presets' / 'music_sources.json'
        if not cache.is_dir() or not catalog.is_file():
            raise ValueError('Pista musical local no disponible')
        library = AudioLibrary(catalog, cache, ffmpeg=self.s.ffmpeg_binary, ffprobe=self.s.ffprobe_binary)
        try:
            return library.preview(track_id)
        finally:
            library.close()

    def create(self, body):
        self.preview(body)  # Bad scripts never become stored jobs. Missing keys may be fixed later.
        cid = f'lf_{uuid4().hex}'
        item, config = self._definition_values(body, cid)
        script_path = self.folder / f'{cid}.txt'
        config['script_file'] = str(script_path.relative_to(self.root))
        script_path.write_text(item.script + '\n', encoding='utf-8')
        write_json_atomic(self.folder / f'{cid}.json', config)
        record = {'id': cid, 'subject': item.subject, 'status': 'draft',
                  'renderer': body.renderer, 'created_at': datetime.now(timezone.utc).isoformat(),
                  'stage': 'Guion guardado. Comprueba los requisitos antes de generar.', 'error': None,
                  'request': body.model_dump()}
        self._write(record)
        return self.detail(cid)

    def detail(self, cid):
        record = self._read(cid)
        path = self.output_path(cid)
        available = record['status'] == 'succeeded' and path.is_file()
        return {k: v for k, v in record.items() if k != 'request'} | {
            'preview_url': f'/api/longform/{cid}/video' if available else None,
            'download_url': f'/api/longform/{cid}/download' if available else None,
            'credits_url': f'/api/longform/{cid}/credits' if available and path.with_suffix('.credits.md').is_file() else None,
            'config_path': str(self.folder / f'{cid}.json'),
            'script_path': str(self.folder / f'{cid}.txt'),
            'output_path': str(path),
            'script': record['request']['script'],
            'keywords': record['request']['keywords'],
            'narrator_voice': record['request']['narrator_voice'] or runner().DEFAULT_NARRATOR_VOICE,
            'music_enabled': record['request'].get('music_mode') not in (None, 'off') or record['request'].get('music_mode') is None and record['request']['music_enabled'],
            'music_mode': record['request'].get('music_mode'),
            'music_track': record['request'].get('music_track'),
            'mounting_style': record['request'].get('mounting_style', 'basic'),
        }

    def list(self):
        return sorted([self.detail(path.stem) for path in self.records.glob('*.json')],
                      key=lambda row: row['created_at'], reverse=True)

    def output_path(self, cid):
        return self.root / 'outputs' / 'longform' / f'{self._valid_id(cid)}.mp4'

    def video_path(self, cid):
        if self._read(cid)['status'] != 'succeeded' or not self.output_path(cid).is_file():
            raise ValueError('El vídeo largo todavía no está disponible')
        return self.output_path(cid)

    def credits_path(self, cid):
        path = self.video_path(cid).with_suffix('.credits.md')
        if not path.is_file() or path.is_symlink():
            raise ValueError('Los créditos todavía no están disponibles')
        return path

    def start(self, cid):
        with self.application._mutex:
            # Hold this cross-process lock from reservation through completion.
            lease = ExitStack()
            submitted = False
            try:
                lease.enter_context(generation_lock(self.s, f'longform-{self._valid_id(cid)}'))
                record = self._read(cid)
                self._native_only(record['renderer'])
                if record['status'] != 'draft':
                    raise ValueError('Este trabajo ya se inició. Revisa su resultado; no se reenvía automáticamente.')
                from .api.schemas import LongformRequest
                body = LongformRequest.model_validate(record['request'])
                preview = self.preview(body)
                if not preview['can_generate']:
                    missing = ', '.join(c['label'] for c in preview['checks'] if not c['ok'])
                    raise ValueError(f'Falta configurar: {missing}')
                # Reject every outside config change, including hidden CLI
                # options. Do this before following script_file from disk.
                config_path = self.folder / f'{cid}.json'
                expected_config = self._definition_values(body, cid)[1]
                expected_config['script_file'] = str((self.folder / f'{cid}.txt').relative_to(self.root))
                if json.loads(config_path.read_text(encoding='utf-8')) != expected_config:
                    raise ValueError('El guion o la configuración cambió fuera del estudio. Crea y revisa un nuevo borrador.')
                definition = runner().load_longform_config(config_path, project_root=self.root)
                if definition.item.script != body.script:
                    raise ValueError('El guion cambió fuera del estudio. Crea y revisa un nuevo borrador.')
                if self.output_path(cid).exists() or runner().longform_task_path(cid, project_root=self.root).exists():
                    raise ValueError('Ya existe una salida o una tarea MPT. Revisa los archivos antes de continuar.')
                record.update(status='queued', stage='En cola; espera a que terminen los otros vídeos.', error=None)
                self._write(record)
                try:
                    # Same single worker as shorts: no extra CPU/GPU competition.
                    self.application._executor.submit(self._run, record, definition, lease)
                    submitted = True  # Ownership of the lease has transferred to the worker.
                except Exception:
                    record.update(status='draft', stage='No se pudo iniciar; puedes volver a intentarlo.')
                    self._write(record)
                    raise
                return self.detail(cid)
            except Exception:
                if not submitted:
                    lease.close()
                raise

    def _run(self, record, definition, lease):
        def stage(message):
            record.update(status='running', stage=message)
            self._write(record)
        try:
            stage('Generando narración y vídeo. Puede tardar varios minutos.')
            self._render(record, definition, stage)
            if not self.output_path(record['id']).is_file():
                raise RuntimeError('El motor terminó sin crear un vídeo')
            record.update(status='succeeded', stage='Vídeo terminado. Reprodúcelo y descárgalo.')
        except Exception as exc:
            log.exception('Long-form job failed: %s', record['id'])
            record.update(status='failed', error='No se pudo terminar el vídeo. Revisa logs/kitok-AAAAMMDD.log. No se reintenta automáticamente; Fish puede haber consumido saldo.',
                          stage='Necesita revisión')
            from .audio_library import AudioLibraryError
            if isinstance(exc, AudioLibraryError):
                record['error'] = f'Mezcla de audio detenida: {exc}. La narración se conserva; revisa la recuperación sin Fish.'
            from .editing.production import EditorialValidationError
            if isinstance(exc, EditorialValidationError):
                record['error'] = f'Montaje de vídeo detenido: {exc}. La narración y los planos se conservan.'
        finally:
            try:
                self._write(record)
            finally:
                lease.close()

    def _recovery_inputs(self, cid):
        """Validate the saved studio request before following any on-disk path."""
        from .api.schemas import LongformRequest
        from .native_recovery import regular, inspect_narration
        regular(self.records / f'{self._valid_id(cid)}.json', self.root)
        record = self._read(cid)
        self._native_only(record['renderer'])
        if record['status'] not in {'failed', 'interrupted'}:
            raise ValueError('Sólo se recuperan trabajos nativos fallidos o interrumpidos.')
        body = LongformRequest.model_validate(record['request'])
        config_path = regular(self.folder / f'{cid}.json', self.root)
        script_path = regular(self.folder / f'{cid}.txt', self.root)
        expected = self._definition_values(body, cid)[1]
        expected['script_file'] = str(script_path.relative_to(self.root))
        if json.loads(config_path.read_text()) != expected:
            raise ValueError('La configuración cambió; la recuperación no volverá a sintetizar voz.')
        definition = runner().load_longform_config(config_path, project_root=self.root)
        if definition.item.script != body.script:
            raise ValueError('El guion cambió; la recuperación no volverá a sintetizar voz.')
        task_path = runner().longform_task_path(cid, project_root=self.root)
        if task_path.exists() or task_path.is_symlink():
            raise ValueError('Existe una tarea MPT histórica; no corresponde a recuperación Native.')
        confirmed = inspect_narration(self.s, definition, self.output_path(cid),
                                      source_files=(config_path, script_path))
        return record, definition, confirmed

    def recovery_audit(self, cid):
        # The audit itself has no writes or lock-file creation.
        return self._recovery_inputs(cid)[2].public()

    def recover(self, cid, expected_sha256, audit_fingerprint):
        """Explicit start, sharing the one executor and the full-life content lock."""
        with self.application._mutex:
            lease = ExitStack()
            submitted = False
            try:
                lease.enter_context(generation_lock(self.s, f'longform-{self._valid_id(cid)}'))
                record, definition, confirmed = self._recovery_inputs(cid)
                if expected_sha256 != confirmed.sha256 or audit_fingerprint != confirmed.fingerprint:
                    raise ValueError('La confirmación no coincide con la auditoría actual; revisa de nuevo.')
                previous = json.loads(json.dumps(record))
                attempts = record.setdefault('recovery_attempts', [])
                attempts.append({'started_at': datetime.now(timezone.utc).isoformat(),
                                 'previous_status': record['status'], 'previous_error': record.get('error'),
                                 'previous_stage': record.get('stage'), **confirmed.public()})
                record.update(status='queued', error=None,
                              stage='Recuperación local en cola; reutiliza narración Fish confirmada.')
                self._write(record)
                try:
                    self.application._executor.submit(self._run_recovery, record, definition, confirmed, lease)
                    submitted = True
                except Exception:
                    self._write(previous)
                    raise
                return self.detail(cid)
            finally:
                if not submitted:
                    lease.close()

    def _run_recovery(self, record, definition, confirmed, lease):
        def stage(message):
            record.update(status='running', stage=message)
            self._write(record)
        try:
            stage('Recuperando montaje sin Fish ni red; sólo recursos confirmados locales.')
            self._render(record, definition, stage, confirmed_narration=confirmed)
            if not self.output_path(record['id']).is_file():
                raise RuntimeError('El motor terminó sin crear un vídeo')
            record.update(status='succeeded', error=None, stage='Vídeo recuperado reutilizando la narración confirmada.')
            record['recovery_attempts'][-1].update(status='succeeded')
        except Exception as exc:
            log.exception('Offline long-form recovery failed: %s', record['id'])
            record.update(status='failed', error=f'Recuperación local detenida: {exc}. No se solicitó voz nueva.', stage='Necesita revisión')
            record['recovery_attempts'][-1].update(status='failed', error=str(exc))
        finally:
            try:
                self._write(record)
            finally:
                lease.close()

    def _render(self, record, definition, stage, *, confirmed_narration=None):
        self._native_only(record['renderer'])
        from .providers.pexels import PexelsProvider
        from .media.ffmpeg import FFmpegNativeEngine, choose_encoder
        from .rendering.native import NativeLongformRenderer
        if confirmed_narration is not None:
            from .native_recovery import CachedStock
            provider = CachedStock(self.s.native_cache_dir, ffprobe=self.s.ffprobe_binary)
        else:
            provider = PexelsProvider(self.s.pexels_api_key.get_secret_value(), self.s.native_cache_dir,
                                      ffprobe=self.s.ffprobe_binary, attempts=self.s.http_retry_attempts)
        try:
            encoder = choose_encoder(self.s.ffmpeg_binary, requested='auto', nvenc_preset='p5')
            engine = FFmpegNativeEngine(ffmpeg=self.s.ffmpeg_binary, ffprobe=self.s.ffprobe_binary, encoder=encoder)
            NativeLongformRenderer(self.s, provider, engine, output_path=self.output_path(record['id']),
                                   output=stage, confirmed_narration=confirmed_narration).render(definition)
        finally:
            provider.close()
