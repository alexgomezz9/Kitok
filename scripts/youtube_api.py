#!/usr/bin/env python3
"""YouTube oficial para agentes: catálogo, OAuth, lecturas y cambios con plan exacto.

Ejecutar desde Kitok con PYTHONPATH=src .venv/bin/python scripts/youtube_api.py.
Consulta docs/integrations/youtube-readonly.md antes de modificar o publicar.
"""
import argparse
import json
from pathlib import Path
import sys

from kitok.youtube import PrivateStore, YouTubeError, connect
from kitok.youtube.management import CATALOG, UNSUPPORTED, YouTubeManagement, operation, public_receipt, request_schemas
from kitok.youtube.oauth import PROFILES
from kitok.youtube.research import public_search, reporting_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path('local/youtube-trazo-maldito'))
    parser.add_argument('--channel', help='ID exacto esperado; obligatorio para consultas y cambios remotos')
    sub = parser.add_subparsers(dest='command', required=True)
    cat = sub.add_parser('catalog', help='Operaciones oficiales o esquema completo de una operación')
    cat.add_argument('operation', nargs='?')
    sub.add_parser('status')
    sub.add_parser('reporting-status', help='Comprobar si hay CSV de los trabajos existentes')
    search = sub.add_parser('public-search', help='Buscar y filtrar datos públicos oficiales')
    search.add_argument('query')
    search.add_argument('--limit', type=int, default=20)
    search.add_argument('--order', choices=('relevance', 'date', 'viewCount'), default='relevance')
    search.add_argument('--published-after', help='Fecha RFC 3339, por ejemplo 2026-01-01T00:00:00Z')
    search.add_argument('--min-views', type=int)
    search.add_argument('--max-subscribers', type=int)
    auth = sub.add_parser('connect')
    auth.add_argument('--profile', choices=PROFILES, default='read')
    for name in ('query', 'plan'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--request', type=Path, required=True, help='JSON operation/params/body/media')
    apply = sub.add_parser('apply', help='Enviar UNA VEZ el plan aprobado')
    apply.add_argument('--approve', required=True, help='SHA256 del plan revisado')
    sub.add_parser('receipt', help='Recibo privado sin credenciales de subida')
    resolve = sub.add_parser('resolve', help='Cerrar recibo incierto tras verificar resultado remoto')
    resolve.add_argument('--approve', required=True)
    resolve.add_argument('--outcome', choices=['succeeded', 'not_applied'], required=True)
    resolve.add_argument('--evidence', required=True)
    sub.add_parser('reconcile', help='Consultar resultado sin repetir la mutación')
    report = sub.add_parser('download-report')
    report.add_argument('--job', required=True)
    report.add_argument('--report', required=True)
    report.add_argument('--output', type=Path, required=True)
    caption = sub.add_parser('download-caption')
    caption.add_argument('--caption', required=True)
    caption.add_argument('--format', default='srt')
    caption.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    api = None
    try:
        if args.command == 'catalog':
            if args.operation:
                source, method = operation(args.operation)
                result = {'operation': args.operation, **method, 'unsupported': UNSUPPORTED.get(args.operation),
                          'schemas': request_schemas(source, method), 'source': source['source']}
            else:
                result = {name: {'source': data['source'], 'revision': data['revision'],
                    'operations': {key: {'method': m['httpMethod'], 'unsupported': UNSUPPORTED.get(key), 'media': m.get('supportsMediaUpload', False)}
                                   for key, m in data['methods'].items()}} for name, data in CATALOG['apis'].items()}
        else:
            store = PrivateStore(args.directory)
            if args.command == 'status':
                result = store.status()
            elif args.command == 'receipt':
                result = public_receipt(store.read('receipt.json') or {})
            elif args.command == 'connect':
                connect(store, profile=args.profile, expected_channel=args.channel)
                result = {'authorized_locally': True, 'next': 'query con channels.list y --channel para verificar acceso remoto'}
            else:
                if not args.channel:
                    raise YouTubeError('Indica --channel con el ID exacto esperado.')
                api = YouTubeManagement(store)
                if args.command in {'query', 'plan'}:
                    request = json.loads(args.request.read_text())
                    result = getattr(api, args.command)(request, args.channel)
                elif args.command == 'reporting-status':
                    result = reporting_status(api, args.channel)
                elif args.command == 'public-search':
                    result = public_search(api, args.channel, args.query, limit=args.limit, order=args.order,
                                           published_after=args.published_after, min_views=args.min_views,
                                           max_subscribers=args.max_subscribers)
                elif args.command == 'apply':
                    result = public_receipt(api.apply(args.approve, args.channel))
                elif args.command == 'resolve':
                    result = public_receipt(api.resolve(args.approve, args.channel, args.outcome, args.evidence))
                elif args.command == 'reconcile':
                    result = public_receipt(api.reconcile(args.channel))
                elif args.command == 'download-report':
                    api.download_report(args.job, args.report, args.channel, args.output)
                    result = {'downloaded': str(args.output)}
                else:
                    api.download_caption(args.caption, args.channel, args.output, args.format)
                    result = {'downloaded': str(args.output)}
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (YouTubeError, OSError, ValueError, TypeError, KeyError):
        error = sys.exc_info()[1]
        print(str(error) if isinstance(error, YouTubeError) else 'Error local de petición o almacenamiento; sin detalles sensibles.', file=sys.stderr)
        return 1
    finally:
        if api:
            api.close()


if __name__ == '__main__':
    raise SystemExit(main())
