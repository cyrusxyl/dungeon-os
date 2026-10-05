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
from pathlib import Path

from dnd_cli import character, dice, effects
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


def _d20_groups(faces: list[int], kept: int) -> list[dict]:
    """The kept d20 first (the legacy dice box colours a natural 20 or 1 from it)."""
    rest = list(faces)
    rest.remove(kept)
    return [{"die": "1d20", "faces": [kept]}] + ([{"die": "1d20 dropped", "faces": rest}] if rest else [])


def _d20(campaign_dir: Path, cid: str, kind: str, adv: bool, dis: bool, rng, skip=()) -> dict:
    """One d20 roll for a creature, with its active effects: advantage, disadvantage and bonus dice."""
    fx = effects.apply(campaign_dir, cid, kind, rng, skip)
    adv, dis = adv or fx["adv"], dis or fx["dis"]
    kept, faces = dice.d20(rng, adv, dis)
    mode = "normal" if len(faces) == 1 else "advantage" if adv else "disadvantage"
    return {"kept": kept, "faces": faces, "mode": mode, "bonus": fx["bonus"], "used": fx["used"]}


def _fx_note(roll: dict) -> str:
    """The effects a roll used, for the DM's output line: ` (advantage 17,5; guidance +3)`."""
    notes = []
    if roll["mode"] != "normal":
        notes.append(f"{roll['mode']} {','.join(map(str, roll['faces']))}")
    notes += [f"{b['label'].lower()} {dice.signed(b['value'])}" for b in roll["bonus"]]
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
    """One creature's roll for the roll window. The total is the d20 plus every tile and bonus die."""
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


def party(campaign_dir: Path, state: dict) -> list[str]:
    members = state.get("party_members") or [p.stem for p in sorted((campaign_dir / "characters").glob("*.json"))]
    return [m for m in members if character.character_path(campaign_dir, m).exists()]


# -- combatant records -------------------------------------------------------


def _mods(scores: dict) -> dict:
    return {a: dice.mod(scores.get(a, 10)) for a in ABILITIES}


def pc_record(sheet: dict, cid: str) -> dict:
    scores = sheet.get("ability_scores", {})
    mods = _mods(scores)
    attacks = [
        {"name": w["name"], "bonus": w.get("attack_bonus", 0),
         "damage": [[w["damage"], w.get("damage_type", "")]] if w.get("damage") else []}
        for w in sheet.get("weapons", [])
    ]
    # Bare fists, as in Baldur's Gate 3: 1 + Strength modifier, bludgeoning.
    attacks.append({"name": "Unarmed Strike", "bonus": mods["strength"] + sheet.get("proficiency_bonus", 2),
                    "damage": [[f"1{dice.signed(mods['strength'])}", "bludgeoning"]]})
    spell = sheet.get("spellcasting") or {}
    if "spell_attack_bonus" in spell:
        attacks.append({"name": "spell", "bonus": spell["spell_attack_bonus"], "damage": []})
    return {
        "id": cid, "kind": "pc", "name": sheet.get("name", cid), "ac": sheet.get("armor_class", 10),
        "hp": sheet["hp"], "mods": mods,
        "saves": {a: sheet.get("saving_throws", {}).get(a, mods[a]) for a in ABILITIES},
        "skills": {s: sheet.get("skills", {}).get(s, mods[a]) for s, a in SKILLS.items()},
        "attacks": attacks, "init": sheet.get("initiative", mods["dexterity"]),
        "spell_dc": spell.get("spell_save_dc"), "resist": [], "immune": [], "vuln": [],
        "prof": sheet.get("proficiency_bonus"),
    }


def monster_record(data: dict, cid: str) -> dict:
    """A compact copy of an API monster: only what play needs (no description text)."""
    mods = _mods(data)
    profs = {p["proficiency"]["index"]: p["value"] for p in data.get("proficiencies", [])}
    attacks = []
    for act in data.get("actions", []):
        damage = [[d["damage_dice"], d.get("damage_type", {}).get("name", "").lower()]
                  for d in act.get("damage", []) if d.get("damage_dice")]
        entry = {"name": act["name"], "damage": damage}
        if "attack_bonus" in act:
            entry["bonus"] = act["attack_bonus"]
        elif act.get("dc"):
            dc = act["dc"]
            entry["dc"] = [dc["dc_type"]["index"], dc["dc_value"], dc.get("success_type", "none")]
        else:
            continue  # Multiattack and abilities with no roll: the DM narrates them.
        attacks.append(entry)
    ac = data.get("armor_class", [{}])
    return {
        "id": cid, "kind": "monster", "index": data.get("index"), "name": data.get("name", cid),
        "ac": ac[0].get("value", 10) if isinstance(ac, list) else ac,
        "hp": {"current": data.get("hit_points", 1), "max": data.get("hit_points", 1)},
        "mods": mods,
        # Only proficient saves and skills: the rest is the ability modifier (see bonus()).
        "saves": {a: profs[f"saving-throw-{a[:3]}"] for a in ABILITIES if f"saving-throw-{a[:3]}" in profs},
        "skills": {s: profs[f"skill-{s.replace('_', '-')}"] for s in SKILLS if f"skill-{s.replace('_', '-')}" in profs},
        "attacks": attacks, "init": mods["dexterity"], "xp": data.get("xp", 0),
        "resist": data.get("damage_resistances", []), "immune": data.get("damage_immunities", []),
        "vuln": data.get("damage_vulnerabilities", []),
    }


