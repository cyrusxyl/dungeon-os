"""Rules engine for the DM: encounters, attacks, saves, checks, damage, XP.

The DM decides what happens; this module does the bookkeeping and the
arithmetic, and prints one short line per result. A combatant is one record
whatever its source:

- a player character (`characters/<id>.json`, saved through dnd_cli.character),
- a monster instance (`goblin#2`), built from the D&D 5e API at encounter start
  and kept in `state.json` -> `active_encounter.monsters`,
- an NPC with stats (`world/npcs/<id>.json` with `hp` and `armor_class`),
  copied into the encounter and written back at the end.

Ids are the visual stage's actor ids, so `goblin#2` works in `@enter` and in
`attack`. Rolls go to the stage's dice box unless `secret`; the stage event
never carries a hidden number (monster HP, AC, a secret DC).
"""

from __future__ import annotations

import json
import os
import random
import re
from collections.abc import Sequence
from pathlib import Path

from dnd_cli import abilities, character, dice, effects
from dnd_cli.api import api_get
from stage.files import read_json, write_json

ABILITIES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")
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


class RulesError(ValueError):
    """A rules command that cannot run. The message says how to fix it."""


# -- small helpers -----------------------------------------------------------


def ability(name: str) -> str:
    key = name.lower().strip()
    if key in ABILITIES:
        return key
    if key[:3] in SHORT:
        return SHORT[key[:3]]
    raise RulesError(f"no ability {name!r}; use str, dex, con, int, wis or cha.")


def level_for_xp(xp: int) -> int:
    return sum(1 for t in XP_LEVELS if xp >= t)


def stage_roll(expr: str, total: int, groups: list[dict], secret: bool = False, detail: dict | None = None) -> None:
    """Show a roll in the stage's dice box (no-op without a running stage, or when secret).

    `detail` is the roll window's breakdown (see `roll_detail`). Without it the stage shows `expr` and the dice.
    """
    log = os.environ.get("DUNGEON_STAGE_LOG")
    if log and not secret:
        event = {"type": "roll", "expr": expr, "total": total, "dice": groups}
        if detail:
            event["detail"] = detail
        with open(log, "a") as f:
            f.write(json.dumps(event) + "\n")


def stage_feed(text: str) -> None:
    """A line for the stage's log (no-op without a running stage). Rolls reach the log by themselves."""
    log = os.environ.get("DUNGEON_STAGE_LOG")
    if log:
        with open(log, "a") as f:
            f.write(json.dumps({"type": "feed", "text": text}) + "\n")


def _secret_feed(secret: bool, recs: list[dict], text: str) -> None:
    """A secret roll hides the dice, but a hero who loses HP to it still gets a line in the log."""
    if secret and any(r["kind"] == "pc" for r in recs):
        stage_feed(text)


def _shown_damage(dtype: str, expr: str, groups: list[dict], total: int) -> dict:
    """One damage entry for the roll window. `faces` is every die in one list (old clients); `groups` keeps them by die type."""
    return {"type": dtype, "expr": expr, "faces": [f for g in groups for f in g["faces"]], "groups": groups, "total": total}


def _d20_groups(faces: list[int], kept: int) -> list[dict]:
    """The kept d20 first (the legacy dice box colours a natural 20 or 1 from it)."""
    rest = list(faces)
    rest.remove(kept)
    return [{"die": "1d20", "faces": [kept]}] + ([{"die": "1d20 dropped", "faces": rest}] if rest else [])


def _d20(campaign_dir: Path, cid: str, kind: str, adv: bool, dis: bool, rng, skip=(), tags=()) -> dict:
    """One d20 roll for a creature, with its active effects: advantage, disadvantage, bonus dice and flat bonuses.

    `tags` say what the roll is about (its ability, its skill) for effects that need one."""
    fx = effects.apply(campaign_dir, cid, kind, rng, skip, tags)
    adv, dis = adv or fx["adv"], dis or fx["dis"]
    kept, faces = dice.d20(rng, adv, dis)
    mode = "normal" if len(faces) == 1 else "advantage" if adv else "disadvantage"
    return {"kept": kept, "faces": faces, "mode": mode, "bonus": fx["bonus"], "flat": fx["flat"], "used": fx["used"]}


def _fx_note(roll: dict) -> str:
    """The effects a roll used, for the DM's output line: ` (advantage 17,5; guidance +3)`."""
    notes = []
    if roll["mode"] != "normal":
        notes.append(f"{roll['mode']} {','.join(map(str, roll['faces']))}")
    notes += [f"{b['label'].lower()} {dice.signed(b['value'])}" for b in roll["bonus"] + roll.get("flat", [])]
    return f" ({'; '.join(notes)})" if notes else ""


def _tiles(rec: dict, abil: str, bonus: int, what: str) -> list[dict]:
    """A skill or save bonus split into the roll window's tiles: ability, proficiency, expertise."""
    base = rec["mods"][abil]
    tiles = [{"label": abil.capitalize(), "value": base}]
    rest = bonus - base
    prof = rec.get("prof") or rest
    if rest and rest == prof:
        tiles.append({"label": f"{what} Proficiency", "value": rest})
    elif rest and rest == 2 * prof:
        tiles += [{"label": f"{what} Proficiency", "value": prof}, {"label": f"{what} Expertise", "value": prof}]
    elif rest:
        tiles.append({"label": "Other", "value": rest})
    return tiles


def check_spec(rec: dict, what: str) -> dict:
    """What a check or a save is: its ability, bonus, window title and the tiles that make the bonus.

    `what` is a skill (`athletics`), an ability (`str`), or a save (`dex-save`).
    """
    what = what.lower().replace(" ", "_")
    if what.endswith(("-save", "_save")):
        abil = ability(what[:-5])
        bonus = save_bonus(rec, abil)
        return {"kind": "save", "abil": abil, "bonus": bonus, "title": f"{abil.capitalize()} Saving Throw", "subtitle": "",
                "label": abil[:3].upper(), "tiles": _tiles(rec, abil, bonus, f"{abil.capitalize()} Save")}
    what = what.replace("-", "_")
    if what in SKILLS:
        abil = SKILLS[what]
        bonus, label = skill_bonus(rec, what), what.replace("_", " ").title()
        return {"kind": "check", "abil": abil, "bonus": bonus, "title": label, "subtitle": f"{abil.capitalize()} Check",
                "label": label, "tiles": _tiles(rec, abil, bonus, label)}
    abil = ability(what)
    bonus = rec["mods"][abil]
    return {"kind": "check", "abil": abil, "bonus": bonus, "title": abil.capitalize(), "subtitle": "Ability Check",
            "label": abil[:3].upper(), "tiles": _tiles(rec, abil, bonus, abil.capitalize())}


