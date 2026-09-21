"""Local FastAPI transport. All business actions go through Python services."""
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import shutil
import subprocess

from fastapi import FastAPI, File, Form, UploadFile, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import ValidationError

from .schemas import (CreateContent, EditContent, JobRequest, ScheduleRequest, CharacterRequest,
                      VoiceRequest, RenamePose, BackgroundImport, ContentView, JobResponse,
                      ScheduleView, PreferencesRequest, QueueRequest, ScheduleMoveRequest,
                      ConfirmRequest)
from ..application import Application, user_error
from ..assets import AssetService, inside, identifier
from ..app_settings import preferences, save_preferences
from ..scheduling import ScheduleService
from ..thumbnails import ThumbnailService

log = logging.getLogger('kitok.api')


def create_app(settings=None, *, catalog_path=None):
    application = Application(settings)
    assets = AssetService(application.s, catalog_path)
    calendar = ScheduleService(application)

    @asynccontextmanager
    async def lifespan(app):
        yield
        application.close()

    app = FastAPI(title='Kitok local studio', version='0.2.0', lifespan=lifespan)
    app.state.application = application
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver', '[::1]'])
    origins = ['http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8000', 'http://localhost:8000']
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['*'], allow_headers=['Content-Type'])

    @app.middleware('http')
    async def local_origin(request: Request, call_next):
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and request.headers.get('origin') not in [None, *origins]:
            return JSONResponse({'detail': 'Only the local Kitok UI may change data'}, status_code=403)
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def request_error(request, error):
        messages = ['.'.join(map(str, e['loc'][1:])) + ': ' + e['msg'] for e in error.errors()]
        return JSONResponse({'detail': '; '.join(messages)}, status_code=422)

    @app.exception_handler(ValueError)
    @app.exception_handler(RuntimeError)
    async def expected_error(request, error):
        return JSONResponse({'detail': user_error(error)}, status_code=409 if 'already' in str(error) else 422)

    @app.exception_handler(Exception)
    async def unexpected_error(request, error):
        log.exception('API request failed', exc_info=error)
        return JSONResponse({'detail': 'No se pudo completar la operación. Revisa los permisos y los logs.'}, status_code=500)

    @app.get('/api/health')
    def health():
        s = application.s
        return {'fish_configured': bool(s.fish_api_key.get_secret_value()),
                'ffmpeg': bool(shutil.which(s.ffmpeg_binary)), 'ffprobe': bool(shutil.which(s.ffprobe_binary)),
                'gameplay_count': sum(1 for x in assets.backgrounds() if x['pool'] == 'gameplay' and x['compatible']),
                'character_count': len(assets.characters()), 'ready_directory': str(s.local_ready_dir),
                'ready_accessible': s.local_ready_dir.is_dir(),
                'buffer_configured': bool(s.buffer_api_key.get_secret_value()),
                'cloudinary_configured': bool(s.cloudinary_api_key.get_secret_value()),
                'publishing_enabled': s.publish_enabled, 'timezone': s.timezone}

    @app.post('/api/health/mpt')
    def check_mpt():
        from ..mpt_client import MPTClient
        s = application.s
        client = MPTClient(s.mpt_base_url, s.mpt_api_key, s.mpt_request_timeout_seconds,
                           s.http_retry_attempts, s.http_retry_base_seconds)
        try:
            client.check()
            return {'ok': True, 'message': 'MPT API conectado'}
        finally:
            client.close()

    @app.get('/api/metadata')
    def metadata():
        return assets.metadata()

    @app.get('/api/content', response_model=list[ContentView])
    def content():
        return application.content()

    @app.post('/api/content', response_model=ContentView, status_code=201)
    def create(body: CreateContent):
        values = body.model_dump(exclude_none=True)
        if not values.get('caption'):
            values['caption'] = values['subject']
        return application.create(values)

    @app.get('/api/content/{cid}', response_model=ContentView)
    def detail(cid: str):
        return application.content(cid)

    @app.patch('/api/content/{cid}', response_model=ContentView)
    def edit(cid: str, body: EditContent):
        return application.edit(cid, body.model_dump(exclude_unset=True))

    @app.post('/api/content/{cid}/duplicate', response_model=ContentView)
    def duplicate(cid: str):
        return application.duplicate(cid)

    @app.delete('/api/content/{cid}')
    def delete(cid: str, confirm: bool = False):
        if not confirm:
            raise ValueError('Confirma la eliminación del contenido. El vídeo se conserva.')
        application.delete(cid)
        return {'ok': True}

    @app.post('/api/content/{cid}/jobs', response_model=JobResponse, status_code=202)
    def generate(cid: str, body: JobRequest):
        return application.start_job(cid, body.action)

    @app.get('/api/content/{cid}/video')
    def video(cid: str):
        return FileResponse(application.video_path(cid), media_type='video/mp4')

    @app.get('/api/content/{cid}/download')
    def download(cid: str):
        path = application.video_path(cid)
        return FileResponse(path, filename=path.name, media_type='video/mp4')

    @app.get('/api/content/{cid}/thumbnail')
    def thumbnail(cid: str):
        path = ThumbnailService(application.s.state_path.parent / 'thumbnails', application.s.ffmpeg_binary).get(cid, application.video_path(cid))
        if not path:
            raise HTTPException(404, 'Thumbnail unavailable')
        return FileResponse(path, media_type='image/jpeg')

    @app.get('/api/schedule', response_model=ScheduleView)
    def schedule():
        return calendar.view()

    @app.put('/api/content/{cid}/schedule', response_model=ContentView)
    def change_schedule(cid: str, body: ScheduleRequest):
        when = body.at
        if body.local_time:
            from datetime import datetime, timezone
            from zoneinfo import ZoneInfo
            if body.at is not None:
                raise ValueError('Use at or local_time, not both')
            naive = datetime.fromisoformat(body.local_time)
            if naive.tzinfo is not None:
                raise ValueError('local_time must not include an offset')
            zone = ZoneInfo(application.s.timezone)
            when = naive.replace(tzinfo=zone)
            if when.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != naive:
                raise ValueError('Esta hora no existe por el cambio de horario. Elige otra hora.')
            if when.utcoffset() != naive.replace(tzinfo=zone, fold=1).utcoffset():
                raise ValueError('Esta hora es ambigua por el cambio de horario. Elige otra hora.')
        return calendar.change(cid, when, body.platforms)

    @app.post('/api/content/{cid}/queue')
    def queue_action(cid: str, body: QueueRequest):
        if body.action == 'add':
            return calendar.queue_add(cid)
        if body.action == 'remove':
            return calendar.queue_remove(cid)
        return calendar.queue_move(cid, body.action)

    @app.post('/api/content/{cid}/schedule-move')
    def move_scheduled(cid: str, body: ScheduleMoveRequest):
        return calendar.schedule_move(cid, body.direction)

    @app.post('/api/schedule/fill')
    def fill_schedule(body: ConfirmRequest):
        return calendar.fill(confirm=body.confirm)

    @app.post('/api/schedule/queue-ready')
    def queue_ready(body: ConfirmRequest):
        return calendar.queue_all_ready(confirm=body.confirm)

    @app.post('/api/schedule/unschedule-future')
    def unschedule_future(body: ConfirmRequest):
        return calendar.unschedule_future(confirm=body.confirm, queue_after=body.queue_after)

    @app.post('/api/schedule/sync')
    def sync_buffer():
        from ..control_panel import ControlPanel
        return ControlPanel(application.s).refresh_buffer(sync=True)

    # Publishing remains a review + explicit confirmation operation in the existing service.
    pending_publications = {}

    @app.post('/api/content/{cid}/publish-preview')
    def publish_preview(cid: str):
        from ..control_panel import ControlPanel
        from uuid import uuid4
        if not application.content(cid)['scheduled_at']:
            raise ValueError('Programa primero una fecha futura para este vídeo')
        action = ControlPanel(application.s).prepare_action('publish', cid)
        token = uuid4().hex
        pending_publications[token] = action
        return {'token': token, 'summary': action.summary, 'rows': action.rows}

    @app.post('/api/publish/{token}/confirm')
    def publish_confirm(token: str):
        from ..control_panel import ControlPanel
        action = pending_publications.pop(token, None)
        if not action:
            raise ValueError('La confirmación ha caducado. Revisa de nuevo el envío.')
        return ControlPanel(application.s).execute(action, confirmed=True)

    @app.get('/api/assets/characters')
    def characters():
        return assets.characters()

    def asset_edit():
        if application._pending:
            raise ValueError('Espera a que termine la generación antes de modificar recursos')

    @app.post('/api/assets/characters', status_code=201)
    def add_character(body: CharacterRequest):
        with application._mutex:
            asset_edit()
            return assets.add_character(body.id, body.display_name, body.side, body.scale)

    @app.post('/api/assets/voices', status_code=201)
    def add_voice(body: VoiceRequest):
        with application._mutex:
            asset_edit()
            return assets.save_voice(body.id, body.display_name, body.provider, body.value, body.character)

    @app.post('/api/assets/characters/{character}/poses', status_code=201)
    def upload_pose(character: str, name: str = Form(...), file: UploadFile = File(...)):
        with application._mutex:
            asset_edit()
            return assets.save_pose(character, name, file.file)

    @app.get('/api/assets/characters/{character}/poses/{filename}')
    def pose(character: str, filename: str):
        path = inside(application.s.character_root / identifier(character), filename)
        if not path.is_file() or path.suffix.lower() != '.png':
            raise HTTPException(404, 'Pose not found')
        return FileResponse(path, media_type='image/png')

    @app.patch('/api/assets/characters/{character}/poses/{filename}')
    def rename_pose(character: str, filename: str, body: RenamePose):
        with application._mutex:
            asset_edit()
            return assets.rename_pose(character, filename, body.name)

    @app.delete('/api/assets/characters/{character}/poses/{filename}')
    def delete_pose(character: str, filename: str, confirm: bool = False):
        if not confirm:
            raise ValueError('Confirma la eliminación de la pose')
        with application._mutex:
            asset_edit()
            assets.delete_pose(character, filename)
        return {'ok': True}

    @app.get('/api/assets/backgrounds')
    def backgrounds():
        return assets.backgrounds()

    @app.post('/api/assets/backgrounds/import', status_code=201)
    def import_background(body: BackgroundImport):
        with application._mutex:
            asset_edit()
            return assets.import_background(body.source, body.pool)

    @app.get('/api/settings')
    def settings_view():
        return preferences(application.s)

    @app.patch('/api/settings')
    def settings_edit(body: PreferencesRequest):
        with application._mutex:
            asset_edit()
            application.s = save_preferences(application.s, body.model_dump(exclude_none=True))
            assets.s = application.s
            return preferences(application.s)

    return app
