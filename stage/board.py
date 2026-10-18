"""The combat board engine: units on an arena, and the rules that need a position.

The turn tracker (`state.json` `active_encounter`, `dnd_cli/combat.py`) keeps the order, the HP, the
conditions and the action pips. This module adds where each unit stands, and the rules of the board:
walking, reach, sight and cover. It calls `combat.py` for rolls and damage. It never calls the DM.
See combat-board.md.
"""

from __future__ import annotations

import time
from pathlib import Path

from dnd_cli import abilities, character, combat, dice, item as items
from dnd_cli.errors import RulesError
from stage import arena, cast
from stage.beat import title


def controlled_by(rec: dict, team: str = combat.HOSTILE) -> str:
    """`dm` for a hostile creature the DM plays (an NPC file, or a monster the DM named, as in boss=bugbear), else `engine`. A creature on
    the party's side or a faction of its own is always the engine's."""
    if team != combat.HOSTILE:
        return "engine"
    if rec.get("kind") == "npc":
        return "dm"
    return "dm" if rec["id"].split("#")[0] != rec.get("index") else "engine"


def start(campaign_dir: Path, state: dict, tokens: list[str], stage: dict) -> list[str]:
    """Build the arena for the running combat, put every combatant on its start tile, and save it."""
    arena_id, a, lines = build(campaign_dir, state, tokens, stage)
    arena.save(campaign_dir, arena_id, a)
    return lines


def room_line(spec: dict) -> str:
    """One line for the DM about the room of a new arena."""
    if spec["shape"] == "scene":
        text = "The fight is in the room of the scene, with the party where it stood."
        if spec["ignored"]:
            text += f" {', '.join(spec['ignored'])} did not apply there."
    else:
        text = f"The room is a {spec['shape']} ({spec['size']}). The party starts at one end and the foes at the other"
        text += " (an ambush: foes also on the flanks)." if spec["ambush"] else "."
    return text + (f" Note: {spec['fallback']}." if spec.get("fallback") else "")


def build(campaign_dir: Path, state: dict, tokens: list[str], stage: dict) -> tuple[str, dict, list[str]]:
    """Like `start`, but the arena is not written: the caller saves it. The state names it (`enc["arena"]`)."""
    enc = combat.encounter(state)
    spec = arena.parse(tokens)
    side = [c for c in enc["participants"] if combat.team_of(state, c) == combat.PARTY]  # the party's team: the players' characters and its allies
    others = [c for c in enc["participants"] if c not in side]
    source = arena.source_of(campaign_dir, stage, spec)
    a = arena.generate(spec, source, len(side), len(others), side, others)
    a["units"] = {cid: {"x": x, "y": y} for cid, (x, y) in zip(side, a["starts"]["party"])}
    a["units"] |= {cid: {"x": x, "y": y} for cid, (x, y) in zip(others, a["starts"]["foes"])}
    a["control"] = {cid: controlled_by(enc["monsters"][cid], combat.team_of(state, cid)) for cid in enc["monsters"]}
    a["bystanders"] = bystanders_of(stage, a)
    refresh_sight(campaign_dir, state, a)
    refresh_intents(campaign_dir, state, a)
    arena_id = arena.new_id(campaign_dir)
    enc["arena"] = arena_id
    spec = a["spec"]
    dm = [cid for cid, who in a["control"].items() if who == "dm"]
    where = {"site": f"the site {spec['source_id']}", "scene": f"the scene {spec['source_id']}", "none": "an empty field"}[spec["source"]]
    return arena_id, a, [f"Arena {arena_id}: {a['w']} x {a['h']}, layout {spec['layout']}, light {spec['light']}, built from {where} (seed {spec['seed']}).",
                         room_line(spec),
                         "You play: " + (", ".join(dm) if dm else "no one") + ". The stage plays the other creatures."]


# -- a fight a player starts with the Attack card --------------------------------

def bystanders_of(stage: dict, a: dict) -> dict[str, dict]:
    """The actors of the scene that take no part in the fight: {id: {"x", "y"}}. Each stands on the cell it had, and blocks it; one whose
    cell a fighter holds, or that is not floor of this arena, is left out."""
    held = {(u["x"], u["y"]) for u in a["units"].values()}
    out = {}
    for aid, v in (stage.get("actors") or {}).items():
        x, y = (v.get("cell") or (None, None))
        if v.get("side") == "bystander" and not v.get("down") and x is not None and a["grid"][y][x] == arena.FLOOR and (x, y) not in held:
            out[aid] = {"x": x, "y": y}
            held.add((x, y))
    return out


