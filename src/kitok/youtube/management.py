"""Official discovery-backed API for local agents. No automatic mutation retries."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from importlib.resources import files
import json
import mimetypes
import os
from pathlib import Path
import re
import time
from urllib.parse import quote, urlsplit

import httpx

from .client import DATA, YouTubeReadOnly
from .oauth import ALLOWED_SCOPES, PrivateStore, YouTubeError, access_token

CATALOG = json.loads(files(__package__).joinpath('discovery.json').read_text())
CHANNEL = re.compile(r'UC[A-Za-z0-9_-]{22}\Z')
SAFE_ID = re.compile(r'[A-Za-z0-9_-]+\Z')
UNSUPPORTED = {
    'youtube.youtube.v3.liveChat.messages.stream': 'Usa youtube.liveChatMessages.list; streaming RPC no implementado.',
    'youtube.tests.insert': 'Endpoint interno de prueba, no es una función operativa del canal.',
}


class RemoteRejected(YouTubeError):
    """Definitive Google 4xx rejection: not an ambiguous write outcome."""


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def operation(name: str) -> tuple[dict, dict]:
    for api in CATALOG['apis'].values():
        if name in api['methods']:
            return api, api['methods'][name]
    raise YouTubeError('Operación desconocida. Consulta catalog.')


def file_info(filename: str) -> dict:
    path = Path(filename).absolute()
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise YouTubeError('Se requiere un archivo regular no vacío, sin enlace simbólico.')
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return {'path': str(path), 'size': path.stat().st_size, 'sha256': h.hexdigest(),
            'mime': mimetypes.guess_type(path.name)[0] or 'application/octet-stream'}


def validate_schema(value, schema: dict, schemas: dict, trail='body'):
    if '$ref' in schema:
        schema = schemas[schema['$ref']]
    kind = schema.get('type')
    valid = {'object': isinstance(value, dict), 'array': isinstance(value, list),
             'string': isinstance(value, str), 'integer': type(value) is int,
             'number': type(value) in (int, float), 'boolean': type(value) is bool}
    if kind in valid and not valid[kind]:
        raise YouTubeError(f'Tipo inválido en {trail}.')
    if schema.get('enum') and value not in schema['enum']:
        raise YouTubeError(f'Valor no permitido en {trail}.')
    if isinstance(value, dict):
        properties = schema.get('properties', {})
        for key, child in value.items():
            child_schema = properties.get(key, schema.get('additionalProperties'))
            if not isinstance(child_schema, dict):
                raise YouTubeError(f'Campo desconocido en {trail}.{key}.')
            validate_schema(child, child_schema, schemas, trail+'.'+key)
    elif isinstance(value, list):
        for item in value:
            validate_schema(item, schema.get('items', {}), schemas, trail+'[]')


class YouTubeManagement(YouTubeReadOnly):
    """Bounded official API; caller must pass the expected channel on every call."""

    def _identity(self, expected: str) -> dict:
        if not isinstance(expected, str) or not CHANNEL.fullmatch(expected):
            raise YouTubeError('Se requiere el ID exacto del canal esperado.')
        result = self._get(DATA+'channels', {'mine': 'true', 'part': 'snippet,contentDetails'})
        items = result.get('items', [])
        if len(items) != 1 or items[0].get('id') != expected:
            raise YouTubeError('El canal remoto no coincide con el canal esperado; operación bloqueada.')
        tokens = self.store.read('tokens.json')
        if tokens.get('channel_id') not in (None, expected):
            raise YouTubeError('La conexión está vinculada a otro canal.')
        tokens['channel_id'] = expected
        self.store.write('tokens.json', tokens)
        return items[0]

    def _scope(self, method: dict):
        granted = set((self.store.read('tokens.json') or {}).get('scope', '').split())
        if not granted.intersection(method.get('scopes', [])):
            raise YouTubeError('Falta permiso para esta operación. Conecta el perfil manage o members.')

    def _spec(self, request: dict) -> tuple[str, dict, dict, dict]:
        if not isinstance(request, dict) or set(request) - {'operation', 'params', 'body', 'media'}:
            raise YouTubeError('Petición: operation, params, body y media opcional.')
        if request.get('operation') in UNSUPPORTED:
            raise YouTubeError(UNSUPPORTED[request['operation']])
        api, method = operation(request.get('operation', ''))
        if not set(method.get('scopes', [])) & ALLOWED_SCOPES:
            raise YouTubeError('Esta operación requiere acceso de socio no configurado en Kitok.')
        params = deepcopy(request.get('params', {}))
        if not isinstance(params, dict):
            raise YouTubeError('params debe ser un objeto JSON.')
        allowed = method.get('parameters', {})
        if set(params) - set(allowed):
            raise YouTubeError('Parámetro desconocido; no se admiten tokens, claves ni URLs arbitrarias.')
        # A local channel connection is never a content-owner delegation.
        if any(key.lower().startswith('onbehalfof') for key in params):
            raise YouTubeError('La delegación Content Owner requiere otra integración.')
        for key, schema in allowed.items():
            if schema.get('required') and key not in params:
                raise YouTubeError('Falta el parámetro requerido: '+key)
            if key in params:
                check = dict(schema)
                if schema.get('repeated'):
                    check = {'type': 'array', 'items': schema}
                validate_schema(params[key], check, api['schemas'], 'params.'+key)
        path = method['path']
        for name in re.findall(r'\{([^{}]+)\}', path):
            key = name.lstrip('+')
            value = params.pop(key, None)
            if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
                raise YouTubeError('Identificador de ruta inválido: '+key)
            path = path.replace('{'+name+'}', quote(value, safe=''))
        url = api['rootUrl'] + api['servicePath'] + path
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc not in {
                'www.googleapis.com', 'youtubeanalytics.googleapis.com', 'youtubereporting.googleapis.com'}:
            raise YouTubeError('Endpoint oficial inválido.')
        body = request.get('body')
        if body is not None:
            if not method.get('request'):
                raise YouTubeError('Esta operación no acepta body.')
            validate_schema(body, method['request'], api['schemas'])
        media = request.get('media')
        if media and (not isinstance(media, str) or not method.get('supportsMediaUpload')):
            raise YouTubeError('Esta operación no admite un archivo de subida.')
        # Request.download URLs never enter the HTTP transport. Reporting CSV has its own method.
        return url, params, method, api

    def _send(self, method: str, url: str, *, params=None, body=None, headers=None,
              content=None, success=(200, 201, 204), raw=False):
        auth = {'Authorization': 'Bearer '+access_token(self.store, self.client)}
        auth.update(headers or {})
        try:
            response = self.client.request(method, url, params=params, json=body,
                content=content, headers=auth, timeout=120, follow_redirects=False)
        except httpx.HTTPError:
            raise YouTubeError('Resultado remoto incierto. No reintentar la mutación; revisar receipt y reconciliar.') from None
        if response.status_code not in success:
            error = RemoteRejected if 400 <= response.status_code < 500 and response.status_code != 408 else YouTubeError
            raise error(f'Google rechazó la operación (HTTP {response.status_code}). Sin reintento automático.')
        if raw:
            return response
        if response.status_code == 204 or not response.content:
            return {}
        try:
            value = response.json()
        except ValueError:
            raise YouTubeError('Respuesta JSON inválida; revisar el resultado remoto antes de continuar.') from None
        if not isinstance(value, dict):
            raise YouTubeError('Respuesta remota inválida.')
        return value

    def query(self, request: dict, expected: str) -> dict:
        url, params, method, _ = self._spec(request)
        if method['httpMethod'] != 'GET' or request.get('body') or request.get('media'):
            raise YouTubeError('query sólo acepta operaciones GET sin body ni media.')
        if method.get('supportsMediaDownload'):
            raise YouTubeError('La descarga de subtítulos requiere download-caption.')
        with self.store.lock():
            self._identity(expected)
            self._scope(method)
            result = self._send('GET', url, params=params)
            return {'channel_id': expected, 'operation': request['operation'],
                    'fetched_at': time.time(), 'result': result}

    def _before(self, request: dict) -> dict | None:
        """Snapshot where a direct official read-by-ID exists, never an inferred match."""
        name = request['operation']
        resource, action = name.rsplit('.', 1)
        read = resource+'.list'
        api, method = operation(name)
        if action not in {'update', 'delete'} or read not in api['methods']:
            return None
        listing = api['methods'][read]
        identifier = (request.get('body') or {}).get('id') or request.get('params', {}).get('id')
        if not identifier or 'id' not in listing.get('parameters', {}):
            return None
        params = {'id': [identifier] if listing['parameters']['id'].get('repeated') else identifier}
        if 'part' in listing['parameters']:
            part = request.get('params', {}).get('part', ['snippet'])
            params['part'] = part
        if 'videoId' in listing['parameters']:
            video = (request.get('body') or {}).get('snippet', {}).get('videoId')
            if video:
                params['videoId'] = video
        if any(schema.get('required') and key not in params for key, schema in listing['parameters'].items()):
            return None
        url, params, _, _ = self._spec({'operation': read, 'params': params})
        return self._send('GET', url, params=params)

    def plan(self, request: dict, expected: str) -> dict:
        _, _, method, _ = self._spec(request)
        if method['httpMethod'] == 'GET':
            raise YouTubeError('Usa query para lecturas.')
        request = deepcopy(request)
        media = file_info(request['media']) if request.get('media') else None
        with self.store.lock():
            self._identity(expected)
            prior = self.store.read('receipt.json')
            if prior and prior.get('status') in {'started', 'uncertain'}:
                raise YouTubeError('Hay una operación incierta. Reconcíliala antes de crear otro plan.')
            before = self._before(request)
            plan = {'version': 1, 'channel_id': expected, 'created_at': time.time(),
                    'expires_at': time.time()+1800, 'request': request, 'media': media,
                    'before': before, 'warning': 'PUT reemplaza las partes enviadas: omitir propiedades puede borrarlas. Revisar body completo. DELETE es irreversible.',
                    'scope_ready': bool(set((self.store.read('tokens.json') or {}).get('scope', '').split()) & set(method.get('scopes', [])))}
            plan['sha256'] = digest(plan)
            self.store.write('operation.json', plan)
            return plan

    def apply(self, approval: str, expected: str) -> dict:
        with self.store.lock():
            plan = self.store.read('operation.json')
            if not plan:
                raise YouTubeError('Falta crear un plan.')
            canonical = {key: value for key, value in plan.items() if key != 'sha256'}
            if approval != plan.get('sha256') or digest(canonical) != approval:
                raise YouTubeError('La aprobación no coincide con el plan exacto.')
            if plan.get('channel_id') != expected or time.time() >= plan['expires_at']:
                raise YouTubeError('Plan caducado o canal distinto.')
            previous = self.store.read('receipt.json')
            archived = self.store.read('receipt-'+approval+'.json')
            if archived or (previous and (previous.get('sha256') == approval or previous.get('status') in {'started', 'uncertain'})):
                raise YouTubeError('Operación ya enviada o incierta; reconciliar sin repetirla.')
            self._identity(expected)
            request = plan['request']
            url, params, method, _ = self._spec(request)
            self._scope(method)
            if plan['media'] and file_info(request['media']) != plan['media']:
                raise YouTubeError('El archivo cambió después del plan.')
            if self._before(request) != plan['before']:
                raise YouTubeError('El recurso remoto cambió; crea y revisa otro plan.')
            receipt = {'sha256': approval, 'channel_id': expected, 'operation': request['operation'],
                       'started_at': time.time(), 'status': 'started'}
            self.store.write('receipt.json', receipt)
            try:
                if plan['media']:
                    result = self._upload(request, params, plan['media'], receipt)
                else:
                    result = self._send(method['httpMethod'], url, params=params, body=request.get('body'))
                receipt.update(status='succeeded', response=result, finished_at=time.time())
                self.store.write('receipt.json', receipt)
                try:
                    receipt['readback'] = self._before(request)
                    receipt['readback_status'] = 'available' if receipt['readback'] is not None else 'not_supported'
                except YouTubeError:
                    receipt['readback_status'] = 'unavailable'
                self.store.write('receipt.json', receipt)
                return receipt
            except RemoteRejected:
                receipt['status'] = 'failed'
                self.store.write('receipt.json', receipt)
                raise
            except (YouTubeError, OSError):
                receipt['status'] = 'uncertain'
                self.store.write('receipt.json', receipt)
                raise

    def _upload(self, request: dict, params: dict, media: dict, receipt: dict) -> dict:
        api, method = operation(request['operation'])
        upload = method['mediaUpload'].get('protocols', {}).get('resumable')
        if not upload:
            # thumbnails.set and channelBanners.insert accept raw media with uploadType=media.
            simple = method['mediaUpload'].get('protocols', {}).get('simple')
            if not simple or request.get('body'):
                raise YouTubeError('Esta subida no soporta el protocolo elegido.')
            url = api['rootUrl'].rstrip('/') + simple['path']
            with open(media['path'], 'rb') as stream:
                return self._send(method['httpMethod'], url, params={**params, 'uploadType': 'media'},
                    content=iter(lambda: stream.read(1024*1024), b''), headers={'Content-Type': media['mime'], 'Content-Length': str(media['size'])})
        url = api['rootUrl'].rstrip('/') + upload['path']
        response = self._send(method['httpMethod'], url, params={**params, 'uploadType': 'resumable'},
            body=request.get('body', {}), headers={'X-Upload-Content-Type': media['mime'],
            'X-Upload-Content-Length': str(media['size'])}, raw=True)
        session = response.headers.get('location', '')
        parsed = urlsplit(session)
        if (parsed.scheme != 'https' or parsed.netloc != 'www.googleapis.com' or
                not parsed.path.startswith(('/upload/youtube/v3/', '/resumable/upload/youtube/v3/')) or parsed.fragment):
            raise YouTubeError('Google devolvió una URL de subida no permitida.')
        # Session URLs are credentials: private receipt only, never CLI output.
        receipt['upload_session'] = session
        receipt['media'] = media
        self.store.write('receipt.json', receipt)
        with open(media['path'], 'rb') as stream:
            return self._send('PUT', session, content=iter(lambda: stream.read(1024*1024), b''), headers={
                'Content-Type': media['mime'], 'Content-Length': str(media['size'])})

    def reconcile(self, expected: str) -> dict:
        """Read upload status; never resubmit bytes or repeat a mutation."""
        with self.store.lock():
            self._identity(expected)
            receipt = self.store.read('receipt.json')
            if not receipt or receipt.get('channel_id') != expected:
                raise YouTubeError('No hay recibo para este canal.')
            session = receipt.get('upload_session')
            if session:
                parsed = urlsplit(session)
                if parsed.scheme != 'https' or parsed.netloc != 'www.googleapis.com' or not parsed.path.startswith(('/upload/youtube/v3/', '/resumable/upload/youtube/v3/')):
                    raise YouTubeError('Sesión de subida inválida.')
                response = self._send('PUT', session, content=b'', headers={
                    'Content-Length': '0', 'Content-Range': 'bytes */'+str(receipt['media']['size'])},
                    raw=True, success=(200, 201, 308))
                if response.status_code in (200, 201):
                    receipt.update(status='succeeded', response=response.json())
                else:
                    receipt['uploaded_range'] = response.headers.get('range')
            else:
                plan = self.store.read('operation.json')
                if not plan or plan.get('sha256') != receipt['sha256']:
                    raise YouTubeError('No hay plan correspondiente para consultar el recurso.')
                receipt['readback'] = self._before(plan['request'])
                # A read may aid human reconciliation, but does not prove a POST was not applied.
            self.store.write('receipt.json', receipt)
            return receipt

    def resolve(self, approval: str, expected: str, outcome: str, evidence: str) -> dict:
        """Explicit local acknowledgement after checking remote state; never sends a write."""
        if outcome not in {'succeeded', 'not_applied'} or not isinstance(evidence, str) or len(evidence.strip()) < 20:
            raise YouTubeError('Registra resultado y evidencia remota concreta de al menos20caracteres.')
        with self.store.lock():
            receipt = self.store.read('receipt.json')
            if not receipt or receipt.get('sha256') != approval or receipt.get('channel_id') != expected:
                raise YouTubeError('El recibo o canal no coincide.')
            self._identity(expected)
            if receipt.get('status') not in {'started', 'uncertain'}:
                raise YouTubeError('El recibo no necesita resolución.')
            receipt.update(status='resolved', resolved_outcome=outcome, evidence=evidence, resolved_at=time.time())
            self.store.write('receipt.json', receipt)
            return receipt

    def download_report(self, job: str, report: str, expected: str, output: Path):
        if not SAFE_ID.fullmatch(job) or not SAFE_ID.fullmatch(report):
            raise YouTubeError('ID de informe inválido.')
        with self.store.lock():
            self._identity(expected)
            metadata = self._send('GET', 'https://youtubereporting.googleapis.com/v1/jobs/'+job+'/reports/'+report)
            url = metadata.get('downloadUrl', '')
            parsed = urlsplit(url)
            if (parsed.scheme != 'https' or parsed.netloc != 'youtubereporting.googleapis.com' or
                    not parsed.path.startswith('/v1/media/') or parsed.fragment):
                raise YouTubeError('URL de informe no permitida; no se enviaron credenciales.')
            self._download(url, {'alt': 'media'}, output)

    def download_caption(self, caption: str, expected: str, output: Path, fmt='srt'):
        if not SAFE_ID.fullmatch(caption) or fmt not in {'srt', 'vtt', 'sbv', 'ttml', 'scc'}:
            raise YouTubeError('ID o formato de subtítulos inválido.')
        with self.store.lock():
            self._identity(expected)
            self._scope(operation('youtube.captions.download')[1])
            self._download(DATA+'captions/'+caption, {'tfmt': fmt}, output)

    def _download(self, url: str, params: dict, output: Path):
        # O_EXCL avoids clobbering deliveries and rejects symlink files.
        fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, 'wb') as target:
                token = access_token(self.store, self.client)
                try:
                    with self.client.stream('GET', url, params=params, headers={'Authorization': 'Bearer '+token},
                                            follow_redirects=False, timeout=120) as response:
                        if response.status_code != 200:
                            raise YouTubeError(f'Descarga rechazada (HTTP {response.status_code}).')
                        count = 0
                        for block in response.iter_bytes():
                            count += len(block)
                            if count > 512*1024*1024:
                                raise YouTubeError('Informe demasiado grande; límite local 512 MiB.')
                            target.write(block)
                except httpx.HTTPError:
                    raise YouTubeError('Descarga interrumpida; archivo parcial retirado.') from None
        except BaseException:
            output.unlink(missing_ok=True)
            raise


def public_receipt(receipt: dict) -> dict:
    return {key: value for key, value in receipt.items() if key not in {'upload_session', 'media'}}


def request_schemas(api: dict, method: dict) -> dict:
    """Only request-reachable schemas, avoiding hundreds of unrelated definitions."""
    result = {}
    def visit(value):
        if isinstance(value, dict):
            reference = value.get('$ref')
            if reference and reference not in result:
                result[reference] = api['schemas'][reference]
                visit(result[reference])
            for key, child in value.items():
                if key != '$ref':
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(method.get('request', {}))
    return result
