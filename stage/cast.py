"""Where each actor stands in a scene room. The server runs this for every actor that has no cell, and keeps the cell.

The order of the steps:
 1. An actor `on` a prop stands on the cell of the prop, at a point of its picture. The browser finds the point; the cell is kept here.
 2. An actor `near` a prop takes a free cell next to it.
 3. The party and its allies stand in one tight group, as far from the others as the room allows.
 4. Every other actor takes a cell drawn from a weight map: hostile actors favour cells far from the party, neutral actors cells
    at a middle distance, and no one stands on top of another.
Each choice is made on the screen, not on the grid. A figure is 64 px wide and a cell is 64 px across on the screen, so two
cells (x, y) and (x+1, y) differ by 32 px across and the figures overlap. `apart` is the rule: two actors differ by 2 or more
across (s = x - y) or deep (d = x + y). A room too full for that relaxes the rule to "not the same cell"; no one is left out.
"""

from __future__ import annotations

import math
import random

SPACE = 2  # the least difference across or deep (see above)
AWAY = 8  # the distance from the others at which a group has "enough" room
FRONT = ((1, 0), (0, 1), (1, 1))  # the cells in front of a prop, on the screen: no one stands there when the prop holds someone

PARTY = ("party", "ally")

Cell = tuple[int, int]


def apart(a: Cell, b: Cell, space: int = SPACE) -> bool:
    return abs((a[0] - a[1]) - (b[0] - b[1])) >= space or abs((a[0] + a[1]) - (b[0] + b[1])) >= space


