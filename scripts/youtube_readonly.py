#!/usr/bin/env python3
"""Local official read-only YouTube CLI. Run with PYTHONPATH=src.

1. Enable YouTube Data API v3, YouTube Analytics API, YouTube Reporting API
   in your own Google Cloud project; configure consent and your test user.
2. Download an OAuth Desktop client JSON (do not paste it into chats).
3. setup --client /private/path/downloaded.json; connect; sync.
Never uploads, deletes, creates Reporting jobs, or requests write scopes.
"""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from kitok.youtube import PrivateStore, YouTubeError, YouTubeReadOnly, connect


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parents[1] / "local/youtube",
                        help="Directorio privado de esta conexión (otro directorio para otro canal)")
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup", help="Guardar cliente Desktop localmente con permisos 0600")
    setup.add_argument("--client", type=Path, required=True)
    sub.add_parser("status", help="Estado local; no prueba acceso remoto")
    sub.add_parser("connect", help="Autorizar ambos permisos de lectura en el navegador local")
    sync = sub.add_parser("sync", help="Consultar catálogo/estadísticas e informes existentes")
    today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    sync.add_argument("--start", default=(today - timedelta(days=30)).isoformat())
    sync.add_argument("--end", default=(today - timedelta(days=1)).isoformat())
    sync.add_argument("--video", help="ID de vídeo del canal para su curva de retención")
    sync.add_argument("--limit", type=int, default=100, help="Máximo de vídeos recientes, hasta 500")
    args = parser.parse_args()
    try:
        store = PrivateStore(args.directory)
        if args.command == "setup":
            with store.lock():
                store.setup(args.client)
            print("Cliente Desktop guardado. Siguiente: connect.")
        elif args.command == "status":
            print(json.dumps(store.status(), ensure_ascii=False, indent=2))
        elif args.command == "connect":
            connect(store)
            print("Autorización local guardada. Ejecuta sync para comprobar la identidad remota.")
        else:
            api = YouTubeReadOnly(store)
            try:
                snapshot = api.sync(start=args.start, end=args.end, video=args.video, limit=args.limit)
            finally:
                api.close()
            print(json.dumps({"channel_id": snapshot["channel_id"], "fetched_at": snapshot["fetched_at"],
                              "videos": len(snapshot["videos"]), "catalog_truncated": snapshot["catalog_truncated"],
                              "daily": snapshot["daily"]["status"], "traffic": snapshot["traffic"]["status"],
                              "retention": snapshot["retention"]["status"], "reporting": snapshot["reporting"]["status"],
                              "snapshot": str(store.path("snapshot.json"))}, ensure_ascii=False, indent=2))
        return 0
    except (YouTubeError, OSError) as error:
        # OSError details can contain private paths. Deliberately avoid tracebacks.
        import sys
        message = str(error) if isinstance(error, YouTubeError) else "No se pudo acceder al almacenamiento privado local."
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