def roll_preview(campaign_dir: Path, state: dict, cid: str, what: str) -> dict:
    """The roll window before the roll: who rolls what, and the tiles that will add to the d20."""
    rec = combatant(campaign_dir, state, cid)
    spec = check_spec(rec, what)
    return {"name": rec["name"], "kind": spec["kind"], "title": spec["title"], "subtitle": spec["subtitle"], "mods": spec["tiles"]}


def _entry(rec: dict, roll: dict, tiles: list[dict], outcome: str | None = None, total: int | None = None) -> dict:
    """One creature's roll for the roll window. The total is the d20 plus every tile and bonus die.
    Flat bonuses from effects join the tiles."""
    tiles = tiles + roll.get("flat", [])
    total = roll["kept"] + sum(t["value"] for t in tiles) + sum(b["value"] for b in roll["bonus"]) if total is None else total
    return {"who": rec["id"], "name": rec["name"], "d20": roll["faces"], "kept": roll["faces"].index(roll["kept"]),
            "mode": roll["mode"], "mods": tiles, "bonus": roll["bonus"], "total": total, "outcome": outcome}


def roll_detail(kind: str, title: str, subtitle: str, rolls: list[dict], target: dict | None = None,
                damage: list[dict] | None = None) -> dict:
    """The roll window's data: what is rolled, the target number (only when the players may see it), each roll."""
    detail: dict = {"kind": kind, "title": title, "subtitle": subtitle, "rolls": rolls}
    if target:
        detail["target"] = target
    if damage:
        detail["damage"] = damage
    return detail


# -- state -------------------------------------------------------------------


def state_path(campaign_dir: Path) -> Path:
    return campaign_dir / "state.json"


def load_state(campaign_dir: Path) -> dict:
    return read_json(state_path(campaign_dir)) or {}


def save_state(campaign_dir: Path, state: dict) -> None:
    write_json(state_path(campaign_dir), state, indent=2)


def encounter(state: dict) -> dict:
    enc = state.get("active_encounter")
    if not enc or enc.get("type") != "combat":
        raise RulesError("no combat is running. Start one with: uv run dnd-cli encounter start goblin:3")
    return enc


# -- teams: who fights whom ------------------------------------------------------
# Every combatant is on a team. The player characters are `party`; the creatures the DM names are `hostile` unless the encounter says
# otherwise (`enc["teams"]`: id -> team). `party` and `hostile` are at war, and so are `neutral` and `hostile`; `party` and `neutral`
# are at peace until a feud (`enc["feuds"]`: pairs of ids or teams) is made, as when a player attacks a neutral.

PARTY, HOSTILE, NEUTRAL = "party", "hostile", "neutral"
WAR = {frozenset((PARTY, HOSTILE)), frozenset((NEUTRAL, HOSTILE))}


def team_of(state: dict, cid: str) -> str:
    enc = state.get("active_encounter") or {}
    return (enc.get("teams") or {}).get(cid) or (HOSTILE if cid in (enc.get("monsters") or {}) else PARTY)


def _war(state: dict, a: str, b: str, labels_a: set[str], labels_b: set[str]) -> bool:
    """Are two teams (`a`, `b`) at war, or is there a feud between a label of one side (its id or its team) and a label of the other?"""
    if a == b:
        return False
    if frozenset((a, b)) in WAR:
        return True
    feuds = (state.get("active_encounter") or {}).get("feuds") or []
    return any((x in labels_a and y in labels_b) or (x in labels_b and y in labels_a) for x, y in feuds)


def enemies(state: dict, a: str, b: str) -> bool:
    """Are combatants `a` and `b` enemies?"""
    ta, tb = team_of(state, a), team_of(state, b)
    return _war(state, ta, tb, {a, ta}, {b, tb})


def feud(state: dict, attacker: str, target: str) -> bool:
    """`attacker` strikes `target`. When they are on different teams that are at peace, `target` is an enemy of the attacker's whole
    team from now on (one pair in `enc["feuds"]`; other members of the target's team are not drawn in). True when a feud was made."""
    enc = state.get("active_encounter") or {}
    if enc.get("type") != "combat" or team_of(state, attacker) == team_of(state, target) or enemies(state, attacker, target):
        return False
    enc.setdefault("feuds", []).append([target, team_of(state, attacker)])
    return True


def hostile_to_party(state: dict, cid: str) -> bool:
    """Is `cid` an enemy of the player characters' team?"""
    t = team_of(state, cid)
    return _war(state, t, PARTY, {cid, t}, {PARTY})


def party(campaign_dir: Path, state: dict) -> list[str]:
    members = state.get("party_members") or [p.stem for p in sorted((campaign_dir / "characters").glob("*.json"))]
    return [m for m in members if character.character_path(campaign_dir, m).exists()]


# -- combatant records -------------------------------------------------------


def _feet(text: str | None, default: int = 30) -> int:
    m = re.match(r"\s*(\d+)", text or "")
    return int(m.group(1)) if m else default


def geometry(text: str, ranged_only: bool = False) -> dict:
    """How far an attack reaches, from its text: `reach 5 ft.` (melee) and `range 80/320 ft.` or `(range 150/600)` (ranged), in feet.

    A weapon with neither word is a melee weapon with reach 5. `ranged_only` is for ammunition weapons.
    """
    out = {}
    if m := re.search(r"reach (\d+) ft", text):
        out["reach_ft"] = int(m.group(1))
    if m := re.search(r"range (\d+)(?:/\d+)?", text):
        out["range_ft"] = int(m.group(1))
    if not out and not ranged_only:
        out["reach_ft"] = 5
    return out


def _mods(scores: dict) -> dict:
    return {a: dice.mod(scores.get(a, 10)) for a in ABILITIES}


