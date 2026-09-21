"""Allowlisted local preferences. Secrets always remain environment settings."""
import json
from .config import Settings
from .state import write_json_atomic

EDITABLE = {
    'default_visual_profile', 'character_active_height', 'character_bottom_margin',
    'character_max_width', 'character_scale_variation', 'character_position_variation',
    'character_entry_seconds', 'character_exit_seconds', 'character_reaction_probability',
    'character_entry_horizontal_pixels', 'character_left_anchor', 'character_right_anchor',
    'character_reaction_min_seconds', 'character_reaction_max_seconds',
    'dialogue_subtitle_max_chars', 'dialogue_gap_ms', 'default_posting_slots', 'timezone',
}


def preferences(settings):
    return {key: getattr(settings, key) for key in sorted(EDITABLE)}


def configured(settings=None):
    base = settings or Settings()
    path = base.state_path.parent / 'app_config.json'
    if path.exists():
        values = json.loads(path.read_text())
        if not isinstance(values, dict) or set(values) - EDITABLE:
            raise ValueError('Invalid app_config.json: only editable preferences are allowed')
        base = Settings(_env_file=None, **{**base.model_dump(), **values})
    if base.character_reaction_min_seconds > base.character_reaction_max_seconds:
        raise ValueError('Reaction minimum must not exceed its maximum')
    for slot in base.default_posting_slots:
        from datetime import time
        time.fromisoformat(slot)
    return base


def save_preferences(settings, changes):
    if set(changes) - EDITABLE:
        raise ValueError('This setting is not editable; keep API keys in .env')
    from .profiles import VISUAL_PROFILES
    merged = {**preferences(settings), **changes}
    candidate = Settings(_env_file=None, **{**settings.model_dump(), **merged})
    if candidate.default_visual_profile not in VISUAL_PROFILES:
        raise ValueError('Unknown default visual profile')
    if candidate.character_reaction_min_seconds > candidate.character_reaction_max_seconds:
        raise ValueError('Reaction minimum must not exceed its maximum')
    from datetime import time
    for slot in candidate.default_posting_slots:
        time.fromisoformat(slot)
    path = settings.state_path.parent / 'app_config.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, merged)
    return candidate
