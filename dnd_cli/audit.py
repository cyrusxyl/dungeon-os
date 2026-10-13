"""Check a character sheet against the 5e API data for its class and level, and fix what is certain.

`fetch(endpoint) -> dict` raises RulesError for an unknown endpoint. If the API cannot be
reached, `audit` says "cannot check" and does not fail. `repair` changes only fields that
the rules fix: the spellcasting block, slot maximums, spell DC and attack, proficiency
bonus. It never changes remaining slots or chosen spells.
"""

from __future__ import annotations

from dnd_cli import actions, combat, resources, sheet
from dnd_cli.combat import RulesError

# Features that need a recorded choice: feature name -> sheet key.
CHOICES = {
    "Fighting Style": "fighting_style",
    "Sacred Oath": "subclass", "Primal Path": "subclass", "Bard College": "subclass",
    "Divine Domain": "subclass", "Druid Circle": "subclass", "Martial Archetype": "subclass",
    "Monastic Tradition": "subclass", "Ranger Archetype": "subclass", "Roguish Archetype": "subclass",
    "Sorcerous Origin": "subclass", "Otherworldly Patron": "subclass", "Arcane Tradition": "subclass",
}

# Features that cost something: feature name -> the resource that pays for it.
COSTED = {
    "Divine Smite": "spell slots", "Lay on Hands": "Lay on Hands", "Divine Sense": "Divine Sense",
    "Channel Divinity": "Channel Divinity", "Ki": "Ki", "Rage": "Rage", "Bardic Inspiration": "Bardic Inspiration",
    "Wild Shape": "Wild Shape", "Font of Magic": "Sorcery Points", "Action Surge": "Action Surge",
    "Second Wind": "Second Wind", "Arcane Recovery": "Arcane Recovery", "Indomitable": "Indomitable",
    "Divine Intervention": "Divine Intervention", "Cleansing Touch": "Cleansing Touch",
    "Stroke of Luck": "Stroke of Luck",
}


def card_gaps(held) -> list[str]:
    """Features in `held` (names from COSTED) that have no entry in `actions.FEATURES`: a feature the stage could forget."""
    return [f"feature {name} has no action card" for name in COSTED if name in held and name not in actions.FEATURES]


class CannotCheck(Exception):
    pass


def _memo(fetch):
    """`fetch` that asks each endpoint once, and fails at once after the first failure (an offline API gives one timeout)."""
    cache, failed = {}, []

    def get(endpoint: str) -> dict:
        if failed:
            raise failed[0]
        if endpoint not in cache:
            try:
                cache[endpoint] = fetch(endpoint)
            except (RulesError, KeyError, ValueError, OSError) as e:
                failed.append(e)
                raise
        return cache[endpoint]

    return get


def _data(sheet_: dict, fetch) -> tuple[dict, dict, list[dict]]:
    """(class data, data of the sheet's level, data of every level up to it)."""
    cls, fetch = str(sheet_.get("class", "")).split()[0].lower(), _memo(fetch)
    try:
        c = fetch(f"classes/{cls}")
        levels = [fetch(f"classes/{cls}/levels/{n}") for n in range(1, int(sheet_["level"]) + 1)]
    except (RulesError, KeyError, ValueError, OSError) as e:
        raise CannotCheck(f"cannot check the sheet against the 5e API ({e})") from None
    return c, levels[-1], levels


def _checked(work, sheet_: dict, fetch) -> list[str]:
    """`work(sheet, class data, level data, all level data)`, or the one "cannot check" line."""
    try:
        data = _data(sheet_, fetch)
    except CannotCheck as e:
        return [str(e)]
    return work(sheet_, *data)


def _slot_max(spell: dict) -> dict[str, int]:
    return {k: v.get("max", 0) for k, v in (spell.get("spell_slots") or {}).items() if v.get("max", 0)}


def audit(sheet_: dict, fetch) -> list[str]:
    """Problems found, one short line each. Empty when the sheet is right."""
    return _checked(_audit, sheet_, fetch)


