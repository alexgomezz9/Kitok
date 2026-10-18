"""Explicit local-only editorial renders over saved, operator-authored plans."""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import shutil
from uuid import uuid4

from .config import PROJECT_ROOT
from .editing.production import render_editorial_plan
from .editing.quality import inspect_video
from .editing.storyboard import EditorialPlan, file_hash, project_file
from .locks import generation_lock, GenerationBusy
from .state import write_json_atomic

log = logging.getLogger('kitok.editorial_studio')
FILES = frozenset({'A_current.mp4', 'B_improved.mp4', 'B_improved.qa.json', 'B_improved.contact.jpg', 'CREDITS.md'})


class EditorialStudio:
    def __init__(self, application):
        self.application = application
        self.s = application.s
        self.root = (self.s.data_root or PROJECT_ROOT).resolve()
        self.folder = self.root / 'outputs' / 'evaluation'
        self.records = self.s.state_path.parent / 'editorial'
        self._media_hashes = {}
        self.records.mkdir(parents=True, exist_ok=True)
        for path in self.records.glob('*.json'):
            try:
                cid = self.valid_id(path.stem)
                with generation_lock(self.s, f'editorial-{cid}'):
                    record = self._record(cid)
                    if record['status'] in {'queued', 'running'}:
                        record.update(status='interrupted', stage='Interrumpido; revisa los archivos antes de iniciar otro montaje.', error='El trabajo no se reanuda automáticamente.')
                        self._write(record)
            except GenerationBusy:
                pass
            except (ValueError, OSError, KeyError):
                log.warning('Skipped invalid editorial state file: %s', path.name)

    @staticmethod
    def valid_id(cid):
        if not isinstance(cid, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', cid):
            raise ValueError('Montaje no encontrado')
        return cid

    def _inside(self, base, path):
        # Output aliases must never redirect promotion onto A, the plan or an
        # input. Containment alone also accepts symlinks within this folder.
        lexical = path.absolute()
        if not lexical.is_relative_to(self.root):
            raise ValueError('Archivo de montaje fuera de su carpeta')
        component = self.root
        for part in lexical.relative_to(self.root).parts:
            component = component / part
            if component.is_symlink():
                raise ValueError('Los archivos y carpetas de montaje no pueden ser enlaces simbólicos')
        resolved = path.resolve()
        if not resolved.is_relative_to(base.resolve()) or not resolved.is_relative_to(self.root):
            raise ValueError('Archivo de montaje fuera de su carpeta')
        return resolved

    def _folder(self, cid):
        path = self._inside(self.folder, self.folder / self.valid_id(cid))
        if not path.is_dir():
            raise ValueError('Montaje no encontrado')
        return path

    def _path(self, cid, name):
        return self._inside(self._folder(cid), self._folder(cid) / name)

    def _plan(self, cid):
        path = self._path(cid, 'plan.json')
        plan = EditorialPlan.load(path)
        inputs = [project_file(self.root, plan.audio_source)]
        inputs += [project_file(self.root, asset.path) for asset in plan.assets.values()]
        # The approved input must survive replacement of the current B output.
        if any(self._path(cid, name) in inputs for name in FILES - {'A_current.mp4'}):
            raise ValueError('El plan usa B como entrada. Conserva esa entrada con otro nombre antes de renderizar.')
        self.file(cid, 'A_current.mp4')
        return plan

    def _record(self, cid):
        path = self._inside(self.records, self.records / f'{self.valid_id(cid)}.json')
        if not path.is_file():
            return {'id': cid, 'status': 'ready', 'stage': 'Plan local guardado. Listo para revisar.', 'error': None}
        record = json.loads(path.read_text(encoding='utf-8'))
        if record.get('id') != cid:
            raise ValueError('Estado del montaje no válido')
        return record

    def _write(self, record):
        record['updated_at'] = datetime.now(timezone.utc).isoformat()
        path = self._inside(self.records, self.records / f"{self.valid_id(record['id'])}.json")
        write_json_atomic(path, record)

    def file(self, cid, name):
        if name not in FILES:
            raise ValueError('Archivo de montaje no permitido')
        path = self._path(cid, name)
        if not path.is_file():
            raise ValueError('Archivo de montaje todavía no disponible')
        if name in {'B_improved.qa.json', 'B_improved.contact.jpg'} and self._approved_report(cid) is None:
            raise ValueError('El informe no corresponde al vídeo B actual; revisa el montaje interrumpido')
        return path

    def _approved_report(self, cid):
        qa, video = self._path(cid, 'B_improved.qa.json'), self._path(cid, 'B_improved.mp4')
        if not qa.is_file() or not video.is_file():
            return None
        report = json.loads(qa.read_text(encoding='utf-8'))
        stat = video.stat()
        identity = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        previous = self._media_hashes.get(cid)
        if previous is None or previous[0] != identity:
            previous = (identity, file_hash(video))
            self._media_hashes[cid] = previous
        contact = self._path(cid, 'B_improved.contact.jpg')
        if (report.get('video_sha256') != previous[1] or not contact.is_file()
                or report.get('contact_sheet_sha256') != file_hash(contact)):
            return None
        return report

    def detail(self, cid):
        plan = self._plan(cid)
        record = self._record(cid)
        files = {name: f'/api/editorial/{cid}/files/{name}' for name in FILES if self._path(cid, name).is_file()}
        stats = None
        report = self._approved_report(cid)
        warning = None
        if 'B_improved.qa.json' in files:
            if report is not None:
                stats = {key: report.get(key) for key in ('duration', 'geometry', 'fps', 'full_decode', 'black_intervals', 'loudness', 'comparison', 'manual_review_required')}
            else:
                warning = 'El informe no corresponde al vídeo B actual. Revisa los archivos y copias anteriores antes de continuar.'
        if report is None:
            files.pop('B_improved.qa.json', None)
            files.pop('B_improved.contact.jpg', None)
        video = self._path(cid, 'B_improved.mp4')
        stat = video.stat() if video.is_file() else None
        revision = f'{stat.st_ino}-{stat.st_ctime_ns}-{stat.st_size}' if stat else None
        return record | {'title': plan.title, 'duration': plan.duration, 'scene_count': len(plan.scenes),
                         'files': files, 'stats': stats, 'qa_warning': warning, 'media_revision': revision}

    def list(self):
        result = []
        if self.folder.is_dir():
            for folder in sorted(self.folder.iterdir()):
                try:
                    result.append(self.detail(folder.name))
                except (ValueError, OSError, KeyError):
                    continue
        return result

    def start(self, cid):
        with self.application._mutex:
            lease = ExitStack()
            try:
                lease.enter_context(generation_lock(self.s, f'editorial-{self.valid_id(cid)}'))
                plan = self._plan(cid)  # Validate saved timeline and inputs before reserving a job.
                record = self._record(cid)
                if record['status'] in {'queued', 'running'}:
                    raise ValueError('Este montaje ya está en curso')
                record.update(status='queued', stage='En cola; reutilizará audio y recursos locales.', error=None, run_id=uuid4().hex)
                self._write(record)
                try:
                    self.application._executor.submit(self._run, record, plan, lease)
                except Exception:
                    record.update(status='failed', stage='No se pudo iniciar el montaje.', error='Vuelve a revisar el plan antes de iniciar.')
                    self._write(record)
                    raise
                lease = None  # Worker owns the generation lease.
                return self.detail(cid)
            finally:
                if lease is not None:
                    lease.close()

    def _run(self, record, plan, lease):
        cid = record['id']
        def stage(message):
            record.update(status='running', stage=message)
            self._write(record)
        try:
            output = self._path(cid, f'.render-{record["run_id"]}.mp4')
            qa = output.with_suffix('.qa.json')
            contact = qa.with_suffix('.contact.jpg')
            stage('Montando con audio y recursos existentes; sin proveedores.')
            render_editorial_plan(plan, root=self.root, output=output, settings=self.s, on_stage=stage)
            stage('Comprobando vídeo completo y audio A/B.')
            report = inspect_video(output, qa, settings=self.s, comparison=self.file(cid, 'A_current.mp4'),
                                   scene_boundaries=[(scene.start + scene.end) / 2 for scene in plan.scenes])
            target = self._path(cid, 'B_improved.mp4')
            # All artifacts must exist before touching the current comparison.
            if not all(path.is_file() for path in (output, qa, contact)):
                raise RuntimeError('El render o sus comprobaciones no crearon todos los archivos')
            report.update(video=str(target), video_sha256=file_hash(output),
                          contact_sheet_sha256=file_hash(contact),
                          contact_sheet=str(self._path(cid, 'B_improved.contact.jpg')))
            write_json_atomic(qa, report)
            replacements = [(contact, self._path(cid, 'B_improved.contact.jpg')),
                            (qa, self._path(cid, 'B_improved.qa.json')), (output, target)]
            backups = {}
            for _, previous in replacements:
                if previous.exists():
                    backup = self._path(cid, f'{previous.stem}.previous-{record["run_id"]}{previous.suffix}')
                    shutil.copy2(previous, backup)
                    backups[previous] = backup
            replaced = []
            try:
                # The MP4 is the final atomic switch; a failed preparation leaves B intact.
                for source, destination in replacements:
                    source.replace(destination)
                    replaced.append(destination)
            except Exception:
                for destination in reversed(replaced):
                    if destination in backups:
                        shutil.copy2(backups[destination], destination)
                    else:
                        destination.unlink(missing_ok=True)
                raise
            record.update(status='succeeded', stage='Montaje terminado. Revisa A y B.', error=None)
        except Exception:
            log.exception('Editorial render failed: %s', cid)
            record.update(status='failed', stage='Necesita revisión', error='No se pudo terminar el montaje. Revisa los logs; no se reintenta automáticamente.')
        finally:
            try:
                self._write(record)
            finally:
                lease.close()