def npc_record(data: dict, cid: str) -> dict:
    mods = _mods(data.get("ability_scores", {}))
    attacks = []
    for act in data.get("actions", []):
        if "attack_bonus" in act:
            attacks.append({"name": act["name"], "bonus": act["attack_bonus"],
                            "damage": [[act["damage"], ""]] if act.get("damage") else []})
    hp = data["hp"]
    return {
        "id": cid, "kind": "npc", "name": data.get("name", cid), "ac": data.get("armor_class", 10),
        "hp": {"current": hp.get("current", hp.get("max", 1)), "max": hp.get("max", 1)},
        "mods": mods, "saves": {}, "skills": {},
        "attacks": attacks, "init": mods["dexterity"], "xp": 0, "resist": [], "immune": [], "vuln": [],
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
        return pc_record(character.load(campaign_dir, cid), cid)
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


def _parse_spec(spec: str) -> tuple[str, str, int]:
    """`goblin:3`, `boss=bugbear`, `cassara-whitmore` -> (id base, source index, count)."""
    m = re.fullmatch(r"(?:([a-z0-9][a-z0-9_-]*)=)?([a-z0-9][a-z0-9_-]*)(?::(\d+))?", spec.strip().lower())
    if not m:
        raise RulesError(f"{spec!r}: write a monster as goblin, goblin:3 or boss=bugbear.")
    index = m.group(2)
    return m.group(1) or index, index, int(m.group(3) or 1)


def _new_ids(base: str, count: int, taken: set[str]) -> list[str]:
    if count == 1 and base not in taken and not any(t.startswith(base + "#") for t in taken):
        return [base]
    n, out = 1, []
    while len(out) < count:
        if f"{base}#{n}" not in taken:
            out.append(f"{base}#{n}")
        n += 1
    return out


def _creatures(campaign_dir: Path, specs: list[str], taken: set[str]) -> list[dict]:
    out = []
    for spec in specs:
        base, index, count = _parse_spec(spec)
        npc = read_json(npc_path(campaign_dir, index))
        if npc and "hp" in npc and "armor_class" in npc:
            out.append(npc_record(npc, index))
            continue
        data, error, _ = api_get(f"monsters/{index}")
        if error or not data or "hit_points" not in data:
            raise RulesError(f"no monster {index!r} in the 5e API, and no NPC file with stats. "
                             f"Find the index with: uv run dnd-cli search monsters --name {index.split('-')[0]}")
        for cid in _new_ids(base, count, taken):
            out.append(monster_record(data, cid))
            taken.add(cid)
    return out


def _order_lines(enc: dict) -> str:
    return "Order: " + ", ".join(f"{o['name']} {o['initiative']}" for o in enc["initiative_order"])


def start(campaign_dir: Path, state: dict, specs: list[str], pcs: list[str] | None, rng=None) -> list[str]:
    """Roll initiative for the party and the creatures; write active_encounter."""
    rng = rng or random
    if (state.get("active_encounter") or {}).get("type") == "combat":
        raise RulesError("a combat is already running. Add creatures with `encounter add`, or end it first.")
    pcs = pcs if pcs is not None else party(campaign_dir, state)
    enc = {"type": "combat", "round": 1, "participants": [], "initiative_order": [],
           "current_turn": None, "conditions": {}, "monsters": {}}
    state["active_encounter"] = enc
    lines = _join(campaign_dir, state, pcs, specs, rng)
    enc["current_turn"] = enc["initiative_order"][0]["name"] if enc["initiative_order"] else None
    return lines + [_order_lines(enc), f"Round 1: {enc['current_turn']}'s turn."]


def _join(campaign_dir: Path, state: dict, pcs: list[str], specs: list[str], rng) -> list[str]:
    enc = state["active_encounter"]
    entrants = [combatant(campaign_dir, state, p) for p in pcs]
    entrants += _creatures(campaign_dir, specs, set(enc["participants"]))
    lines = []
    for rec in entrants:
        if rec["id"] in enc["participants"]:
            continue
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


def add(campaign_dir: Path, state: dict, specs: list[str], rng=None) -> list[str]:
    enc = encounter(state)
    lines = _join(campaign_dir, state, [], specs, rng or random)
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


def end(campaign_dir: Path, state: dict, award_xp: bool = True) -> list[str]:
    """Split the XP of defeated creatures among the party; write NPC HP back; clear the encounter."""
    enc = encounter(state)
    pcs = [p for p in enc["participants"] if p not in enc["monsters"]]
    lines = []
    for cid, rec in enc["monsters"].items():
        if rec["kind"] == "npc":
            path = npc_path(campaign_dir, cid)
            npc = read_json(path)
            if npc is not None:
                npc["hp"] = {**npc.get("hp", {}), "current": rec["hp"]["current"]}
                write_json(path, npc, indent=2)
    xp = sum(r.get("xp", 0) for r in enc["monsters"].values() if r["hp"]["current"] == 0)
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
           secret: bool = False, rng=None, skip=(), cost: str | None = "action") -> list[str]:
    """One attack roll against AC; on a hit, roll and apply the damage. Crits double the dice.

    The attack uses the attacker's `cost` (action, bonus or reaction; None for a free attack). A multiattack
    is several attacks for one action. A dodging target gives disadvantage; a hidden attacker gets
    advantage and is seen afterwards.
    """
    rng = rng or random
    a_rec = combatant(campaign_dir, state, attacker)
    t_rec = combatant(campaign_dir, state, target)
    act = _find_attack(a_rec, weapon)
    if "dc" in act:
        abil, dc, _ = act["dc"]
        raise RulesError(f"{act['name']} is a saving throw, not an attack roll: "
                         f"uv run dnd-cli save <targets> {abil} --from {attacker}:{act['name'].lower().replace(' ', '-')}")
    parts = [[damage_expr, damage_type]] if damage_expr else act["damage"]
    if not parts:
        raise RulesError(f"{act['name']} has no damage on record; give it with --damage 1d10 --type fire.")
    turn_lines = _catch_up(campaign_dir, state, attacker)
    if cost:
        spend_turn(state, attacker, cost, quiet=True)
    if has_condition(state, target, "dodging"):
        dis = True
    if has_condition(state, attacker, "hidden"):
        adv = True
        condition(state, attacker, "remove", "hidden")
    r = _d20(campaign_dir, attacker, "attack", adv, dis, rng, skip)
    kept = r["kept"]
    tiles = [{"label": "Attack Bonus", "value": act["bonus"]}] + ([{"label": "Bonus", "value": bonus}] if bonus else [])
    entry = _entry(a_rec, r, tiles)
    to_hit = entry["total"]
    crit, fumble = kept == 20, kept == 1
    hit = crit or (not fumble and to_hit >= t_rec["ac"])
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
        return turn_lines + [head + (" — natural 1, miss" if fumble else " — miss")]
    lines, total_text, shown_dmg = [], [], []
    for expr, dtype in parts:
        amount, dmg_groups = dice.roll(expr, rng, crit=crit)
        groups += dmg_groups
        total_text.append(f"{amount} {dtype}".strip())
        shown_dmg.append({"type": dtype, "expr": expr, "faces": [f for g in dmg_groups for f in g["faces"]], "total": amount})
        lines.append(damage(campaign_dir, state, target, amount, dtype, crit=crit))
    stage_roll(f"{a_rec['name']}: {act['name']} — {' + '.join(total_text)} damage", to_hit, groups, secret,
               detail(shown_dmg))
    return turn_lines + [head + (" — CRITICAL HIT" if crit else " — hit") + f", {' + '.join(total_text)} damage"] + lines


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
        r = _d20(campaign_dir, t, "save", adv, dis, rng, skip)
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
    shown_dmg = ([{"type": damage_type, "expr": damage_expr, "faces": [f for g in dmg_groups for f in g["faces"]],
                   "total": amount}] if amount is not None else None)
    detail = roll_detail("save", f"{abil.capitalize()} Saving Throw", "Half damage on a success" if half and amount else "",
                         entries, None if hide_dc else {"label": "Difficulty Class", "value": dc}, shown_dmg)
    # One target: its save total. Several: how many succeeded.
    stage_roll(shown, total if len(targets) == 1 else successes, groups + (dmg_groups if amount is not None else []),
               secret, detail)
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
        r = _d20(campaign_dir, cid, spec["kind"], adv, dis, rng, skip)
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
