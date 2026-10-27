#!/usr/bin/env python3
"""Prepare a compact handoff, inventory files, or remove reviewed visual caches."""
import argparse
import json
from pathlib import Path

from kitok.config import PROJECT_ROOT
from kitok.youtube_stickman_es.delivery import compact_delivery, clean_visual_cache, inventory
from kitok.youtube_stickman_es.files import episode_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['bundle', 'inventory', 'clean-cache'])
    parser.add_argument('episode', type=Path)
    parser.add_argument('--apply', action='store_true', help='clean-cache only: delete listed regenerable visual files; otherwise dry-run')
    args = parser.parse_args()
    if args.apply and args.command != 'clean-cache':
        parser.error('--apply only applies to clean-cache')
    try:
        episode = episode_path(PROJECT_ROOT, args.episode)
        result = (compact_delivery(PROJECT_ROOT, episode) if args.command == 'bundle' else
                  clean_visual_cache(PROJECT_ROOT, episode, apply=args.apply) if args.command == 'clean-cache' else
                  inventory(episode))
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
