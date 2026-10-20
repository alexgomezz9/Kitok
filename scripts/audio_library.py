#!/usr/bin/env python3
"""Licensed local music: list → fetch → select → mix. No speech APIs or uploads."""
import argparse
import json
from pathlib import Path
import sys

from kitok.audio_library import AudioLibrary, AudioLibraryError, SFX_KINDS, synthesize_sfx


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=root / "presets/music_sources.json")
    parser.add_argument("--cache", type=Path, default=root / "cache/audio-library")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List audited tracks and their channel/mood fit")
    sub.add_parser("available", help="List hash-verified local choices without network or selection writes")
    fetch = sub.add_parser("fetch", help="Download free CC BY 4.0 tracks with provenance and fixed hashes")
    fetch.add_argument("tracks", nargs="+", help="Track IDs or all")
    select = sub.add_parser("select", help="Persist a reproducible per-job choice; avoid previous primary track")
    select.add_argument("--job", required=True)
    select.add_argument("--channel", default="loose_thread")
    select.add_argument("--mood", default="investigation")
    select.add_argument("--count", type=int, choices=(1, 2), default=2)
    select.add_argument("--track", help="Choose one cached track manually instead of mood rotation")
    select.add_argument("--script", type=Path, help="Choose distinct opening/closing tracks from a full existing narration text")
    mix = sub.add_parser("mix", help="Create a separate ducked, crossfaded, measured audio mix")
    mix.add_argument("--job", required=True)
    mix.add_argument("--narration", type=Path, required=True)
    mix.add_argument("--output", type=Path, required=True)
    mix.add_argument("--duration", type=float, required=True)
    mix.add_argument("--offset", type=float, default=0)
    mix.add_argument("--transition-at", type=float, help="Center the two-track crossfade on this narrative boundary (seconds)")
    mix.add_argument("--sfx-events", type=Path, help="JSON list of editorial cues: [{\"time\":2,\"kind\":\"soft_tick\"}]")
    sfx = sub.add_parser("sfx", help="Synthesize a quiet original Kitok sound, no external samples")
    sfx.add_argument("--output", type=Path, required=True)
    sfx.add_argument("--kind", choices=SFX_KINDS, default="soft_tick")
    args = parser.parse_args()
    library = None
    try:
        if args.command == "sfx":
            result = synthesize_sfx(args.output, kind=args.kind)
        else:
            library = AudioLibrary(args.catalog, args.cache)
            if args.command == "list":
                result = [{"id": source.id, "title": source.title, "channels": source.channels,
                           "moods": library.describe(source)["moods"], "license": source.license_id, "attribution": source.attribution,
                           "editorial_affinities": library.describe(source)["editorial_affinities"],
                           "content_id": source.content_id} for source in library.sources.values()]
            elif args.command == "available":
                result = library.available()
            elif args.command == "fetch":
                ids = list(library.sources) if args.tracks == ["all"] else args.tracks
                result = [{"track": track, "sha256": receipt["sha256"], "cache_hit": receipt["cache_hit"],
                           "duration": receipt["duration"]} for track in ids for receipt in [library.fetch(track)]]
            elif args.command == "select":
                if args.track and args.script:
                    raise AudioLibraryError("Choose either a manual track or narrative script")
                result = (library.select_manual(args.job, args.track, channel=args.channel) if args.track else
                          library.select_narrative(args.job, args.script.read_text(), channel=args.channel) if args.script else
                          library.select(args.job, channel=args.channel, mood=args.mood, count=args.count))
            else:
                events = json.loads(args.sfx_events.read_text()) if args.sfx_events else None
                receipt = library.mix(args.job, args.narration, args.output, duration=args.duration,
                                      offset=args.offset, sfx_events=events, transition_at=args.transition_at)
                result = {"output": str(args.output), "duration": receipt["duration"], "measured": receipt["measured"],
                          "credits": receipt["selection"]["credits"], "changes_notice": receipt["selection"]["changes_notice"]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (AudioLibraryError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        if library:
            library.close()


if __name__ == "__main__":
    raise SystemExit(main())
