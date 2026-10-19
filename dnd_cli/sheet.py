"""Character-sheet changes the DM used to make by hand: items, gold, gear, rests, XP, level-up.

All functions change a loaded sheet dict and return short lines for the DM;
the caller saves through dnd_cli.character (which validates the schema).

Sheets store totals (a skill bonus, a weapon's attack bonus), not whether a
character is proficient. Level-up and gear infer proficiency from the totals:
`(total - ability modifier) / proficiency bonus` is 0, 1, or 2 (expertise).
"""

from __future__ import annotations

import random

from dnd_cli import dice, item as items, resources
from dnd_cli.combat.records import ABILITIES, SKILLS, ability, level_for_xp
from dnd_cli.errors import RulesError
from dnd_cli.dice import prof_for_level



def prof_from(level_data: dict, level: int) -> int:
    """The proficiency bonus at `level`: the API's, else the table."""
    return level_data.get("prof_bonus", prof_for_level(level))


def spell_numbers(sheet: dict, spell: dict, prof: int) -> tuple[int, int]:
    """(spell save DC, spell attack bonus) of this spellcasting block."""
    m = dice.mods(sheet["ability_scores"]).get(spell.get("ability"), 0)
    return 8 + prof + m, prof + m


def sync_slots(spell: dict, want: dict[str, int], prune: bool = True) -> list[tuple[str, int, int]]:
    """Set each slot maximum to `want`, keeping the used slots as they were. `prune` also drops a level that `want` lacks.

    Returns (level, old max, new max) for each change.
    """
    slots = spell.setdefault("spell_slots", {})
    changes = []
    for k in sorted(set(want) | (set(slots) if prune else set())):
        old = slots.get(k, {"max": 0, "remaining": 0})
        new = want.get(k, 0)
        if old.get("max", 0) == new:
            continue
        changes.append((k, old.get("max", 0), new))
        if new:
            slots[k] = {"max": new, "remaining": max(0, min(new, old.get("remaining", 0) + new - old.get("max", 0)))}
        else:
            del slots[k]
    return changes


def base_ac(class_name: str, m: dict) -> int:
    """Unarmored AC: 10 + DEX, plus CON for a Barbarian or WIS for a Monk."""
    extra = {"barbarian": m["constitution"], "monk": m["wisdom"]}.get(class_name.lower(), 0)
    return 10 + m["dexterity"] + extra


# -- items and gold ----------------------------------------------------------


def gold(sheet: dict, delta: int) -> str:
    purse = items.find(sheet, items.GOLD)
    have = purse.quantity if purse else 0
    if have + delta < 0:
        raise RulesError(f"{sheet['name']} has only {have} gp; {-delta} gp is too much.")
    if delta > 0:
        items.add(sheet, items.GOLD, delta)
    elif delta < 0:
        items.remove(sheet, items.GOLD, -delta)
    return f"{sheet['name']}: {have + delta} gp"


# -- gear --------------------------------------------------------------------


# -- rests -------------------------------------------------------------------


def _hit_die(sheet: dict, fallback: int = 8) -> int:
    t = str(sheet.get("hit_dice", {}).get("type", f"d{fallback}"))
    return int(t.lstrip("d")) if t.lstrip("d").isdigit() else fallback


