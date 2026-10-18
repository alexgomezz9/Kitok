"""Desktop OAuth, based on developers.google.com/identity/protocols/oauth2/native-app.

Tokens stay in a private local directory, never in API responses or logging.
No Google account mutations are available; the only POST is token exchange.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import stat
import tempfile
import time
from urllib.parse import parse_qs, urlencode, urlsplit
import webbrowser

import httpx

SCOPES = (
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
)
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


class YouTubeError(RuntimeError):
    """Sanitized operator error: never include HTTP request bodies or tokens."""


class AuthorizationError(YouTubeError):
    """Abort the whole sync: never retry a token POST as another metric query."""


class PrivateStore:
    def __init__(self, directory: Path):
        raw = Path(directory).absolute()
        # Refuse redirected directory components, including local/youtube itself.
        if any(p.is_symlink() for p in (raw, *raw.parents)):
            raise YouTubeError("El directorio privado no puede contener enlaces simbólicos.")
        raw.mkdir(parents=True, exist_ok=True, mode=0o700)
        raw.chmod(0o700)
        self.directory = raw

    def path(self, name: str) -> Path:
        if name not in {"client.json", "tokens.json", "snapshot.json", "connection.lock"}:
            raise YouTubeError("Archivo privado no permitido.")
        path = self.directory / name
        if path.is_symlink():
            raise YouTubeError("Un archivo privado no puede ser un enlace simbólico.")
        return path

    def read(self, name: str) -> dict | None:
        path = self.path(name)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return None
        with os.fdopen(fd) as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise YouTubeError("El archivo privado debe ser regular.")
            os.fchmod(handle.fileno(), 0o600)
            try:
                result = json.load(handle)
            except (ValueError, UnicodeError):
                raise YouTubeError("Archivo privado JSON inválido.") from None
        if not isinstance(result, dict):
            raise YouTubeError("Archivo privado JSON inválido.")
        return result

    def write(self, name: str, value: dict) -> None:
        path = self.path(name)
        fd, temporary = tempfile.mkstemp(prefix=".private-", dir=self.directory)
        try:
            with os.fdopen(fd, "w") as handle:
                os.fchmod(handle.fileno(), 0o600)
                json.dump(value, handle, ensure_ascii=False, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    @contextmanager
    def lock(self):
        path = self.path("connection.lock")
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(fd, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise YouTubeError("Ya hay una operación de YouTube en curso.") from None
            yield
        finally:
            os.close(fd)

    def setup(self, source: Path) -> None:
        try:
            data = json.loads(source.read_text())
        except (OSError, ValueError):
            raise YouTubeError("No se pudo leer el JSON del cliente Desktop.") from None
        installed = data.get("installed") if isinstance(data, dict) else None
        if not isinstance(installed, dict) or not installed.get("client_id"):
            raise YouTubeError("Descarga un cliente OAuth de tipo Desktop, no Web.")
        if self.path("tokens.json").exists():
            raise YouTubeError("Ya existe una conexión. No se sustituye su cliente silenciosamente.")
        # Ignore endpoint URLs supplied in the file: endpoints are pinned above.
        self.write("client.json", {"client_id": str(installed["client_id"]),
                                  "client_secret": str(installed.get("client_secret", ""))})

    def status(self) -> dict:
        tokens = self.read("tokens.json")
        snapshot = self.read("snapshot.json")
        return {
            "client_configured": self.path("client.json").is_file(),
            "authorized_locally": tokens is not None,
            "live_verified": False,
            "scopes": list(SCOPES),
            "last_sync": snapshot.get("fetched_at") if snapshot else None,
            "channel_id": snapshot.get("channel_id") if snapshot else None,
            "note": "Estado local; ejecuta sync para comprobar el acceso actual.",
        }


class AuthorizationAttempt:
    def __init__(self, client_id: str, redirect_uri: str, *, ttl: float = 300):
        parsed = urlsplit(redirect_uri)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
            raise YouTubeError("OAuth requiere un retorno a 127.0.0.1 con puerto local.")
        self.redirect_uri = redirect_uri
        self.state = secrets.token_urlsafe(32)
        self.verifier = secrets.token_urlsafe(64)
        self.expires_at = time.monotonic() + ttl
        self.used = False
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).decode().rstrip("=")
        self.url = AUTH_URL + "?" + urlencode({
            "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": " ".join(SCOPES), "state": self.state, "code_challenge": challenge,
            "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent",
        })

    def consume(self, query: str) -> str:
        if self.used or time.monotonic() >= self.expires_at:
            raise YouTubeError("La autorización ha caducado o ya fue utilizada.")
        params = parse_qs(query, keep_blank_values=True)
        states = params.get("state", [])
        if len(states) != 1 or not secrets.compare_digest(states[0].encode("utf-8", errors="replace"), self.state.encode("ascii")):
            raise YouTubeError("El estado OAuth no coincide.")
        self.used = True
        if "error" in params:
            raise YouTubeError("La autorización no fue concedida.")
        codes = params.get("code", [])
        if len(codes) != 1 or not codes[0]:
            raise YouTubeError("Google no devolvió un código válido.")
        return codes[0]


def token_request(client: httpx.Client, data: dict) -> dict:
    try:
        response = client.post(TOKEN_URL, data=data, timeout=20, follow_redirects=False)
    except httpx.HTTPError:
        raise AuthorizationError("Falló el intercambio OAuth. No se reintenta automáticamente.") from None
    if response.status_code != 200:
        raise AuthorizationError(f"Google rechazó OAuth (HTTP {response.status_code}). Vuelve a conectar.")
    try:
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str) or not payload["access_token"]:
            raise ValueError
        if not isinstance(payload.get("token_type", "Bearer"), str) or payload.get("token_type", "Bearer").lower() != "bearer":
            raise ValueError
        expires = float(payload.get("expires_in", 3600))
        if not 0 < expires <= 86400:
            raise ValueError
    except (ValueError, TypeError):
        raise AuthorizationError("Respuesta OAuth inválida.") from None
    return payload


def validate_scopes(scope: str) -> None:
    if not isinstance(scope, str) or set(scope.split()) != set(SCOPES):
        raise AuthorizationError("Se necesitan exactamente los dos permisos de lectura de Kitok; vuelve a conectar.")


def save_tokens(store: PrivateStore, payload: dict, *, prior: dict | None = None) -> dict:
    scopes = payload.get("scope", prior.get("scope", "") if prior else "")
    validate_scopes(scopes)
    refresh = payload.get("refresh_token") or (prior or {}).get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        raise AuthorizationError("Google no devolvió autorización offline; vuelve a conectar.")
    result = {"access_token": payload["access_token"], "refresh_token": refresh,
              "scope": scopes, "expires_at": time.time() + float(payload.get("expires_in", 3600))}
    if prior and prior.get("channel_id"):
        result["channel_id"] = prior["channel_id"]
    store.write("tokens.json", result)
    return result


def _client_config(store: PrivateStore) -> dict | None:
    config = store.read("client.json")
    if config is not None and (not isinstance(config.get("client_id"), str) or not config["client_id"]
                               or not isinstance(config.get("client_secret", ""), str)):
        raise AuthorizationError("El cliente Desktop local es inválido; configura su JSON de nuevo.")
    return config


def access_token(store: PrivateStore, client: httpx.Client) -> str:
    tokens = store.read("tokens.json")
    config = _client_config(store)
    if not tokens or not config:
        raise AuthorizationError("Falta conectar YouTube: ejecuta setup y connect.")
    validate_scopes(tokens.get("scope", ""))
    try:
        expires_at = float(tokens.get("expires_at", 0))
    except (TypeError, ValueError):
        raise AuthorizationError("Autorización local inválida; vuelve a conectar.") from None
    if not math.isfinite(expires_at) or not isinstance(tokens.get("access_token"), str) or not tokens["access_token"]:
        raise AuthorizationError("Autorización local inválida; vuelve a conectar.")
    if expires_at <= time.time() + 60:
        if not isinstance(tokens.get("refresh_token"), str) or not tokens["refresh_token"]:
            raise AuthorizationError("Falta autorización offline; vuelve a conectar.")
        payload = token_request(client, {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
                                       "client_id": config["client_id"], "client_secret": config.get("client_secret", "")})
        tokens = save_tokens(store, payload, prior=tokens)
    return tokens["access_token"]


def connect(store: PrivateStore, *, client: httpx.Client | None = None, timeout: float = 300,
            open_browser=webbrowser.open) -> None:
    """Explicit interactive connection. The callback never logs query parameters."""
    with store.lock():
        config = _client_config(store)
        if not config:
            raise YouTubeError("Primero configura el JSON del cliente Desktop con setup.")
        outcome: dict = {}
        attempt = None

        class Callback(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                parsed = urlsplit(self.path)
                if parsed.path != "/oauth/callback":
                    self.send_error(404)
                    return
                try:
                    outcome["code"] = attempt.consume(parsed.query)
                    body = b"Autorizacion recibida. Puedes cerrar esta ventana."
                    status = 200
                except YouTubeError as exc:
                    body = str(exc).encode()
                    status = 400
                    # Invalid-state probes must not consume a valid authorization.
                    if attempt.used:
                        outcome["error"] = exc
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

        class LoopbackServer(HTTPServer):
            def get_request(self):
                connection, address = super().get_request()
                # An incomplete local HTTP request must not bypass the OAuth TTL.
                connection.settimeout(1)
                return connection, address

        with LoopbackServer(("127.0.0.1", 0), Callback) as server:
            server.timeout = min(1, timeout)
            attempt = AuthorizationAttempt(config["client_id"],
                f"http://127.0.0.1:{server.server_port}/oauth/callback", ttl=timeout)
            if not open_browser(attempt.url):
                raise YouTubeError("No se pudo abrir el navegador local. Configura el navegador del sistema.")
            while not outcome and time.monotonic() < attempt.expires_at:
                server.handle_request()
        if outcome.get("error"):
            raise outcome["error"]
        if not outcome.get("code"):
            raise YouTubeError("La autorización ha caducado.")
        owns_client = client is None
        client = client or httpx.Client(trust_env=False)
        try:
            payload = token_request(client, {"grant_type": "authorization_code", "client_id": config["client_id"],
                "client_secret": config.get("client_secret", ""), "code": outcome["code"],
                "code_verifier": attempt.verifier, "redirect_uri": attempt.redirect_uri})
            # A new consent replaces this authorization only after a valid response.
            # Keep prior channel binding: switching channel requires separate storage.
            validate_scopes(payload.get("scope", ""))
            if not isinstance(payload.get("refresh_token"), str) or not payload["refresh_token"]:
                raise YouTubeError("Google no devolvió autorización offline; vuelve a conectar.")
            save_tokens(store, payload, prior=store.read("tokens.json"))
        finally:
            if owns_client:
                client.close()
