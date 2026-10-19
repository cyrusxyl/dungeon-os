"""Divine Smite: who can smite, and the extra damage."""

from __future__ import annotations

import random
from pathlib import Path

from dnd_cli import character, dice
from dnd_cli.errors import RulesError
from dnd_cli.combat.records import combatant
from dnd_cli.combat.rolls import stage_roll
from dnd_cli.combat.tracker import encounter, in_combat
from dnd_cli.combat.wounds import damage


def smite_dice(level: int, ctype: str = "") -> str:
    """2d8 for a level 1 slot, +1d8 per level above 1, at most 5d8; +1d8 against an undead or a fiend."""
    n = min(5, level + 1) + (1 if any(t in ctype.lower() for t in ("undead", "fiend")) else 0)
    return f"{n}d8"


def has_feature(sheet: dict, name: str) -> bool:
    return any(f.get("name", "").lower().split(":")[0] == name.lower() for f in sheet.get("features_and_traits", []))


def smite_levels(sheet: dict) -> dict[int, int]:
    """{slot level: slots left} for a character who has Divine Smite; empty without the feature or without slots."""
    if not has_feature(sheet, "Divine Smite"):
        return {}
    slots = (sheet.get("spellcasting") or {}).get("spell_slots") or {}
    return {int(k): v["remaining"] for k, v in slots.items() if v.get("remaining", 0) > 0}


def can_smite(campaign_dir: Path, cid: str) -> bool:
    return character.character_path(campaign_dir, cid).exists() and bool(smite_levels(character.load(campaign_dir, cid)))


def smite_check(campaign_dir: Path, cid: str, level: int) -> dict:
    """The sheet of `cid` if it can smite with a slot of `level`, else a RulesError (nothing is changed)."""
    if not character.character_path(campaign_dir, cid).exists():
        raise RulesError(f"{cid} is not a player character: no Divine Smite.")
    sheet = character.load(campaign_dir, cid)
    if not has_feature(sheet, "Divine Smite"):
        raise RulesError(f"{cid} does not have Divine Smite.")
    if smite_levels(sheet).get(level, 0) <= 0:
        raise RulesError(f"{cid} has no level {level} spell slot left for Divine Smite.")
    return sheet


def smite_hit(campaign_dir: Path, state: dict, attacker: str, target: str, level: int, crit: bool = False,
              rng=None, secret: bool = False) -> list[str]:
    """Spend a slot of `level` and deal the smite damage (radiant, doubled on a crit) to `target`."""
    rng = rng or random
    sheet = smite_check(campaign_dir, attacker, level)
    ctype = str(combatant(campaign_dir, state, target).get("ctype", ""))
    expr = smite_dice(level, ctype)
    left = character.cast_spell(sheet, level)["remaining"]
    character.save(campaign_dir, attacker, sheet)
    amount, groups = dice.roll(expr, rng, crit=crit)
    stage_roll(f"{sheet.get('name', attacker)}: Divine Smite {expr}{' x2' if crit else ''} — {amount} radiant damage", amount, groups, secret)
    line = damage(campaign_dir, state, target, amount, "radiant", crit=crit)
    if in_combat(state, attacker):
        encounter(state).pop("pending_smite", None)
    return [f"{attacker} Divine Smite → {target}: level {level} slot ({left} left), {expr}{' doubled' if crit else ''} = {amount} radiant", line]
