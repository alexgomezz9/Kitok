#!/usr/bin/env python3
"""Discover Commons images or register existing Pexels stock without downloading it."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from kitok.config import Settings
from kitok.media_library import CommonsLibrary, local_records, register_cached_pexels


def main(argv=None, *, settings=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    search = commands.add_parser('search', help='Read-only search; results are unreviewed candidates')
    search.add_argument('entity')
    search.add_argument('--limit', type=int, default=5)
    fetch = commands.add_parser('fetch', help='Download after reviewing identity and source context')
    fetch.add_argument('title', help='Exact Commons File: title')
    fetch.add_argument('--entity', action='append', required=True)
    fetch.add_argument('--role', action='append', required=True)
    fetch.add_argument('--usage', choices=['context', 'identity', 'document', 'illustration'], default='context')
    pexels = commands.add_parser('register-pexels', help='Register an existing verified Pexels cache entry; offline')
    pexels.add_argument('asset_id', type=int)
    pexels.add_argument('--entity', action='append', required=True)
    pexels.add_argument('--role', action='append', required=True)
    pexels.add_argument('--accept-lower-resolution', action='store_true',
                        help='After reviewing the actual clip, accept smaller dimensions with the same aspect ratio')
    commands.add_parser('list', help='Show the local catalog without contacting providers')
    args = parser.parse_args(argv)
    settings = settings or Settings()
    library = None
    try:
        if args.command == 'register-pexels':
            result = register_cached_pexels(settings, args.asset_id, entities=args.entity, roles=args.role,
                                            accept_lower_resolution=args.accept_lower_resolution)
        elif args.command == 'list':
            result = local_records(settings.data_root or ROOT)
        elif args.command == 'search':
            library = CommonsLibrary(settings)
            result = library.search(args.entity, args.limit)
        elif args.command == 'fetch':
            library = CommonsLibrary(settings)
            result = library.fetch(args.title, entities=args.entity, roles=args.role, usage=args.usage)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, RuntimeError, OSError) as error:
        print(f'Media library operation failed: {error}', file=sys.stderr)
        return 1
    finally:
        if library is not None:
            library.close()


if __name__ == '__main__':
    raise SystemExit(main())
