#!/usr/bin/env python3
"""Licensed local music: list → fetch → select → mix. No speech APIs or uploads."""
import argparse
import json
from pathlib import Path
import sys

from kitok.audio_library import AudioLibrary, AudioLibraryError, synthesize_sfx


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=root / "presets/music_sources.json")
    parser.add_argument("--cache", type=Path, default=root / "cache/audio-library")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List four audited tracks and their channel/mood fit")
    fetch = sub.add_parser("fetch", help="Download free CC BY 4.0 tracks with provenance and fixed hashes")
    fetch.add_argument("tracks", nargs="+", help="Track IDs or all")
    select = sub.add_parser("select", help="Persist a reproducible per-job choice; avoid previous primary track")
    select.add_argument("--job", required=True)
    select.add_argument("--channel", default="loose_thread")
    select.add_argument("--mood", default="investigation")
    select.add_argument("--count", type=int, choices=(1, 2), default=2)
    mix = sub.add_parser("mix", help="Create a separate ducked, crossfaded, measured audio mix")
    mix.add_argument("--job", required=True)
    mix.add_argument("--narration", type=Path, required=True)
    mix.add_argument("--output", type=Path, required=True)
    mix.add_argument("--duration", type=float, required=True)
    mix.add_argument("--offset", type=float, default=0)
    sfx = sub.add_parser("sfx", help="Synthesize a quiet original Kitok sound, no external samples")
    sfx.add_argument("--output", type=Path, required=True)
    sfx.add_argument("--kind", choices=("soft_tick", "low_pulse"), default="soft_tick")
    args = parser.parse_args()
    library = None
    try:
        if args.command == "sfx":
            result = synthesize_sfx(args.output, kind=args.kind)
        else:
            library = AudioLibrary(args.catalog, args.cache)
            if args.command == "list":
                result = [{"id": source.id, "title": source.title, "channels": source.channels,
                           "moods": source.moods, "license": source.license_id, "attribution": source.attribution,
                           "content_id": source.content_id} for source in library.sources.values()]
            elif args.command == "fetch":
                ids = list(library.sources) if args.tracks == ["all"] else args.tracks
                result = [{"track": track, "sha256": receipt["sha256"], "cache_hit": receipt["cache_hit"],
                           "duration": receipt["duration"]} for track in ids for receipt in [library.fetch(track)]]
            elif args.command == "select":
                result = library.select(args.job, channel=args.channel, mood=args.mood, count=args.count)
            else:
                receipt = library.mix(args.job, args.narration, args.output, duration=args.duration, offset=args.offset)
                result = {"output": str(args.output), "duration": receipt["duration"], "measured": receipt["measured"],
                          "credits": receipt["selection"]["credits"], "changes_notice": receipt["selection"]["changes_notice"]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (AudioLibraryError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if library:
            library.close()


if __name__ == "__main__":
    raise SystemExit(main())