def pc_record(sheet: dict, cid: str) -> dict:
    scores = sheet.get("ability_scores", {})
    mods = _mods(scores)
    attacks = []
    for w in sheet.get("weapons", []):
        props = " ".join(w.get("properties", []))
        reach = geometry(props, ranged_only="ammunition" in props)
        if "ammunition" not in props:
            reach["reach_ft"] = 10 if "reach" in props.split() else 5  # a thrown weapon is also a melee weapon
        attacks.append({"name": w["name"], "bonus": w.get("attack_bonus", 0), "equipped": bool(w.get("equipped")), **reach,
                        **({"thrown": True} if "thrown" in props.split() else {}),
                        "damage": [[w["damage"], w.get("damage_type", "")]] if w.get("damage") else []})
    # Bare fists, as in Baldur's Gate 3: 1 + Strength modifier, bludgeoning.
    attacks.append({"name": "Unarmed Strike", "bonus": mods["strength"] + sheet.get("proficiency_bonus", 2), "reach_ft": 5,
                    "damage": [[f"1{dice.signed(mods['strength'])}", "bludgeoning"]], "plain": True})
    spell = sheet.get("spellcasting") or {}
    if "spell_attack_bonus" in spell:
        attacks.append({"name": "spell", "bonus": spell["spell_attack_bonus"], "damage": [], "plain": True})
    return {
        "id": cid, "kind": "pc", "name": sheet.get("name", cid), "ac": sheet.get("armor_class", 10),
        "hp": sheet["hp"], "mods": mods,
        "saves": {a: sheet.get("saving_throws", {}).get(a, mods[a]) for a in ABILITIES},
        "skills": {s: sheet.get("skills", {}).get(s, mods[a]) for s, a in SKILLS.items()},
        "attacks": attacks, "init": sheet.get("initiative", mods["dexterity"]), "speed_ft": sheet.get("speed", 30),
        "spell_dc": spell.get("spell_save_dc"), "resist": [], "immune": [], "vuln": [],
        "prof": sheet.get("proficiency_bonus"),
    }


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
    mods = _mods(data)
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
    mods = _mods(data.get("ability_scores", {}))
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
        rec = pc_record(character.load(campaign_dir, cid), cid)
        fx = effects.defense(campaign_dir, cid)  # worn gear: Armor Class and resistances
        rec["ac"] += fx["ac"]
        rec["resist"] = rec["resist"] + fx["resist"]
        rec["reduce"] = fx["reduce"]
        return rec
    known = list((enc.get("monsters") or {})) + party(campaign_dir, state)
    raise RulesError(f"no combatant {cid!r}. Known: {', '.join(known) or 'none'}.")


def _conditions(state: dict, cid: str) -> list[dict]:
    return ((state.get("active_encounter") or {}).get("conditions") or {}).get(cid, [])


# -- damage and healing ------------------------------------------------------


def _scaled(rec: dict, amount: int, dtype: str) -> tuple[int, str]:
    """Damage after immunity, resistance, vulnerability (simple type matches only)."""
    if not dtype:
        return amount, ""
    plain = lambda lst: any(dtype in s.lower() and "nonmagical" not in s.lower() for s in lst)  # noqa: E731
    if plain(rec.get("immune", [])):
        return 0, f" (immune to {dtype})"
    if plain(rec.get("resist", [])):
        return amount // 2, f" (resists {dtype})"
    if plain(rec.get("vuln", [])):
        return amount * 2, f" (vulnerable to {dtype})"
    return amount, ""


def damage(campaign_dir: Path, state: dict, cid: str, amount: int, dtype: str = "", crit: bool = False) -> str:
    """Apply damage; returns the DM line. PCs are saved to their sheet; creatures stay in the encounter."""
    rec = combatant(campaign_dir, state, cid)
    amount, note = _scaled(rec, amount, dtype.lower())
    if amount and (cut := rec.get("reduce", {}).get(dtype.lower(), 0) + rec.get("reduce", {}).get("all", 0)):
        amount, note = max(0, amount - cut), note + f" (gear absorbs {min(cut, amount)})"
    concentrating = any(c["condition"] == "concentrating" for c in _conditions(state, cid))
    conc = f"; concentration save DC {max(10, amount // 2)}" if concentrating and amount else ""
    if rec["kind"] == "pc":
        sheet = character.load(campaign_dir, cid)
        was_down = sheet["hp"]["current"] == 0
        report = character.apply_damage(sheet, amount)
        line = f"{cid} takes {amount}{note}: HP {report['hp_current']}/{report['hp_max']}"
        if was_down and amount:
            saves = sheet.setdefault("death_saves", {"successes": 0, "failures": 0})
            saves["failures"] = min(3, saves.get("failures", 0) + (2 if crit else 1))
            line += f"; death save failures {saves['failures']}/3" + (" DEAD" if saves["failures"] >= 3 else "")
        elif report["dropped_to_zero"]:
            line += " DOWN (unconscious; death saves start)"
        character.save(campaign_dir, cid, sheet)
        return line + conc
    hp = rec["hp"]
    hp["current"] = max(0, hp["current"] - amount)
    return f"{cid} takes {amount}{note}: HP {hp['current']}/{hp['max']}" + (" DOWN" if hp["current"] == 0 else "") + conc


def heal(campaign_dir: Path, state: dict, cid: str, amount: int) -> str:
    rec = combatant(campaign_dir, state, cid)
    if rec["kind"] == "pc":
        sheet = character.load(campaign_dir, cid)
        report = character.heal(sheet, amount)
        if amount > 0:
            sheet["death_saves"] = {"successes": 0, "failures": 0}
        character.save(campaign_dir, cid, sheet)
        return f"{cid} heals {amount}: HP {report['hp_current']}/{report['hp_max']}"
    hp = rec["hp"]
    hp["current"] = min(hp["max"], hp["current"] + amount)
    return f"{cid} heals {amount}: HP {hp['current']}/{hp['max']}"


# -- encounter ---------------------------------------------------------------

# What an NPC with no stat block fights as: a whole word in its role or type picks an SRD monster, longest phrase first;
# only if those name none, the same words are looked for in the rest of its file. The default is a commoner.
ROLE_MONSTERS = (("high priest", "priest"), ("priest", "acolyte"), ("cleric", "acolyte"), ("acolyte", "acolyte"),
                 ("guard", "guard"), ("soldier", "guard"), ("captain", "veteran"), ("noble", "noble"),
                 ("bandit", "bandit"), ("thief", "bandit"), ("smuggler", "bandit"), ("assassin", "assassin"),
                 ("mage", "mage"), ("wizard", "mage"), ("cultist", "cultist"), ("scout", "scout"), ("spy", "spy"))


def _monster_in(text: str) -> str | None:
    """The SRD monster for the whole word or phrase of the table found in `text`; the longest phrase wins, then table order."""
    text = text.lower()
    found = [(word, m) for word, m in ROLE_MONSTERS if re.search(rf"\b{re.escape(word)}\b", text)]
    return max(found, key=lambda wm: len(wm[0]))[1] if found else None


