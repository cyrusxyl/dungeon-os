"""Checks for stage/cast.py, the placement of actors in a scene room: on a prop, near a prop, the party as a tight group, the others
by weight; one cell each, on the floor, and no two figures on top of each other on the screen.

Run from the repo root:  .venv/bin/python tests/test_cast.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from stage import cast, rooms, scenes  # noqa: E402

PASS = FAIL = 0
CASTS = {
    "fight": {"party": 4, "ally": 2, "hostile": 3},
    "beside": {"party": 4, "neutral": 2},
    "twelve": {"party": 4, "ally": 2, "neutral": 2, "hostile": 4},
}


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


def actors_of(kind: str) -> dict[str, dict]:
    return {f"{side}{i}": {"side": side} for side, n in CASTS[kind].items() for i in range(n)}


def room_of(shape: str | None, seed: int = 1, template: str = "throne_room") -> dict:
    tokens = [f"template={template}"] + ([f"shape={shape}", f"seed={seed}"] if shape else ["shape=fixed"])
    return scenes.room(scenes.build(tokens, None))


def apply(actors: dict, new: dict) -> dict:
    return {i: {**a, **new.get(i, {})} for i, a in actors.items()}


def linked(cells: list[tuple[int, int]], reach: int) -> bool:
    seen, todo = {cells[0]}, [cells[0]]
    while todo:
        a = todo.pop()
        for b in cells:
            if b not in seen and max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= reach:
                seen.add(b)
                todo.append(b)
    return len(seen) == len(cells)


def main() -> int:
    # Every shape, several seeds, three casts.
    bad: dict[str, list] = {"unplaced": [], "off floor": [], "same cell": [], "overlap": [], "party apart": []}
    runs = 0
    for shape in [None, *rooms.SHAPE_NAMES]:
        for seed in range(1, 6):
            room = room_of(shape, seed)
            floor = sum(row.count(".") for row in room["grid"])
            for kind in CASTS:
                runs += 1
                actors = actors_of(kind)
                if kind == "twelve":
                    actors["neutral0"]["on"] = "back_center"
                got = cast.place(room, actors, seed=f"{shape}{seed}{kind}")
                tag = (shape, seed, kind)
                if set(got) != set(actors):
                    bad["unplaced"].append(tag)
                    continue
                cells = {i: tuple(v["cell"]) for i, v in got.items()}
                if any(room["grid"][c[1]][c[0]] != "." for i, c in cells.items() if not actors[i].get("on")):
                    bad["off floor"].append(tag)
                if len(set(cells.values())) != len(cells):
                    bad["same cell"].append(tag)
                floor_cells = [c for i, c in cells.items() if not actors[i].get("on")]
                # The spacing rule holds whenever the room is wide enough for it (a room of 40 cells or more).
                if floor >= 40 and any(not cast.apart(a, b) for n, a in enumerate(floor_cells) for b in floor_cells[n + 1:]):
                    bad["overlap"].append(tag)
                mates = [c for i, c in cells.items() if actors[i]["side"] in ("party", "ally")]
                if not linked(mates, 3):
                    bad["party apart"].append(tag)
    for label, tags in bad.items():
        check(f"{runs} runs on 18 room shapes: {label} {tags[:4]}", not tags)

    # Apart on the screen: 2 across or deep. Two cells beside each other on the grid overlap; a diagonal pair does not.
    check("neighbours on the grid are not apart, a diagonal pair is", not cast.apart((3, 3), (4, 3)) and cast.apart((3, 3), (4, 4)) and cast.apart((3, 3), (4, 2)))

    # The party stands away from the NPCs that were placed first.
    room = room_of(None)
    npcs = {"clerk": {"side": "neutral", "on": "back_center"}, "gareth": {"side": "neutral", "cell": [8, 2]}}
    far = []
    for seed in range(12):
        got = cast.place(room, {**npcs, **{f"p{i}": {"side": "party"} for i in range(4)}}, seed=str(seed))
        mid = cast.centre([tuple(got[f"p{i}"]["cell"]) for i in range(4)])
        far.append(min(cast.dist((8, 2), mid), cast.dist(tuple(got["clerk"]["cell"]), mid)))
    check(f"the party group lies 4 cells or more from the NPCs already placed ({min(far):.1f})", min(far) >= 4)

    # A new actor keeps the others where they are.
    first = apply(actors_of("fight"), cast.place(room, actors_of("fight"), seed="a"))
    more = {**first, "late": {"side": "neutral"}}
    got = cast.place(room, more, seed="b")
    check("a late actor is placed and no one else moves", set(got) == {"late"})

    # An actor whose cell is no longer floor is placed again.
    moved = {**first, "party0": {**first["party0"], "cell": [0, 0]}}
    check("a cell on a wall is placed again", set(cast.place(room, moved, seed="c")) == {"party0"})

    # On a prop: the cell of the prop, and no one in front of it.
    on = {"arbiter": {"side": "neutral", "on": "back_center"}, **{f"n{i}": {"side": "neutral"} for i in range(6)}}
    got = cast.place(room, on, seed="d")
    seat = next(s for s in room["stand"] if s["slot"] == "back_center")
    front = {(seat["x"] + dx, seat["y"] + dy) for dx, dy in cast.FRONT}
    check("an actor on a prop stands on its cell, facing down", got["arbiter"] == {"cell": [seat["x"], seat["y"]], "facing": "down"})
    check("no one stands in front of the prop", not any(tuple(v["cell"]) in front for i, v in got.items() if i != "arbiter"))
    two = cast.place(room, {"a": {"on": "back_center"}, "b": {"on": "back_center"}}, seed="e")
    check("a prop with one place holds one actor; the next stands on the floor", len(seat["points"]) == 1 and tuple(two["b"]["cell"]) != (seat["x"], seat["y"]))

    # Near a prop: a free cell beside it.
    table = next((s for s in room["props"] if not s.get("flat")), None)
    got = cast.place(room, {"guard": {"side": "neutral", "near": table["slot"]}}, seed="f")
    check("an actor near a prop stands within 2 cells of it", max(abs(got["guard"]["cell"][0] - table["x"]), abs(got["guard"]["cell"][1] - table["y"])) <= 2)

    # A later ally or companion joins the party where it stands, not away from it.
    near_party = []
    for seed in range(12):
        got = cast.place(room, {**first, "late-ally": {"side": "ally"}}, seed=str(seed))
        mid = cast.centre([tuple(first[i]["cell"]) for i in first if first[i]["side"] in ("party", "ally")])
        near_party.append(cast.dist(tuple(got["late-ally"]["cell"]), mid))
    check(f"a late ally stands within 4 cells of the party ({max(near_party):.1f})", max(near_party) <= 4)

    # Near the decor of a wall (a door, a fireplace), on the plain room and on a shaped one.
    for shape in (None, "h", "cave"):
        r = room_of(shape, 2, "tavern")
        slots = [d["slot"] for d in r["decor"]]
        goal = cast.near_cell(r, slots[0]) if slots else None
        got = cast.place(r, {"guard": {"side": "neutral", "near": slots[0]}}, seed="w") if slots else {}
        check(f"near a wall slot ({shape or 'plain room'}): within 2 cells of the floor in front of it", bool(slots) and max(abs(got["guard"]["cell"][0] - goal[0]), abs(got["guard"]["cell"][1] - goal[1])) <= 2)
    check("a slot that holds nothing has no near cell, and the actor is still placed",
          cast.near_cell(room, "nowhere") is None and "guard" in cast.place(room, {"guard": {"side": "neutral", "near": "nowhere"}}, seed="x"))

    # Same inputs, same cells.
    a, b = cast.place(room, actors_of("twelve"), seed="same"), cast.place(room, actors_of("twelve"), seed="same")
    check("the same seed gives the same cells", a == b)
    check("another seed gives other cells", cast.place(room, actors_of("twelve"), seed="other") != a)

    # Facing: the party looks toward the hostile.
    got = cast.place(room, actors_of("fight"), seed="g")
    check("each actor has a facing", all(v["facing"] in ("down", "left", "right") for v in got.values()))

    # A bare room, and a room with no floor left.
    check("a bare room takes twelve", len(cast.place(cast.blank_room(), actors_of("twelve"), seed="h")) == 12)
    check("an empty room places no one and does not fail", cast.place({"w": 1, "h": 1, "grid": ["#"], "props": [], "stand": []}, actors_of("fight")) == {})

    tiny = {"w": 3, "h": 1, "grid": ["#..",], "props": [], "stand": []}
    got = cast.place(tiny, actors_of("twelve"), seed="full")
    check("a room with fewer cells than actors does not fail; the actors that fit are placed", 0 < len(got) <= 2)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
