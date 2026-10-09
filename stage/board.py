"""The combat board engine: units on an arena, and the rules that need a position.

The turn tracker (`state.json` `active_encounter`, `dnd_cli/combat.py`) keeps the order, the HP, the
conditions and the action pips. This module adds where each unit stands, and the rules of the board:
walking, reach, sight and cover. It calls `combat.py` for rolls and damage. It never calls the DM.
See combat-board.md.
"""

from __future__ import annotations

import time
from pathlib import Path

from dnd_cli import abilities, character, combat
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
    refresh_sight(campaign_dir, state, a)
    refresh_intents(campaign_dir, state, a)
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
    torch = TORCH_TILES if any("torch" in i["name"].lower() for i in sheet.get("inventory", [])) else 0
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


def hidden_foes(campaign_dir: Path, state: dict, a: dict) -> set[str]:
    """The creatures the party cannot see now. They stay out of the board view, the turn bar and the summary."""
    if (vis := visible_cells(campaign_dir, state, a)) is None:
        return set()
    return {c for c in a["units"] if is_foe(state, c) and pos(a, c) not in vis}


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


def attack_rolls(rec: dict) -> list[dict]:
    """The attacks of a creature that roll to hit and do damage (not saving throws, not a spell with no dice)."""
    return [x for x in rec["attacks"] if x["damage"] and "dc" not in x]


def melee_attack(rec: dict) -> dict | None:
    """The attack a creature makes with a reaction: its equipped melee weapon, else any melee attack."""
    melee = [x for x in attack_rolls(rec) if x.get("reach_ft")]
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
               if o != attacker and is_foe(state, o) != is_foe(state, attacker) and standing(combat.combatant(campaign_dir, state, o)))
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
           catch_up: bool = True) -> list[str]:
    """An attack with the board's rules: reach or range, line of sight, cover (-2 or -5 to hit), and an enemy next to an archer.

    `own_turn_only`: the stage refuses an attack out of turn. The DM's `attack` command keeps its way of moving the tracker.
    """
    if own_turn_only and cost != "reaction" and state["active_encounter"].get("current_turn") != attacker:
        raise BoardError(f"it is {state['active_encounter'].get('current_turn')}'s turn, not {attacker}'s.")
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
                          damage_expr=damage_expr, damage_type=damage_type)
    note(a, brief(campaign_dir, state, a, lines, attacker, entry["name"], target))
    notes = [f"{target} has {check['cover']} cover: -{arena.COVER_BONUS[check['cover']]} to hit."] if check["cover"] != "none" else []
    return notes + (["An enemy is next to the archer: disadvantage."] if check["dis"] else []) + lines


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
    hidden = {c for c in a["units"] if is_foe(state, c) and pos(a, c) not in vis} if fog else set()
    seen = ({(x, y) for y, row in enumerate(a["seen"]) for x, c in enumerate(row) if c == "1"} | vis) if fog else None
    units = []
    for cid in a["units"]:
        rec = combat.combatant(campaign_dir, state, cid)
        x, y = pos(a, cid)
        if cid in hidden:
            continue
        u = {"id": cid, "name": rec["name"], "x": x, "y": y, "pc": not is_foe(state, cid), "down": not standing(rec),
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
        "id": arena_id, "w": a["w"], "h": a["h"], "light": a["spec"]["light"],
        "grid": ["".join(c if known(x, y) else " " for x, c in enumerate(row)) for y, row in enumerate(a["grid"])],
        "visible": ["".join("1" if (x, y) in vis else "0" for x in range(a["w"])) for y in range(a["h"])] if fog else None,
        "hazard": "water" if a["spec"]["decor"] == "forest" else "lava",
        "tiles": arena.look_counts(a["look"]),
        "props": [{"id": p["id"], "kind": p["kind"], "x": p["x"], "y": p["y"]} for p in a["props"] if known(p["x"], p["y"])],
        "items": [{"id": i["id"], "name": i["name"], "x": i["x"], "y": i["y"]} for i in a["items"] if known(i["x"], i["y"])],
        "units": units, "current": None if current in hidden else current, "round": enc.get("round", 1),
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
    return next((x for x in pool if x.get("equipped")), pool[0])["name"]


# -- the stage plays the creatures ------------------------------------------------


def standing_pcs(campaign_dir: Path, state: dict, a: dict) -> list[str]:
    return [c for c in a["units"] if not is_foe(state, c) and standing(combat.combatant(campaign_dir, state, c))]


def standing_foes(campaign_dir: Path, state: dict, a: dict) -> list[str]:
    return [c for c in a["units"] if is_foe(state, c) and standing(combat.combatant(campaign_dir, state, c))]


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


def player_attack(campaign_dir: Path, state: dict, a: dict, who: str, target: str | None, weapon: str | None = None) -> list[str]:
    """An attack a player makes from the stage: on their own turn, with the weapon they name or the one that reaches."""
    if target not in a["units"]:
        raise BoardError("pick a target on the board.")
    if target in hidden_foes(campaign_dir, state, a):
        raise BoardError("you cannot see that target.")
    return attack(campaign_dir, state, a, who, weapon or default_weapon(campaign_dir, state, a, who, target), target, own_turn_only=True)


# -- abilities on the board --------------------------------------------------------


def _party_adjacent(campaign_dir: Path, state: dict, a: dict, attacker: str, target: str) -> bool:
    """An ally of `attacker` (up and not the attacker) stands next to `target`: Pack Tactics and Martial Advantage need it."""
    return any(o != attacker and is_foe(state, o) == is_foe(state, attacker) and arena.cheb(pos(a, o), pos(a, target)) <= 1
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
    rec = combat.combatant(campaign_dir, state, cid)
    if not abilities.available(rec, ab):
        raise BoardError(f"{rec['name']} cannot use {ab['name']} now.")
    check = attack_check(campaign_dir, state, a, cid, {"name": ab["name"], **ab["attack"]}, target)
    spend_ability(campaign_dir, state, cid, ab)
    expr, dtype = ab["damage"][0]
    lines = combat.attack(campaign_dir, state, cid, "spell", target, rng=rng, cost=None, damage_expr=expr, damage_type=dtype,
                          bonus=-arena.COVER_BONUS[check["cover"]], dis=check["dis"])
    note(a, brief(campaign_dir, state, a, [ln.replace(" spell ", f" {ab['name']} ", 1) for ln in lines], cid, ab["name"], target))
    return [f"{cid} casts {ab['name']}."] + lines


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