def foe_index(campaign_dir: Path, actor_id: str) -> str:
    """The NPC file or the SRD monster index a stage actor fights as."""
    return _parse_spec(foe_spec(campaign_dir, actor_id)[0])[1]


def stage_record(campaign_dir: Path, actor_id: str) -> dict:
    """The combat record of a stage actor, under its own id."""
    return _record(campaign_dir, foe_index(campaign_dir, actor_id), actor_id)


def foe_spec(campaign_dir: Path, actor_id: str) -> tuple[str, str | None]:
    """The `encounter start` spec for a creature on the stage, and a note when the stat block is a guess.

    An NPC file with hp and armor_class is used as it is. Else the id is a monster name (`goblin#2` is a goblin),
    or an NPC whose role picks an SRD monster (`orlo-tin=acolyte`).
    """
    base = actor_id.split("#")[0]
    npc = read_json(npc_path(campaign_dir, base))
    if not npc or ("hp" in npc and "armor_class" in npc):
        return base, None
    said = lambda keys: " ".join(str(npc.get(k, "")) for k in keys)  # noqa: E731
    index = _monster_in(said(("role", "type"))) or _monster_in(said(("name", "personality", "motivation"))) or "commoner"
    return f"{base}={index}", f"{npc.get('name', base)} has no stat block here, so the stage used the SRD {index.replace('-', ' ')}."



def _parse_spec(spec: str) -> tuple[str, str, int]:
    """`goblin:3`, `boss=bugbear`, `cassara-whitmore` -> (id base, source index, count)."""
    m = re.fullmatch(r"(?:([a-z0-9][a-z0-9_-]*)=)?([a-z0-9][a-z0-9_-]*)(?::(\d+))?", spec.strip().lower())
    if not m:
        raise RulesError(f"{spec!r}: write a monster as goblin, goblin:3 or boss=bugbear.")
    index = m.group(2)
    return m.group(1) or index, index, int(m.group(3) or 1)


def _new_ids(base: str, count: int, taken: set[str], prefer: Sequence[str] = ()) -> list[str]:
    """Ids for `count` new creatures of a kind. `prefer`: ids of creatures of that kind already on the stage; they are taken first, so a
    `goblin#3` on the stage is the goblin the fight uses."""
    out = [p for p in prefer if p.startswith(base + "#") and p not in taken][:count]
    if len(out) == count:
        return out
    if count == 1 and base not in taken and not any(t.startswith(base + "#") for t in taken):
        return [base]
    n = 1
    while len(out) < count:
        if f"{base}#{n}" not in taken and f"{base}#{n}" not in out:
            out.append(f"{base}#{n}")
        n += 1
    return out


def _record(campaign_dir: Path, index: str, cid: str) -> dict:
    """The combat record of an NPC with a stat block, or of an SRD monster, under the id `cid`."""
    npc = read_json(npc_path(campaign_dir, index))
    if npc and "hp" in npc and "armor_class" in npc:
        return npc_record(npc, cid)
    data, error, _ = api_get(f"monsters/{index}")
    if error or not data or "hit_points" not in data:
        raise RulesError(f"no monster {index!r} in the 5e API, and no NPC file with stats. "
                         f"Find the index with: uv run dnd-cli search monsters --name {index.split('-')[0]}")
    return monster_record(data, cid)


def _creatures(campaign_dir: Path, specs: list[str], taken: set[str], prefer: Sequence[str] = ()) -> list[dict]:
    out = []
    for spec in specs:
        base, index, count = _parse_spec(spec)
        npc = read_json(npc_path(campaign_dir, index))
        if npc and "hp" in npc and "armor_class" in npc:
            out.append(_record(campaign_dir, index, index))
            continue
        for cid in _new_ids(base, count, taken, prefer):
            out.append(_record(campaign_dir, index, cid))
            taken.add(cid)
    return out


TEAM_OF_SIDE = {"ally": PARTY, "neutral": NEUTRAL, "hostile": HOSTILE}  # the stage sides that fight; a bystander does not, until provoked


def _stage_fighters(campaign_dir: Path, stage: dict | None, taken: set[str], skipped: list[str] | None = None) -> list[tuple[dict, str]]:
    """The actors of the stage that fight (green companions, yellow neutrals, red creatures), each with its team, as combat records
    under their stage ids. A player character is not one of them, and neither is an actor that has no stat block the stage can find."""
    out = []
    for aid, a in (stage or {}).items():
        team = TEAM_OF_SIDE.get(a.get("side"))
        if not team or aid in taken or a.get("down") or character.character_path(campaign_dir, aid).exists():
            continue
        try:
            rec = stage_record(campaign_dir, aid)
        except RulesError as err:
            if skipped is not None:
                skipped.append(f"{aid} is not in the fight: {err}")
            continue
        out.append((rec, team))
    return out


def _order_lines(enc: dict) -> str:
    return "Order: " + ", ".join(f"{o['name']} {o['initiative']}" for o in enc["initiative_order"])


def start(campaign_dir: Path, state: dict, specs: list[str], pcs: list[str] | None, rng=None, stage: dict | None = None) -> list[str]:
    """Roll initiative for the party and the creatures; write active_encounter. `stage`: the actors on the stage (id -> {"side"}); those
    that fight (see `_stage_fighters`) join too, whatever the specs say."""
    rng = rng or random
    if (state.get("active_encounter") or {}).get("type") == "combat":
        raise RulesError("a combat is already running. Add creatures with `encounter add`, or end it first.")
    pcs = pcs if pcs is not None else party(campaign_dir, state)
    enc = {"type": "combat", "round": 1, "participants": [], "initiative_order": [],
           "current_turn": None, "conditions": {}, "monsters": {}}
    state["active_encounter"] = enc
    lines = _join(campaign_dir, state, pcs, specs, rng, stage)
    enc["current_turn"] = enc["initiative_order"][0]["name"] if enc["initiative_order"] else None
    _initiative_feed(campaign_dir, state, enc)
    return lines + [_order_lines(enc), f"Round 1: {enc['current_turn']}'s turn."]


def _initiative_feed(campaign_dir: Path, state: dict, enc: dict) -> None:
    """Tell the stage's log the turn order, by display name."""
    names = []
    for o in enc["initiative_order"]:
        name = combatant(campaign_dir, state, o["name"])["name"]
        names.append(f"{name}{' ' + o['name'].split('#')[1] if '#' in o['name'] else ''} {o['initiative']}")
    stage_feed("Initiative: " + ", ".join(names))


