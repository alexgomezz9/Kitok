from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import PROJECT_ROOT, Settings
from .fish_voice import FishVoiceClient, FishVoiceError


PLAIN_TEXT = """A seventeen-year-old is sitting in a hotel room in Britain.
Police have already taken his laptop.

But there is still a television in the room.
Connected to it is an Amazon Fire TV Stick.

Within days, ninety clips from one of the most secretive video games in the world will appear online.

The strange part is not that a teenager managed to hack Rockstar Games.

The strange part is what this tiny device reveals about the way modern companies are actually breached."""

TAGGED_TEXT = """[professional broadcast tone]
A seventeen-year-old is sitting in a hotel room in Britain.

[soft]
Police have already taken his laptop.

[pause]

[quietly]
But there is still a television in the room.

Connected to it is an Amazon Fire TV Stick.

[serious]
Within days, ninety clips from one of the most secretive video games in the world will appear online.

[reflective]
The strange part is not that a teenager managed to hack Rockstar Games.

The strange part is what this tiny device reveals about the way modern companies are actually breached."""

SPEED = 0.95
TEMPERATURE = 0.8
TOP_P = 0.7


@dataclass(frozen=True)
class VoiceChoice:
    slug: str
    name: str
    reference_id: str


DEFAULT_VOICES = (
    VoiceChoice("baseline", "Loose Thread Narrator", "e686ae649ee44f219a108aacba206c1a"),
    VoiceChoice("adrian", "Adrian - Fish Official", "bf322df2096a46f18c579d0baa36f41d"),
    VoiceChoice("ethan", "Ethan - Fish Official", "536d3a5e000945adb7038665781a4aca"),
    VoiceChoice("narrator", "Narrator", "0327fdb5da9e4fd782899a8058c8ae2b"),
)


def parse_voice(value: str) -> VoiceChoice:
    name, separator, reference_id = value.partition("=")
    name = name.strip()
    reference_id = reference_id.strip()
    if not separator or not name or not reference_id:
        raise argparse.ArgumentTypeError("use NAME=REFERENCE_ID")
    slug = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    if not slug:
        raise argparse.ArgumentTypeError("voice name must contain letters or numbers")
    return VoiceChoice(slug, name, reference_id)


def generate_voice_tests(
    voices: tuple[VoiceChoice, ...],
    output_dir: Path,
    *,
    include_tags: bool = True,
    settings: Settings | None = None,
    client_factory=FishVoiceClient,
) -> tuple[list[Path], list[str]]:
    settings = settings or Settings()
    api_key = settings.fish_api_key.get_secret_value()
    if not api_key:
        raise FishVoiceError("FISH_API_KEY is required for voice tests")

    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    failures: list[str] = []
    variants = [("plain", PLAIN_TEXT)]
    if include_tags:
        variants.append(("tags", TAGGED_TEXT))

    client = client_factory(
        api_key,
        settings.fish_model,
        timeout=settings.fish_tts_timeout_seconds,
    )
    try:
        for index, voice in enumerate(voices, start=1):
            print(f"Generating {index}/{len(voices)}: {voice.name}...")
            for variant, text in variants:
                destination = output_dir / f"{voice.slug}_{variant}.mp3"
                try:
                    client.synthesize(
                        text,
                        voice.reference_id,
                        destination,
                        speed=SPEED,
                        temperature=TEMPERATURE,
                        top_p=TOP_P,
                        normalize_loudness=True,
                    )
                    generated.append(destination)
                    print(f"  {variant}: {destination.resolve()}")
                except FishVoiceError as exc:
                    message = (
                        f"{voice.name} ({voice.reference_id}) [{variant}]: {exc}"
                    )
                    failures.append(message)
                    print(f"  ERROR: {message}", file=sys.stderr)
    finally:
        client.close()
    return generated, failures


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare Fish voices with identical Loose Thread test text and settings."
    )
    parser.add_argument(
        "--voice",
        action="append",
        type=parse_voice,
        help="Test only a custom voice, as NAME=REFERENCE_ID. Repeat to compare several.",
    )
    parser.add_argument(
        "--plain-only",
        action="store_true",
        help="Generate only clean text, without the supported Fish direction-tag variant.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "voice-tests",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    voices = tuple(args.voice) if args.voice else DEFAULT_VOICES
    try:
        generated, failures = generate_voice_tests(
            voices,
            args.output_dir,
            include_tags=not args.plain_only,
        )
    except FishVoiceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("\nGenerated files:")
    for path in generated:
        print(path.resolve())
    if failures:
        print(f"\nCompleted with {len(failures)} failed generation(s).", file=sys.stderr)
        return 1
    return 0
