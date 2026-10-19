"""Actors that walk in a scene room before a fight: they stand still, wander, or patrol, and a player may send a character somewhere.

The engine does all of it; the DM may only name a pattern (`@walk <id> still|wander|patrol`). The rules of walking are those of the
combat board (`arena.reach`: 8 directions, no cutting a corner past a blocking tile, no passing through someone). The code here is
pure: it takes the clock and the random generator, and it gives back the steps taken, so a test can run it without a server.

A step is a change of cell. `Walkers.tick` returns {id: {"cell", "facing"}} for the actors that stepped; the caller keeps them
in the stage state. Steps are not events: they never go in the log (see `Stage.walk_tick`).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from stage import arena, cast

WALKS = ("still", "wander", "patrol")
GO = 0.45  # the same, for a walk a player ordered
STEP = 0.8  # seconds from one step to the next: a calm walk, well over the 300 ms the canvas takes to draw one
PAUSE = {"wander": (6.0, 14.0), "patrol": (3.0, 8.0)}  # the rest after a walk, in seconds
RADIUS = 2  # a wanderer goes this far (in cells) from its anchor
REACH = 30  # the longest walk planned, in steps

Cell = tuple[int, int]


@dataclass
class Ground:
    """What the walkers need of a room: its size, the tiles no one enters, and the tiles one may stand on."""

    size: tuple[int, int]
    blocked: set[Cell]
    floor: list[Cell]


def ground(board: dict) -> Ground:
    """From `arena.room_board(room)`. Besides what blocks a unit in a fight, every prop that is not flat blocks here too (a chair, a bush):
    the placer (`cast.place`) keeps actors off those cells, and a walker that stopped on one would be placed again at the next beat."""
    blocked = arena.blocked_cells(board) | {(p["x"], p["y"]) for p in board["props"] if not p.get("flat")}
    w, h = board["w"], board["h"]
    return Ground((w, h), blocked, [(x, y) for y in range(h) for x in range(w) if (x, y) not in blocked])


def default_walk(aid: str, actor: dict) -> str:
    """The pattern an actor has when the DM names none. A pure function of the id and the actor, so nothing needs to be logged."""
    if actor.get("on") or actor.get("near"):
        return "still"
    side = actor.get("side") or "neutral"
    if side == "party":
        return "still"  # a player's character moves when its player says
    if side == "ally":
        return "wander"  # a companion stays about the party
    roll = random.Random(f"walk:{aid}").random()
    if side == "hostile":
        return "patrol" if roll < 0.4 else "still"
    return "still" if roll < 0.5 else "wander" if roll < 0.85 else "patrol"


def facing_of(a: Cell, b: Cell) -> str:
    """The way an actor looks after a step from a to b (the rule of `facing` in lib/iso.ts)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx + dy < 0:
        return "up"
    return "left" if dx - dy < 0 else "right" if dx - dy > 0 else "down"


def find_path(g: Ground, start: Cell, target: Cell, occupied=frozenset(), limit: int = REACH) -> list[Cell] | None:
    """The steps from start to target (not counting start), or None when there is no way within `limit` steps."""
    if start == target or target in occupied or target in g.blocked:
        return None
    dist, prev = arena.reach(start, limit, g.blocked, g.size, occupied)
    return arena.path_from(prev, start, target) if target in dist else None


