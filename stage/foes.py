"""The stage plays a creature's turn: it scores every legal play and takes the best one.

A play is a cell to walk to (within its speed) and one thing to do from there: an attack, a Multiattack, a spell attack,
or an area ability aimed at a point or a direction. The score is the expected damage, a bonus for a kill, a value for each
creature an area hits (and a cost for each ally in it), less the danger of the cell. The style of the creature sets the
weights (`styles` in stage/data/arena.json). A limited ability (a slot, a recharge, a use a day) must hit two party
members or kill, else the creature uses something cheaper. Abilities the stage cannot read are left to the DM.
See combat-board.md, section 4.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from dnd_cli import abilities, combat, dice
from stage import arena, board

THREAT_COST = 3.0  # the weight of one hero that can reach a cell, against one point of damage
STEP_COST = 0.15


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def style_of(a: dict, rec: dict) -> str:
    """The style of a creature: the fight's `style=` (aggressive by default); a creature with only ranged attacks keeps its distance."""
    style = a["spec"].get("style", "aggressive")
    rolls = board.attack_rolls(rec)
    ranged_only = bool(rolls) and all(not x.get("reach_ft") for x in rolls)
    caster = any(ab.get("spell_level") is not None for ab in rec.get("abilities", []))
    return "skirmisher" if style == "aggressive" and (ranged_only or caster) else style


