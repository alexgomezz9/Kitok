#!/usr/bin/env python3
"""Discover Commons candidates or import one explicitly reviewed, licensed image."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from kitok.config import Settings
from kitok.media_library import CommonsLibrary


def main(argv=None):
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
    commands.add_parser('list', help='Show the local catalog without contacting providers')
    args = parser.parse_args(argv)
    library = CommonsLibrary(Settings())
    try:
        if args.command == 'search':
            result = library.search(args.entity, args.limit)
        elif args.command == 'fetch':
            result = library.fetch(args.title, entities=args.entity, roles=args.role, usage=args.usage)
        else:
            result = library.records()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        library.close()


if __name__ == '__main__':
    main()