def _audit(sheet_: dict, cls: dict, lvl: dict, levels: list[dict]) -> list[str]:
    out, level = [], sheet_["level"]
    want, prof = sheet.api_slots(lvl), sheet.prof_from(lvl, level)
    spell = sheet_.get("spellcasting")
    if want or (lvl.get("spellcasting") or {}).get("cantrips_known"):
        if spell is None:
            out.append(f"no spellcasting block (level {level} {cls['name']} has slots {want or 'none'}, cantrips)")
        else:
            if _slot_max(spell) != want:
                out.append(f"spell slots max {_slot_max(spell) or 'none'}, should be {want}")
            dc, attack = sheet.spell_numbers(sheet_, spell, prof)
            if (spell.get("spell_save_dc"), spell.get("spell_attack_bonus")) != (dc, attack):
                out.append(f"spell DC/attack are {spell.get('spell_save_dc')}/{spell.get('spell_attack_bonus')}, should be {dc}/{attack}")
    elif spell and _slot_max(spell):
        out.append("has spell slots but the class gets none at this level")
    if sheet_.get("proficiency_bonus") != prof:
        out.append(f"proficiency bonus {sheet_.get('proficiency_bonus')}, should be {prof}")
    hd = (sheet_.get("hit_dice") or {}).get("total")
    if hd != level:
        out.append(f"hit dice total {hd}, should be {level}")

    have = {f.get("name", "").lower() for f in sheet_.get("features_and_traits", [])}
    for n, data in enumerate(levels, 1):
        for f in data.get("features", []):
            if f["name"].lower() not in have:
                out.append(f"missing feature {f['name']} (level {n})")
    for name, key in CHOICES.items():
        if name.lower() in have and not sheet_.get(key):
            out.append(f"choose: {name} is not recorded (ask the player; sheet key {key})")

    held = {n: res for n, res in COSTED.items() if combat.has_feature(sheet_, n)}
    out += card_gaps(held)
    tracked = {r["name"] for r in resources.for_sheet(sheet_)}
    has_slots = bool(spell and _slot_max(spell))
    for name, res in held.items():
        if res == "spell slots" and not has_slots:
            out.append(f"{name} costs spell slots but the sheet has none")
        elif res != "spell slots" and res not in tracked:
            out.append(f"{name} has no tracked resource {res}")
    return out


def repair(sheet_: dict, fetch) -> list[str]:
    """Fix the fields the rules fix. Returns what changed."""
    return _checked(_repair, sheet_, fetch)


def _repair(sheet_: dict, cls: dict, lvl: dict, _levels: list[dict]) -> list[str]:
    out = []
    if sheet.ensure_spellcasting(sheet_, lvl, cls):
        out.append(f"made the spellcasting block ({sheet_['spellcasting']['ability'][:3].upper()}), "
                   f"slots {sheet.api_slots(lvl) or 'none'}")
    spell, want, prof = sheet_.get("spellcasting"), sheet.api_slots(lvl), sheet.prof_from(lvl, sheet_["level"])
    if sheet_.get("proficiency_bonus") != prof:
        out.append(f"proficiency bonus {sheet_.get('proficiency_bonus')} -> {prof} (skill and save totals not recomputed)")
        sheet_["proficiency_bonus"] = prof
    if spell is not None and (want or _slot_max(spell)):
        out += [f"level {k} slots max {old} -> {new}" for k, old, new in sheet.sync_slots(spell, want)]
    if spell is not None and spell.get("ability") in sheet_["ability_scores"]:
        dc, attack = sheet.spell_numbers(sheet_, spell, prof)
        if (spell.get("spell_save_dc"), spell.get("spell_attack_bonus")) != (dc, attack):
            spell["spell_save_dc"], spell["spell_attack_bonus"] = dc, attack
            out.append(f"spell DC {dc}, attack {attack:+d}")
    return out


def summary(problems: list[str]) -> str:
    return "sheet problems: " + "; ".join(problems)
