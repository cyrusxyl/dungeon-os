"""Abilities: one format for what a creature can do with its action, bonus action or reaction on a board.

An attack roll is already in a combat record (`attacks`). This module adds the rest, from the 5e API:
a save-based action (a breath weapon), a Multiattack, a spell, and the few traits that change a turn.
The same format serves a card, a list row and the stage's foe planner (combat-board.md, section 3).

    {"id": "fire-breath", "name": "Fire Breath", "cost": "action", "kind": "zone",
     "save": {"ability": "dex", "dc": 21, "success": "none"},
     "shape": {"type": "cone", "size_ft": 60, "range_ft": 0},
     "damage": [["18d6", "fire"]], "uses": {"per": "recharge", "min": 5, "left": 1}}

`kind` is `zone` (a save, in an area or on one target), `spell_attack` (a spell with an attack roll), `multiattack`,
`self` (a stance or a move), or `dm` (the stage cannot read it: only the DM plays it). `uses` is `recharge`
(`min` on 1d6), `day` (`max`, `left`), `slot` (`level`; the creature's `slots` hold the count), or absent for at will.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from dnd_cli.api import api_get

TRAITS_PATH = Path(__file__).resolve().parents[1] / "stage" / "data" / "traits.json"
COSTS = {"1 action": "action", "1 bonus action": "bonus", "1 reaction": "reaction"}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def traits() -> dict:
    """The hand-written rules of the traits that are plain text in the API (Nimble Escape, Pack Tactics...)."""
    return json.loads(TRAITS_PATH.read_text())


def _feet(text: str | None) -> int:
    m = re.match(r"\s*(\d+)\s*(?:feet|foot|ft)", text or "")
    return int(m.group(1)) if m else 0


def shape_from_text(text: str) -> dict:
    """The area of an action from its text: `a 60-foot cone`, `a 20-foot-radius sphere`, `a line 90 feet long`, else one target."""
    if m := re.search(r"(\d+)-foot[- ]radius", text):
        return {"type": "sphere", "size_ft": int(m.group(1))}
    if m := re.search(r"(\d+)-foot cone", text):
        return {"type": "cone", "size_ft": int(m.group(1))}
    if m := re.search(r"(\d+)-foot cube", text):
        return {"type": "cube", "size_ft": int(m.group(1))}
    if m := re.search(r"line (?:that is )?(\d+) feet long", text) or re.search(r"(\d+)-foot line", text):
        return {"type": "line", "size_ft": int(m.group(1))}
    return {"type": "single", "size_ft": 0}


def _usage(usage: dict | None) -> dict | None:
    if not usage:
        return None
    kind = usage.get("type", "")
    if kind == "recharge on roll":
        return {"per": "recharge", "min": usage.get("min_value", 5), "left": 1}
    if kind == "per day":
        return {"per": "day", "max": usage.get("times", 1), "left": usage.get("times", 1)}
    if kind == "recharge after rest":
        return {"per": "day", "max": 1, "left": 1}
    return None


def _damage(parts: list[dict]) -> list[list[str]]:
    return [[d["damage_dice"].replace(" ", ""), d.get("damage_type", {}).get("name", "").lower()] for d in parts if d.get("damage_dice")]


def from_action(act: dict) -> dict | None:
    """A monster action that is not an attack roll: a save-based action, a Multiattack, or an action only the DM can play."""
    name, desc = act["name"], act.get("desc", "")
    if "attack_bonus" in act:
        return None  # an attack roll is in the combat record already
    if name == "Multiattack":
        if act.get("multiattack_type") == "actions" and act.get("actions"):
            parts = [[a["action_name"], int(a["count"])] for a in act["actions"] if a.get("type") != "ability"]
            return {"id": "multiattack", "name": name, "cost": "action", "kind": "multiattack", "parts": parts}
        return {"id": "multiattack", "name": name, "cost": "action", "kind": "dm", "desc": desc}
    out = {"id": slug(name), "name": name, "cost": "action", "uses": _usage(act.get("usage"))}
    if act.get("dc") and act.get("damage"):
        dc = act["dc"]
        out |= {"kind": "zone", "save": {"ability": dc["dc_type"]["index"], "dc": dc["dc_value"], "success": dc.get("success_type", "none")},
                "shape": {**shape_from_text(desc), "range_ft": 0}, "damage": _damage(act["damage"])}
        if out["shape"]["type"] == "single":
            out["shape"]["range_ft"] = (_feet(m.group(1)) if (m := re.search(r"within (\d+ feet)", desc)) else 5) or 5
        return out
    return out | {"kind": "dm", "desc": desc}


def at_level(table: dict, level: int) -> str | None:
    """The entry of a `damage_at_*_level` table for a level: the highest key at or under it."""
    keys = sorted((int(k) for k in table), key=int)
    fit = [k for k in keys if k <= level]
    return table[str(fit[-1] if fit else keys[0])].replace(" ", "") if keys else None


def from_spell(data: dict, slot: int | None = None, caster_level: int = 1, dc: int | None = None, attack: int | None = None) -> dict | None:
    """A damage spell as an ability, or None when the stage cannot run it (a buff, a utility spell, a long cast)."""
    cost = COSTS.get(data.get("casting_time", ""))
    dmg = data.get("damage") or {}
    table = dmg.get("damage_at_slot_level") or dmg.get("damage_at_character_level")
    if cost is None or not table:
        return None
    level = data.get("level", 0)
    expr = at_level(table, slot or level or caster_level) if "damage_at_slot_level" in dmg else at_level(table, caster_level)
    base = {"id": slug(data["name"]), "name": data["name"], "cost": cost, "spell_level": level, "slot": slot or level or None,
            "damage": [[expr, dmg.get("damage_type", {}).get("name", "").lower()]]}
    reach = _feet(data.get("range")) or (5 if data.get("range") == "Touch" else 0)
    if data.get("dc") and dc is not None:
        area = data.get("area_of_effect") or {"type": "single", "size": 0}
        return base | {"kind": "zone", "save": {"ability": data["dc"]["dc_type"]["index"], "dc": dc, "success": data["dc"].get("dc_success", "none")},
                       "shape": {"type": area["type"], "size_ft": area["size"], "range_ft": reach}}
    if data.get("attack_type") and attack is not None:
        return base | {"kind": "spell_attack", "attack": {"bonus": attack, "range_ft": reach if data["attack_type"] == "ranged" else 0,
                                                          "reach_ft": reach if data["attack_type"] == "melee" else 0}}
    return None


def _spell(index: str) -> dict | None:
    data, err, _ = api_get(f"spells/{index}")
    return None if err else data


def from_spellcasting(sc: dict) -> tuple[list[dict], dict]:
    """The damage spells of a monster's Spellcasting, and its slots by level."""
    out = []
    for entry in sc.get("spells", []):
        if (data := _spell(entry["url"].rsplit("/", 1)[-1])) is None:
            continue
        slot = entry["level"] or None
        if ability := from_spell(data, slot=slot, caster_level=sc.get("level", 1), dc=sc.get("dc"), attack=sc.get("modifier")):
            out.append(ability | ({"uses": {"per": "slot", "level": entry["level"]}} if entry["level"] else {}))
    return out, {k: int(v) for k, v in (sc.get("slots") or {}).items()}


