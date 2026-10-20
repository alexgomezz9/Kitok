#!/usr/bin/env python3
"""Local Fish voice metadata, existing previews, favorites and channel assignments.

This command never generates speech. Only discover/inspect contact Fish with
one official metadata GET; list, preferences and preview access remain local.
"""
import argparse
import json
from pathlib import Path
import sys

from kitok.voice_library import VoiceLibrary, VoiceLibraryError, discover_fish_voices


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=root / "presets/voice_sources.json")
    parser.add_argument("--preferences", type=Path, default=root / "state/voice-preferences.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    favorite = sub.add_parser("favorite")
    favorite.add_argument("voice")
    favorite.add_argument("--remove", action="store_true")
    assign = sub.add_parser("assign")
    assign.add_argument("channel")
    assign.add_argument("voice")
    sample = sub.add_parser("sample", help="Print the verified local preview path")
    sample.add_argument("voice")
    sample.add_argument("--index", type=int, default=0)
    discover = sub.add_parser("discover", help="One read-only GET of Fish-licensed voices; no synthesis")
    discover.add_argument("--language", default="en")
    discover.add_argument("--limit", type=int, default=10)
    inspect = sub.add_parser("inspect", help="Refresh metadata for a catalogued voice without modifying it")
    inspect.add_argument("voice")
    args = parser.parse_args()
    try:
        library = VoiceLibrary(args.catalog, args.preferences)
        if args.command in {"discover", "inspect"}:
            from kitok.config import Settings
            if args.command == "inspect" and args.voice not in library.voices:
                raise VoiceLibraryError("Unknown voice ID")
            options = ({"reference_id": library.voices[args.voice]["reference_id"]} if args.command == "inspect" else
                       {"language": args.language, "limit": args.limit})
            result = discover_fish_voices(Settings().fish_api_key.get_secret_value(), **options)
        elif args.command == "favorite":
            library.favorite(args.voice, not args.remove)
            result = library.list()
        elif args.command == "assign":
            library.assign(args.channel, args.voice)
            result = library.assigned(args.channel)
        elif args.command == "sample":
            result = {"path": str(library.sample(args.voice, args.index, root=root))}
        else:
            result = library.list()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (VoiceLibraryError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