def _join(campaign_dir: Path, state: dict, pcs: list[str], specs: list[str], rng, stage: dict | None = None) -> list[str]:
    enc = state["active_encounter"]
    entrants = [(combatant(campaign_dir, state, p), None) for p in pcs]
    prefer = [a for a, v in (stage or {}).items() if v.get("side") == "hostile"]  # the creatures the DM names take the ids they have on the stage
    entrants += [(r, None) for r in _creatures(campaign_dir, specs, set(enc["participants"]), prefer)]
    skipped: list[str] = []
    entrants += _stage_fighters(campaign_dir, stage, set(enc["participants"]) | {r["id"] for r, _ in entrants}, skipped)
    return _enroll(state, entrants, rng) + skipped


def _enroll(state: dict, entrants: list[tuple[dict, str | None]], rng) -> list[str]:
    """Put combatants in the encounter: initiative, team, and a line about each creature. `entrants`: (record, team or None)."""
    enc = state["active_encounter"]
    lines = []
    for rec, team in entrants:
        if rec["id"] in enc["participants"]:
            continue
        if team:
            enc.setdefault("teams", {})[rec["id"]] = team
        if rec["kind"] != "pc":
            enc["monsters"][rec["id"]] = rec
        kept, _ = dice.d20(rng)
        init = kept + rec["init"]
        enc["participants"].append(rec["id"])
        # Ties: the higher initiative bonus first.
        enc["initiative_order"].append({"name": rec["id"], "initiative": init, "bonus": rec["init"]})
        if rec["kind"] != "pc":
            lines.append(f"{rec['id']}: {rec['name']}, AC {rec['ac']}, HP {rec['hp']['current']}"
                         + "".join(f", {k} {', '.join(v)}" for k, v in (("resists", rec["resist"]), ("immune", rec["immune"]),
                                                                         ("vulnerable", rec["vuln"])) if v))
    enc["initiative_order"].sort(key=lambda o: (o["initiative"], o["bonus"]), reverse=True)
    return lines


def provoke(campaign_dir: Path, state: dict, target: str, attacker: str, rng=None) -> list[str]:
    """A bystander is attacked: it joins the fight on a team of its own (`neutral`) against the attacker's team, and rolls initiative.
    Result: the lines for the DM. Raises RulesError when it has no stat block the stage can use."""
    enc = encounter(state)
    lines: list[str] = []
    if target not in enc["participants"]:
        rec = stage_record(campaign_dir, target)
        lines = _enroll(state, [(rec, NEUTRAL)], rng or random)
        _initiative_feed(campaign_dir, state, enc)
    feud(state, attacker, target)
    return lines + [f"{target} is drawn into the fight against {attacker}'s side."]


def add(campaign_dir: Path, state: dict, specs: list[str], rng=None) -> list[str]:
    enc = encounter(state)
    lines = _join(campaign_dir, state, [], specs, rng or random)
    _initiative_feed(campaign_dir, state, enc)
    return lines + [_order_lines(enc)]


def _down(campaign_dir: Path, state: dict, cid: str) -> bool:
    rec = combatant(campaign_dir, state, cid)
    return rec["kind"] != "pc" and rec["hp"]["current"] == 0


def next_turn(campaign_dir: Path, state: dict) -> list[str]:
    """Move to the next living combatant; count down conditions on its turn; say what is due."""
    enc = encounter(state)
    order = [o["name"] for o in enc["initiative_order"]]
    alive = [c for c in order if not _down(campaign_dir, state, c)]
    if not alive:
        raise RulesError("no combatant is left standing. End the encounter.")
    i = order.index(enc["current_turn"]) if enc["current_turn"] in order else -1
    lines = []
    while True:
        i += 1
        if i >= len(order):
            i = 0
            enc["round"] = enc.get("round", 1) + 1
        if order[i] in alive:
            break
    cid = enc["current_turn"] = order[i]
    enc.pop("pending_smite", None)  # a smite not declared by the end of the turn is gone
    enc.setdefault("resources", {})[cid] = {}  # a new turn: action, bonus action and reaction are back
    kept = []
    for c in enc.get("conditions", {}).get(cid, []):
        if "rounds" in c:
            c["rounds"] -= 1
            if c["rounds"] <= 0:
                lines.append(f"{cid}: {c['condition']} ends.")
                continue
        if c.get("save_dc"):
            lines.append(f"{cid}: {c['condition']} — save {c['save_type'][:3].upper()} DC {c['save_dc']} at the end of the turn "
                         f"(uv run dnd-cli save {cid} {c['save_type'][:3]} --dc {c['save_dc']}).")
        kept.append(c)
    enc.setdefault("conditions", {})[cid] = kept
    rec = combatant(campaign_dir, state, cid)
    turn = f"Round {enc['round']}: {cid}'s turn ({rec['name']}, HP {rec['hp']['current']}/{rec['hp']['max']})."
    if rec["kind"] == "pc" and rec["hp"]["current"] == 0:
        turn += f" At 0 HP: roll a death save (uv run dnd-cli check {cid} death)."
    return [turn] + lines


def _catch_up(campaign_dir: Path, state: dict, cid: str) -> list[str]:
    """An attacker acts on its own turn: move the tracker there if `encounter next` was skipped."""
    enc = (state.get("active_encounter") or {})
    if enc.get("type") != "combat" or cid not in enc.get("participants", []) or enc.get("current_turn") == cid:
        return []
    lines: list[str] = []
    for _ in range(len(enc["initiative_order"])):
        lines += [ln for ln in next_turn(campaign_dir, state) if not ln.startswith("Round ")]
        if enc["current_turn"] == cid:
            return lines + [f"(turn moved to {cid}, round {enc['round']})"]
    return lines


TURN_KINDS = ("action", "bonus", "reaction")
# What a creature does on its turn and what it leaves behind. `rounds=1` ends when its next turn starts.
STANCES = {"dodging": "Dodge", "dashing": "Dash", "disengaged": "Disengage", "helping": "Help", "hidden": "Hide"}