def long_rest(sheet: dict) -> str:
    hp = sheet["hp"]
    hp["current"], hp["temp"] = hp["max"], 0
    hd = sheet.setdefault("hit_dice", {"total": sheet["level"], "remaining": sheet["level"]})
    total = hd.get("total", sheet["level"])
    hd["remaining"] = min(total, hd.get("remaining", 0) + max(1, total // 2))
    sheet["death_saves"] = {"successes": 0, "failures": 0}
    slots = (sheet.get("spellcasting") or {}).get("spell_slots") or {}
    for s in slots.values():
        s["remaining"] = s.get("max", s.get("remaining", 0))
    resources.rest(sheet, "long")
    return (f"{sheet['name']}: HP {hp['max']}/{hp['max']}, hit dice {hd['remaining']}/{total}"
            + (", spell slots full" if slots else ""))


def short_rest(sheet: dict, spend: int, rng=None) -> str:
    rng = rng or random
    hd = sheet.setdefault("hit_dice", {"total": sheet["level"], "remaining": sheet["level"]})
    spend = min(spend, hd.get("remaining", 0))
    die, con = _hit_die(sheet), dice.mods(sheet["ability_scores"])["constitution"]
    healed = sum(max(0, rng.randint(1, die) + con) for _ in range(spend))
    hp = sheet["hp"]
    hp["current"] = min(hp["max"], hp["current"] + healed)
    hd["remaining"] = hd.get("remaining", 0) - spend
    if healed:
        sheet["death_saves"] = {"successes": 0, "failures": 0}
    resources.rest(sheet, "short")
    return (f"{sheet['name']}: spends {spend} hit dice (d{die}{dice.signed(con)} each), heals {healed}: "
            f"HP {hp['current']}/{hp['max']}, hit dice {hd['remaining']}/{hd.get('total', sheet['level'])}")


# -- XP and level-up ---------------------------------------------------------


def hp_bonus_per_level(sheet: dict) -> int:
    """Extra HP each level from a trait (Hill Dwarf: Dwarven Toughness)."""
    return 1 if any(f.get("name") == "Dwarven Toughness" for f in sheet.get("features_and_traits", [])) else 0


def add_xp(sheet: dict, xp: int) -> str:
    sheet["experience_points"] = sheet.get("experience_points", 0) + xp
    line = f"{sheet['name']}: {sheet['experience_points']} XP"
    if level_for_xp(sheet["experience_points"]) > sheet["level"]:
        line += " — LEVEL UP READY"
    return line


def retotal(sheet: dict, old_prof: int, prof: int) -> None:
    """Set skill and save totals for a new proficiency bonus.

    The old total shows the bonus the character had: none, half (rounded down),
    full, or double. Keep that kind and apply it to the new bonus.
    """
    m = dice.mods(sheet["ability_scores"])

    def new(total: int, mod: int) -> int:
        extra = total - mod
        kinds = {0: 0, 1: old_prof // 2, 2: old_prof, 3: 2 * old_prof}
        kind = min(kinds, key=lambda k: abs(kinds[k] - extra))
        return mod + (0, prof // 2, prof, 2 * prof)[kind]

    for s, v in sheet.get("skills", {}).items():
        if s in SKILLS:
            sheet["skills"][s] = new(v, m[SKILLS[s]])
    for a, v in sheet.get("saving_throws", {}).items():
        if a in ABILITIES:
            sheet["saving_throws"][a] = new(v, m[a])


def api_slots(level_data: dict) -> dict[str, int]:
    """{"1": 3, ...}: the spell slots the API gives at this class level."""
    sc = level_data.get("spellcasting") or {}
    return {str(i): sc[f"spell_slots_level_{i}"] for i in range(1, 10) if sc.get(f"spell_slots_level_{i}")}


def ensure_spellcasting(sheet: dict, level_data: dict, class_data: dict | None) -> bool:
    """Make the spellcasting block when the class level gives slots or cantrips and the sheet has none.

    A half caster has none at level 1, so level-up must start it. Returns True if it made the block.
    """
    sc = level_data.get("spellcasting") or {}
    abil = ((class_data or {}).get("spellcasting") or {}).get("spellcasting_ability", {}).get("index")
    if sheet.get("spellcasting") is not None or not abil or not (api_slots(level_data) or sc.get("cantrips_known")):
        return False
    abil = ability(abil)
    spell = {"ability": abil}
    dc, attack = spell_numbers(sheet, spell, prof_from(level_data, sheet["level"]))
    sheet["spellcasting"] = {
        "ability": abil, "spell_save_dc": dc, "spell_attack_bonus": attack, "spells_known": [],
        "spell_slots": {k: {"max": n, "remaining": n} for k, n in api_slots(level_data).items()},
    }
    return True


def level_up(sheet: dict, level_data: dict, hit_die: int, hp_mode: str = "avg",
             asi: dict | None = None, features: list[dict] | None = None, rng=None,
             class_data: dict | None = None) -> list[str]:
    """Apply one class level from the API's `classes/<c>/levels/<n>` data.

    Recomputes every stored total from the new ability modifiers and the new
    proficiency bonus, keeping each entry's proficiency (none, proficient,
    expertise) as inferred from its old total.
    """
    rng = rng or random
    old_level, new_level = sheet["level"], level_data["level"]
    if new_level != old_level + 1:
        raise RulesError(f"{sheet['name']} is level {old_level}; the next level is {old_level + 1}, not {new_level}.")
    old_mods, old_prof = dice.mods(sheet["ability_scores"]), sheet.get("proficiency_bonus", prof_for_level(old_level))
    skill_mult = {s: dice.multiple(v, old_mods[SKILLS[s]], old_prof) for s, v in sheet.get("skills", {}).items() if s in SKILLS}
    save_mult = {a: dice.multiple(v, old_mods[a], old_prof) for a, v in sheet.get("saving_throws", {}).items() if a in ABILITIES}

    lines = []
    for abil, n in (asi or {}).items():
        scores = sheet["ability_scores"]
        scores[abil] = min(20, scores[abil] + n)
        lines.append(f"{abil[:3].upper()} {scores[abil]}")
    new_mods, prof = dice.mods(sheet["ability_scores"]), prof_from(level_data, new_level)

    con = new_mods["constitution"]
    rolled = rng.randint(1, hit_die) if hp_mode == "roll" else hit_die // 2 + 1
    gain = max(1, rolled + con) + (con - old_mods["constitution"]) * old_level + hp_bonus_per_level(sheet)
    sheet["hp"]["max"] += gain
    sheet["hp"]["current"] += gain
    hd = sheet.setdefault("hit_dice", {"total": old_level, "remaining": old_level})
    hd["total"] = hd.get("total", old_level) + 1
    hd["remaining"] = hd.get("remaining", 0) + 1
    hd.setdefault("type", f"d{hit_die}")
    sheet["level"], sheet["proficiency_bonus"] = new_level, prof
    sheet["ability_modifiers"] = new_mods
    if "initiative" in sheet:
        sheet["initiative"] = new_mods["dexterity"]

    for s, mult in skill_mult.items():
        sheet["skills"][s] = new_mods[SKILLS[s]] + mult * prof
    for a, mult in save_mult.items():
        sheet["saving_throws"][a] = new_mods[a] + mult * prof
    items.retotal_weapons(sheet, old_mods, old_prof, new_mods, prof)
    if ensure_spellcasting(sheet, level_data, class_data):
        lines.append(f"{sheet['class']} now casts spells ({sheet['spellcasting']['ability'][:3].upper()}): "
                     "ask the player which spells to prepare or learn")
    spell = sheet.get("spellcasting")
    if spell and spell.get("ability") in ABILITIES:
        spell["spell_save_dc"], spell["spell_attack_bonus"] = spell_numbers(sheet, spell, prof)
    sc = level_data.get("spellcasting") or {}
    if spell is not None and sc:
        sync_slots(spell, api_slots(level_data), prune=False)
        known = {k: v for k, v in sc.items() if k in ("cantrips_known", "spells_known") and v}
        if known:
            lines.append("may know: " + ", ".join(f"{v} {k.replace('_known', '')}" for k, v in known.items()))
    for f in features or []:
        sheet.setdefault("features_and_traits", []).append(f)
    plain = {k: v for k, v in (level_data.get("class_specific") or {}).items() if isinstance(v, (int, float, str))}
    if plain:
        lines.append("class: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in plain.items()))
    head = (f"{sheet['name']} reaches level {new_level}: HP +{gain} ({sheet['hp']['max']} max), "
            f"proficiency +{prof}, hit dice {hd['total']}")
    if features:
        head += "; new: " + ", ".join(f["name"] for f in features)
    if new_mods["dexterity"] != old_mods["dexterity"] or new_mods["wisdom"] != old_mods["wisdom"]:
        lines.append("DEX or WIS changed: check the armor class")
    return [head] + lines
