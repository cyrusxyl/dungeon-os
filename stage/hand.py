"""What a player character can do on the board: the hand.

Weapons, damage spells, the common actions (Dash, Disengage, Dodge, Help, Hide, Shove) and class features, as one list of
abilities in the format of dnd_cli/abilities.py, each with the reason it is off now. The player picks one; `act` runs it
with the rules of the board (stage/board.py). See combat-board.md, sections 3 and 5.
"""

from __future__ import annotations

import re
from pathlib import Path

from dnd_cli import abilities, actions, character, combat
from dnd_cli.api import api_get
from stage import arena, board, items

ICONS = {"attack": "sword", "spell_attack": "flame", "zone": "flame", "shove": "fist", "hide": "eye", "dash": "boot", "disengage": "boot",
         "dodge": "shield", "help": "spark", "heal": "heart", "pickup": "hand", "feature": "spark", "improvise": "spark"}


def odds(chance: float) -> str:
    """The players see no AC: a hit chance is only words."""
    return "good odds" if chance >= 0.65 else "even odds" if chance >= 0.35 else "poor odds"


def _spell_abilities(campaign_dir: Path, sheet: dict) -> list[dict]:
    sc = sheet.get("spellcasting") or {}
    slots = sc.get("spell_slots") or {}
    out = []
    for name in sc.get("spells_known", []):
        data, err, _ = api_get(f"spells/{re.sub(r'[^a-z0-9-]', '', name.lower().replace(' ', '-'))}")
        if err or not data:
            continue
        level = data.get("level", 0)
        slot = None if level == 0 else next((int(k) for k in sorted(slots, key=int) if int(k) >= level and slots[k].get("remaining", 0) > 0), None)
        ab = abilities.from_spell(data, slot=slot or level or None, caster_level=sheet.get("level", 1), dc=sc.get("spell_save_dc"),
                                  attack=sc.get("spell_attack_bonus"))
        if ab:
            out.append(ab | {"no_slot": level > 0 and slot is None, "source": "spell"})
    return out


def _target_info(campaign_dir: Path, state: dict, a: dict, cid: str, ab: dict, visible: set | None) -> list[dict]:
    """Each creature in sight, with whether this ability can reach it now (and why not), and the odds."""
    out = []
    here = board.pos(a, cid)
    for foe in board.standing_foes(campaign_dir, state, a):
        if visible is not None and board.pos(a, foe) not in visible:
            continue
        rec = combat.combatant(campaign_dir, state, foe)
        item = {"id": foe, "name": rec["name"], "dist_ft": arena.cheb(here, board.pos(a, foe)) * board.TILE_FT, "ok": True, "why": None}
        try:
            if ab["kind"] == "shove":
                if item["dist_ft"] > board.TILE_FT:
                    raise board.BoardError("Not next to you.")
            else:
                entry = ab["entry"] if ab["kind"] == "attack" else {"name": ab["name"], **ab["attack"]}
                check = board.attack_check(campaign_dir, state, a, cid, entry, foe)
                bonus = entry["bonus"] if ab["kind"] == "attack" else ab["attack"]["bonus"]
                chance = max(0.05, min(0.95, (21 - (rec["ac"] + arena.COVER_BONUS[check["cover"]] - bonus)) / 20))
                item["odds"] = odds(chance)
        except board.BoardError as e:
            item.update(ok=False, why=str(e))
        out.append(item)
    return out


def _spent(turn: dict, cost: str) -> str | None:
    """Why an action, bonus action or reaction cannot be paid now, or None (a free cost is always paid)."""
    return {"action": "The action is used.", "bonus": "The bonus action is used.", "reaction": "The reaction is used."}[cost] if turn.get(cost) else None


