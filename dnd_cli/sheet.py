"""Character-sheet changes the DM used to make by hand: items, gold, gear, rests, XP, level-up.

All functions change a loaded sheet dict and return short lines for the DM;
the caller saves through dnd_cli.character (which validates the schema).

Sheets store totals (a skill bonus, a weapon's attack bonus), not whether a
character is proficient. Level-up and gear infer proficiency from the totals:
`(total - ability modifier) / proficiency bonus` is 0, 1, or 2 (expertise).
"""

from __future__ import annotations

import random
import re

from dnd_cli import dice
from dnd_cli.combat import ABILITIES, SKILLS, RulesError, level_for_xp

GOLD = "Gold Pieces"


def mods(sheet: dict) -> dict:
    return {a: dice.mod(sheet["ability_scores"].get(a, 10)) for a in ABILITIES}


def prof_for_level(level: int) -> int:
    return 2 + (level - 1) // 4


def base_ac(class_name: str, m: dict) -> int:
    """Unarmored AC: 10 + DEX, plus CON for a Barbarian or WIS for a Monk."""
    extra = {"barbarian": m["constitution"], "monk": m["wisdom"]}.get(class_name.lower(), 0)
    return 10 + m["dexterity"] + extra


# -- items and gold ----------------------------------------------------------


def _find_item(sheet: dict, name: str) -> dict | None:
    items = sheet.setdefault("inventory", [])
    return next((i for i in items if i.get("name", "").lower() == name.lower()), None)


def add_item(sheet: dict, name: str, qty: int = 1, description: str = "") -> str:
    if qty < 1:
        raise RulesError("quantity must be 1 or more.")
    item = _find_item(sheet, name)
    if item:
        item["quantity"] = item.get("quantity", 1) + qty
    else:
        item = {"name": name, "quantity": qty}
        if description:
            item["description"] = description
        sheet["inventory"].append(item)
    return f"{sheet['name']}: {item['name']} x{item['quantity']}"


def remove_item(sheet: dict, name: str, qty: int = 1) -> str:
    item = _find_item(sheet, name)
    if not item:
        have = ", ".join(i["name"] for i in sheet.get("inventory", [])) or "nothing"
        raise RulesError(f"{sheet['name']} has no {name!r}. Inventory: {have}.")
    if item.get("quantity", 1) < qty:
        raise RulesError(f"{sheet['name']} has only {item.get('quantity', 1)} {item['name']}.")
    item["quantity"] = item.get("quantity", 1) - qty
    if item["quantity"] == 0:  # the schema has no zero quantities
        sheet["inventory"].remove(item)
        return f"{sheet['name']}: no {item['name']} left"
    return f"{sheet['name']}: {item['name']} x{item['quantity']}"


def gold(sheet: dict, delta: int) -> str:
    item = _find_item(sheet, GOLD)
    have = item.get("quantity", 0) if item else 0
    if have + delta < 0:
        raise RulesError(f"{sheet['name']} has only {have} gp; {-delta} gp is too much.")
    if delta > 0:
        add_item(sheet, GOLD, delta)
    elif delta < 0:
        remove_item(sheet, GOLD, -delta)
    return f"{sheet['name']}: {have + delta} gp"


# -- gear --------------------------------------------------------------------


def _weapon_ability(sheet: dict, props: list[str], ranged: bool) -> str:
    m = mods(sheet)
    if "finesse" in props or "martial arts" in props:
        return "dexterity" if m["dexterity"] >= m["strength"] else "strength"
    return "dexterity" if ranged else "strength"


def _with_bonus(expr: str, bonus: int) -> str:
    base = re.sub(r"[+-]\d+$", "", expr.replace(" ", ""))
    return base + (dice.signed(bonus) if bonus else "")


def _shield_equipped(sheet: dict) -> bool:
    return any(i.get("equipped") and i.get("name", "").lower() == "shield" for i in sheet.get("inventory", []))


def equip(sheet: dict, item: dict, proficient: bool = True) -> list[str]:
    """Equip a weapon, armor, or shield from the 5e API. Only armor and shields change AC.

    Unarmored AC (a monk's 10 + DEX + WIS) is never recomputed: a shield adds 2 to it.
    """
    name = item["name"]
    category = item.get("equipment_category", {}).get("index", "")
    armor_cat = item.get("armor_category", "").lower()
    if armor_cat == "shield" and _shield_equipped(sheet):
        return [f"{sheet['name']} already carries a shield: AC {sheet['armor_class']}"]
    shield = _shield_equipped(sheet)
    if not _find_item(sheet, name):
        add_item(sheet, name, 1)
    _find_item(sheet, name)["equipped"] = True
    m, prof = mods(sheet), sheet.get("proficiency_bonus", prof_for_level(sheet["level"]))
    if category == "weapon":
        props = [p["index"] for p in item.get("properties", [])]
        abil = _weapon_ability(sheet, props, item.get("weapon_range") == "Ranged")
        dmg = item.get("damage") or {}
        bonus = m[abil] + (prof if proficient else 0)
        entry = {
            "name": name, "attack_bonus": bonus,
            "damage": _with_bonus(dmg.get("damage_dice", "1"), m[abil]),
            "damage_type": dmg.get("damage_type", {}).get("index", ""),
            "properties": props, "equipped": True,
        }
        sheet["weapons"] = [w for w in sheet.get("weapons", []) if w.get("name") != name] + [entry]
        return [f"{sheet['name']} wields {name}: {dice.signed(bonus)} to hit, {entry['damage']} {entry['damage_type']}"]
    if armor_cat == "shield":
        sheet["armor_class"] += 2
        return [f"{sheet['name']} takes up a shield: AC {sheet['armor_class']}"]
    if category == "armor":
        ac = item.get("armor_class", {})
        cap = ac.get("max_bonus") if ac.get("dex_bonus") else 0  # None: no cap
        dex = m["dexterity"] if cap is None else min(m["dexterity"], cap)
        sheet["armor"] = {"name": name, "type": armor_cat, "ac_bonus": ac.get("base", 10), "equipped": True}
        sheet["armor_class"] = ac.get("base", 10) + dex + (2 if shield else 0)
        line = f"{sheet['name']} wears {name}: AC {sheet['armor_class']}"
        if item.get("str_minimum") and sheet["ability_scores"]["strength"] < item["str_minimum"]:
            line += f" (STR under {item['str_minimum']}: speed -10 ft)"
        if item.get("stealth_disadvantage"):
            line += " (disadvantage on Stealth)"
        return [line]
    return [f"{sheet['name']} carries {name} (no attack or AC change)."]


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
    return (f"{sheet['name']}: HP {hp['max']}/{hp['max']}, hit dice {hd['remaining']}/{total}"
            + (", spell slots full" if slots else ""))