class Ctx:
    """What the planner reads once: the records, the places, and the lines of sight. Nothing here is written."""

    def __init__(self, campaign_dir: Path, state: dict, a: dict, cid: str):
        self.state, self.a, self.cid = state, a, cid
        self.recs = {c: combat.combatant(campaign_dir, state, c) for c in a["units"]}
        self.rec = self.recs[cid]
        self.pos = {c: board.pos(a, c) for c in a["units"]}
        self.pcs = [c for c in a["units"] if not board.is_foe(state, c) and board.standing(self.recs[c])]
        self.opaque, self.cover = arena.opaque_cells(a), arena.cover_cells(a)
        self.size = (a["w"], a["h"])

    def attack_at(self, entry: dict, p, target: str) -> dict | None:
        """The attack from cell p on `target`: {"ranged", "cover", "dis"}, or None if it cannot reach or cannot see."""
        there = self.pos[target]
        dist = arena.cheb(p, there)
        reach, rng = entry.get("reach_ft", 0) // board.TILE_FT, entry.get("range_ft", 0) // board.TILE_FT
        if dist <= reach:
            return {"ranged": False, "cover": "none", "dis": False}
        if not rng or dist > rng or not arena.clear_line(p, there, self.opaque):
            return None
        near = any(arena.cheb(p, self.pos[c]) <= 1 for c in self.pcs)
        return {"ranged": True, "cover": arena.cover_between(p, there, self.cover), "dis": near}

    def hit_chance(self, bonus: int, target: str, info: dict, adv: bool = False) -> float:
        need = self.recs[target]["ac"] + arena.COVER_BONUS[info["cover"]] - bonus
        p = clamp((21 - need) / 20, 0.05, 0.95)
        if adv and not info["dis"]:
            return 1 - (1 - p) ** 2
        return p * p if info["dis"] and not adv else p

    def average(self, entry: dict) -> float:
        return sum(dice.average(expr) for expr, _ in entry["damage"])

    def threat(self, p) -> int:
        """How many heroes can walk to a cell next to p and strike."""
        return sum(1 for c in self.pcs if arena.cheb(p, self.pos[c]) <= self.recs[c].get("speed_ft", 30) // board.TILE_FT + 1)

    def fail_chance(self, target: str, save: dict) -> float:
        return clamp((save["dc"] - combat.save_bonus(self.recs[target], combat.ability(save["ability"])) - 1) / 20, 0.05, 0.95)


def _kill(ctx: Ctx, target: str, expected: float, weights: dict) -> float:
    return weights["kill"] if ctx.recs[target]["hp"]["current"] <= expected * 1.2 else 0.0


def _weak(ctx: Ctx, target: str, expected: float, weights: dict) -> float:
    rec = ctx.recs[target]
    return weights["weak"] * (1 - rec["hp"]["current"] / max(rec["hp"]["max"], 1)) * expected * 0.5


def attack_options(ctx: Ctx, p, weights: dict, ally_next: dict):
    """(gain, option) for each attack roll, Multiattack and spell attack that works from cell p."""
    rec = ctx.rec
    attacks = {x["name"]: x for x in board.attack_rolls(rec)}
    for target in ctx.pcs:
        adv = "Pack Tactics" in rec.get("traits", []) and ally_next.get(target, False)
        for entry in attacks.values():
            if info := ctx.attack_at(entry, p, target):
                exp = ctx.hit_chance(entry["bonus"], target, info, adv) * ctx.average(entry)
                yield (exp * weights["dmg"] + _kill(ctx, target, exp, weights) + _weak(ctx, target, exp, weights),
                       {"kind": "attack", "entry": entry["name"], "target": target, "info": f"{round(ctx.hit_chance(entry['bonus'], target, info, adv) * 100)}%"})
        for ab in rec.get("abilities", []):
            if not abilities.available(rec, ab):
                continue
            if ab["kind"] == "multiattack":
                parts = [(attacks.get(name), count) for name, count in ab["parts"]]
                infos = [ctx.attack_at(e, p, target) if e else None for e, _ in parts]
                if parts and all(infos):
                    exp = sum(ctx.hit_chance(e["bonus"], target, i, adv) * ctx.average(e) * n for (e, n), i in zip(parts, infos))
                    yield (exp * weights["dmg"] + _kill(ctx, target, exp, weights) + _weak(ctx, target, exp, weights),
                           {"kind": "multiattack", "ability": ab["id"], "target": target, "info": f"{len(parts)} attacks"})
            elif ab["kind"] == "spell_attack" and (info := ctx.attack_at({"name": ab["name"], **ab["attack"]}, p, target)):
                chance = ctx.hit_chance(ab["attack"]["bonus"], target, info)
                exp = chance * sum(dice.average(e) for e, _ in ab["damage"])
                yield (exp * weights["dmg"] + _kill(ctx, target, exp, weights) + _weak(ctx, target, exp, weights),
                       {"kind": "spell_attack", "ability": ab["id"], "target": target, "info": f"{round(chance * 100)}%"})


def aims(ctx: Ctx, p, ab: dict):
    """The aims worth testing for an area ability from cell p: every cell in range for a sphere or a cube, 16 bearings for a cone or a line."""
    shape = ab["shape"]
    w, h = ctx.size
    if shape["type"] in ("cone", "line"):
        length = max(2, shape["size_ft"] // board.TILE_FT)
        seen = set()
        for k in range(16):
            angle = k * math.pi / 8
            cell = (round(p[0] + math.cos(angle) * length), round(p[1] + math.sin(angle) * length))
            if cell != tuple(p) and cell not in seen:  # a direction: the aim may lie past the edge of the map
                seen.add(cell)
                yield cell
        return
    reach = shape["range_ft"] // board.TILE_FT
    for x in range(max(0, p[0] - reach), min(w, p[0] + reach + 1)):
        for y in range(max(0, p[1] - reach), min(h, p[1] + reach + 1)):
            if (x, y) not in ctx.opaque and arena.clear_line(p, (x, y), ctx.opaque):
                yield (x, y)


def zone_options(ctx: Ctx, p, weights: dict):
    """(gain, option) for each area ability aimed from cell p. Heroes in it count; allies in it cost."""
    rec = ctx.rec
    unit_at = {pos: c for c, pos in ctx.pos.items() if c != ctx.cid and (c in ctx.pcs or board.is_foe(ctx.state, c) and board.standing(ctx.recs[c]))}
    for ab in rec.get("abilities", []):
        if ab["kind"] != "zone" or not abilities.available(rec, ab):
            continue
        dmg = sum(dice.average(e) for e, _ in ab["damage"])
        limited = bool(ab.get("uses"))
        for aim in aims(ctx, p, ab):
            cells = arena.shape_cells(ab["shape"], p, aim, ctx.size)
            gain, heroes, kill = 0.0, 0, 0.0
            hit = [(c, ctx.fail_chance(c, ab["save"])) for pos, c in unit_at.items() if pos in cells]
            if tuple(p) in cells and ab["shape"]["type"] not in ("cone", "line"):
                hit.append((ctx.cid, ctx.fail_chance(ctx.cid, ab["save"])))  # the caster is in its own sphere
            for c, fail in hit:
                exp = fail * dmg + (1 - fail) * (dmg / 2 if ab["save"]["success"] == "half" else 0)
                if c in ctx.pcs:
                    gain += exp * weights["dmg"]
                    heroes += 1
                    kill += _kill(ctx, c, exp, weights)
                else:
                    gain -= exp * 1.2
            if heroes >= (2 if limited else 1) or (heroes and kill):
                yield gain + kill, {"kind": "zone", "ability": ab["id"], "aim": list(aim), "info": f"{heroes} target" + ("s" if heroes != 1 else "")}


def plan(campaign_dir: Path, state: dict, a: dict, cid: str, style: str | None = None) -> dict | None:
    """The best play for a creature, as {"p", "steps", "kind", ...}: walk to p, then do the option. None: nothing worth doing."""
    ctx = Ctx(campaign_dir, state, a, cid)
    if not ctx.pcs:
        return None
    weights = arena.arena_data()["styles"][style or style_of(a, ctx.rec)]
    dist, _ = board.reachable(campaign_dir, state, a, cid)
    if combat.turn_used(state, cid)["action"]:
        return None
    allies_of = {t: any(c != cid and c in ctx.pos and board.is_foe(state, c) and board.standing(ctx.recs[c]) and arena.cheb(ctx.pos[c], ctx.pos[t]) <= 1
                        for c in ctx.pos) for t in ctx.pcs}
    best = None
    tiles = list(dist.items())
    area_tiles = {ctx.pos[cid]} | {c for c, _ in sorted(tiles, key=lambda t: min(arena.cheb(t[0], ctx.pos[h]) for h in ctx.pcs))[:12]}
    for p, steps in tiles:
        base = -weights["danger"] * THREAT_COST * ctx.threat(p) - STEP_COST * steps
        base += weights["cover"] if any(ctx.cover.get((p[0] + dx, p[1] + dy)) for dx in (-1, 0, 1) for dy in (-1, 0, 1)) else 0
        base += weights["kite"] * min(arena.cheb(p, ctx.pos[h]) for h in ctx.pcs)
        options = list(attack_options(ctx, p, weights, allies_of))
        if p in area_tiles:
            options += list(zone_options(ctx, p, weights))
        for gain, option in options:
            if gain > 0 and (best is None or gain + base > best["score"]):
                best = {**option, "p": p, "steps": steps, "score": gain + base}
    return best


def describe(campaign_dir: Path, state: dict, a: dict, cid: str) -> dict:
    """What the players see over a creature (its intent), as {"kind", "text"}: the play the planner would make now."""
    rec = combat.combatant(campaign_dir, state, cid)
    if a["control"].get(cid) == "dm":
        return {"kind": "dm", "text": "DM decides"}
    weights = arena.arena_data()["styles"][style_of(a, rec)]
    if (limit := weights.get("flee_below")) and rec["hp"]["current"] <= rec["hp"]["max"] * limit:
        return {"kind": "flee", "text": "Flees"}
    pl = plan(campaign_dir, state, a, cid) or approach_plan(campaign_dir, state, a, cid)
    if pl is None:
        return {"kind": "none", "text": "Waits"}
    name = lambda c: combat.combatant(campaign_dir, state, c)["name"]  # noqa: E731
    kind = pl["kind"]
    if kind == "move":
        return {"kind": "move", "text": f"Moves → {name(pl['target'])}"}
    label = pl.get("entry") or next(x["name"] for x in rec["abilities"] if x["id"] == pl["ability"])
    return {"kind": kind, "text": f"{label} → " + (pl["info"] if kind == "zone" else f"{name(pl['target'])} {pl['info']}")}


def approach_plan(campaign_dir: Path, state: dict, a: dict, cid: str) -> dict | None:
    """No play works from where it can reach: walk toward the nearest hero."""
    pcs = board.standing_pcs(campaign_dir, state, a)
    if not pcs:
        return None
    here = board.pos(a, cid)
    target = min(pcs, key=lambda p: (arena.cheb(here, board.pos(a, p)), combat.combatant(campaign_dir, state, p)["hp"]["current"]))
    dest = board.approach(campaign_dir, state, a, cid, target)
    return {"kind": "move", "p": dest, "target": target, "score": 0.0} if dest else None


def _flee(campaign_dir: Path, state: dict, a: dict, cid: str, rng) -> dict:
    """A creature below its courage runs: it dashes to the cell farthest from every hero."""
    combat.condition(state, cid, "add", "dashing", rounds=1)
    combat.spend_turn(state, cid, "action", quiet=True)
    dist, prev = board.reachable(campaign_dir, state, a, cid)
    pcs = board.standing_pcs(campaign_dir, state, a)
    best = max(dist, key=lambda c: (min(arena.cheb(c, board.pos(a, p)) for p in pcs), -dist[c]))
    lines = [f"{cid} is hurt and flees."]
    if best != board.pos(a, cid):
        out = board.move(campaign_dir, state, a, cid, best, rng=rng)
        return {"lines": lines + out["lines"], "pending": bool(out["pending"])}
    return {"lines": lines, "pending": False}


def play_foe(campaign_dir: Path, state: dict, a: dict, cid: str, rng=None) -> dict:
    """The stage plays one creature's turn. Returns {"lines", "pending"}; `pending` is True when a hero is asked for a reaction
    attack and the turn waits for the answer (the stage plays on from where the creature stands)."""
    rec = combat.combatant(campaign_dir, state, cid)
    weights = arena.arena_data()["styles"][style_of(a, rec)]
    lines = []
    if not board.resources(state, cid).get("recharged"):  # once at the start of the turn, not again after a reaction question
        board.resources(state, cid)["recharged"] = True
        lines = abilities.recharge(rec, rng or random)
    if (limit := weights.get("flee_below")) and rec["hp"]["current"] <= rec["hp"]["max"] * limit and not combat.turn_used(state, cid)["action"]:
        out = _flee(campaign_dir, state, a, cid, rng)
        return {"lines": lines + out["lines"], "pending": out["pending"]}
    pl = plan(campaign_dir, state, a, cid) or approach_plan(campaign_dir, state, a, cid)
    if pl is None:
        return {"lines": lines, "pending": False}
    here = board.pos(a, cid)
    if tuple(pl["p"]) != here:
        lines += _disengage_first(campaign_dir, state, a, cid)
        out = board.move(campaign_dir, state, a, cid, pl["p"], rng=rng)
        lines += out["lines"]
        if out["pending"]:
            return {"lines": lines, "pending": True}
        if not board.standing(combat.combatant(campaign_dir, state, cid)):
            return {"lines": lines, "pending": False}
    try:
        return {"lines": lines + _perform(campaign_dir, state, a, cid, pl, rng), "pending": False}
    except board.BoardError as e:  # the play stopped working (a reaction attack changed the board)
        return {"lines": lines + [f"{cid}: {e}"], "pending": False}


def _disengage_first(campaign_dir: Path, state: dict, a: dict, cid: str) -> list[str]:
    """A creature with Nimble Escape (a bonus Disengage) uses it before it walks away from a hero it stands next to."""
    rec = combat.combatant(campaign_dir, state, cid)
    ab = next((x for x in rec.get("abilities", []) if x.get("effect") == "disengage"), None)
    here = board.pos(a, cid)
    if ab is None or combat.turn_used(state, cid)["bonus"] or combat.has_condition(state, cid, "disengaged") \
            or not any(arena.cheb(here, board.pos(a, p)) <= 1 for p in board.standing_pcs(campaign_dir, state, a)):
        return []
    combat.spend_turn(state, cid, "bonus", quiet=True)
    combat.condition(state, cid, "add", "disengaged", rounds=1)
    return [f"{cid} uses {ab['name']} to slip away without a reaction attack."]


def _perform(campaign_dir: Path, state: dict, a: dict, cid: str, pl: dict, rng) -> list[str]:
    rec = combat.combatant(campaign_dir, state, cid)
    ab = next((x for x in rec.get("abilities", []) if x["id"] == pl.get("ability")), None)
    kind = pl["kind"]
    if kind == "attack":
        return board.attack(campaign_dir, state, a, cid, pl["entry"], pl["target"], rng=rng)
    if kind == "multiattack":
        return board.use_multiattack(campaign_dir, state, a, cid, ab, pl["target"], rng=rng)
    if kind == "spell_attack":
        return board.use_spell_attack(campaign_dir, state, a, cid, ab, pl["target"], rng=rng)
    if kind == "zone":
        return board.use_zone(campaign_dir, state, a, cid, ab, pl["aim"], rng=rng)
    return []  # a move only: it walked, and has nothing in reach