def dist(a: Cell, b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def centre(cells: list[Cell]) -> tuple[float, float] | None:
    return (sum(x for x, _ in cells) / len(cells), sum(y for _, y in cells) / len(cells)) if cells else None


def nearest_free(floor: list[Cell], held, cell: Cell) -> Cell:
    """The free floor cell nearest `cell` (ties: the lowest cell); `cell` itself when there is none."""
    return min((c for c in floor if c not in held), key=lambda c: (dist(c, cell), c), default=cell)


def blank_room(w: int = 14, h: int = 11) -> dict:
    """A room with nothing in it, for a place that has no look yet."""
    return {"w": w, "h": h, "grid": ["." * w for _ in range(h)], "props": [], "stand": []}


def near_cell(room: dict, slot: str) -> Cell | None:
    """The cell to stand near for a slot: the cell of the prop there, or the floor cell in front of a piece of wall decor. None if the slot holds nothing."""
    if prop := next((p for p in room["props"] if p["slot"] == slot), None):
        return prop["x"], prop["y"]
    if d := next((d for d in room.get("decor", []) if d["slot"] == slot), None):
        return (int(d["t"]), d["line"] + 1) if d["wall"] == "n" else (d["line"] + 1, int(d["t"]))
    return None


def place(room: dict, actors: dict[str, dict], seed: str = "") -> dict[str, dict]:
    """The new place of every actor that needs one: {id: {"cell": [x, y], "facing": "down" | "left" | "right"}}.

    `actors`: id -> {"side", "on", "near", "cell"}. An actor keeps its cell while it is on floor of the room. `room` is
    `scenes.room()`: {"grid", "props", "stand"}.
    """
    rng = random.Random(seed)
    solid = {(p["x"], p["y"]) for p in room["props"] if not p.get("flat")}
    floor = [(x, y) for y, row in enumerate(room["grid"]) for x, c in enumerate(row) if c == "." and (x, y) not in solid]
    floor_set = set(floor)
    side = lambda a: a.get("side") or "neutral"  # noqa: E731
    out: dict[str, dict] = {}
    cur: dict[str, Cell] = {}
    keep_clear: set[Cell] = set()
    todo: list[str] = []

    # 1. On a prop: the cell of the prop, whatever the actor held before. The n-th actor on a slot takes its n-th point (see layout.ts).
    used: dict[str, int] = {}
    for aid, a in actors.items():
        spot = next((s for s in room["stand"] if s["slot"] == a.get("on")), None) if a.get("on") else None
        n = used.get(spot["slot"], 0) if spot else 0
        if spot and n < len(spot["points"]):
            used[spot["slot"]] = n + 1
            cur[aid] = (spot["x"], spot["y"])
            keep_clear |= {(spot["x"] + dx, spot["y"] + dy) for dx, dy in FRONT}
            if a.get("cell") != list(cur[aid]) or a.get("facing") != "down":
                out[aid] = {"cell": list(cur[aid]), "facing": "down"}
        elif a.get("cell") and tuple(a["cell"]) in floor_set:
            cur[aid] = tuple(a["cell"])
        else:
            todo.append(aid)
    on_prop = set(out)

    def open_cells(need: int = 1) -> tuple[list[Cell], int]:
        """The cells no one holds that are `apart` from everyone, from `SPACE` down to 1. Too full: any cell left, kept-clear ones too."""
        held = list(cur.values())
        for space in (SPACE, 1):
            cells = [c for c in floor if c not in keep_clear and all(apart(c, o, space) for o in held)]
            if len(cells) >= need:
                return cells, space
        return [c for c in floor if c not in held], 1

    def take(aid: str, cell: Cell) -> None:
        cur[aid] = cell
        out[aid] = {"cell": list(cell), "facing": "down"}

    # 2. Near a prop, or near a piece of wall decor (a door, a fireplace): a free cell around it, the nearest ones likelier.
    for aid in [i for i in todo if actors[i].get("near")]:
        where = near_cell(room, actors[aid]["near"])
        if not where:
            continue
        reach = lambda c: max(abs(c[0] - where[0]), abs(c[1] - where[1]))  # noqa: E731
        around = [c for c in open_cells()[0] if reach(c) <= 2]
        if around:
            take(aid, rng.choices(around, [3.0 if reach(c) <= 1 else 1.0 for c in around])[0])
            todo.remove(aid)

    # 3. The party in one tight group, away from everyone placed.
    mates = [i for i in todo if side(actors[i]) in PARTY]
    cells, space = open_cells(len(mates)) if mates else ([], 1)
    if mates and cells:
        # A party that is already on stage is the place to join: the newcomers stand around its middle. Else the group goes where it is
        # far from everyone placed.
        home = centre([c for i, c in cur.items() if side(actors[i]) in PARTY])
        others = [c for i, c in cur.items() if side(actors[i]) not in PARTY]
        best: list[Cell] = []
        score = -math.inf
        for anchor in [min(cells, key=lambda c: (dist(c, home), c))] if home else rng.sample(cells, min(len(cells), 24)):
            pick: list[Cell] = []
            for c in sorted(cells, key=lambda c: (dist(c, anchor), c)):
                if all(apart(c, p, space) for p in pick):
                    pick.append(c)
                    if len(pick) == len(mates):
                        break
            if len(pick) < len(mates):
                continue
            away = min((dist(anchor, o) for o in others), default=AWAY)
            got = min(away, AWAY) - 0.6 * sum(dist(c, anchor) for c in pick) / len(pick) + rng.random()
            if got > score:
                best, score = pick, got
        for aid, c in zip(mates, best or cells[: len(mates)]):
            take(aid, c)
            todo.remove(aid)

    # 4. Everyone else, one at a time, by weight.
    party = centre([c for i, c in cur.items() if side(actors[i]) in PARTY])
    for aid in list(todo):
        cells, _ = open_cells()
        if not cells:
            break
        mine = side(actors[aid])
        kin = [c for i, c in cur.items() if side(actors[i]) == mine]
        weights = []
        for c in cells:
            w = 1.0
            if party:
                d = dist(c, party)
                w *= 0.3 + min(d, 10) / 10 * 1.7 if mine == "hostile" else math.exp(-(((d - 5) / 3) ** 2)) + 0.1
            if kin and mine == "hostile":
                w *= 1 + 1.5 * math.exp(-(min(dist(c, k) for k in kin) - 1.5) / 2)  # a hostile band keeps together a little
            w *= 0.4 + min(min((dist(c, o) for o in cur.values()), default=4), 4) / 4 * 0.6  # no crowding
            weights.append(w)
        take(aid, rng.choices(cells, weights)[0])
        todo.remove(aid)

    # Each new floor actor faces the centre of the other group.
    hostile_at = centre([c for i, c in cur.items() if side(actors[i]) == "hostile"])
    party_at = centre([c for i, c in cur.items() if side(actors[i]) in PARTY])
    for aid, v in out.items():
        if aid in on_prop:
            continue
        goal = (hostile_at if side(actors[aid]) in PARTY else party_at) or centre(floor) or (0, 0)
        across = (goal[0] - cur[aid][0]) - (goal[1] - cur[aid][1])
        v["facing"] = "down" if abs(across) < 0.5 else "left" if across < 0 else "right"
    return out