def short_rest(sheet: dict, spend: int, rng=None) -> str:
    rng = rng or random
    hd = sheet.setdefault("hit_dice", {"total": sheet["level"], "remaining": sheet["level"]})
    spend = min(spend, hd.get("remaining", 0))
    die, con = _hit_die(sheet), mods(sheet)["constitution"]
    healed = sum(max(0, rng.randint(1, die) + con) for _ in range(spend))
    hp = sheet["hp"]
    hp["current"] = min(hp["max"], hp["current"] + healed)
    hd["remaining"] = hd.get("remaining", 0) - spend
    if healed:
        sheet["death_saves"] = {"successes": 0, "failures": 0}
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


def _stored_ability(weapon: dict, old_mods: dict) -> str:
    """The ability a stored weapon uses: the one whose modifier is its damage bonus (DEX on a tie)."""
    m = re.search(r"([+-]\d+)$", weapon.get("damage", "").replace(" ", ""))
    flat = int(m.group(1)) if m else 0
    for abil in ("dexterity", "strength"):
        if old_mods[abil] == flat:
            return abil
    props = [p.lower() for p in weapon.get("properties", [])]
    ranged = "ammunition" in props or any(k in weapon.get("name", "").lower() for k in ("bow", "sling", "dart"))
    return "dexterity" if ranged or "finesse" in props else "strength"


def _multiple(total: int, mod: int, prof: int) -> int:
    return max(0, min(2, round((total - mod) / prof))) if prof else 0


def level_up(sheet: dict, level_data: dict, hit_die: int, hp_mode: str = "avg",
             asi: dict | None = None, features: list[dict] | None = None, rng=None) -> list[str]:
    """Apply one class level from the API's `classes/<c>/levels/<n>` data.

    Recomputes every stored total from the new ability modifiers and the new
    proficiency bonus, keeping each entry's proficiency (none, proficient,
    expertise) as inferred from its old total.
    """
    rng = rng or random
    old_level, new_level = sheet["level"], level_data["level"]
    if new_level != old_level + 1:
        raise RulesError(f"{sheet['name']} is level {old_level}; the next level is {old_level + 1}, not {new_level}.")
    old_mods, old_prof = mods(sheet), sheet.get("proficiency_bonus", prof_for_level(old_level))
    weapon_abil = {w["name"]: _stored_ability(w, old_mods) for w in sheet.get("weapons", [])}
    skill_mult = {s: _multiple(v, old_mods[SKILLS[s]], old_prof) for s, v in sheet.get("skills", {}).items() if s in SKILLS}
    save_mult = {a: _multiple(v, old_mods[a], old_prof) for a, v in sheet.get("saving_throws", {}).items() if a in ABILITIES}
    weapon_mult = {w["name"]: _multiple(w.get("attack_bonus", 0), old_mods[weapon_abil[w["name"]]], old_prof)
                   for w in sheet.get("weapons", [])}

    lines = []
    for abil, n in (asi or {}).items():
        scores = sheet["ability_scores"]
        scores[abil] = min(20, scores[abil] + n)
        lines.append(f"{abil[:3].upper()} {scores[abil]}")
    new_mods, prof = mods(sheet), level_data.get("prof_bonus", prof_for_level(new_level))

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
    for w in sheet.get("weapons", []):
        abil = weapon_abil[w["name"]]
        w["attack_bonus"] = new_mods[abil] + weapon_mult[w["name"]] * prof
        if w.get("damage"):
            w["damage"] = _with_bonus(w["damage"], new_mods[abil])
    spell = sheet.get("spellcasting")
    if spell and spell.get("ability") in ABILITIES:
        m = new_mods[spell["ability"]]
        spell["spell_save_dc"], spell["spell_attack_bonus"] = 8 + prof + m, prof + m
    api_slots = (level_data.get("spellcasting") or {})
    if spell is not None and api_slots:
        slots = spell.setdefault("spell_slots", {})
        for lvl in range(1, 10):
            n = api_slots.get(f"spell_slots_level_{lvl}", 0)
            if n:
                old = slots.get(str(lvl), {"max": 0, "remaining": 0})
                slots[str(lvl)] = {"max": n, "remaining": old.get("remaining", 0) + n - old.get("max", 0)}
        known = {k: v for k, v in api_slots.items() if k in ("cantrips_known", "spells_known") and v}
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