def spend_turn(state: dict, cid: str, kind: str, used: bool = True, quiet: bool = False) -> None:
    """Mark an action, bonus action or reaction as used (or free) for a combatant of the running combat.

    `quiet` ignores a creature outside the combat (a DM attack with no tracker running).
    """
    if quiet and not in_combat(state, cid):
        return
    enc = encounter(state)
    if kind not in TURN_KINDS or cid not in enc["participants"]:
        raise RulesError(f"use one of {', '.join(TURN_KINDS)} for a creature in this combat.")
    enc.setdefault("resources", {}).setdefault(cid, {})[kind] = bool(used)


def in_combat(state: dict, cid: str) -> bool:
    enc = state.get("active_encounter") or {}
    return enc.get("type") == "combat" and cid in enc.get("participants", [])


def turn_used(state: dict, cid: str) -> dict:
    spent = ((state.get("active_encounter") or {}).get("resources") or {}).get(cid, {}) if in_combat(state, cid) else {}
    return {k: bool(spent.get(k)) for k in TURN_KINDS}


def has_condition(state: dict, cid: str, name: str) -> bool:
    return any(c["condition"] == name for c in _conditions(state, cid))


def end_turn(campaign_dir: Path, state: dict, cid: str) -> list[str]:
    """A creature ends its own turn: refuse if it is not its turn, then move on like `encounter next`."""
    enc = encounter(state)
    if enc.get("current_turn") != cid:
        raise RulesError(f"it is {enc.get('current_turn')}'s turn, not {cid}'s.")
    return next_turn(campaign_dir, state)


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


def condition(state: dict, cid: str, op: str, name: str, rounds: int | None = None,
              save: str | None = None) -> str:
    enc = encounter(state)
    if cid not in enc["participants"]:
        raise RulesError(f"{cid!r} is not in this combat. In it: {', '.join(enc['participants'])}.")
    conds = enc.setdefault("conditions", {}).setdefault(cid, [])
    name = name.lower()
    if op == "remove":
        enc["conditions"][cid] = [c for c in conds if c["condition"] != name]
        return f"{cid}: {name} removed."
    entry: dict = {"condition": name}
    if rounds:
        entry["rounds"] = rounds
    if save:
        abil, _, dc = save.partition(":")
        entry["save_type"], entry["save_dc"] = ability(abil), int(dc)
    enc["conditions"][cid] = [c for c in conds if c["condition"] != name] + [entry]
    extra = (f", {rounds} rounds" if rounds else "") + (f", save {save.upper()} each turn" if save else "")
    return f"{cid}: {name}{extra}."


def status(campaign_dir: Path, state: dict) -> list[str]:
    enc = encounter(state)
    lines = [f"Round {enc.get('round', 1)}, {enc['current_turn']}'s turn."]
    for o in enc["initiative_order"]:
        rec = combatant(campaign_dir, state, o["name"])
        conds = ", ".join(c["condition"] + (f" {c['rounds']}r" if "rounds" in c else "")
                          for c in enc.get("conditions", {}).get(o["name"], []))
        mark = ">" if o["name"] == enc["current_turn"] else " "
        lines.append(f"{mark} {o['initiative']:>2} {o['name']}: HP {rec['hp']['current']}/{rec['hp']['max']}, AC {rec['ac']}"
                     + (f", {conds}" if conds else "") + (" DOWN" if rec["hp"]["current"] == 0 else ""))
    return lines


