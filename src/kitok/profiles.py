"""Small, local catalogs for generation choices. No credentials live here."""
from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceProfile:
    display_name: str
    provider: str
    value: str

    @property
    def mpt_voice(self) -> str:
        return self.value if self.provider == "edge" else f"fish_audio:{self.value}:{self.display_name}"


VOICES = {
    "alvaro": VoiceProfile("Álvaro", "edge", "es-ES-AlvaroNeural"),
    "rick_es": VoiceProfile("Rick ES", "fish", "f75ae6efbe9945c19be01e233e045d0e"),
    "morty_es": VoiceProfile("Morty ES", "fish", "5d4a03fbc6d94f9897d5f3969fd9a765"),
}

VISUAL_PROFILES = {"pexels": None, "minecraft": "minecraft", "random": "random",
                   "satisfying": "satisfying", "subway": "subway"}

CHARACTER_PROFILES = {
    "rick_morty_es": {"rick_es": ("rick", "left"), "morty_es": ("morty", "right")},
}

DIALOGUE_PRESETS = {"rick_morty_es": ("rick_es", "morty_es")}


def voice(name: str) -> VoiceProfile:
    try:
        return VOICES[name]
    except KeyError as error:
        raise ValueError(f"Unknown voice profile: {name}") from error
