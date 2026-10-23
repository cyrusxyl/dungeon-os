"""Checks for blocks (blocks.md): made for the full room, shown in the set, cover and sight on the board, the DM's count.

Run from the repo root:  .venv/bin/python tests/test_blocks.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from stage import arena, blocks, cast, scenes  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


def cells(room: dict) -> list[tuple[int, int, str]]:
    return [(p["x"], p["y"], p["kind"]) for p in room["props"] if blocks.is_block(p["kind"])]


def joined(room: dict) -> bool:
    free = {(x, y) for y, row in enumerate(room["grid"]) for x, c in enumerate(row) if c == "."} - {(p["x"], p["y"]) for p in room["props"] if not p.get("flat")}
    return blocks._joined(free)


def spec(**extra) -> dict:
    return {"template": "dungeon", "shape": "l", "seed": 5, "size": "large", **extra}


def test_make() -> None:
    print("blocks are made for the full room")
    full = scenes.room(spec(blocks="auto"), full=True)
    mine = cells(full)
    check("an auto room has blocks of more than one height", len(mine) > 6 and len({k for _x, _y, k in mine}) >= 2)
    check("every block cell is on floor, not on a prop", all(full["grid"][y][x] == "." for x, y, _k in mine)
          and len({(x, y) for x, y, _k in mine} | {(p["x"], p["y"]) for p in full["props"] if not blocks.is_block(p["kind"])}) == len(mine) + sum(not blocks.is_block(p["kind"]) for p in full["props"]))
    check("the floor that is left is one piece", joined(full))
    check("the same seed gives the same blocks", cells(scenes.room(spec(blocks="auto"), full=True)) == mine)
    check("another seed gives other blocks", cells(scenes.room({**spec(blocks="auto"), "seed": 6}, full=True)) != mine)
    wall = sum(any(full["grid"][y + dy][x + dx] != "." for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))) for x, y, _k in mine)
    check(f"some blocks stand against a wall, some do not ({wall} of {len(mine)} cells)", 0 < wall < len(mine))
    check("a place saved before blocks has none", cells(scenes.room(spec(), full=True)) == [] and scenes.room(spec())["blocks_look"] is None)


def test_count() -> None:
    print("the DM's count")
    some = scenes.room(spec(blocks=3), full=True)
    check("blocks=3 makes 3 blocks", len(some["blocks"]) == 3)
    check("blocks=0 makes none", cells(scenes.room(spec(blocks=0), full=True)) == [])
    check("more blocks, more cells", len(cells(scenes.room(spec(blocks=12), full=True))) > len(cells(some)))
    low = {k for _x, _y, k in cells(scenes.room(spec(blocks=10, heights="low"), full=True))}
    tall = {k for _x, _y, k in cells(scenes.room(spec(blocks=10, heights="tall"), full=True))}
    check("heights=low makes no tall block and heights=tall mostly tall ones", "block_tall" not in low and "block_pillar" not in low and "block_tall" in tall)
    check("a bad count or height is refused", all(_raises(lambda b=b: scenes.resolve({**spec(), **b})) for b in ({"blocks": 99}, {"blocks": "many"}, {"blocks": -1}, {"heights": "huge"})))
    built = scenes.build(["template=tavern", "blocks=5", "heights=low"], None)
    check("scene set takes blocks= and heights=", built["blocks"] == 5 and built["heights"] == "low")
    check("a new place gets blocks=auto, with a shape asked or not", scenes.build(["template=tavern"], None)["blocks"] == "auto"
          and scenes.build(["template=tavern", "shape=l"], None)["blocks"] == "auto" and scenes.build(["template=tavern", "shape=fixed"], None)["blocks"] == "auto")
    check("blocks=none is 0", scenes.build(["template=tavern", "blocks=none"], None)["blocks"] == 0)
    check("a saved place keeps what it has", "blocks" not in scenes.build(["mood=night"], {"template": "tavern", "slots": {}, "add": [], "mood": "day"}))


def _raises(fn) -> bool:
    try:
        fn()
    except scenes.SceneError:
        return True
    return False


def test_set() -> None:
    print("the story set shows the same blocks, smaller")
    s, f = scenes.room(spec(blocks="auto")), scenes.room(spec(blocks="auto"), full=True)
    check("the set has blocks, one cell each, fewer than the full room", 0 < len(cells(s)) < len(cells(f)) and len(s["blocks"]) <= len(f["blocks"]))
    check("the floor of the set is one piece", joined(s))
    scaled = {cast.scale_cell((bx, by), f["grid"], s["grid"]) for g in f["blocks"] for bx, by, _k in g}
    check("each block of the set stands within 2 cells of the scaled place of a block of the full room",
          all(any(max(abs(x - sx), abs(y - sy)) <= 2 for sx, sy in scaled) for x, y, _k in cells(s)))
    plain = {"template": "tavern", "shape": "fixed", "blocks": "auto"}
    check("the plain 14 x 11 room is its own set, with the same blocks", cells(scenes.room(plain)) == cells(scenes.room(plain, full=True)) and cells(scenes.room(plain)))
    check("the look comes from the theme table", scenes.room(spec(blocks="auto"))["blocks_look"]["skin"] == "wall"
          and scenes.room({**spec(blocks="auto"), "template": "tavern"})["blocks_look"]["skin"] == "flat")
    check("a place with no walls has flat blocks", scenes.room({"template": "forest", "blocks": "auto"})["blocks_look"]["skin"] == "flat")


def test_board() -> None:
    print("cover and sight")
    check("a low block gives half cover and does not stop sight", arena.board_of("block_low")["cover"] == "half" and not arena.board_of("block_low")["blocks_sight"])
    check("a tall block stops sight and blocks movement", arena.board_of("block_tall")["blocks_sight"] and arena.board_of("block_tall")["blocks_move"])
    check("a half block gives three-quarters cover", arena.board_of("block_half")["cover"] == "three-quarters")
    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp)
        scenes.save(c, "hall", {**spec(blocks="auto"), "slots": {}, "add": [], "mood": "day"})
        actors = {"aragorn": {"side": "party"}, "legolas": {"side": "party"}, "goblin#1": {"side": "hostile"}, "goblin#2": {"side": "hostile"}}
        src = arena.source_of(c, {"scene": "hall", "actors": actors}, {})
        a = arena.generate({"features": [], "hazards": [], "seed": 3}, src, 2, 2, ["aragorn", "legolas"], ["goblin#1", "goblin#2"])
        kinds = [p["kind"] for p in a["props"]]
        check("the fight is in the full room with its blocks", a["spec"]["shape"] == "scene" and sum(blocks.is_block(k) for k in kinds) > 6)
        blocked = arena.blocked_cells(a)
        check("no one starts on a block, and the starts reach each other", not any(tuple(p) in blocked for p in a["starts"]["party"] + a["starts"]["foes"])
              and arena._joined({(x, y) for y in range(a["h"]) for x in range(a["w"])} - blocked, a["starts"]["party"][0]))
        tall = {(p["x"], p["y"]) for p in a["props"] if p["kind"] in ("block_tall", "block_pillar")}
        check("tall blocks stop sight on the board", tall <= arena.opaque_cells(a) and bool(tall))
        low = {(p["x"], p["y"]) for p in a["props"] if p["kind"] == "block_low"}
        check("low blocks give cover on the board", low <= set(arena.cover_cells(a)))


if __name__ == "__main__":
    test_make()
    test_count()
    test_set()
    test_board()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