class Walkers:
    """The walk of every actor of the scene on stage. Forget it (`reset`) when the scene changes."""

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.w: dict[str, dict] = {}

    def reset(self) -> None:
        self.w.clear()

    def _slot(self, aid: str, at: Cell, now: float) -> dict:
        """The walk state of an actor. An actor that is new, or was placed again, starts afresh from where it stands."""
        w = self.w.get(aid)
        if w is None or w["at"] != at:
            w = self.w[aid] = {"at": at, "home": at, "path": [], "go": False, "next": now + self.rng.uniform(1, 8), "route": None, "i": 0}
        return w

    def order(self, aid: str, at: Cell, path: list[Cell], now: float) -> None:
        """A player's order: walk this path now, whatever the pattern."""
        w = self._slot(aid, at, now)
        w.update(path=list(path), go=True, goal=path[-1], next=now)

    def busy(self, aid: str) -> bool:
        return bool(self.w.get(aid, {}).get("path"))

    def tick(self, now: float, actors: dict[str, dict], g: Ground) -> dict[str, dict]:
        """One look at every actor: those whose time has come take a step. Result: {id: {"cell": [x, y], "facing"}} for those that moved."""
        cells = {i: tuple(a["cell"]) for i, a in actors.items() if a.get("cell")}
        for gone in set(self.w) - set(cells):
            del self.w[gone]
        seated = [c for i, c in cells.items() if actors[i].get("on")]
        keep = {(x + dx, y + dy) for x, y in seated for dx, dy in cast.FRONT}  # no one stops in front of someone on a prop
        pcs = [c for i, c in cells.items() if actors[i].get("side") == "party"] or [c for i, c in cells.items() if actors[i].get("side") == "ally"]
        party_at = cast.centre(pcs)
        moves: dict[str, dict] = {}
        for aid, a in actors.items():
            if aid not in cells or a.get("on") or a.get("down"):
                self.w.pop(aid, None)
                continue
            w = self._slot(aid, cells[aid], now)
            if now < w["next"]:
                continue
            mode = a.get("walk") or default_walk(aid, a)
            others = {c for i, c in cells.items() if i != aid}
            if not w["path"]:
                w["go"] = False
                if mode != "still":
                    w["path"] = self._plan(aid, a, w, mode, others, g, keep, party_at)
                if not w["path"]:
                    w["next"] = now + (self.rng.uniform(*PAUSE[mode]) if mode != "still" else 2.0)
                    continue
            nxt = w["path"][0]
            if nxt in g.blocked:  # the room changed under the walk (a look was set): plan again
                w["path"], w["go"], w["next"] = [], False, now + 0.6
                continue
            if nxt in others:  # someone stands there now: an order goes round them, a pattern plans again later
                again = find_path(g, cells[aid], w["goal"], others) if w["go"] else None
                if again:
                    w["path"], w["next"] = again, now + 0.3
                else:
                    w["path"], w["go"], w["next"] = [], False, now + 0.6
                continue
            here = cells[aid]
            w["path"].pop(0)
            w["at"] = cells[aid] = nxt
            moves[aid] = {"cell": list(nxt), "facing": facing_of(here, nxt)}
            w["next"] = now + (GO if w["go"] else STEP)
            if not w["path"]:
                ordered, w["go"] = w["go"], False
                w["next"] = now + (GO if ordered or mode not in PAUSE else self.rng.uniform(*PAUSE[mode]))
        return moves

    def _plan(self, aid: str, a: dict, w: dict, mode: str, others: set[Cell], g: Ground, keep: set[Cell], party_at) -> list[Cell]:
        here = w["at"]
        spaced = lambda c: c not in keep and c not in others and all(cast.apart(c, o) for o in others)  # noqa: E731
        if mode == "wander":
            anchor = party_at if a.get("side") == "ally" and party_at else w["home"]
            near = [c for c in g.floor if c != here and cast.dist(c, anchor) <= RADIUS and spaced(c)]
            self.rng.shuffle(near)
            for target in near[:5]:
                if path := find_path(g, here, target, others):
                    return path
            return []
        if w["route"] is None:
            w["route"] = self._route(w["home"], g, keep)
        route = w["route"]
        if not route:
            return []
        if here == route[w["i"] % len(route)]:
            w["i"] += 1
        return find_path(g, here, route[w["i"] % len(route)], others) or []

    def _route(self, home: Cell, g: Ground, keep: set[Cell]) -> list[Cell]:
        """A patrol: the waypoints of a line (two) or a loop (three), 4 or more cells from each other, in the floor joined to home."""
        dist, _ = arena.reach(home, 10, g.blocked, g.size)
        pool = [c for c, d in dist.items() if d >= 4 and c not in keep]
        self.rng.shuffle(pool)
        want = 2 if self.rng.random() < 0.5 else 3
        route: list[Cell] = []
        for c in pool:
            if all(arena.cheb(c, r) >= 4 for r in route):
                route.append(c)
                if len(route) == want:
                    break
        return route if len(route) >= 2 else []
