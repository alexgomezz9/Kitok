"""Generation choices loaded from one editable catalog (never credentials)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VoiceProfile:
    display_name: str
    provider: str
    value: str

    @property
    def mpt_voice(self) -> str:
        return self.value if self.provider == "edge" else f"fish_audio:{self.value}:{self.display_name}"


CATALOG_PATH = Path(__file__).resolve().parents[2] / "presets" / "generation_profiles.json"


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict):
        raise ValueError("Generation profile catalog must be an object")
    return catalog


VOICES = {}
VISUAL_PROFILES = {}
CHARACTER_PROFILES = {}
DIALOGUE_PRESETS = {}
CHARACTERS = {}


def reload_catalog(path: Path = CATALOG_PATH):
    catalog = load_catalog(path)
    import re
    for section in ("voices", "visual_profiles", "character_profiles", "dialogue_presets"):
        if not isinstance(catalog.get(section), dict):
            raise ValueError(f"Profile catalog is missing {section}")
        if any(not re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in catalog[section]):
            raise ValueError("Profile IDs must use letters, digits, underscores or hyphens")
    voices = {name: VoiceProfile(**value) for name, value in catalog["voices"].items()}
    if any(v.provider not in {"edge", "fish"} or not v.value for v in voices.values()):
        raise ValueError("Voice provider must be edge or fish, with a reference ID")
    for folder in catalog["visual_profiles"].values():
        if folder is not None and (not isinstance(folder, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", folder)):
            raise ValueError("Background folder must be a simple directory name")
    mappings = {}
    for name, speakers in catalog["character_profiles"].items():
        mappings[name] = {}
        for speaker, placement in speakers.items():
            if speaker not in voices or placement["side"] not in {"left", "right"}:
                raise ValueError("Invalid character speaker or side")
            if not re.fullmatch(r"[A-Za-z0-9_-]+", placement["character"]):
                raise ValueError("Invalid character folder")
            mappings[name][speaker] = (placement["character"], placement["side"])
    for speakers in catalog["dialogue_presets"].values():
        if not speakers or any(s not in voices or voices[s].provider != "fish" for s in speakers):
            raise ValueError("Dialogue presets require known Fish speakers")
    characters = catalog.get("characters", {})
    if not isinstance(characters, dict):
        raise ValueError("Characters must be an object")
    pose_fields = ("active_poses", "reaction_poses", "disabled_poses")
    for character, character_config in characters.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", character) or not isinstance(character_config, dict):
            raise ValueError("Invalid character configuration")
        pose_sets = []
        for field in pose_fields:
            names = character_config.get(field, [])
            if (not isinstance(names, list) or any(not isinstance(name, str) or
                    not re.fullmatch(r"[A-Za-z0-9_-]+", name) for name in names)):
                raise ValueError(f"{field} must contain simple pose names")
            pose_sets.append(set(names))
        if any(left & right for index, left in enumerate(pose_sets)
               for right in pose_sets[index + 1:]):
            raise ValueError("A pose cannot belong to multiple character pose categories")
    for target, source in ((VOICES, voices), (VISUAL_PROFILES, catalog["visual_profiles"]),
                           (CHARACTER_PROFILES, mappings), (DIALOGUE_PRESETS, catalog["dialogue_presets"]),
                           (CHARACTERS, characters)):
        target.clear()
        target.update(source)
    return catalog


reload_catalog()


def voice(name: str) -> VoiceProfile:
    try:
        return VOICES[name]
    except KeyError as error:
        raise ValueError(f"Unknown voice profile: {name}") from error