def listing(campaign_dir: Path, state: dict, a: dict, cid: str) -> list[dict]:
    """The hand of a character: every ability with `why` (the reason it is off, or None) and, for one that needs a target, `targets`."""
    sheet = character.load(campaign_dir, cid)
    rec = combat.pc_record(sheet, cid)
    turn = combat.turn_used(state, cid)
    mine_turn = state["active_encounter"].get("current_turn") == cid
    visible = board.visible_cells(campaign_dir, state, a)
    out: list[dict] = []

    def add(ab: dict, why: str | None, **extra) -> None:
        if not mine_turn:
            why = why or "Not your turn."
        ab = {**ab, "why": why, "icon": ICONS.get(ab["kind"], "spark"), **extra}
        if ab["kind"] in ("attack", "spell_attack", "shove"):
            ab["needs"] = "target"
            ab["targets"] = _target_info(campaign_dir, state, a, cid, ab, visible)
        elif ab["kind"] == "heal":
            ab["needs"] = "target"
            ab["targets"] = items.ally_targets(campaign_dir, state, a, cid)
        else:
            ab["needs"] = "aim" if ab["kind"] == "zone" else "text" if ab["kind"] == "improvise" else "none"
        out.append(ab)

    for entry in board.attack_rolls(rec):
        why = "The action is used." if turn["action"] else None
        reach = f"Reach {entry['reach_ft']} ft" if entry.get("reach_ft") else f"Range {entry['range_ft']} ft"
        add({"id": f"attack:{entry['name']}", "name": entry["name"], "cost": "action", "kind": "attack", "entry": entry,
             "text": reach, "stat": f"+{entry['bonus']} · " + " + ".join(e for e, _ in entry["damage"])}, why)
    for ab in _spell_abilities(campaign_dir, sheet):
        why = "The action is used." if ab["cost"] == "action" and turn["action"] else "The bonus action is used." if ab["cost"] == "bonus" and turn["bonus"] else None
        why = why or ("No spell slot left." if ab["no_slot"] else None)
        reach = (ab["attack"].get("range_ft") or ab["attack"].get("reach_ft")) if ab["kind"] == "spell_attack" else ab["shape"]["range_ft"] or ab["shape"]["size_ft"]
        stat = (f"+{ab['attack']['bonus']} · " if ab["kind"] == "spell_attack" else f"DC {ab['save']['dc']} · ") + ab["damage"][0][0]
        add({**ab, "id": f"spell:{ab['id']}", "text": f"Level {ab['spell_level']} spell · {reach} ft" if ab["spell_level"] else f"Cantrip · {reach} ft", "stat": stat}, why)
    for spec in actions.listing(campaign_dir, state, cid, sheet):
        kind = "shove" if spec["id"] == "shove" else "hide" if spec["id"] == "hide" else "feature" if spec["id"].startswith("feature:") else "self"
        why = None if spec["why"] in (None, "No enemy") else spec["why"]
        add({"id": spec["id"], "name": spec["label"], "cost": spec["cost"] or "free", "kind": kind, "text": spec["info"], "stat": ""}, why)
    for ab in items.listing(sheet, rec):
        add(ab, _spent(turn, ab["cost"]))
    for ab in items.pickups(state, a, cid):
        add(ab, ab.pop("why"))
    add({"id": "improvise", "name": "Improvise", "cost": "action", "kind": "improvise", "text": "Try something else: tell the DM what", "stat": ""},
        "The action is used." if turn["action"] else None)
    for ab in out:
        if ab["id"] in ("dash", "disengage", "dodge", "help") and not mine_turn:
            ab["why"] = "Not your turn."
    return out


def preview(campaign_dir: Path, state: dict, a: dict, cid: str, ability_id: str, aim) -> dict:
    """The cells and creatures an area ability would cover from here, for the board to draw before the player confirms."""
    ab = next((x for x in listing(campaign_dir, state, a, cid) if x["id"] == ability_id), None)
    if ab is None or ab["kind"] != "zone":
        raise board.BoardError("that ability has no area.")
    try:
        board.check_aim(a, cid, ab, aim)
        ok, why = True, None
    except board.BoardError as e:
        ok, why = False, str(e)
    cells = arena.shape_cells(ab["shape"], board.pos(a, cid), tuple(aim), (a["w"], a["h"]))
    vis = board.visible_cells(campaign_dir, state, a)
    units = [u for u in board.covered_units(campaign_dir, state, a, cid, ab, aim) if is_known(state, a, u, vis)]
    return {"ok": ok, "why": why, "cells": sorted([list(c) for c in cells]), "units": units}