def _place_foe(campaign_dir: Path, state: dict, a: dict, who: str, foe: str, entry: dict) -> None:
    """Put `foe` where this attack can reach it from the start: next to `who` for a melee attack, 2 to 6 tiles away
    in a clear line for a ranged one (30 ft, or the range if it is less). It stays near its own start if it can."""
    here, start = pos(a, who), pos(a, foe)
    taken = set(occupied(campaign_dir, state, a, skip=foe))
    walk, _ = arena.reach(here, a["w"] * a["h"], arena.blocked_cells(a), (a["w"], a["h"]), taken)
    if "reach_ft" in entry:
        ok = lambda c: arena.cheb(here, c) == 1  # noqa: E731
    else:
        far, opaque = max(2, min(entry.get("range_ft", 30), 30) // TILE_FT), arena.opaque_cells(a)
        ok = lambda c: 2 <= arena.cheb(here, c) <= far and arena.clear_line(here, c, opaque)  # noqa: E731
    cells = [c for c in walk if c != here and c not in taken and ok(c)]
    if not cells:
        raise BoardError("there is no room to start the fight there.")
    x, y = min(cells, key=lambda c: (arena.cheb(c, start), c))
    a["units"][foe] = {"x": x, "y": y}


def open_fight(campaign_dir: Path, state: dict, stage: dict, who: str, target: str, weapon: str | None, here: list[str],
               pcs: list[str], rng=None) -> dict:
    """A player attacks a creature on the stage and no fight is running: start one with the party (`pcs`) and the target,
    on a board with the target in reach of the attack. If `who` is first in the order, the attack is made now.

    `here`: the creatures on the stage that are not in the party. Returns {"arena", "foe", "lines", "note"}; `lines` are for the DM.
    A refusal raises before the arena is written (the caller saves the state only if this returns).
    """
    if (state.get("active_encounter") or {}).get("type") == "combat":
        raise BoardError("a fight is already running.")
    if target not in here:
        raise BoardError(f"{target} is not here to attack. Here: {', '.join(here) or 'no one'}.")
    pcs = list(dict.fromkeys([who, *[p for p in pcs if p != who]]))
    spec, note = combat.foe_spec(campaign_dir, target)
    actors = stage.get("actors") or {}
    # A target on the stage joins as one of its fighters, under its own id; a bystander is drawn in by this attack.
    lines = combat.start(campaign_dir, state, [] if target in actors else [spec], pcs, rng, actors)
    enc = state["active_encounter"]
    if target in actors and target not in enc["participants"]:
        lines += combat.provoke(campaign_dir, state, target, who, rng)
        enc["current_turn"] = enc["initiative_order"][0]["name"]
    else:
        combat.feud(state, who, target)
    arena_id, a, arena_lines = build(campaign_dir, state, [], stage)
    foe = target if target in enc["monsters"] else next(iter(enc["monsters"]))
    rec = combat.combatant(campaign_dir, state, who)
    pool = attack_rolls(rec)
    entry = combat._find_attack(rec, weapon) if weapon else combat.wielded(pool)
    _place_foe(campaign_dir, state, a, who, foe, entry)
    refresh_sight(campaign_dir, state, a)
    refresh_intents(campaign_dir, state, a)
    first = enc["current_turn"]
    if first == who:
        lines += attack(campaign_dir, state, a, who, entry["name"], foe, rng=rng, own_turn_only=True)
    else:
        lines.append(f"{first} acts first. {who} attacks with {entry['name']} on their turn.")
    arena.save(campaign_dir, arena_id, a)
    return {"arena": arena_id, "foe": foe, "lines": arena_lines[:1] + lines, "note": note}


# -- who is where ------------------------------------------------------------

TILE_FT = 5


class BoardError(RulesError):
    """A move or an attack the board refuses. The message says why."""


class NeedsConfirm(BoardError):
    """An attack that starts a fight with someone who is not an enemy. The player must say it again with `confirm`."""


def outcome(campaign_dir: Path, state: dict, a: dict) -> dict:
    """What the scene must know when the fight ends, for the `arena_end` event: where each unit stands, who is down, and the sides that
    changed (a faction that fought on its own, or a bystander that was drawn in, is `hostile` if it is still at war with the party, else
    `neutral`, never a bystander). Ids are the stage's."""
    solid = {(p["x"], p["y"]) for p in (a.get("room") or {}).get("props", []) if not p.get("flat")}  # the scene keeps these cells clear; a fight may not
    held = {(u["x"], u["y"]) for u in a["units"].values() if (u["x"], u["y"]) not in solid} | {(b["x"], b["y"]) for b in (a.get("bystanders") or {}).values()}
    floor = None
    cells = {}
    for cid, u in a["units"].items():
        cell = (u["x"], u["y"])
        if cell in solid:  # it ended on a chair or a bush: stand on the nearest free floor
            floor = floor or [(x, y) for y, row in enumerate(a["grid"]) for x, ch in enumerate(row) if ch == arena.FLOOR and (x, y) not in solid]
            cell = cast.nearest_free(floor, held, cell)
            held.add(cell)
        cells[cid] = {"cell": list(cell), "facing": "down"}
    monsters = state["active_encounter"]["monsters"]  # a player character who is down is not a corpse: only creatures are listed
    down = [cid for cid in a["units"] if cid in monsters and not standing(monsters[cid])]
    sides = {cid: "hostile" if combat.hostile_to_party(state, cid) else "neutral" for cid in a["units"] if combat.team_of(state, cid) == combat.NEUTRAL}
    return {"cells": cells, "down": down, "sides": sides}


def arena_id_of(state: dict) -> str | None:
    """The id of the arena of the running combat, if the fight is on a board. The one place that says so."""
    return (state.get("active_encounter") or {}).get("arena")


def effective_settings(a: dict, defaults: dict) -> dict:
    """The combat settings in force: the stage's (or the machine's default), with what the DM set for this fight on top."""
    return {**defaults, **a["spec"].get("settings", {})}


def note(a: dict, text: str) -> None:
    """Keep a short line of what happened this round, for the one summary the DM hears."""
    a["log"] = (a.get("log", []) + [text])[-40:]


def running(campaign_dir: Path, state: dict) -> tuple[str, dict]:
    """The id and the arena of the running combat."""
    arena_id = arena_id_of(state)
    a = arena.load(campaign_dir, arena_id) if arena_id else None
    if a is None:
        raise BoardError("no fight on a board is running. Start one with: uv run dnd-cli encounter start goblin:3")
    return arena_id, a


def pos(a: dict, cid: str) -> tuple[int, int]:
    u = a["units"].get(cid)
    if u is None:
        raise BoardError(f"{cid!r} is not on the board. On it: {', '.join(a['units'])}.")
    return u["x"], u["y"]


def is_foe(state: dict, cid: str) -> bool:
    return cid in state["active_encounter"]["monsters"]


def standing(rec: dict) -> bool:
    return rec["hp"]["current"] > 0


def occupied(campaign_dir: Path, state: dict, a: dict, skip: str | None = None) -> dict[tuple[int, int], str]:
    """The cells units stand on: every creature still up, and a player character at 0 HP (it lies where it fell)."""
    out = {}
    for cid in a["units"]:
        if cid != skip and (not is_foe(state, cid) or standing(combat.combatant(campaign_dir, state, cid))):
            out[pos(a, cid)] = cid
    for bid, b in (a.get("bystanders") or {}).items():
        out[(b["x"], b["y"])] = bid  # a bystander stands where it stood, and blocks the cell
    return out


def sync_units(campaign_dir: Path, state: dict, a: dict) -> list[str]:
    """Put every combatant that has no place yet (a creature added in the fight) on a free cell near its side's start."""
    enc = state["active_encounter"]
    blocked = arena.blocked_cells(a)
    taken = set(occupied(campaign_dir, state, a))
    added = []
    for cid in enc["participants"]:
        if cid in a["units"]:
            continue
        starts = a["starts"]["party" if combat.team_of(state, cid) == combat.PARTY else "foes"]
        w, h = a["w"], a["h"]
        cells = [(x, y) for y in range(h) for x in range(w) if (x, y) not in blocked and (x, y) not in taken]
        if not cells:
            raise BoardError("no free cell is left in the arena.")
        cell = min(cells, key=lambda c: min(arena.cheb(c, s) for s in starts) * 100 + abs(c[1] - h // 2))
        a["units"][cid] = {"x": cell[0], "y": cell[1]}
        taken.add(cell)
        added.append(cid)
    return added


# -- light and sight ----------------------------------------------------------------

DIM_TILES, TORCH_TILES, LIT_PROP_TILES = 8, 6, 4


def sight_radius(campaign_dir: Path, state: dict, a: dict, cid: str) -> int:
    """How far a party member sees in tiles. A lit room is seen whole. In dim light everyone sees 8 tiles (or their darkvision).
    In the dark: darkvision, else a carried torch (6 tiles), else the next cell."""
    if a["spec"]["light"] == "lit":
        return max(a["w"], a["h"])
    sheet = character.load(campaign_dir, cid)
    race = sheet.get("race", "").lower()
    dv = max((ft for word, ft in arena.arena_data()["darkvision_ft"].items() if word in race), default=0) // TILE_FT
    if a["spec"]["light"] == "dim":
        return max(DIM_TILES, dv)
    torch = TORCH_TILES if any("torch" in it.name.lower() for it in items.items(sheet)) else 0
    return max(dv, torch, 1)


def visible_cells(campaign_dir: Path, state: dict, a: dict) -> set[tuple[int, int]] | None:
    """The cells the party sees now (None: a lit room, everything). Lines stop at walls and tall props; a light-source prop
    lights the cells within 4 tiles of it."""
    if a["spec"]["light"] == "lit":
        return None
    opaque = arena.opaque_cells(a)
    cells = {(x, y) for y in range(a["h"]) for x in range(a["w"])}
    lamps = [(p["x"], p["y"]) for p in a["props"] if "light-source" in arena.board_of(p["kind"])["tags"]]
    vis: set[tuple[int, int]] = set()
    for cid in standing_pcs(campaign_dir, state, a):
        here, radius = pos(a, cid), sight_radius(campaign_dir, state, a, cid)
        for cell in cells:
            if cell in vis or not arena.clear_line(here, cell, opaque):
                continue
            if arena.cheb(here, cell) <= radius or any(arena.cheb(lamp, cell) <= LIT_PROP_TILES for lamp in lamps):
                vis.add(cell)
    return vis


def refresh_intents(campaign_dir: Path, state: dict, a: dict) -> None:
    """Work out what each creature would do now, to show over it (computed after each change, not on each fetch)."""
    from stage import foes

    a["intents"] = {cid: foes.describe(campaign_dir, state, a, cid) for cid in standing_foes(campaign_dir, state, a)}


def refresh_sight(campaign_dir: Path, state: dict, a: dict) -> None:
    """Remember what the party has seen (the cells that stay on the map when they are out of sight)."""
    if (vis := visible_cells(campaign_dir, state, a)) is None:
        return
    rows = [list(r) for r in a["seen"]]
    for x, y in vis:
        rows[y][x] = "1"
    a["seen"] = ["".join(r) for r in rows]


def hidden_foes(campaign_dir: Path, state: dict, a: dict, vis: set | None = ...) -> set[str]:
    """The creatures the party cannot see now. They stay out of the board view, the turn bar and the summary. `vis`: the cells in sight,
    when the caller has them already."""
    if vis is ...:
        vis = visible_cells(campaign_dir, state, a)
    if vis is None:
        return set()
    return {c for c in a["units"] if combat.team_of(state, c) != combat.PARTY and pos(a, c) not in vis}


# -- walking ---------------------------------------------------------------------


def resources(state: dict, cid: str) -> dict:
    return state["active_encounter"].setdefault("resources", {}).setdefault(cid, {})


def tiles_left(state: dict, rec: dict) -> int:
    """Tiles the creature can still walk this turn: its speed (doubled by Dash) less what it has walked."""
    base = rec.get("speed_ft", 30) // TILE_FT * (2 if combat.has_condition(state, rec["id"], "dashing") else 1)
    return max(0, base - resources(state, rec["id"]).get("moved", 0))


def reachable(campaign_dir: Path, state: dict, a: dict, cid: str) -> tuple[dict, dict]:
    """Where `cid` can walk now: (steps by cell, previous cell by cell)."""
    rec = combat.combatant(campaign_dir, state, cid)
    others = set(occupied(campaign_dir, state, a, skip=cid))
    return arena.reach(pos(a, cid), tiles_left(state, rec), arena.blocked_cells(a), (a["w"], a["h"]), others)


def engage(campaign_dir: Path, state: dict, a: dict, attacker: str, target: str, rng=None) -> list[str]:
    """A hostile act against `target`. A bystander (it is not a unit yet) is drawn into the fight: it gets a record and an initiative,
    stands on the cell it had, and is an enemy of the attacker's team. Result: lines for the DM (empty when nothing changed)."""
    by = a.get("bystanders") or {}
    if target not in by:
        return []
    lines = combat.provoke(campaign_dir, state, target, attacker, rng)
    cell = by.pop(target)
    a["units"][target] = {"x": cell["x"], "y": cell["y"]}
    a.setdefault("control", {})[target] = controlled_by(state["active_encounter"]["monsters"][target], combat.NEUTRAL)
    return lines


def confirm_why(side: str, name: str) -> str:
    """The question for an attack that starts a fight with a bystander, or breaks a peace (`side`: the target's side)."""
    return f"{name} is a bystander. Attacking draws them into the fight against you." if side == "bystander" else f"{name} is at peace with you. Attacking makes them an enemy."


def needs_confirm(state: dict, a: dict, attacker: str, target: str) -> str | None:
    """Why a player should confirm an attack: it starts a fight with a bystander, or breaks the peace with a faction at peace."""
    name = (state.get("active_encounter") or {}).get("monsters", {}).get(target, {}).get("name") or title(target)
    if target in (a.get("bystanders") or {}):
        return confirm_why("bystander", name)
    if combat.team_of(state, target) != combat.team_of(state, attacker) and not combat.enemies(state, attacker, target):
        return confirm_why("neutral", name)
    return None


def attack_rolls(rec: dict) -> list[dict]:
    """The attacks of a creature that roll to hit and do damage (not saving throws, not a spell with no dice)."""
    return [x for x in rec["attacks"] if x["damage"] and "dc" not in x]


def melee_attack(rec: dict) -> dict | None:
    """The attack a creature makes with a reaction: its equipped melee weapon, else any melee attack."""
    melee = [x for x in attack_rolls(rec) if x.get("reach_ft")]
    return combat.wielded(melee)


def provokers(campaign_dir: Path, state: dict, a: dict, cid: str, to: tuple[int, int]) -> list[str]:
    """The enemies that get a reaction attack when `cid` steps from where it stands to `to`."""
    if combat.has_condition(state, cid, "disengaged"):
        return []
    here, out = pos(a, cid), []
    for other in a["units"]:
        if other == cid or not combat.enemies(state, other, cid):
            continue
        rec = combat.combatant(campaign_dir, state, other)
        weapon = melee_attack(rec)
        if not standing(rec) or weapon is None or combat.turn_used(state, other)["reaction"]:
            continue
        reach = weapon["reach_ft"] // TILE_FT
        if arena.cheb(pos(a, other), here) <= reach < arena.cheb(pos(a, other), to):
            out.append(other)
    return out


def _react(campaign_dir: Path, state: dict, a: dict, who: str, against: str, rng) -> list[str]:
    weapon = melee_attack(combat.combatant(campaign_dir, state, who))
    lines = combat.attack(campaign_dir, state, who, weapon["name"], against, rng=rng, cost="reaction", catch_up=False)
    note(a, brief(campaign_dir, state, a, lines, who, weapon["name"], against, " as a reaction"))
    return [f"{who} takes a reaction attack as {against} leaves its reach."] + lines


def walk(campaign_dir: Path, state: dict, a: dict, cid: str, path: list, rng=None) -> dict:
    """Walk the steps one by one. A creature that is left gets a reaction attack: a creature the stage plays attacks at once;
    a player character is asked (the walk stops, and `a["pending"]` holds the rest of it). Stops if the walker falls."""
    lines, steps = [], []
    for i, cell in enumerate(path):
        cell = tuple(cell)
        for foe in provokers(campaign_dir, state, a, cid, cell):
            if not is_foe(state, foe):
                a["pending"] = {"type": "react", "who": foe, "against": cid, "path": [list(c) for c in path[i:]], "asked_at": time.time()}
                return {"steps": steps, "lines": lines, "pending": a["pending"]}
            lines += _react(campaign_dir, state, a, foe, cid, rng)
            if not standing(combat.combatant(campaign_dir, state, cid)):
                return {"steps": steps, "lines": lines, "pending": None}
        a["units"][cid] = {"x": cell[0], "y": cell[1]}
        resources(state, cid)["moved"] = resources(state, cid).get("moved", 0) + 1
        steps.append(list(cell))
    if not is_foe(state, cid):
        refresh_sight(campaign_dir, state, a)
    return {"steps": steps, "lines": lines, "pending": None}


def move(campaign_dir: Path, state: dict, a: dict, cid: str, to, rng=None) -> dict:
    """Walk `cid` to a cell by the shortest way it can afford. Raises BoardError when it cannot."""
    if a.get("pending"):
        raise BoardError("a reaction question waits for an answer.")
    to = tuple(to)
    dist, prev = reachable(campaign_dir, state, a, cid)
    if to == pos(a, cid):
        raise BoardError(f"{cid} is already there.")
    if to not in dist:
        rec = combat.combatant(campaign_dir, state, cid)
        raise BoardError(f"{cid} cannot reach {to[0]},{to[1]}: {tiles_left(state, rec) * TILE_FT} ft of walking left.")
    return walk(campaign_dir, state, a, cid, arena.path_from(prev, pos(a, cid), to), rng)


def answer(campaign_dir: Path, state: dict, a: dict, take: bool, rng=None) -> dict:
    """The player answers a reaction question: attack or not, then the walk goes on."""
    p = a.get("pending")
    if not p:
        raise BoardError("no reaction question is waiting.")
    a["pending"] = None
    lines = []
    mover = p["against"]
    if take and standing(combat.combatant(campaign_dir, state, p["who"])) and not combat.turn_used(state, p["who"])["reaction"]:
        lines += _react(campaign_dir, state, a, p["who"], mover, rng)
    else:
        combat.spend_turn(state, p["who"], "reaction")  # the answer is final: no second question for this reaction
    if not standing(combat.combatant(campaign_dir, state, mover)):
        return {"steps": [], "lines": lines, "pending": None}
    rest = walk(campaign_dir, state, a, mover, p["path"], rng)
    rest["lines"] = lines + rest["lines"]
    return rest


# -- attacking -----------------------------------------------------------------------


def attack_check(campaign_dir: Path, state: dict, a: dict, attacker: str, entry: dict, target: str) -> dict:
    """Can `attacker` hit `target` with this attack from where they stand? {"mode", "cover", "dis"} or a BoardError."""
    here, there = pos(a, attacker), pos(a, target)
    t_rec = combat.combatant(campaign_dir, state, target)
    if not standing(t_rec):
        raise BoardError(f"{target} is down.")
    dist = arena.cheb(here, there)
    reach, rng_ft = entry.get("reach_ft", 0) // TILE_FT, entry.get("range_ft", 0) // TILE_FT
    if dist <= reach:
        return {"mode": "melee", "cover": "none", "dis": False}
    if not rng_ft or dist > rng_ft:
        if rng_ft:
            raise BoardError(f"{target} is {dist * TILE_FT} ft away. {entry['name']} reaches {rng_ft * TILE_FT} ft.")
        raise BoardError(f"{target} is {dist * TILE_FT} ft away. Walk next to it: {entry['name']} reaches {reach * TILE_FT} ft.")
    if not arena.clear_line(here, there, arena.opaque_cells(a)):
        raise BoardError(f"A wall or a tall prop hides {target}.")
    near = any(arena.cheb(here, pos(a, o)) <= 1 for o in a["units"]
               if o != attacker and combat.enemies(state, o, attacker) and standing(combat.combatant(campaign_dir, state, o)))
    return {"mode": "ranged", "cover": arena.cover_between(here, there, arena.cover_cells(a)), "dis": near}


def brief(campaign_dir: Path, state: dict, a: dict, lines: list[str], attacker: str, weapon: str, target: str, how: str = "") -> str:
    """One line for the round summary: who used what on whom, hit or miss, and whether it is down. No numbers."""
    unseen = hidden_foes(campaign_dir, state, a)
    names = ["Something unseen" if c in unseen else combat.combatant(campaign_dir, state, c)["name"] for c in (attacker, target)]
    head = next((ln for ln in lines if ln.startswith(f"{attacker} ") and " → " in ln), "")
    down = not standing(combat.combatant(campaign_dir, state, target))
    return f"{names[0]} {'missed' if 'miss' in head else 'hit'} {names[1]} with {weapon}{how}" + (f"; {names[1]} is down" if down else "")


def attack(campaign_dir: Path, state: dict, a: dict, attacker: str, weapon: str, target: str, rng=None, cost: str | None = "action",
           adv: bool = False, dis: bool = False, bonus: int = 0, secret: bool = False, own_turn_only: bool = False,
           catch_up: bool = True, smite: int | None = None) -> list[str]:
    """An attack with the board's rules: reach or range, line of sight, cover (-2 or -5 to hit), and an enemy next to an archer.

    `own_turn_only`: the stage refuses an attack out of turn. The DM's `attack` command keeps its way of moving the tracker.
    """
    if own_turn_only and cost != "reaction" and state["active_encounter"].get("current_turn") != attacker:
        raise BoardError(f"it is {state['active_encounter'].get('current_turn')}'s turn, not {attacker}'s.")
    pulled = engage(campaign_dir, state, a, attacker, target, rng)
    rec = combat.combatant(campaign_dir, state, attacker)
    entry = combat._find_attack(rec, weapon)
    check = attack_check(campaign_dir, state, a, attacker, entry, target)
    traits, damage_expr, damage_type = rec.get("traits", []), None, ""
    ally = bool(traits) and _party_adjacent(campaign_dir, state, a, attacker, target)
    if ally and "Pack Tactics" in traits:
        adv = True
    if ally and "Martial Advantage" in traits and not resources(state, attacker).get("martial") and len(entry["damage"]) == 1:
        resources(state, attacker)["martial"] = True  # once per turn
        damage_expr, damage_type = f"{entry['damage'][0][0]}+{abilities.traits()['Martial Advantage']['dice']}", entry["damage"][0][1]
    lines = combat.attack(campaign_dir, state, attacker, entry["name"], target, rng=rng, cost=cost, adv=adv, secret=secret,
                          bonus=bonus - arena.COVER_BONUS[check["cover"]], dis=dis or check["dis"], catch_up=catch_up,
                          damage_expr=damage_expr, damage_type=damage_type, melee=check["mode"] == "melee", smite=smite)
    note(a, brief(campaign_dir, state, a, lines, attacker, entry["name"], target))
    notes = [f"{target} has {check['cover']} cover: -{arena.COVER_BONUS[check['cover']]} to hit."] if check["cover"] != "none" else []
    return pulled + notes + (["An enemy is next to the archer: disadvantage."] if check["dis"] else []) + lines


def approach(campaign_dir: Path, state: dict, a: dict, cid: str, target: str) -> tuple[int, int] | None:
    """The cell `cid` can reach this turn that is nearest to `target` (fewest steps among equals), or None if it cannot get nearer."""
    dist, _ = reachable(campaign_dir, state, a, cid)
    goal = pos(a, target)
    best = min(dist, key=lambda c: (arena.cheb(c, goal), dist[c]))
    return best if best != pos(a, cid) and arena.cheb(best, goal) < arena.cheb(pos(a, cid), goal) else None


# -- what the browser may know ------------------------------------------------


def view(campaign_dir: Path, state: dict, arena_id: str, a: dict, settings: dict) -> dict:
    """The arena as a player sees it. A creature shows how hurt it is as a band, never as numbers.

    In dim or dark light the browser gets only what the party has seen: cells never seen are blank, creatures out of sight
    are left out, and props and items show only on cells seen before.
    """
    enc = state["active_encounter"]
    vis = visible_cells(campaign_dir, state, a)
    fog = vis is not None
    hidden = hidden_foes(campaign_dir, state, a, vis)
    seen = ({(x, y) for y, row in enumerate(a["seen"]) for x, c in enumerate(row) if c == "1"} | vis) if fog else None
    units = []
    for cid in a["units"]:
        rec = combat.combatant(campaign_dir, state, cid)
        x, y = pos(a, cid)
        if cid in hidden:
            continue
        u = {"id": cid, "name": rec["name"], "x": x, "y": y, "pc": not is_foe(state, cid), "team": combat.team_of(state, cid), "down": not standing(rec),
             "health": combat.health_band(rec), "conditions": [c["condition"] for c in enc.get("conditions", {}).get(cid, [])]}
        if u["pc"]:
            u["hp"] = rec["hp"]
        elif cid in a.get("intents", {}):
            u["intent"] = a["intents"][cid]
        units.append(u)
    current = enc.get("current_turn")
    walk: list[list[int]] = []
    left = 0
    if current in a["units"] and not is_foe(state, current) and standing(combat.combatant(campaign_dir, state, current)) and not a.get("pending"):
        dist, _ = reachable(campaign_dir, state, a, current)
        walk = [list(c) for c, n in dist.items() if n > 0]
        left = tiles_left(state, combat.combatant(campaign_dir, state, current)) * TILE_FT
    pending = a.get("pending")
    known = (lambda x, y: (x, y) in seen) if fog else (lambda x, y: True)
    return {
        "id": arena_id, "w": a["w"], "h": a["h"], "shape": a["spec"].get("shape", "rect"), "room": a.get("room"), "light": a["spec"]["light"],
        "grid": ["".join(c if known(x, y) else " " for x, c in enumerate(row)) for y, row in enumerate(a["grid"])],
        "visible": ["".join("1" if (x, y) in vis else "0" for x in range(a["w"])) for y in range(a["h"])] if fog else None,
        "hazard": "water" if a["spec"]["decor"] == "forest" else "lava",
        "tiles": arena.look_counts(a["look"]),
        "props": [{"id": p["id"], "kind": p["kind"], "x": p["x"], "y": p["y"]} for p in a["props"] if known(p["x"], p["y"])],
        "items": [{"id": i["id"], "name": i["name"], "x": i["x"], "y": i["y"]} for i in a["items"] if known(i["x"], i["y"])],
        "units": units, "current": None if current in hidden else current, "round": enc.get("round", 1),
        "bystanders": [{"id": b, "name": title(b), "x": v["x"], "y": v["y"]} for b, v in (a.get("bystanders") or {}).items() if known(v["x"], v["y"])],
        "walk": walk, "feet_left": left,
        "pending": {"who": pending["who"], "against": pending["against"], "seconds_left": (
            max(0, round(settings["reaction_seconds"] - (time.time() - pending.get("asked_at", 0)))) if settings["reaction_seconds"] else None)}
        if pending else None,
        "settings": settings,
    }


def require_turn(state: dict, cid: str) -> None:
    """The stage lets a player act only on their character's turn."""
    now = (state.get("active_encounter") or {}).get("current_turn")
    if now != cid:
        raise BoardError(f"it is {now}'s turn, not {cid}'s.")


def default_weapon(campaign_dir: Path, state: dict, a: dict, attacker: str, target: str) -> str:
    """The attack a click on a creature means: an equipped weapon that reaches it, else any attack that does."""
    rec = combat.combatant(campaign_dir, state, attacker)
    dist = arena.cheb(pos(a, attacker), pos(a, target))
    armed = attack_rolls(rec)
    reaching = [x for x in armed if dist <= max(x.get("reach_ft", 0), x.get("range_ft", 0)) // TILE_FT]
    pool = reaching or armed
    return combat.wielded(pool)["name"]


# -- the stage plays the creatures ------------------------------------------------


def standing_pcs(campaign_dir: Path, state: dict, a: dict) -> list[str]:
    """The standing units of the party's team."""
    return [c for c in a["units"] if combat.team_of(state, c) == combat.PARTY and standing(combat.combatant(campaign_dir, state, c))]


def standing_enemies(campaign_dir: Path, state: dict, a: dict, cid: str) -> list[str]:
    """The standing units that are enemies of `cid`."""
    return [c for c in a["units"] if combat.enemies(state, cid, c) and standing(combat.combatant(campaign_dir, state, c))]


def standing_foes(campaign_dir: Path, state: dict, a: dict) -> list[str]:
    """The standing units that are enemies of the party."""
    return [c for c in a["units"] if combat.hostile_to_party(state, c) and standing(combat.combatant(campaign_dir, state, c))]


def dm_prompt(campaign_dir: Path, state: dict, a: dict, cid: str) -> str:
    """What the DM is told when a creature it plays is up. It names only what the party can see (the console is public)."""
    rec = combat.combatant(campaign_dir, state, cid)
    here = pos(a, cid)
    near = ", ".join(f"{combat.combatant(campaign_dir, state, p)['name']} ({p}) {arena.cheb(here, pos(a, p))} tiles, "
                     f"{combat.health_band(combat.combatant(campaign_dir, state, p))}" for p in standing_pcs(campaign_dir, state, a))
    attacks = "; ".join(f"{x['name']} +{x.get('bonus', 0)} " + ", ".join(e for e, _ in x["damage"])
                        + (f" (reach {x['reach_ft']} ft)" if x.get("reach_ft") else f" (range {x['range_ft']} ft)") for x in rec["attacks"] if x["damage"])
    walk = tiles_left(state, rec) * TILE_FT
    other = "; ".join(f"{x['name']} ({x['kind'] if x['kind'] != 'dm' else 'play it from the rules: ' + x.get('desc', '')[:90]})"
                      for x in rec.get("abilities", []) if abilities.available(rec, x) or x["kind"] == "dm")
    attacks += f". Also: {other}" if other else ""
    return (f"[combat] Round {state['active_encounter'].get('round', 1)}: {rec['name']} ({cid}) acts, and you play it. "
            f"It has {walk} ft of walking. Party: {near}. Its attacks: {attacks}. Move it with "
            f"`uv run dnd-cli encounter move {cid} --toward <id>`, attack with `uv run dnd-cli attack {cid} \"<attack>\" <id>` "
            "(the board checks reach, sight and cover), narrate it in one beat, then run `uv run dnd-cli encounter next`.")


def expired(pending: dict, settings: dict) -> bool:
    """The player did not answer a reaction question in time (a limit of 0 seconds means no limit)."""
    limit = settings["reaction_seconds"]
    return bool(limit) and time.time() - pending.get("asked_at", 0) >= limit


def summary_prompt(campaign_dir: Path, state: dict, a: dict, rnd: int, lines: list[str]) -> str:
    """The one line the DM hears for a round: what happened, without numbers, and who is down."""
    unseen = hidden_foes(campaign_dir, state, a)
    down = [combat.combatant(campaign_dir, state, c)["name"] for c in a["units"] if c not in unseen and not standing(combat.combatant(campaign_dir, state, c))]
    return (f"[combat] Round {rnd} is over. What happened: {'; '.join(lines)}." + (f" Down: {', '.join(down)}." if down else "")
            + " Tell it in one short beat (two sentences at most) and wait: the stage runs the next round.")


def pump_step(campaign_dir: Path, state: dict, a: dict, rng=None, settings: dict | None = None) -> dict | None:
    """One step of a fight on a board when it is not a player's turn. None when there is nothing to do now.

    - {"kind": "summary", "prompt"}: a round is over; the DM hears it once, if the setting is on.
    - {"kind": "over"}: no creature or no party member is standing (the DM ends the fight and tells it).
    - {"kind": "dm", "prompt"}: a creature the DM plays is up; send the prompt once. When the DM is idle again and the
      turn is still its, the stage ends it.
    - {"kind": "turn", "who", "lines", "pending"}: the stage played a creature's turn (and ended it unless a reaction question waits).
    """
    enc = state["active_encounter"]
    cid = enc.get("current_turn")
    if (rnd := enc.get("round", 1)) > a.get("summarized", 1):
        lines, a["log"], a["summarized"] = a.get("log", []), [], rnd
        if lines and (settings or {}).get("round_summary", True):
            return {"kind": "summary", "prompt": summary_prompt(campaign_dir, state, a, rnd - 1, lines)}
    if a.get("pending") or cid not in a["units"] or not is_foe(state, cid):
        return None
    if not standing_foes(campaign_dir, state, a) or not standing_pcs(campaign_dir, state, a):
        if a.get("announced_end"):
            return None
        a["announced_end"] = True
        return {"kind": "over", "won": bool(standing_pcs(campaign_dir, state, a))}
    if not standing(combat.combatant(campaign_dir, state, cid)):
        return {"kind": "turn", "who": cid, "lines": combat.next_turn(campaign_dir, state), "pending": False}
    asked = a.get("asked")
    if a["control"].get(cid) == "dm":
        if asked != [cid, enc.get("round", 1)]:
            a["asked"] = [cid, enc.get("round", 1)]
            return {"kind": "dm", "prompt": dm_prompt(campaign_dir, state, a, cid)}
        # The DM answered and did not end the turn: the stage ends it.
        a["asked"] = None
        return {"kind": "turn", "who": cid, "lines": combat.next_turn(campaign_dir, state), "pending": False}
    from stage import foes  # the planner reads this module

    played = foes.play_foe(campaign_dir, state, a, cid, rng)
    if played["pending"]:
        return {"kind": "turn", "who": cid, "lines": played["lines"], "pending": True}
    return {"kind": "turn", "who": cid, "lines": played["lines"] + combat.next_turn(campaign_dir, state), "pending": False}


def player_attack(campaign_dir: Path, state: dict, a: dict, who: str, target: str | None, weapon: str | None = None, confirm: bool = False) -> list[str]:
    """An attack a player makes from the stage: on their own turn, with the weapon they name or the one that reaches. An attack on a
    bystander, or on someone at peace with the party, needs `confirm` (it starts a fight or breaks a peace)."""
    if target not in a["units"] and target not in (a.get("bystanders") or {}):
        raise BoardError("pick a target on the board.")
    if target in hidden_foes(campaign_dir, state, a):
        raise BoardError("you cannot see that target.")
    if not confirm and (why := needs_confirm(state, a, who, target)):
        raise NeedsConfirm(why)
    pulled = engage(campaign_dir, state, a, who, target)
    return pulled + attack(campaign_dir, state, a, who, weapon or default_weapon(campaign_dir, state, a, who, target), target, own_turn_only=True)


# -- abilities on the board --------------------------------------------------------


def _party_adjacent(campaign_dir: Path, state: dict, a: dict, attacker: str, target: str) -> bool:
    """An ally of `attacker` (up and not the attacker) stands next to `target`: Pack Tactics and Martial Advantage need it."""
    return any(o != attacker and combat.team_of(state, o) == combat.team_of(state, attacker) and arena.cheb(pos(a, o), pos(a, target)) <= 1
               and standing(combat.combatant(campaign_dir, state, o)) for o in a["units"])


def check_aim(a: dict, cid: str, ab: dict, aim) -> None:
    """The aim of an area ability: in range with a clear line (a sphere or a cube), or any other cell (a cone or a line)."""
    shape, here, aim = ab["shape"], pos(a, cid), tuple(aim)
    if shape["type"] in ("cone", "line"):
        if aim == here:
            raise BoardError(f"{ab['name']} needs a direction: aim at another cell.")
        return
    if not (0 <= aim[0] < a["w"] and 0 <= aim[1] < a["h"]):
        raise BoardError("aim inside the arena.")
    reach = shape["range_ft"] // TILE_FT
    if arena.cheb(here, aim) > reach:
        raise BoardError(f"{ab['name']} reaches {reach * TILE_FT} ft; that is {arena.cheb(here, aim) * TILE_FT} ft away.")
    if not arena.clear_line(here, aim, arena.opaque_cells(a)):
        raise BoardError("A wall or a tall prop blocks the line there.")


def covered_units(campaign_dir: Path, state: dict, a: dict, cid: str, ab: dict, aim) -> list[str]:
    """The creatures an area covers (an ally too). A cone or a line never covers its caster."""
    cells = arena.shape_cells(ab["shape"], pos(a, cid), tuple(aim), (a["w"], a["h"]))
    return [u for u in a["units"] if pos(a, u) in cells and (u != cid or ab["shape"]["type"] not in ("cone", "line"))
            and standing(combat.combatant(campaign_dir, state, u))]


def spend_ability(campaign_dir: Path, state: dict, cid: str, ab: dict) -> None:
    """The action, bonus action or reaction an ability costs, and its use or slot."""
    if ab["cost"] in combat.TURN_KINDS:
        combat.spend_turn(state, cid, ab["cost"], quiet=True)
    abilities.spend(combat.combatant(campaign_dir, state, cid), ab)


def use_zone(campaign_dir: Path, state: dict, a: dict, cid: str, ab: dict, aim, rng=None) -> list[str]:
    """A save-based ability on an area: each creature in it saves, and takes the damage (half on a success for a `half` ability)."""
    rec = combat.combatant(campaign_dir, state, cid)
    if not abilities.available(rec, ab):
        raise BoardError(f"{rec['name']} cannot use {ab['name']} now.")
    check_aim(a, cid, ab, aim)
    cells = arena.shape_cells(ab["shape"], pos(a, cid), tuple(aim), (a["w"], a["h"]))
    pulled: list[str] = []
    for b, v in list((a.get("bystanders") or {}).items()):  # a copy: engage takes the bystander out
        if (v["x"], v["y"]) in cells:
            pulled += engage(campaign_dir, state, a, cid, b, rng)
    targets = covered_units(campaign_dir, state, a, cid, ab, aim)
    spend_ability(campaign_dir, state, cid, ab)
    expr, dtype = ab["damage"][0]
    lines = combat.save(campaign_dir, state, targets, ab["save"]["ability"], ab["save"]["dc"], damage_expr=expr, damage_type=dtype,
                        half=ab["save"]["success"] == "half", rng=rng) if targets else []
    names = ", ".join(combat.combatant(campaign_dir, state, t)["name"] for t in targets) or "no one"
    note(a, f"{rec['name']} used {ab['name']} on {names}")
    return [f"{cid} uses {ab['name']}: {len(targets)} in the area."] + lines


def use_spell_attack(campaign_dir: Path, state: dict, a: dict, cid: str, ab: dict, target: str, rng=None) -> list[str]:
    """A spell with an attack roll: the board's reach, sight and cover decide, then the usual attack roll with the spell's damage."""
    pulled = engage(campaign_dir, state, a, cid, target, rng)
    rec = combat.combatant(campaign_dir, state, cid)
    if not abilities.available(rec, ab):
        raise BoardError(f"{rec['name']} cannot use {ab['name']} now.")
    check = attack_check(campaign_dir, state, a, cid, {"name": ab["name"], **ab["attack"]}, target)
    spend_ability(campaign_dir, state, cid, ab)
    expr, dtype = ab["damage"][0]
    weapon = ab.get("weapon", "spell")  # an item thrown as an improvised weapon rolls with its own to-hit
    lines = combat.attack(campaign_dir, state, cid, weapon, target, rng=rng, cost=None, damage_expr=expr, damage_type=dtype,
                          bonus=ab.get("to_hit", 0) - arena.COVER_BONUS[check["cover"]], dis=check["dis"])
    note(a, brief(campaign_dir, state, a, [ln.replace(f" {weapon} ", f" {ab['name']} ", 1) for ln in lines], cid, ab["name"], target))
    return pulled + [f"{cid} casts {ab['name']}."] + lines


def use_multiattack(campaign_dir: Path, state: dict, a: dict, cid: str, ab: dict, target: str, rng=None) -> list[str]:
    """Each attack of a Multiattack on one target; the first spends the action."""
    lines, first = [], True
    for name, count in ab["parts"]:
        for _ in range(count):
            if not standing(combat.combatant(campaign_dir, state, target)):
                return lines
            lines += attack(campaign_dir, state, a, cid, name, target, rng=rng, cost=ab["cost"] if first else None)
            first = False
    return lines


# -- actions that need the board: shove and hide -----------------------------------


def shove(campaign_dir: Path, state: dict, a: dict, cid: str, target: str, rng=None) -> list[str]:
    """Athletics against the target's Athletics or Acrobatics. A win pushes it 5 ft straight away; into a hazard it takes 2d6."""
    import random

    rng = rng or random
    pulled = engage(campaign_dir, state, a, cid, target, rng)
    here, there = pos(a, cid), pos(a, target)
    if arena.cheb(here, there) > 1:
        raise BoardError(f"{target} is {arena.cheb(here, there) * TILE_FT} ft away. Shove needs it next to you.")
    me, foe = combat.combatant(campaign_dir, state, cid), combat.combatant(campaign_dir, state, target)
    mine = dice.d20(rng)[0] + combat.skill_bonus(me, "athletics")
    theirs = dice.d20(rng)[0] + max(combat.skill_bonus(foe, "athletics"), combat.skill_bonus(foe, "acrobatics"))
    combat.spend_turn(state, cid, "bonus", quiet=True)
    combat.stage_feed(f"{me['name']} shoves {foe['name']}: {mine} against {theirs}.")
    lines = pulled + [f"{cid} shoves {target}: Athletics {mine} against {theirs}."]
    if mine < theirs:
        return lines + [f"{target} holds its ground."]
    dx, dy = (there[0] > here[0]) - (there[0] < here[0]), (there[1] > here[1]) - (there[1] < here[1])
    dest = (there[0] + dx, there[1] + dy)
    solid_cells, others = arena.blocked_cells(a) - {c for c in arena.blocked_cells(a) if a["grid"][c[1]][c[0]] == arena.HAZARD}, set(occupied(campaign_dir, state, a, skip=target))
    if not (0 <= dest[0] < a["w"] and 0 <= dest[1] < a["h"]) or dest in solid_cells or dest in others:
        return lines + [f"{target} is pushed, but something blocks the way: it does not move."]
    a["units"][target] = {"x": dest[0], "y": dest[1]}
    lines.append(f"{target} is pushed 5 ft.")
    if a["grid"][dest[1]][dest[0]] == arena.HAZARD:
        amount, groups = dice.roll("2d6", rng)
        combat.stage_roll(f"{foe['name']} falls into the {'water' if a['spec']['decor'] == 'forest' else 'lava'}: 2d6", amount, groups)
        lines.append(combat.damage(campaign_dir, state, target, amount, "fire"))
    note(a, f"{me['name']} shoved {foe['name']}")
    return lines


def hide(campaign_dir: Path, state: dict, a: dict, cid: str, rng=None) -> list[str]:
    """Stealth against the highest passive Perception of the creatures that stand. On a success the character is hidden:
    its next attack has advantage."""
    foes = [c for c in standing_foes(campaign_dir, state, a)]
    dc = max((10 + combat.skill_bonus(combat.combatant(campaign_dir, state, f), "perception") for f in foes), default=10)
    combat.spend_turn(state, cid, "action", quiet=True)
    done = combat.check(campaign_dir, state, [cid], "stealth", dc=dc, hide_dc=True, rng=rng)[-1]
    if "— success" in done:
        combat.condition(state, cid, "add", "hidden")
    name = combat.combatant(campaign_dir, state, cid)["name"]
    return [f"{name} slips out of sight." if "— success" in done else f"{name} tries to hide, and is noticed."]  # the DC and the roll stay on the stage
