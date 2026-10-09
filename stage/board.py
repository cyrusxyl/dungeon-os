"""The combat board engine: units on an arena, and the rules that need a position.

The turn tracker (`state.json` `active_encounter`, `dnd_cli/combat.py`) keeps the order, the HP, the
conditions and the action pips. This module adds where each unit stands, and the rules of the board:
walking, reach, sight and cover. It calls `combat.py` for rolls and damage. It never calls the DM.
See combat-board.md.
"""

from __future__ import annotations

from pathlib import Path

from dnd_cli import combat
from stage import arena


def controlled_by(rec: dict) -> str:
    """`dm` for a creature the DM plays (an NPC file, or a monster the DM named, as in boss=bugbear), else `engine`."""
    if rec.get("kind") == "npc":
        return "dm"
    return "dm" if rec["id"].split("#")[0] != rec.get("index") else "engine"


def start(campaign_dir: Path, state: dict, tokens: list[str], stage: dict) -> list[str]:
    """Build the arena for the running combat and put every combatant on its start tile."""
    enc = combat.encounter(state)
    spec = arena.parse(tokens)
    pcs = [c for c in enc["participants"] if c not in enc["monsters"]]
    foes = list(enc["monsters"])
    source = arena.source_of(campaign_dir, stage, spec)
    a = arena.generate(spec, source, len(pcs), len(foes))
    a["units"] = {cid: {"x": x, "y": y} for cid, (x, y) in zip(pcs, a["starts"]["party"])}
    a["units"] |= {cid: {"x": x, "y": y} for cid, (x, y) in zip(foes, a["starts"]["foes"])}
    a["control"] = {cid: controlled_by(enc["monsters"][cid]) for cid in foes}
    arena_id = arena.new_id(campaign_dir)
    arena.save(campaign_dir, arena_id, a)
    enc["arena"] = arena_id
    spec = a["spec"]
    dm = [cid for cid, who in a["control"].items() if who == "dm"]
    where = {"site": f"the site {spec['source_id']}", "scene": f"the scene {spec['source_id']}", "none": "an empty field"}[spec["source"]]
    return [f"Arena {arena_id}: {a['w']} x {a['h']}, layout {spec['layout']}, light {spec['light']}, built from {where} (seed {spec['seed']}).",
            "The party starts on the left, the foes on the right" + (" (an ambush: foes also on the flanks)." if spec["ambush"] else "."),
            "You play: " + (", ".join(dm) if dm else "no one") + ". The stage plays the other creatures."]


# -- who is where ------------------------------------------------------------

TILE_FT = 5


class BoardError(combat.RulesError):
    """A move or an attack the board refuses. The message says why."""


def running(campaign_dir: Path, state: dict) -> tuple[str, dict]:
    """The id and the arena of the running combat."""
    arena_id = (state.get("active_encounter") or {}).get("arena")
    a = arena.load(campaign_dir, arena_id) if arena_id else None
    if a is None:
        raise BoardError("no fight on a board is running. Start one with: uv run dnd-cli encounter start goblin:3 --arena")
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
        starts = a["starts"]["foes" if is_foe(state, cid) else "party"]
        w, h = a["w"], a["h"]
        cells = sorted(((x, y) for y in range(h) for x in range(w) if (x, y) not in blocked and (x, y) not in taken),
                       key=lambda c: min(arena.cheb(c, s) for s in starts) * 100 + abs(c[1] - h // 2))
        if not cells:
            raise BoardError("no free cell is left in the arena.")
        a["units"][cid] = {"x": cells[0][0], "y": cells[0][1]}
        taken.add(cells[0])
        added.append(cid)
    return added


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


def melee_attack(rec: dict) -> dict | None:
    """The attack a creature makes with a reaction: its equipped melee weapon, else any melee attack."""
    melee = [x for x in rec["attacks"] if x.get("reach_ft") and x["damage"]]
    return next((x for x in melee if x.get("equipped")), melee[0] if melee else None)


def provokers(campaign_dir: Path, state: dict, a: dict, cid: str, to: tuple[int, int]) -> list[str]:
    """The enemies that get a reaction attack when `cid` steps from where it stands to `to`."""
    if combat.has_condition(state, cid, "disengaged"):
        return []
    here, out = pos(a, cid), []
    for other in a["units"]:
        if other == cid or is_foe(state, other) == is_foe(state, cid):
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
    return [f"{who} takes a reaction attack as {against} leaves its reach."] + combat.attack(
        campaign_dir, state, who, weapon["name"], against, rng=rng, cost="reaction")


def walk(campaign_dir: Path, state: dict, a: dict, cid: str, path: list, rng=None) -> dict:
    """Walk the steps one by one. A creature that is left gets a reaction attack: a creature the stage plays attacks at once;
    a player character is asked (the walk stops, and `a["pending"]` holds the rest of it). Stops if the walker falls."""
    lines, steps = [], []
    for i, cell in enumerate(path):
        cell = tuple(cell)
        for foe in provokers(campaign_dir, state, a, cid, cell):
            if not is_foe(state, foe):
                a["pending"] = {"type": "react", "who": foe, "against": cid, "path": [list(c) for c in path[i:]]}
                return {"steps": steps, "lines": lines, "pending": a["pending"]}
            lines += _react(campaign_dir, state, a, foe, cid, rng)
            if not standing(combat.combatant(campaign_dir, state, cid)):
                return {"steps": steps, "lines": lines, "pending": None}
        a["units"][cid] = {"x": cell[0], "y": cell[1]}
        resources(state, cid)["moved"] = resources(state, cid).get("moved", 0) + 1
        steps.append(list(cell))
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
               if o != attacker and is_foe(state, o) != is_foe(state, attacker) and standing(combat.combatant(campaign_dir, state, o)))
    return {"mode": "ranged", "cover": arena.cover_between(here, there, arena.cover_cells(a)), "dis": near}


def attack(campaign_dir: Path, state: dict, a: dict, attacker: str, weapon: str, target: str, rng=None, cost: str | None = "action",
           adv: bool = False, dis: bool = False, bonus: int = 0, secret: bool = False) -> list[str]:
    """An attack with the board's rules: reach or range, line of sight, cover (-2 or -5 to hit), and an enemy next to an archer."""
    rec = combat.combatant(campaign_dir, state, attacker)
    entry = combat._find_attack(rec, weapon)
    check = attack_check(campaign_dir, state, a, attacker, entry, target)
    lines = combat.attack(campaign_dir, state, attacker, entry["name"], target, rng=rng, cost=cost, adv=adv, secret=secret,
                          bonus=bonus - arena.COVER_BONUS[check["cover"]], dis=dis or check["dis"])
    notes = [f"{target} has {check['cover']} cover: -{arena.COVER_BONUS[check['cover']]} to hit."] if check["cover"] != "none" else []
    return notes + (["An enemy is next to the archer: disadvantage."] if check["dis"] else []) + lines


def approach(campaign_dir: Path, state: dict, a: dict, cid: str, target: str) -> tuple[int, int] | None:
    """The cell `cid` can reach this turn that is nearest to `target` (fewest steps among equals), or None if it cannot get nearer."""
    dist, _ = reachable(campaign_dir, state, a, cid)
    goal = pos(a, target)
    best = min(dist, key=lambda c: (arena.cheb(c, goal), dist[c]))
    return best if best != pos(a, cid) and arena.cheb(best, goal) < arena.cheb(pos(a, cid), goal) else None
