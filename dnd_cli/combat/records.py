"""Combatant records: a player character, a monster and an NPC have one shape. Ability and skill bonuses."""

from __future__ import annotations

import re
from pathlib import Path

from dnd_cli import abilities, character, dice, effects
from dnd_cli.errors import RulesError
from dnd_cli.item import attacks as pc_attacks, geometry
from dnd_cli.combat.tracker import party


ABILITIES = dice.ABILITIES


SHORT = {a[:3]: a for a in ABILITIES}


SKILLS = {
    "acrobatics": "dexterity", "animal_handling": "wisdom", "arcana": "intelligence", "athletics": "strength",
    "deception": "charisma", "history": "intelligence", "insight": "wisdom", "intimidation": "charisma",
    "investigation": "intelligence", "medicine": "wisdom", "nature": "intelligence", "perception": "wisdom",
    "performance": "charisma", "persuasion": "charisma", "religion": "intelligence", "sleight_of_hand": "dexterity",
    "stealth": "dexterity", "survival": "wisdom",
}


XP_LEVELS = [0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000, 64000, 85000, 100000,
             120000, 140000, 165000, 195000, 225000, 265000, 305000, 355000]


def ability(name: str) -> str:
    key = name.lower().strip()
    if key in ABILITIES:
        return key
    if key[:3] in SHORT:
        return SHORT[key[:3]]
    raise RulesError(f"no ability {name!r}; use str, dex, con, int, wis or cha.")


def level_for_xp(xp: int) -> int:
    return sum(1 for t in XP_LEVELS if xp >= t)


def _feet(text: str | None, default: int = 30) -> int:
    m = re.match(r"\s*(\d+)", text or "")
    return int(m.group(1)) if m else default


def pc_record(sheet: dict, cid: str) -> dict:
    scores = sheet.get("ability_scores", {})
    mods = dice.mods(scores)
    return {
        "id": cid, "kind": "pc", "name": sheet.get("name", cid), "ac": sheet.get("armor_class", 10),
        "hp": sheet["hp"], "mods": mods,
        "saves": {a: sheet.get("saving_throws", {}).get(a, mods[a]) for a in ABILITIES},
        "skills": {s: sheet.get("skills", {}).get(s, mods[a]) for s, a in SKILLS.items()},
        "attacks": pc_attacks(sheet), "init": sheet.get("initiative", mods["dexterity"]), "speed_ft": sheet.get("speed", 30),
        "spell_dc": (sheet.get("spellcasting") or {}).get("spell_save_dc"), "resist": [], "immune": [], "vuln": [],
        "prof": sheet.get("proficiency_bonus"),
    }


def wielded(attacks: list[dict]) -> dict | None:
    """The attack in hand: the first equipped one, else the first."""
    return next((x for x in attacks if x.get("equipped")), attacks[0] if attacks else None)


def damage_parts(damage: list[dict]) -> list[list[str]]:
    """The [dice, type] parts of an API action's damage. A weapon that offers a choice (a longsword one or two handed)
    gives its first option."""
    out = []
    for d in damage:
        if "damage_dice" not in d and (options := (d.get("from") or {}).get("options")):
            d = options[0]
        if d.get("damage_dice"):
            out.append([d["damage_dice"], d.get("damage_type", {}).get("name", "").lower()])
    return out