def from_monster(data: dict) -> dict:
    """What the stage can plan for a monster beyond its attack rolls: `abilities`, `slots` and `traits`."""
    abilities = [a for act in data.get("actions", []) if (a := from_action(act))]
    slots: dict = {}
    known = traits()
    found = []
    for sp in data.get("special_abilities", []):
        if sp["name"] == "Spellcasting" and sp.get("spellcasting"):
            spells, slots = from_spellcasting(sp["spellcasting"])
            abilities += spells
        elif sp["name"] in known:
            found.append(sp["name"])
            if (extra := known[sp["name"]].get("ability")):
                abilities.append(dict(extra))
    for act in data.get("reactions", []) + data.get("legendary_actions", []):
        abilities.append({"id": slug(act["name"]), "name": act["name"], "cost": "reaction" if act in data.get("reactions", []) else "legendary",
                          "kind": "dm", "desc": act.get("desc", "")})
    return {"abilities": abilities, "slots": slots, "traits": found}


def recharge(rec: dict, rng) -> list[str]:
    """At the start of its turn, a creature rolls 1d6 for each spent recharge ability: it is back on its minimum or more."""
    lines = []
    for ab in rec.get("abilities", []):
        use = ab.get("uses")
        if use and use["per"] == "recharge" and not use["left"]:
            roll = rng.randint(1, 6)
            if roll >= use["min"]:
                use["left"] = 1
            lines.append(f"{rec['name']}'s {ab['name']}: recharge roll {roll} — " + ("ready." if use["left"] else "not yet."))
    return lines


def available(rec: dict, ab: dict) -> bool:
    """Can the creature use this ability now: it is one the stage can run, and it has a use or a slot left."""
    if ab["kind"] == "dm":
        return False
    use = ab.get("uses")
    if not use:
        return True
    if use["per"] == "slot":
        return rec.get("slots", {}).get(str(use["level"]), 0) > 0
    return use["left"] > 0


def spend(rec: dict, ab: dict) -> None:
    use = ab.get("uses")
    if not use:
        return
    if use["per"] == "slot":
        rec["slots"][str(use["level"])] -= 1
    else:
        use["left"] -= 1