def is_known(state: dict, a: dict, cid: str, vis: set | None) -> bool:
    return not board.is_foe(state, cid) or vis is None or board.pos(a, cid) in vis


def act(campaign_dir: Path, state: dict, a: dict, cid: str, ability_id: str, target: str | None = None, aim=None, rng=None) -> list[str]:
    """Run an ability of a character's hand on the board. Raises BoardError with the reason when it cannot be done."""
    board.require_turn(state, cid)
    ab = next((x for x in listing(campaign_dir, state, a, cid) if x["id"] == ability_id), None)
    if ab is None:
        raise board.BoardError(f"no ability {ability_id!r}.")
    if ab["why"]:
        raise board.BoardError(ab["why"])
    kind = ab["kind"]
    if kind == "improvise":
        raise board.BoardError("an improvised action goes to the DM: send what you try.")
    if kind == "attack":
        return board.player_attack(campaign_dir, state, a, cid, target, ab["entry"]["name"])
    if kind == "pickup":
        return items.pick_up(campaign_dir, state, a, cid, ab["id"])
    if kind == "heal":
        lines = items.heal(campaign_dir, state, a, cid, ab, target, rng)
        items.consume(campaign_dir, cid, ab["name"])
        return lines
    if kind in ("spell_attack", "zone"):
        lines = _cast(campaign_dir, state, a, cid, ab, target, aim, rng)
        if ab.get("source") == "item":
            items.consume(campaign_dir, cid, ab["name"])
        return lines
    if kind == "shove":
        _need_target(campaign_dir, state, a, target)
        return board.shove(campaign_dir, state, a, cid, target, rng)
    if kind == "hide":
        return board.hide(campaign_dir, state, a, cid, rng)
    done = actions.perform(campaign_dir, state, cid, ab["id"], target, None, rng=rng)
    if done.get("roll"):
        raise board.BoardError(f"{ab['name']} is not on the board yet.")
    for line in done["lines"]:
        combat.stage_feed(line)
    return done["lines"]


def _need_target(campaign_dir: Path, state: dict, a: dict, target: str | None) -> None:
    if target not in a["units"]:
        raise board.BoardError("pick a target on the board.")
    if target in board.hidden_foes(campaign_dir, state, a):
        raise board.BoardError("you cannot see that target.")


def _cast(campaign_dir: Path, state: dict, a: dict, cid: str, ab: dict, target: str | None, aim, rng) -> list[str]:
    """A damage spell: check it can be done first, then spend the slot, then cast (so a refusal costs nothing)."""
    ab = {k: v for k, v in ab.items() if k not in ("why", "targets", "needs", "icon", "text", "stat", "no_slot", "source")}
    if ab["kind"] == "spell_attack":
        _need_target(campaign_dir, state, a, target)
        board.attack_check(campaign_dir, state, a, cid, {"name": ab["name"], **ab["attack"]}, target)
    else:
        if aim is None:
            raise board.BoardError("aim the spell at a cell.")
        board.check_aim(a, cid, ab, aim)
    if ab["spell_level"]:
        sheet = character.load(campaign_dir, cid)
        character.cast_spell(sheet, ab["slot"])
        character.save(campaign_dir, cid, sheet)
    if ab["kind"] == "spell_attack":
        return board.use_spell_attack(campaign_dir, state, a, cid, ab, target, rng=rng)
    return board.use_zone(campaign_dir, state, a, cid, ab, aim, rng=rng)