def end(campaign_dir: Path, state: dict, award_xp: bool = True, resolved: list[str] | None = None) -> list[str]:
    """Split the XP of defeated creatures among the party; write NPC HP back; clear the encounter.

    A creature in `resolved` (fled, yielded, talked down) counts as beaten without a kill."""
    enc = encounter(state)
    for cid in resolved or []:
        if cid not in enc["monsters"]:
            raise RulesError(f"--resolved: {cid!r} is not a creature of this fight. Creatures: {', '.join(enc['monsters']) or 'none'}.")
    pcs = [p for p in enc["participants"] if p not in enc["monsters"]]
    lines = []
    for cid, rec in enc["monsters"].items():
        if rec["kind"] == "npc":
            path = npc_path(campaign_dir, cid)
            npc = read_json(path)
            if npc is not None:
                npc["hp"] = {**npc.get("hp", {}), "current": rec["hp"]["current"]}
                write_json(path, npc, indent=2)
    xp = sum(r.get("xp", 0) for cid, r in enc["monsters"].items()
             if hostile_to_party(state, cid) and (r["hp"]["current"] == 0 or cid in (resolved or [])))  # only the party's enemies give XP
    if award_xp and xp and pcs:
        lines += award(campaign_dir, pcs, xp // len(pcs))
        lines.insert(0, f"Defeated foes give {xp} XP: {xp // len(pcs)} each.")
    state["active_encounter"] = None
    return lines + ["The combat is over."]


def award(campaign_dir: Path, pcs: list[str], each: int) -> list[str]:
    lines = []
    for p in pcs:
        sheet = character.load(campaign_dir, p)
        sheet["experience_points"] = sheet.get("experience_points", 0) + each
        character.save(campaign_dir, p, sheet)
        ready = level_for_xp(sheet["experience_points"]) > sheet["level"]
        lines.append(f"{p}: {sheet['experience_points']} XP" + (" — LEVEL UP READY (uv run dnd-cli character level-up "
                                                               f"{p})" if ready else ""))
    return lines


# -- attacks, saves, checks --------------------------------------------------


def _find_attack(rec: dict, name: str) -> dict:
    wanted = name.lower()
    for a in rec["attacks"]:
        if a["name"].lower() == wanted:
            return a
    for a in rec["attacks"]:
        if wanted in a["name"].lower():
            return a
    names = ", ".join(a["name"] for a in rec["attacks"]) or "none"
    raise RulesError(f"{rec['id']} has no attack {name!r}. Attacks: {names}.")


def attack(campaign_dir: Path, state: dict, attacker: str, weapon: str, target: str, adv: bool = False,
           dis: bool = False, damage_expr: str | None = None, damage_type: str = "", bonus: int = 0,
           secret: bool = False, rng=None, skip=(), cost: str | None = "action", catch_up: bool = True,
           smite: int | None = None, melee: bool | None = None) -> list[str]:
    """One attack roll against AC; on a hit, roll and apply the damage. Crits double the dice.

    `smite` is a spell slot level a paladin spends on a hit for Divine Smite (a melee weapon attack only). Without it,
    a melee hit that the paladin could smite leaves `pending_smite` in the encounter for the stage to offer.
    `melee` says whether this is a melee attack; by default a weapon with a reach is.

    The attack uses the attacker's `cost` (action, bonus or reaction; None for a free attack). A multiattack
    is several attacks for one action. A dodging target gives disadvantage; a hidden attacker gets
    advantage and is seen afterwards.
    """
    rng = rng or random
    a_rec = combatant(campaign_dir, state, attacker)
    t_rec = combatant(campaign_dir, state, target)
    feud(state, attacker, target)
    if weapon.lower() == "improvised" and damage_expr:
        act = {"name": "improvised", "bonus": 0, "damage": [], "plain": True}  # a thrown item or an improvised weapon: the to-hit is all in `bonus`
    else:
        act = _find_attack(a_rec, weapon)
    if "dc" in act:
        abil, dc, _ = act["dc"]
        raise RulesError(f"{act['name']} is a saving throw, not an attack roll: "
                         f"uv run dnd-cli save <targets> {abil} --from {attacker}:{act['name'].lower().replace(' ', '-')}")
    parts = [[damage_expr, damage_type]] if damage_expr else act["damage"]
    if not parts:
        raise RulesError(f"{act['name']} has no damage on record; give it with --damage 1d10 --type fire.")
    if melee is None:
        melee = "reach_ft" in act and not act.get("thrown")  # a thrown weapon is ranged unless the board says it is a melee attack
    if smite is not None:
        if not melee:
            raise RulesError("Divine Smite needs a melee weapon attack.")
        smite_check(campaign_dir, attacker, smite)
    if in_combat(state, attacker):
        encounter(state).pop("pending_smite", None)
    # `catch_up` False: a reaction happens on someone else's turn, so the tracker must not move to the attacker.
    turn_lines = _catch_up(campaign_dir, state, attacker) if catch_up else []
    if cost:
        spend_turn(state, attacker, cost, quiet=True)
    if has_condition(state, target, "dodging"):
        dis = True
    if has_condition(state, attacker, "hidden"):
        adv = True
        condition(state, attacker, "remove", "hidden")
    r = _d20(campaign_dir, attacker, "attack", adv, dis, rng, skip)
    kept = r["kept"]
    # Weapon gear (a +1 sword, Keen, of Flame) touches weapon attacks only, not Unarmed Strike, spells or throws.
    wfx = effects.NO_WEAPON if act.get("plain") else effects.weapon(campaign_dir, attacker, str(t_rec.get("ctype", "")), act["name"])
    r["flat"] = r["flat"] + wfx["hit"]
    tiles = [{"label": "Attack Bonus", "value": act["bonus"]}] + ([{"label": "Bonus", "value": bonus}] if bonus else [])
    entry = _entry(a_rec, r, tiles)
    to_hit = entry["total"]
    fumble = kept == 1
    hit = kept == 20 or (not fumble and to_hit >= t_rec["ac"])
    crit = hit and kept >= wfx["crit"]  # a natural 20 always hits; a lower crit range (Keen) crits only when it hits
    entry["outcome"] = "crit" if crit else "fumble" if fumble else "hit" if hit else "miss"
    groups = _d20_groups(r["faces"], kept) + [{"die": b["die"], "faces": b["faces"]} for b in r["bonus"]]
    # A monster's AC stays behind the screen; the AC of a player character is on their sheet.
    shown_ac = {"label": "Armor Class", "value": t_rec["ac"]} if t_rec["kind"] == "pc" else None

    def detail(dmg=None) -> dict:
        return roll_detail("attack", act["name"], f"Attack Roll · {a_rec['name']} → {t_rec['name']}", [entry], shown_ac, dmg)

    head = (f"{attacker} {act['name']} → {target}: {kept}{dice.signed(act['bonus'] + bonus)} = {to_hit}"
            f"{_fx_note(r)} vs AC {t_rec['ac']}")
    if not hit:
        stage_roll(f"{a_rec['name']}: {act['name']}", to_hit, groups, secret, detail())
        _secret_feed(secret, [t_rec], f"{a_rec['name']}'s {act['name']} misses {t_rec['name']}.")
        return turn_lines + [head + (" \u2014 natural 1, miss" if fumble else " \u2014 miss")]
    lines, total_text, shown_dmg = [], [], []
    if wfx["dmg"] and parts:
        parts = [[parts[0][0] + dice.signed(wfx["dmg"]), parts[0][1]]] + parts[1:]
    for expr, dtype in parts + wfx["extra"]:
        amount, dmg_groups = dice.roll(expr, rng, crit=crit)
        groups += dmg_groups
        total_text.append(f"{amount} {dtype}".strip())
        shown_dmg.append(_shown_damage(dtype, expr, dmg_groups, amount))
        lines.append(damage(campaign_dir, state, target, amount, dtype, crit=crit))
    stage_roll(f"{a_rec['name']}: {act['name']} — {' + '.join(total_text)} damage", to_hit, groups, secret,
               detail(shown_dmg))
    _secret_feed(secret, [t_rec], f"{a_rec['name']}'s {act['name']} hits {t_rec['name']}: " + "; ".join(lines))
    out = turn_lines + [head + (" — CRITICAL HIT" if crit else " — hit") + f", {' + '.join(total_text)} damage"] + lines
    if smite is not None:
        if combatant(campaign_dir, state, target)["hp"]["current"] <= 0:
            return out + [f"{attacker} does not smite: {target} is already down, no slot spent."]
        return out + smite_hit(campaign_dir, state, attacker, target, smite, crit, rng, secret)
    if melee and in_combat(state, attacker) and can_smite(campaign_dir, attacker) \
            and combatant(campaign_dir, state, target)["hp"]["current"] > 0:
        encounter(state)["pending_smite"] = {"by": attacker, "target": target, "crit": crit}
    return out


# -- Divine Smite --------------------------------------------------------------


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


def save(campaign_dir: Path, state: dict, targets: list[str], abil: str | None, dc: int | None,
         damage_expr: str | None = None, damage_type: str = "", half: bool = False, source: str | None = None,
         adv: bool = False, dis: bool = False, secret: bool = False, rng=None, hide_dc: bool = False,
         skip=()) -> list[str]:
    """A saving throw for each target; optional damage rolled once (half on a success with --half)."""
    rng = rng or random
    if source:
        who, _, act_name = source.partition(":")
        act = _find_attack(combatant(campaign_dir, state, who), act_name.replace("-", " "))
        if "dc" not in act:
            raise RulesError(f"{act['name']} is an attack roll: uv run dnd-cli attack {who} \"{act['name']}\" <target>")
        abil = abil or act["dc"][0]
        dc = dc or act["dc"][1]
        half = half or act["dc"][2] == "half"
        if not damage_expr and act["damage"]:
            damage_expr, damage_type = act["damage"][0]
    if not abil or not dc:
        raise RulesError("give the ability and --dc (or --from <creature>:<action>).")
    abil = ability(abil)
    # Every id first: a typo must not leave half the targets damaged (and a retry damage them twice).
    recs = [combatant(campaign_dir, state, t) for t in targets]
    amount = None
    if damage_expr:
        amount, dmg_groups = dice.roll(damage_expr, rng)
    lines, groups, entries, successes, total = [], [], [], 0, 0
    for t, rec in zip(targets, recs):
        r = _d20(campaign_dir, t, "save", adv, dis, rng, skip, (abil,))
        bonus = save_bonus(rec, abil)
        entry = _entry(rec, r, _tiles(rec, abil, bonus, f"{abil.capitalize()} Save"))
        total = entry["total"]
        ok = total >= dc
        entry["outcome"] = "success" if ok else "fail"
        entries.append(entry)
        successes += ok
        groups += _d20_groups(r["faces"], r["kept"]) + [{"die": b["die"], "faces": b["faces"]} for b in r["bonus"]]
        lines.append(f"{t} {abil[:3].upper()} save: {r['kept']}{dice.signed(bonus)} = {total}{_fx_note(r)} "
                     f"vs DC {dc} — {'success' if ok else 'fail'}")
        if amount is not None:
            taken = amount // 2 if ok and half else 0 if ok else amount
            if taken:
                lines.append(damage(campaign_dir, state, t, taken, damage_type))
    shown = f"{abil[:3].upper()} save" + (f", {amount} {damage_type} damage".rstrip() if amount is not None else "")
    shown_dmg = [_shown_damage(damage_type, damage_expr, dmg_groups, amount)] if amount is not None else None
    detail = roll_detail("save", f"{abil.capitalize()} Saving Throw", "Half damage on a success" if half and amount else "",
                         entries, None if hide_dc else {"label": "Difficulty Class", "value": dc}, shown_dmg)
    # One target: its save total. Several: how many succeeded.
    stage_roll(shown, total if len(targets) == 1 else successes, groups + (dmg_groups if amount is not None else []),
               secret, detail)
    if hurt := [ln for ln in lines if " takes " in ln]:  # not the save lines: they show a hidden DC
        _secret_feed(secret, recs, "; ".join(hurt))
    return lines


def check(campaign_dir: Path, state: dict, who: list[str], what: str, dc: int | None = None,
          adv: bool = False, dis: bool = False, passive: bool = False, secret: bool = False, rng=None,
          hide_dc: bool = False, skip=()) -> list[str]:
    """Skill or ability checks (or death saves). Several characters: a group check, half must pass."""
    rng = rng or random
    what = what.lower().replace("-", "_").replace(" ", "_")
    if what == "death":
        return [death_save(campaign_dir, state, c, rng, secret) for c in who]
    lines, passed, groups, entries, total = [], 0, [], [], 0
    for cid in who:
        rec = combatant(campaign_dir, state, cid)
        spec = check_spec(rec, what)
        bonus, label = spec["bonus"], spec["label"]
        if passive:
            lines.append(f"{cid} passive {label}: {10 + bonus + (5 if adv else 0) - (5 if dis else 0)}")
            continue
        r = _d20(campaign_dir, cid, spec["kind"], adv, dis, rng, skip, (spec["abil"], what if what in SKILLS else ""))
        entry = _entry(rec, r, spec["tiles"])
        total = entry["total"]
        ok = dc is not None and total >= dc
        entry["outcome"] = None if dc is None else "success" if ok else "fail"
        entries.append(entry)
        passed += ok
        groups += _d20_groups(r["faces"], r["kept"]) + [{"die": b["die"], "faces": b["faces"]} for b in r["bonus"]]
        lines.append(f"{cid} {label}: {r['kept']}{dice.signed(bonus)} = {total}{_fx_note(r)}"
                     + (f" vs DC {dc} — {'success' if ok else 'fail'}" if dc is not None else ""))
    if passive:
        return lines
    if dc is not None and len(who) > 1:
        lines.append(f"Group check: {passed}/{len(who)} succeed — {'SUCCESS' if passed * 2 >= len(who) else 'FAIL'}")
    shown = spec["title"] + (" check" if what in SKILLS else "")
    if len(who) == 1:
        shown += f" ({dice.signed(bonus)})"  # the legacy dice box shows only the d20; the modifier explains the total
    title, sub = spec["title"], spec["subtitle"]
    detail = roll_detail(spec["kind"], title, sub, entries, None if dc is None or hide_dc else {"label": "Difficulty Class", "value": dc})
    stage_roll(shown, total if len(who) == 1 else passed, groups, secret, detail)
    return lines


def death_save(campaign_dir: Path, state: dict, cid: str, rng=None, secret: bool = False) -> str:
    rng = rng or random
    sheet = character.load(campaign_dir, cid)
    if sheet["hp"]["current"] > 0:
        raise RulesError(f"{cid} is not at 0 HP.")
    saves = sheet.setdefault("death_saves", {"successes": 0, "failures": 0})
    kept, faces = dice.d20(rng)
    if kept == 20:
        sheet["hp"]["current"] = 1
        sheet["death_saves"] = {"successes": 0, "failures": 0}
        result = "natural 20: back up with 1 HP"
    else:
        key = "successes" if kept >= 10 else "failures"
        saves[key] = min(3, saves.get(key, 0) + (2 if kept == 1 else 1))
        result = (f"{'success' if kept >= 10 else 'failure'}; "
                  f"{saves.get('successes', 0)} successes, {saves.get('failures', 0)} failures")
        if saves["successes"] >= 3:
            result += " — STABLE"
        if saves["failures"] >= 3:
            result += " — DEAD"
    character.save(campaign_dir, cid, sheet)
    entry = _entry({"id": cid, "name": sheet.get("name", cid)}, {"kept": kept, "faces": faces, "mode": "normal", "bonus": []}, [],
                   "crit" if kept == 20 else "fumble" if kept == 1 else "success" if kept >= 10 else "fail")
    detail = roll_detail("death", "Death Saving Throw", sheet.get("name", cid), [entry], {"label": "Difficulty Class", "value": 10})
    stage_roll(f"{sheet.get('name', cid)}: death save", kept, _d20_groups(faces, kept), secret, detail)
    return f"{cid} death save: {kept} — {result}"
