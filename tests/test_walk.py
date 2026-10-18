"""Checks for stage/walk.py: actors that stand still, wander, patrol or obey an order in a scene room, by the rules of the combat board.

Run from the repo root:  .venv/bin/python tests/test_walk.py
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from stage import arena, cast, rooms, scenes, walk  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


def setup(shape: str | None = None, seed: int = 1, template: str = "tavern"):
    tokens = [f"template={template}"] + ([f"shape={shape}", f"seed={seed}"] if shape else ["shape=fixed"])
    room = scenes.room(scenes.build(tokens, None))
    return room, walk.ground(arena.room_board(room))


def run(actors: dict, g: walk.Ground, seconds: float, seed: int = 1, walkers: walk.Walkers | None = None):
    """Tick for `seconds` of game time; keep the moves in `actors` like the server. Result: (walkers, the cells each actor stood on)."""
    walkers = walkers or walk.Walkers(random.Random(seed))
    seen: dict[str, list] = {i: [tuple(a["cell"])] for i, a in actors.items()}
    t = 0.0
    while t < seconds:
        for i, v in walkers.tick(t, actors, g).items():
            actors[i] = {**actors[i], **v}
            seen[i].append(tuple(v["cell"]))
        t += 0.15
    return walkers, seen


def main() -> int:
    room, g = setup()
    spots = [c for c in g.floor if all(arena.cheb(c, o) >= 3 for o in [(5, 4)])]

    # Still: no one moves.
    actors = {"a": {"cell": [3, 3], "walk": "still"}, "seat": {"cell": [5, 2], "on": "back_center", "walk": "wander"}}
    _, seen = run(actors, g, 60)
    check("a still actor and a seated one never move", len(set(seen["a"])) == 1 and len(set(seen["seat"])) == 1)

    # Wander: steps are legal, and it stays near home.
    actors = {"w": {"cell": [4, 5], "walk": "wander", "side": "neutral"}}
    _, seen = run(actors, g, 120)
    path = seen["w"]
    check("a wanderer walks", len(set(path)) > 2)
    check("every step lands on a tile that does not block", all(c not in g.blocked for c in path))
    check("every step is one cell, no corner cut", all(arena.cheb(a, b) == 1 and not (a[0] != b[0] and a[1] != b[1] and ((b[0], a[1]) in g.blocked or (a[0], b[1]) in g.blocked)) for a, b in zip(path, path[1:]) if a != b))
    check("a wanderer stays within its radius of home (+ the walk round a prop)", max(cast.dist(c, (4, 5)) for c in path) <= walk.RADIUS + 1)

    # Patrol: it goes from end to end and comes back, along legal steps.
    actors = {"p": {"cell": [3, 3], "walk": "patrol", "side": "hostile"}}
    walkers, seen = run(actors, g, 240, seed=3)
    route = walkers.w["p"]["route"]
    path = seen["p"]
    check("a patrol has a route of 2 or 3 waypoints, 4 cells or more apart", len(route) in (2, 3) and all(arena.cheb(a, b) >= 4 for a in route for b in route if a != b))
    check("a patrol reaches every waypoint and starts over", all(r in path for r in route) and sum(path.count(r) for r in route) > len(route))
    check("a patrol steps on legal tiles", all(c not in g.blocked for c in path))

    # No two on a cell, whatever they do.
    actors = {f"n{i}": {"cell": list(c), "walk": "wander", "side": "neutral"} for i, c in enumerate([(2, 2), (3, 3), (4, 4), (6, 5), (7, 6), (8, 3)])}
    walkers = walk.Walkers(random.Random(5))
    clash = False
    t = 0.0
    while t < 200:
        for i, v in walkers.tick(t, actors, g).items():
            actors[i] = {**actors[i], **v}
        cells = [tuple(a["cell"]) for a in actors.values()]
        clash |= len(set(cells)) != len(cells)
        t += 0.15
    check("six wanderers never share a cell", not clash)

    # An order: the path is walked step by step, with the combat rules, then the actor rests.
    actors = {"pc": {"cell": [2, 2], "side": "party"}}
    walkers = walk.Walkers(random.Random(1))
    steps = walk.find_path(g, (2, 2), (8, 6), set())
    check("a path to a far cell exists", bool(steps) and steps[-1] == (8, 6) and len(steps) >= 6)
    walkers.order("pc", (2, 2), steps, 0.0)
    _, seen = run(actors, g, 30, walkers=walkers)
    check("an order is walked to its end", seen["pc"][-1] == (8, 6) and seen["pc"][1:] == steps)
    check("a cell that blocks or is taken has no path", walk.find_path(g, (2, 2), (0, 0), set()) is None and walk.find_path(g, (2, 2), (8, 6), {(8, 6)}) is None)
    check("a path round someone", all(c != (3, 3) for c in walk.find_path(g, (2, 2), (4, 4), {(3, 3)}) or []))

    # A new cell from the placer starts a fresh walk (no stale path).
    actors = {"a": {"cell": [2, 2], "walk": "wander", "side": "neutral"}}
    walkers, _ = run(actors, g, 20, seed=2)
    actors["a"] = {**actors["a"], "cell": [7, 5]}
    walkers.tick(100.0, actors, g)
    check("an actor placed again forgets its old walk", walkers.w["a"]["home"] == (7, 5))

    # Facing.
    check("facing follows the step on the screen", [walk.facing_of((3, 3), b) for b in [(4, 3), (3, 4), (4, 4), (2, 2), (4, 2)]] == ["right", "left", "down", "up", "right"])

    # Defaults.
    check("a seat, a PC and a companion", walk.default_walk("x", {"on": "back_center"}) == "still" and walk.default_walk("x", {"side": "party"}) == "still"
          and walk.default_walk("x", {"side": "ally"}) == "wander" and walk.default_walk("x", {"side": "neutral", "near": "back_center"}) == "still")
    mix = {walk.default_walk(f"npc{i}", {"side": "neutral"}) for i in range(40)}
    check("neutral NPCs come out still, wandering and patrolling", mix == {"still", "wander", "patrol"})
    check("the default is the same every time", walk.default_walk("gareth", {"side": "neutral"}) == walk.default_walk("gareth", {"side": "neutral"}))

    # Every shape: a wanderer and a patroller take legal steps.
    bad = []
    for shape in rooms.SHAPE_NAMES:
        r, gg = setup(shape, 2)
        floor = [c for c in gg.floor]
        for mode in ("wander", "patrol"):
            actors = {"x": {"cell": list(floor[len(floor) // 2]), "walk": mode, "side": "neutral"}}
            _, seen = run(actors, gg, 120, seed=7)
            if any(c in gg.blocked for c in seen["x"]):
                bad.append((shape, mode))
    check(f"on 17 room shapes every step is on open floor {bad}", not bad)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
