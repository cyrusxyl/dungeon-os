"""Checks for the story set (compact-set.md): a scene shows a small room, a fight is in the full room, and each actor keeps its place.

Run from the repo root:  .venv/bin/python tests/test_set.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from stage import arena, beat, board, cast, rooms, scenes, state  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


def box(grid: list[str]) -> tuple[int, int]:
    return cast.floor_box(grid)[2:]


def test_rooms() -> None:
    print("the set is a squeeze of the full room")
    big = same = 0
    bad = []
    for shape in rooms.SHAPE_NAMES:
        for seed in range(1, 7):
            spec = {"template": "tavern", "shape": shape, "seed": seed, "size": "large"}
            s, f = scenes.room(spec), scenes.room(spec, full=True)
            sw, sh = box(s["grid"])
            fw, fh = box(f["grid"])
            floor = sum(row.count(".") for row in s["grid"])
            if (sw, sh) == (fw, fh):
                same += 1
            else:
                big += 1
            lim = rooms.SET_BOX if fw >= fh else rooms.SET_BOX[::-1]
            tilt = (sw > sh) - (sw < sh) == (fw > fh) - (fw < fh) or abs(fw - fh) <= 2  # a tall room stays tall, a wide one wide
            if not (sw <= lim[0] and sh <= lim[1] or (sw, sh) == (fw, fh)) or floor < rooms.MIN_PART or not tilt:
                bad.append((shape, seed, (sw, sh), (fw, fh)))
    check(f"{big} big rooms squeezed, {same} kept as they were; never over the box unless kept; tall stays tall; floor of 40 cells or more {bad[:3]}", not bad and big > 20)
    spec = {"template": "tavern", "shape": "l", "seed": 5, "size": "large"}
    s, f = scenes.room(spec), scenes.room(spec, full=True)
    check("the set is smaller than the full room", box(s["grid"])[0] * box(s["grid"])[1] < box(f["grid"])[0] * box(f["grid"])[1])
    check("the full room is the room the scene had before", f["w"] > s["w"] or f["h"] > s["h"])
    check("same seed, same set", scenes.room(spec) == s)
    # The silhouette is kept: a floor cell of the set is a floor cell of the full room at the same relative place.
    ok = all(f["grid"][cast.scale_cell((x, y), s["grid"], f["grid"])[1]][cast.scale_cell((x, y), s["grid"], f["grid"])[0]] == "."
             for y, row in enumerate(s["grid"]) for x, c in enumerate(row) if c == ".")
    check("every floor cell of the set lies on floor of the full room at the same relative place", ok)
    plain = {"template": "tavern", "shape": "fixed"}
    check("the plain 14 x 11 room is its own set", scenes.room(plain) == scenes.room(plain, full=True))
    check("the set has a picture of its own size", scenes.room_png(spec) != scenes.room_png(spec, full=True))


def test_scale() -> None:
    print("cast.scale_cell")
    a = ["#####", "#...#", "#...#", "#####"]
    b = ["#########", "#.......#", "#.......#", "#.......#", "#.......#", "#########"]
    check("the same room maps a cell to itself", all(cast.scale_cell((x, y), a, a) == (x, y) for x in (1, 2, 3) for y in (1, 2)))
    check("the first and the last cell keep their order, near the corners", cast.scale_cell((1, 1), a, b) == (2, 2) and cast.scale_cell((3, 2), a, b) == (6, 4))
    check("the middle goes to the middle", cast.scale_cell((2, 1), a, b) in {(3, 2), (4, 2), (4, 1)})
    check("a round trip stays near", all(abs(cast.scale_cell(cast.scale_cell((x, y), a, b), b, a)[0] - x) <= 1 for x in (1, 2, 3) for y in (1, 2)))


def test_fight() -> None:
    print("a fight keeps each actor at the same relative place")
    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp)
        spec = {"template": "tavern", "shape": "rect", "seed": 4, "size": "large", "mood": "day", "slots": {}, "add": []}
        scenes.save(c, "inn", spec)
        small, full = scenes.room(spec), scenes.room(spec, full=True)
        actors = {"aragorn": {"side": "party"}, "legolas": {"side": "party"}, "goblin#1": {"side": "hostile"}, "goblin#2": {"side": "hostile"}}
        src = arena.source_of(c, {"scene": "inn", "actors": actors}, {})
        check("the source has the full room", src["room"] == full and src["room"]["grid"] != small["grid"])
        placed = cast.place(small, actors, seed="inn")
        a = arena.generate({"features": [], "hazards": [], "seed": 3}, src, 2, 2, ["aragorn", "legolas"], ["goblin#1", "goblin#2"])
        check("the arena is the full room", a["grid"] == full["grid"] and a["w"] == full["w"])
        near = []
        for i, who in enumerate(["aragorn", "legolas"]):
            want = cast.scale_cell(tuple(placed[who]["cell"]), small["grid"], full["grid"])
            got = tuple(a["starts"]["party"][i])
            near.append(max(abs(got[0] - want[0]), abs(got[1] - want[1])) <= 3)
        for i, who in enumerate(["goblin#1", "goblin#2"]):
            want = cast.scale_cell(tuple(placed[who]["cell"]), small["grid"], full["grid"])
            got = tuple(a["starts"]["foes"][i])
            near.append(max(abs(got[0] - want[0]), abs(got[1] - want[1])) <= 3)
        check("each start is within 3 cells of the scaled cell of the set", all(near))
        check("the fight is in this room, so the sheet comes from the full room", a["spec"]["shape"] == "scene" and a["scene_spec"]["seed"] == 4)
        # The end: the units go back to the set.
        a["units"] = {"aragorn": {"x": a["starts"]["party"][0][0], "y": a["starts"]["party"][0][1]},
                      "goblin#1": {"x": a["starts"]["foes"][0][0], "y": a["starts"]["foes"][0][1]}}
        st = {"active_encounter": {"monsters": {"goblin#1": {"hp": {"current": 0, "max": 7}}}}}
        end = board.outcome(c, st, a)
        check("the end of a fight gives cells in the set", set(end["cells"]) == {"aragorn", "goblin#1"} and all(
            small["grid"][v["cell"][1]][v["cell"][0]] != "-" and 0 <= v["cell"][0] < small["w"] and 0 <= v["cell"][1] < small["h"] for v in end["cells"].values()))
        check("a foe that is down is listed down", end["down"] == ["goblin#1"])


def test_old_logs() -> None:
    print("old logs and old DM text")
    s = state.apply(state.empty(), {"type": "scene", "location": "hall", "party": ["sireth"]})
    s = state.apply(s, {"type": "place", "scene": "hall", "cells": {"sireth": {"cell": [3, 4], "facing": "down"}}})
    after = state.apply(state.apply(s, {"type": "walk", "actor": "sireth", "walk": "patrol"}), {"type": "stand", "scene": "hall", "actor": "sireth", "cell": [9, 9]})
    check("old walk and stand events change no cell", after["actors"]["sireth"]["cell"] == [3, 4] and "walk" not in after["actors"]["sireth"])
    check("@walk in a beat does nothing", beat.parse("@walk sireth wander\n@narrate Hi.") == beat.parse("@narrate Hi."))


if __name__ == "__main__":
    test_rooms()
    test_scale()
    test_fight()
    test_old_logs()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