def monster_record(data: dict, cid: str) -> dict:
    """A compact copy of an API monster: only what play needs (no description text)."""
    mods = dice.mods(data)
    profs = {p["proficiency"]["index"]: p["value"] for p in data.get("proficiencies", [])}
    attacks = []
    for act in data.get("actions", []):
        damage = damage_parts(act.get("damage", []))
        entry = {"name": act["name"], "damage": damage, **geometry(act.get("desc", ""))}
        if "attack_bonus" in act:
            entry["bonus"] = act["attack_bonus"]
        elif act.get("dc"):
            dc = act["dc"]
            entry["dc"] = [dc["dc_type"]["index"], dc["dc_value"], dc.get("success_type", "none")]
        else:
            continue  # Multiattack and abilities with no roll: the DM narrates them.
        attacks.append(entry)
    ac = data.get("armor_class", [{}])
    extra = abilities.from_monster(data)
    if bonus := next((x["attack"]["bonus"] for x in extra["abilities"] if x["kind"] == "spell_attack"), None):
        attacks.append({"name": "spell", "bonus": bonus, "damage": []})  # a spell attack rolls like a PC's: `attack <id> spell <target> --damage`
    return {
        "id": cid, "kind": "monster", "index": data.get("index"), "name": data.get("name", cid), "ctype": data.get("type", ""),
        "ac": ac[0].get("value", 10) if isinstance(ac, list) else ac,
        "hp": {"current": data.get("hit_points", 1), "max": data.get("hit_points", 1)},
        "mods": mods,
        # Only proficient saves and skills: the rest is the ability modifier (see bonus()).
        "saves": {a: profs[f"saving-throw-{a[:3]}"] for a in ABILITIES if f"saving-throw-{a[:3]}" in profs},
        "skills": {s: profs[f"skill-{s.replace('_', '-')}"] for s in SKILLS if f"skill-{s.replace('_', '-')}" in profs},
        "attacks": attacks, "init": mods["dexterity"], "xp": data.get("xp", 0),
        "speed_ft": _feet((data.get("speed") or {}).get("walk")), **extra,
        "resist": data.get("damage_resistances", []), "immune": data.get("damage_immunities", []),
        "vuln": data.get("damage_vulnerabilities", []),
    }


def npc_record(data: dict, cid: str) -> dict:
    mods = dice.mods(data.get("ability_scores", {}))
    attacks = []
    for act in data.get("actions", []):
        if "attack_bonus" in act:
            attacks.append({"name": act["name"], "bonus": act["attack_bonus"], **geometry(act.get("desc", "")),
                            "damage": [[act["damage"], ""]] if act.get("damage") else []})
    hp = data["hp"]
    return {
        "id": cid, "kind": "npc", "name": data.get("name", cid), "ac": data.get("armor_class", 10),
        "hp": {"current": hp.get("current", hp.get("max", 1)), "max": hp.get("max", 1)},
        "mods": mods, "saves": {}, "skills": {},
        "attacks": attacks, "init": mods["dexterity"], "xp": data.get("xp", 0), "speed_ft": _feet(data.get("speed")),
        "resist": [], "immune": [], "vuln": [],
    }


def save_bonus(rec: dict, abil: str) -> int:
    return rec["saves"].get(abil, rec["mods"][abil])


def skill_bonus(rec: dict, skill: str) -> int:
    return rec["skills"].get(skill, rec["mods"][SKILLS[skill]])


def npc_path(campaign_dir: Path, cid: str) -> Path:
    return campaign_dir / "world" / "npcs" / f"{cid}.json"


def combatant(campaign_dir: Path, state: dict, cid: str) -> dict:
    """The record for any id: an encounter creature, else a player character."""
    enc = state.get("active_encounter") or {}
    if cid in (enc.get("monsters") or {}):
        return enc["monsters"][cid]
    if character.character_path(campaign_dir, cid).exists():
        sheet = character.load(campaign_dir, cid)
        rec = pc_record(sheet, cid)
        fx = effects.defense(campaign_dir, cid, sheet)  # worn gear: Armor Class and resistances
        rec["ac"] += fx["ac"]
        rec["resist"] = rec["resist"] + fx["resist"]
        rec["reduce"] = fx["reduce"]
        return rec
    known = list((enc.get("monsters") or {})) + party(campaign_dir, state)
    raise RulesError(f"no combatant {cid!r}. Known: {', '.join(known) or 'none'}.")


def health_band(rec: dict) -> str:
    """How hurt a creature looks to the players: no numbers (the DM keeps those behind the screen)."""
    cur, top = rec["hp"]["current"], max(rec["hp"]["max"], 1)
    if cur <= 0:
        return "down"
    if cur * 4 <= top:
        return "near death"
    if cur * 2 <= top:
        return "bloodied"
    return "unhurt" if cur >= top else "injured"
