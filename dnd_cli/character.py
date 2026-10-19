"""Character file logic: schema validation and deterministic HP/spell-slot math.

Combat and magic skills currently tell the AI DM to "subtract damage" or
"decrement remaining" and then hand-edit the character JSON. That is the
same failure mode the canon system exists to prevent for clock and thread
math: an LLM computing arithmetic by hand and writing the result into a
file, instead of a program computing it. This module is the character-file
equivalent of dnd_cli/canon.py — see that file's docstring for the
rationale in full, and game/.claude/skills/combat and game/.claude/skills/
magic for how the AI DM is expected to call it.
"""

import json
from functools import cache
from pathlib import Path
from typing import Optional

from dnd_cli import item as items
from dnd_cli.campaign import REPO_ROOT, CampaignError

SCHEMA_PATH = REPO_ROOT / "game" / "schemas" / "character.schema.json"

__all__ = ["CampaignError", "CharacterError", "REPO_ROOT"]


class CharacterError(CampaignError):
    """Raised for any character file problem: missing file, bad data, bad arguments."""


@cache
def _validator():
    """The schema checked and compiled once: `jsonschema.validate` would check the schema again on every call."""
    import jsonschema  # slow to import: only a command that checks a sheet pays for it

    with open(SCHEMA_PATH) as f:
        schema = json.load(f)
    return jsonschema.validators.validator_for(schema)(schema)


def character_path(campaign_dir: Path, name: str) -> Path:
    return campaign_dir / "characters" / f"{name}.json"


def validate(data: dict) -> None:
    """Raise CharacterError with a clear message if data does not match the schema."""
    from jsonschema import ValidationError

    try:
        _validator().validate(data)
    except ValidationError as e:
        location = "/".join(str(p) for p in e.absolute_path) or "(root)"
        raise CharacterError(
            f"character file failed schema validation at {location}: {e.message}"
        ) from e


def load(campaign_dir: Path, name: str) -> dict:
    path = character_path(campaign_dir, name)
    if not path.exists():
        raise CharacterError(f"No character file at {path}")
    with open(path) as f:
        data = json.load(f)
    validate(data)
    items.link_gear(data)  # a sheet from before the `item` link
    return data


def save(campaign_dir: Path, name: str, data: dict) -> None:
    """Validate before writing. A character file that fails its own schema is never saved."""
    validate(data)
    path = character_path(campaign_dir, name)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def apply_damage(data: dict, amount: int) -> dict:
    """Apply damage per 5e rules: temp HP absorbs first, then current HP.

    current HP is floored at 0 (schema minimum). Returns a small report:
    how much came out of temp HP, how much out of current HP, the new
    values, and whether this brought the character to 0.
    """
    if amount < 0:
        raise CharacterError(f"Damage must be zero or positive, got {amount}.")

    hp = data["hp"]
    temp = hp.get("temp", 0)
    current = hp["current"]
    was_positive = current > 0

    from_temp = min(temp, amount)
    remaining = amount - from_temp
    from_current = min(current, remaining)

    hp["temp"] = temp - from_temp
    hp["current"] = current - from_current

    return {
        "damage_applied": amount,
        "absorbed_by_temp_hp": from_temp,
        "absorbed_by_current_hp": from_current,
        "unabsorbed": remaining - from_current,
        "hp_current": hp["current"],
        "hp_temp": hp["temp"],
        "hp_max": hp["max"],
        "dropped_to_zero": was_positive and hp["current"] == 0,
    }


def heal(data: dict, amount: int) -> dict:
    """Heal per 5e rules: current HP cannot exceed max. Healing does not restore temp HP."""
    if amount < 0:
        raise CharacterError(f"Healing must be zero or positive, got {amount}.")

    hp = data["hp"]
    hp["current"] = min(hp["max"], hp["current"] + amount)

    return {
        "healing_applied": amount,
        "hp_current": hp["current"],
        "hp_max": hp["max"],
    }


def add_temp_hp(data: dict, amount: int) -> dict:
    """Set temp HP per 5e rules: temp HP does not stack, the higher value wins."""
    if amount < 0:
        raise CharacterError(f"Temp HP must be zero or positive, got {amount}.")

    hp = data["hp"]
    hp["temp"] = max(hp.get("temp", 0), amount)
    return {"hp_temp": hp["temp"]}


def _spell_slots(data: dict) -> dict:
    slots = data.get("spellcasting", {}).get("spell_slots")
    if not slots:
        raise CharacterError("This character has no spellcasting.spell_slots to track.")
    return slots


def cast_spell(data: dict, level: int) -> dict:
    """Decrement remaining slots at the given level. Refuses if none remain."""
    slots = _spell_slots(data)
    key = str(level)
    if key not in slots:
        raise CharacterError(f"No spell slots recorded at level {level}.")

    slot = slots[key]
    remaining = slot.get("remaining", 0)
    if remaining <= 0:
        raise CharacterError(f"No level {level} spell slots remaining.")

    slot["remaining"] = remaining - 1
    return {"level": level, "remaining": slot["remaining"], "max": slot.get("max")}


def restore_slots(data: dict, level: Optional[int] = None) -> dict:
    """Long rest: restore one level's slots to max, or all levels if level is None."""
    slots = _spell_slots(data)

    if level is not None:
        key = str(level)
        if key not in slots:
            raise CharacterError(f"No spell slots recorded at level {level}.")
        slots[key]["remaining"] = slots[key].get("max", slots[key]["remaining"])
        return {"restored": [level]}

    restored = []
    for key, slot in slots.items():
        slot["remaining"] = slot.get("max", slot.get("remaining", 0))
        restored.append(int(key))
    return {"restored": sorted(restored)}
