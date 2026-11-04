#!/usr/bin/env python3
"""Prepare a compact handoff, inventory files, or remove reviewed visual caches."""
import argparse
import json
from pathlib import Path

from kitok.config import PROJECT_ROOT
from kitok.youtube_stickman_es.delivery import compact_delivery, clean_visual_cache, inventory, normalize_delivery
from kitok.youtube_stickman_es.files import episode_path, local_file
from kitok.youtube_stickman_es.workspace import organize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['bundle', 'inventory', 'clean-cache', 'organize', 'normalize'])
    parser.add_argument('episode', type=Path)
    parser.add_argument('--apply', action='store_true', help='Apply reviewed housekeeping; otherwise dry-run')
    parser.add_argument('--archive-revisions', action='store_true', help='organize: archive closed historical revisions outside the episode')
    parser.add_argument('--report', type=Path, help='Save the full report; print only counts')
    parser.add_argument('--destination-episode', type=Path, help='normalize: deliver an active revision into its parent episode')
    args = parser.parse_args()
    if args.apply and args.command not in {'clean-cache', 'organize', 'normalize'}:
        parser.error('--apply only applies to clean-cache/organize/normalize')
    if args.destination_episode and args.command != 'normalize':
        parser.error('--destination-episode only applies to normalize')
    if args.archive_revisions and args.command != 'organize':
        parser.error('--archive-revisions only applies to organize')
    try:
        report_path = None
        if args.report:
            relative = args.report.relative_to(PROJECT_ROOT) if args.report.is_absolute() else args.report
            report_path = local_file(PROJECT_ROOT, str(relative), exists=False)
            if not report_path.is_relative_to(PROJECT_ROOT / 'local/cleanup'):
                raise ValueError('--report must be inside local/cleanup; preserve production inputs')
        episode = episode_path(PROJECT_ROOT, args.episode)
        result = (normalize_delivery(PROJECT_ROOT, episode, apply=args.apply, destination_episode=args.destination_episode)
                  if args.command == 'normalize' else
                  organize(PROJECT_ROOT, episode, apply=args.apply, archive_revisions=args.archive_revisions)
                  if args.command == 'organize' else
                  compact_delivery(PROJECT_ROOT, episode) if args.command == 'bundle' else
                  clean_visual_cache(PROJECT_ROOT, episode, apply=args.apply) if args.command == 'clean-cache' else
                  inventory(episode))
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + '\n')
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'report': str(report_path.relative_to(PROJECT_ROOT)), 'mode': result.get('mode'),
                          'removed': len(result.get('removed', [])),
                          'duplicate_videos': len(result.get('duplicate_videos', [])),
                          'distinct_videos_preserved': len(result.get('distinct_videos_preserved', [])),
                          'archives': result.get('archives', [])}, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
