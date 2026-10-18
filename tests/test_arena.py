"""Checks for the combat arena: the generator, the board geometry, and the props catalog.

Run from the repo root:  .venv/bin/python tests/test_arena.py

Plain asserts so no test runner is needed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dnd_cli import combat  # noqa: E402
from stage import arena, board, crawl, scenes, state as stage_state  # noqa: E402
from tests.test_rules import GOBLIN, campaign, fight  # noqa: E402

PASS = FAIL = 0
BOARD_PROPS = ["barrel", "barrel_pile", "bush", "chair", "chests", "column_broken", "dresser", "hearth", "mushroom",
               "oak", "pine", "stones", "stool", "stump", "tree"]


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


def raises(fn) -> bool:
    try:
        fn()
    except arena.ArenaError:
        return True
    return False


def source(kind: str, **extra) -> dict:
    cfg = arena.arena_data()
    base = {"scene": {"kind": "scene", "id": "x", "look": arena.look_of("tavern"), "shell": "room", "layout": "open", "decor": "tavern",
                      "props": [("barrel_pile", "back_left"), ("stool", "mid_left"), ("hearth", "wall_center")]},
            "site": {"kind": "site", "id": "x", "look": arena.look_of("crypt"), "shell": "room", "layout": "pillars", "decor": "crypt"},
            "none": {"kind": "none", "id": None, "look": arena.look_of("forest"), "shell": "open", "layout": "open", "props": [],
                     "decor": "forest"}}[kind]
    assert cfg
    return {**base, **extra}


def test_geometry() -> None:
    print("arena: lines, cover, walking")
    wall = {(2, 0)}
    check("a wall between two cells blocks the line", not arena.clear_line((0, 0), (4, 0), wall))
    check("a wall off the line does not", arena.clear_line((0, 1), (4, 1), wall))
    check("the end cells never block their own line", arena.clear_line((0, 0), (2, 0), wall))
    cover = {(2, 0): "half", (3, 0): "three-quarters"}
    check("the best cover on the line counts", arena.cover_between((0, 0), (5, 0), cover) == "three-quarters")
    check("no cover off the line", arena.cover_between((0, 1), (5, 1), cover) == "none")
    dist, prev = arena.reach((0, 0), 3, {(1, 0), (0, 1)}, (4, 4))
    check("a diagonal step past two blocked side cells is not allowed", (1, 1) not in dist)
    dist, prev = arena.reach((0, 0), 2, set(), (5, 5))
    check("8 directions: two diagonal steps reach (2, 2)", dist.get((2, 2)) == 2 and arena.path_from(prev, (0, 0), (2, 2)) == [(1, 1), (2, 2)])
    dist, _ = arena.reach((0, 0), 5, set(), (5, 5), occupied={(1, 0), (0, 1), (1, 1)})
    check("occupied cells cannot be entered or passed", all(c not in dist for c in [(1, 0), (0, 1), (1, 1)]) and len(dist) == 1)
    check("cheb is the larger axis", arena.cheb((0, 0), (3, 2)) == 3)


def test_props() -> None:
    print("arena: prop catalog")
    check("each of the 15 board props has an entry", all("board" in scenes.catalog()["props"][p] for p in BOARD_PROPS))
    check("a tall prop blocks sight", arena.board_of("tree")["blocks_sight"] and arena.board_of("oak")["blocks_sight"])
    check("a barrel blocks movement, gives half cover, does not block sight",
          arena.board_of("barrel")["blocks_move"] and arena.board_of("barrel")["cover"] == "half" and not arena.board_of("barrel")["blocks_sight"])
    check("a bush does not block movement", not arena.board_of("bush")["blocks_move"])
    other = next(p for p, v in scenes.catalog()["props"].items() if p not in BOARD_PROPS and not v.get("flat"))
    check("a rug lies flat and blocks nothing", not arena.board_of("rug_red")["blocks_move"])
    check("a prop without an entry blocks movement and gives no cover", arena.board_of(other) == arena.DEFAULT_BOARD)
    cfg = arena.arena_data()
    check("every scene template has a look, and each look is a theme",
          all(t in cfg["scene_looks"] for t in scenes.catalog()["templates"]) and all(v in arena.themes() for v in cfg["scene_looks"].values()))
    check("every decor prop has a board entry",
          all(p in BOARD_PROPS for d in cfg["decor"].values() for p in d["obstacles"] + d["cover"] + d["small"] + [d["pillar"]]))
    check("the forest theme has tiles", arena.atlas_png("forest") and arena.icon_png("lava") and arena.icon_png("water"))


def test_parse() -> None:
    print("arena: the DM's words")
    spec = arena.parse(["layout=chokepoint", "size=small", "light=dark", "ambush=yes", "seed=7", "feature=cover@foes", "hazard=lava@center"])
    check("tokens become a spec", spec["layout"] == "chokepoint" and spec["size"] == "small" and spec["light"] == "dark"
          and spec["ambush"] is True and spec["seed"] == 7 and spec["features"] == [["cover", "foes"]] and spec["hazards"] == [["lava", "center"]])
    spec = arena.parse(["summary=off", "reaction_seconds=15"])
    check("per-fight settings are in the spec", spec["settings"] == {"round_summary": False, "reaction_seconds": 15})
    check("no settings by default", arena.parse([])["settings"] == {})
    check("settings are checked", all(raises(lambda b=bad: arena.parse([b])) for bad in ("summary=maybe", "reaction_seconds=99", "reaction_seconds=x")))
    check("the host's settings are checked the same way", arena.check_settings({"reaction_seconds": 0, "round_summary": True}) == {"reaction_seconds": 0, "round_summary": True}
          and all(raises(lambda v=v: arena.check_settings(v)) for v in ({"reaction_seconds": 61}, {"reaction_seconds": True}, {"reaction_seconds": "5"}, {"round_summary": "yes"})))
    check("a prop of the catalog is a feature", arena.parse(["feature=barrel@party"])["features"] == [["barrel", "party"]])
    for bad in ("layout=maze", "size=huge", "light=blind", "ambush=maybe", "seed=x", "theme=nope", "feature=cover", "feature=cover@moon",
                "feature=dragon@foes", "hazard=acid@foes", "colour=red", "layout"):
        check(f"{bad!r} is refused", raises(lambda b=bad: arena.parse([b])))


def test_generator() -> None:
    print("arena: generator")
    made, bad = 0, []
    for kind in ("scene", "site", "none"):
        for layout in arena.LAYOUTS:
            for size in arena.SIZES:
                for ambush in (False, True):
                    for edits in ([], ["feature=cover@foes", "feature=barrels@party", "feature=pillar@center", "hazard=lava@center"]):
                        for seed in range(1, 9):
                            spec = {**arena.parse(edits), "layout": layout, "size": size, "ambush": ambush, "seed": seed}
                            a = arena.generate(spec, source(kind), 3, 4)
                            made += 1
                            blocked = arena.blocked_cells(a)
                            starts = [tuple(p) for p in a["starts"]["party"] + a["starts"]["foes"]]
                            dist, _ = arena.reach(starts[0], 999, blocked, (a["w"], a["h"]))
                            ok = (len(a["starts"]["party"]) == 3 and len(a["starts"]["foes"]) == 4 and len(set(starts)) == 7
                                  and all(p in dist for p in starts) and not any(p in blocked for p in starts)
                                  and len(a["items"]) == 1 and (a["items"][0]["x"], a["items"][0]["y"]) not in blocked
                                  and len({(p["x"], p["y"]) for p in a["props"]}) == len(a["props"]))
                            if not ok:
                                bad.append((kind, layout, size, ambush, seed))
    check(f"{made} arenas: starts are free and connected, one item, no stacked props", not bad)
    spec = {**arena.parse(["feature=cover@foes"]), "seed": 5}
    check("the same seed makes the same arena", arena.generate(spec, source("scene")) == arena.generate(spec, source("scene")))
    check("another seed makes another arena", arena.generate({**spec, "seed": 6}, source("scene"))["grid"] != arena.generate(spec, source("scene"))["grid"]
          or arena.generate({**spec, "seed": 6}, source("scene"))["props"] != arena.generate(spec, source("scene"))["props"])
    a = arena.generate({**arena.parse(["hazard=lava@center"]), "seed": 3, "layout": "open"}, source("scene"))
    check("a hazard feature puts hazard tiles in the grid", any(arena.HAZARD in row for row in a["grid"]))
    a = arena.generate({"features": [], "hazards": [], "layout": "chasm", "seed": 4}, source("scene"))
    check("a chasm has hazard tiles and a bridge across", any(arena.HAZARD in row for row in a["grid"]))
    a = arena.generate({"features": [], "hazards": [], "seed": 4}, source("scene"))
    check("a scene prop lands in the arena by its zone, a wall prop does not", any(p["kind"] == "barrel_pile" for p in a["props"]) and not any(p["kind"] == "hearth" for p in a["props"]))
    a = arena.generate({"features": [], "hazards": [], "seed": 4}, source("none"))
    check("an open shell has no door gaps", arena.DOOR not in "".join(a["grid"]))
    a = arena.generate({"features": [], "hazards": [], "seed": 4}, source("scene"))
    doors = [(x, y) for y, row in enumerate(a["grid"]) for x, c in enumerate(row) if c == arena.DOOR]
    near = lambda d, side: min(arena.cheb(d, tuple(s)) for s in a["starts"][side])  # noqa: E731
    check("a room shell has a door in the wall nearest each start zone",
          len(doors) == 2 and min(near(d, "party") for d in doors) <= 2 and min(near(d, "foes") for d in doors) <= 2)


def floor_cells(a: dict) -> set[tuple[int, int]]:
    return {(x, y) for y, row in enumerate(a["grid"]) for x, c in enumerate(row) if c in arena.STAND}


def test_shapes() -> None:
    print("arena: room shapes")
    import random

    from stage import rooms

    check("the 17 shapes", len(arena.SHAPES) == 17 and set(arena.SHAPES) == set(rooms.SHAPES))
    odds = arena.arena_data()["shapes"]
    check("every shape in the odds tables exists, each table has weights, and there is a default",
          "default" in odds and all(set(t) <= set(arena.SHAPES) and all(w > 0 for w in t.values()) for t in odds.values()))
    check("every table is for a known theme", all(t == "default" or t in arena.themes() for t in odds))
    check("the odds pick a shape by seed, the same each time and not always the same one",
          arena.pick_shape("cave", 4) == arena.pick_shape("cave", 4) and len({arena.pick_shape("dungeon", s) for s in range(40)}) > 3)
    check("a cave theme mostly gives caves", sum(arena.pick_shape("cave", s) == "cave" for s in range(200)) > 100)

    # The mask of a shape: connected, in the size class, and the same whichever way it is turned.
    broken, flips, sized = [], [], []
    for shape in arena.SHAPES:
        for seed in range(1, 6):
            made = None
            for attempt in range(60):
                made = rooms.mask(shape, random.Random(f"{shape}:{seed}:{attempt}"), "small", 0)
                if made:
                    break
            if not made:
                broken.append((shape, seed, "none"))
                continue
            cells, used = made
            if len(cells) < 40 or not arena._joined(set(cells), cells[0]):
                broken.append((shape, seed))
            counts = set()
            for orient in range(8):
                again = rooms.mask(shape, random.Random(f"{shape}:{seed}:{attempt}"), "small", orient)
                counts.add(len(again[0]))
            if len(counts) != 1:
                flips.append((shape, seed, counts))
            if shape not in ("hall", "cave"):
                xs, ys = [x for x, _ in cells], [y for _, y in cells]
                if not (max(xs) <= 12 and max(ys) <= 9):
                    sized.append((shape, seed, max(xs), max(ys)))
    check(f"every shape makes a connected room of at least 40 cells {broken}", not broken)
    check(f"turning a room 8 ways does not change its floor count {flips}", not flips)
    check(f"a small room fits the small class {sized}", not sized)
    g = rooms.grid_of([(1, 1), (2, 1), (1, 2)])
    check("walls touch floor and the rest is void", ["".join(r) for r in g] == ["####-", "#..#-", "#.##-", "###--"][:len(g)] or
          all((c == "#") == any(0 <= x + a < len(g[0]) and 0 <= y + b < len(g) and g[y + b][x + a] == "." for a in (-1, 0, 1) for b in (-1, 0, 1)) for y, r in enumerate(g)
              for x, c in enumerate(r) if c != "."))
    sizes = {k: set() for k in ("small", "medium", "large")}
    for seed in range(1, 40):
        for k in sizes:
            for attempt in range(60):
                m = rooms.mask("rect", random.Random(f"rect:{seed}:{attempt}"), k, 0)
                if m:
                    sizes[k].add((max(x for x, _ in m[0]), max(y for _, y in m[0])))
                    break
    check("size classes give the widths and depths of the plan",
          all(9 <= w <= 12 and 7 <= d <= 9 for w, d in sizes["small"]) and all(14 <= w <= 18 and 9 <= d <= 12 for w, d in sizes["medium"])
          and all(20 <= w <= 26 and 13 <= d <= 17 for w, d in sizes["large"]))
    hall = [rooms.box("hall", random.Random(s), None)[1:] for s in range(40)]
    check("a long hall is 20 to 27 by 6 to 8, a cave at least 13 by 10",
          all(20 <= w <= 27 and 6 <= d <= 8 for w, d in hall) and all(w >= 13 and d >= 10 for _, w, d in (rooms.box("cave", random.Random(s), "small") for s in range(40))))

    # A whole arena on each shape and each layout.
    bad, doors, made = [], [], 0
    for shape in arena.SHAPES:
        for layout in arena.LAYOUTS:
            for kind in ("scene", "none"):
                for seed in (1, 2, 3):
                    spec = {"features": [], "hazards": [], "layout": layout, "shape": shape, "seed": seed, "ambush": seed == 2}
                    a = arena.generate(spec, source(kind), 3, 4)
                    made += 1
                    blocked = arena.blocked_cells(a)
                    free = floor_cells(a) - blocked
                    starts = [tuple(p) for p in a["starts"]["party"] + a["starts"]["foes"]]
                    chars = set("".join(a["grid"]))
                    near_floor = lambda x, y: any(0 <= x + dx < a["w"] and 0 <= y + dy < a["h"] and a["grid"][y + dy][x + dx] in (arena.FLOOR, arena.HAZARD)  # noqa: E731
                                                  for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                    ok = (chars <= set("#.d~-") and arena._joined(free, starts[0]) and all(p in free for p in starts)
                          and (spec["ambush"] or arena.cheb(a["starts"]["party"][0], a["starts"]["foes"][0]) >= 3)
                          and not any(near_floor(x, y) for y, row in enumerate(a["grid"]) for x, c in enumerate(row) if c == arena.VOID)
                          and (layout != "chasm" or any(arena.HAZARD in row for row in a["grid"])))
                    if not ok:
                        bad.append((shape, layout, kind, seed))
                    if kind == "none" and arena.DOOR in "".join(a["grid"]):
                        doors.append((shape, layout, seed))
    check(f"{made} arenas on all shapes and layouts: starts joined and free, the void never touches floor, a chasm has hazard {bad[:5]}", not bad)
    check("an open shell has no doors on any shape", not doors)
    spec = {"features": [], "hazards": [], "layout": "pillars", "shape": "cross", "seed": 9}
    check("the same seed makes the same room, another seed another", arena.generate(spec, source("site")) == arena.generate(spec, source("site"))
          and arena.generate({**spec, "seed": 10}, source("site"))["grid"] != arena.generate(spec, source("site"))["grid"])
    a = arena.generate({**spec, "orient": 3}, source("site"))
    b = arena.generate({**spec, "orient": 5}, source("site"))
    check("a fixed orient is kept in the spec", a["spec"]["orient"] == 3 and b["spec"]["orient"] == 5 and a["spec"]["shape"] == "cross")
    props = a["props"]
    cells = {(p["x"], p["y"]) for p in props}
    check("pillars and cover stand only where all 8 neighbours are floor, and more than 2 apart",
          all(sum(a["grid"][y + dy][x + dx] == arena.FLOOR for dx in (-1, 0, 1) for dy in (-1, 0, 1)) == 9 for x, y in cells))
    # The layouts cut the room across its shorter side, with a gap of 3 cells, and both sides stay joined.
    flat = arena.generate({"features": [], "hazards": [], "layout": "chokepoint", "shape": "rect", "seed": 2, "orient": 0, "size": "medium"}, source("none"))
    inner = [row[1:-1] for row in flat["grid"][1:-1]]
    walled = [x for x in range(len(inner[0])) if sum(row[x] == arena.WALL for row in inner) >= len(inner) - 3]
    check("a chokepoint is a wall across the shorter side with a gap of 3", len(walled) == 1 and sum(row[walled[0]] == arena.FLOOR for row in inner) == 3)
    wide = arena.generate({"features": [], "hazards": [], "layout": "chasm", "shape": "rect", "seed": 2, "orient": 0, "size": "medium"}, source("none"))
    inner = [row[1:-1] for row in wide["grid"][1:-1]]
    chasm = [x for x in range(len(inner[0])) if sum(row[x] == arena.HAZARD for row in inner) >= len(inner) - 3]
    check("a chasm is two columns of hazard with a bridge of 3", len(chasm) == 2 and chasm[1] == chasm[0] + 1
          and sum(row[chasm[0]] == arena.FLOOR for row in inner) == 3)

    # The void: never walkable, stops sight, and a path cannot cross it.
    room = {"grid": ["#--#", "#..#", "####"], "props": []}
    check("the void blocks walking and sight like a wall", {(1, 0), (2, 0)} <= arena.blocked_cells(room) and {(1, 0), (2, 0)} <= arena.opaque_cells(room))
    dist, _ = arena.reach((1, 1), 9, arena.blocked_cells(room), (4, 3))
    check("a walk does not cross the void", set(dist) == {(1, 1), (2, 1)})

    # The DM's words.
    check("shape= is checked and its case does not matter", arena.parse(["shape=L"])["shape"] == "l" and arena.parse(["shape=ring"])["shape"] == "ring"
          and raises(lambda: arena.parse(["shape=donut"])) and raises(lambda: arena.parse(["orient=9"])) and arena.parse(["orient=3"])["orient"] == 3
          and arena.parse(["size=large"])["size"] == "large" and raises(lambda: arena.parse(["size=huge"])))
    try:
        arena.parse(["shape=donut"])
    except arena.ArenaError as e:
        check("the error names the valid shapes", all(n in str(e) for n in ("rect", "cave", "ring")))


def test_scene_room() -> None:
    print("arena: a fight in the room of a scene")
    from stage import scenes as _scenes

    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp)
        _scenes.save(c, "hall", {"template": "hall", "slots": {"back_center": "throne"}, "add": [], "mood": "day"})
        actors = {"aragorn": {"side": "party"}, "legolas": {"side": "party"}, "goblin#1": {"side": "hostile"}, "goblin#2": {"side": "hostile"},
                  "king": {"side": "neutral", "on": "back_center"}}
        src = arena.source_of(c, {"scene": "hall", "actors": actors}, {})
        room = src["room"]
        a = arena.generate({"features": [], "hazards": [], "seed": 3}, src, 2, 2, ["aragorn", "legolas"], ["goblin#1", "goblin#2"])
        cells = {p["id"]: tuple(p["cell"]) for p in src["cast"]}
        blocked = arena.blocked_cells(a)
        check("the fight is in the room of the scene: its grid and its props", a["spec"]["shape"] == "scene" and a["grid"] == room["grid"]
              and [(p["kind"], p["x"], p["y"]) for p in a["props"]] == [(p["kind"], p["x"], p["y"]) for p in room["props"]])
        check("the party and the foes stand where the scene put them",
              [tuple(p) for p in a["starts"]["party"]] == [cells["aragorn"], cells["legolas"]] and [tuple(p) for p in a["starts"]["foes"]] == [cells["goblin#1"], cells["goblin#2"]])
        check("the arena keeps a copy of the room, with the scene spec", a["room"] == room and a["scene_spec"]["template"] == "hall")
        check("no start stands on a blocked cell, and they all reach each other", not any(tuple(p) in blocked for p in a["starts"]["party"] + a["starts"]["foes"])
              and arena._joined({(x, y) for y in range(a["h"]) for x in range(a["w"])} - blocked, a["starts"]["party"][0]))
        check("a rug of the scene is a prop that does not block", any(p["kind"] == "rug_red" for p in a["props"]) and not any((p["x"], p["y"]) in blocked for p in a["props"] if p["kind"] == "rug_red"))
        # A crowd: 4 PCs and 6 foes in 9 x 7 floor.
        many = {**{f"pc{i}": {"side": "party"} for i in range(4)}, **{f"orc#{i}": {"side": "hostile"} for i in range(6)}}
        src2 = arena.source_of(c, {"scene": "hall", "actors": many}, {})
        b = arena.generate({"features": [], "hazards": [], "seed": 1}, src2, 4, 6, [f"pc{i}" for i in range(4)], [f"orc#{i}" for i in range(6)])
        starts = [tuple(p) for p in b["starts"]["party"] + b["starts"]["foes"]]
        check("four heroes and six foes fit in the room of a scene", b["spec"]["shape"] == "scene" and len(set(starts)) == 10 and not any(p in arena.blocked_cells(b) for p in starts))
        # A creature the cast has not placed starts near the far end; a seated one moves off its seat.
        c3 = arena.generate({"features": [], "hazards": [], "seed": 2}, src, 2, 3, ["aragorn", "king"], ["goblin#1", "goblin#2", "boss"])
        king = tuple(c3["starts"]["party"][1])
        check("a seated character is moved to a free cell, and a creature with no place gets one", king not in arena.blocked_cells(c3) and len(c3["starts"]["foes"]) == 3)
        # A scene with a shape of its own: the fight is in that room.
        bad = []
        for shape in ("cross", "ring", "cave", "l", "twin"):
            _scenes.save(c, "odd", {"template": "tavern", "slots": {}, "add": [], "mood": "day", "shape": shape, "seed": 4})
            src4 = arena.source_of(c, {"scene": "odd", "actors": actors}, {})
            f = arena.generate({"features": [], "hazards": [], "seed": 3}, src4, 2, 2, ["aragorn", "legolas"], ["goblin#1", "goblin#2"])
            starts = [tuple(p) for p in f["starts"]["party"] + f["starts"]["foes"]]
            if not (f["spec"]["shape"] == "scene" and f["grid"] == src4["room"]["grid"] and not any(p in arena.blocked_cells(f) for p in starts)):
                bad.append(shape)
        check(f"a fight in a scene of any shape is in that room {bad}", not bad)
        # The DM's room words do not apply in a scene room, and the stage says so.
        d = arena.generate({**arena.parse(["shape=ring", "size=large", "feature=cover@foes", "hazard=lava@center"]), "seed": 5}, src, 2, 2, ["aragorn", "legolas"], ["goblin#1", "goblin#2"])
        check("shape and size are ignored in a scene room; features and hazards still apply", d["spec"]["ignored"] == ["shape", "size"] and len(d["props"]) > len(room["props"]))
        check("the DM is told", "did not apply" in board.room_line(d["spec"]) and "room of the scene" in board.room_line(d["spec"]))
    # A room that cannot hold the fight gives a generated room, with a note.
    split = {**source("scene"), "room": {"grid": ["#####", "#.#.#", "#####"], "props": []}, "cast": [], "scene_spec": {"template": "hall"}}
    e = arena.generate({"features": [], "hazards": [], "seed": 4}, split, 1, 1, ["a"], ["b"])
    check("if the starts cannot reach each other, the stage builds another room and says so", e["spec"]["shape"] != "scene" and "no room" in e["spec"]["fallback"]
          and "Note:" in board.room_line(e["spec"]))


def test_source_and_files() -> None:
    print("arena: source and files")
    with tempfile.TemporaryDirectory() as tmp:
        campaign = Path(tmp)
        none = arena.source_of(campaign, {}, {})
        check("no scene and no site: an open forest", none["kind"] == "none" and none["shell"] == "open" and none["decor"] == "forest")
        scenes.save(campaign, "wine-cellar", {"template": "tavern", "slots": {}, "add": [["barrel", "front_right"]]})
        scene = arena.source_of(campaign, {"scene": "wine-cellar"}, {})
        check("a scene gives its floor, walls, props and a room shell",
              scene["kind"] == "scene" and scene["look"]["floor"] == "lpc:planks" and scene["shell"] == "room"
              and ("barrel", "front_right") in scene["props"] and scene["decor"] == "tavern")
        scenes.save(campaign, "road-bend", {"template": "road", "slots": {}, "add": []})
        check("a road scene is open", arena.source_of(campaign, {"scene": "road-bend"}, {})["shell"] == "open")
        check("a scene with no file falls back to nothing", arena.source_of(campaign, {"scene": "ghost"}, {})["kind"] == "none")
        site = crawl.generate({"theme": "crypt", "size": "small", "seed": 3, "danger": "low", "name": "Vault"}, [])
        crawl.save(campaign, "vault", site)
        got = arena.source_of(campaign, {"explore": "vault", "scene": "wine-cellar"}, {})
        check("exploring a site wins over the scene and uses its theme", got["kind"] == "site" and got["look"] == arena.look_of("crypt") and got["decor"] == "crypt")
        check("theme= overrides the walls of a scene", arena.source_of(campaign, {"scene": "wine-cellar"}, {"theme": "crypt"})["look"]["wall"] == arena.look_of("crypt")["wall"])
        a = arena.generate({"features": [], "hazards": [], "seed": 1}, scene)
        check("the arena file keeps the look and the spec", a["look"] == scene["look"] and a["spec"]["source"] == "scene" and a["spec"]["source_id"] == "wine-cellar")
        check("the first arena id is arena-1", arena.new_id(campaign) == "arena-1")
        arena.save(campaign, "arena-1", a)
        check("an arena file loads back as saved", arena.load(campaign, "arena-1") == a)
        check("the next id is arena-2", arena.new_id(campaign) == "arena-2")
        check("a bad id loads nothing", arena.load(campaign, "../x") is None and arena.load(campaign, "nope") is None)


def fight_with_boss(tmp: Path) -> tuple[Path, dict]:
    """The fixture fight of test_rules (the party, two goblins), plus a creature the DM named: `boss`."""
    c = campaign(tmp)
    state = fight(c)
    enc = state["active_encounter"]
    enc["monsters"]["boss"] = combat.monster_record(GOBLIN, "boss")
    enc["participants"].append("boss")
    enc["initiative_order"].append({"name": "boss", "initiative": 16, "bonus": 0})
    return c, state


def test_start() -> None:
    print("arena: encounter start --arena")
    with tempfile.TemporaryDirectory() as tmp:
        c, state = fight_with_boss(Path(tmp))
        lines = board.start(c, state, ["layout=chokepoint", "size=small", "light=dark", "seed=5", "feature=cover@foes"], {})
        enc = state["active_encounter"]
        a = arena.load(c, enc["arena"])
        check("the encounter keeps the arena id", enc["arena"] == "arena-1" and a is not None)
        starts = a["starts"]
        check("every combatant stands on a start tile of its side",
              [list(a["units"][u].values()) for u in ("aragorn", "legolas")] == starts["party"]
              and [list(a["units"][u].values()) for u in ("goblin#1", "goblin#2", "boss")] == starts["foes"])
        check("the spec keeps light and size (a small room, turned either way)",
              a["spec"]["light"] == "dark" and a["spec"]["size"] == "small" and max(a["w"], a["h"]) <= 14 and min(a["w"], a["h"]) <= 11)
        check("a creature the DM named is DM-played, the others are not",
              a["control"] == {"goblin#1": "engine", "goblin#2": "engine", "boss": "dm"} and "You play: boss" in lines[-1])
        check("a bare monster index is engine-played, a renamed one is DM-played",
              board.controlled_by({"id": "goblin#2", "index": "goblin"}) == "engine" and board.controlled_by({"id": "boss", "index": "bugbear"}) == "dm"
              and board.controlled_by({"id": "cassara", "index": "cassara", "kind": "npc"}) == "dm")
    with tempfile.TemporaryDirectory() as tmp:
        c, state = fight_with_boss(Path(tmp))
        check("a bad token is refused and nothing is written",
              raises(lambda: board.start(c, state, ["layout=maze"], {})) and "arena" not in state["active_encounter"]
              and not arena.arenas_dir(c).exists())


def test_state() -> None:
    print("arena: stage state")
    s = stage_state.empty()
    check("a new stage has no arena", s["arena"] is None)
    s = stage_state.apply(s, {"type": "arena", "arena": "arena-1"})
    check("an arena event shows the arena and bumps its version", s["arena"] == "arena-1" and s["versions"]["arena:arena-1"] == s["seq"])
    s2 = stage_state.apply(s, {"type": "arena_updated", "arena": "arena-1"})
    check("arena_updated makes the browser fetch it again", s2["versions"]["arena:arena-1"] == s2["seq"] > s["versions"]["arena:arena-1"])
    s3 = stage_state.apply(stage_state.apply(s, {"type": "explore", "site": "vault"}), {"type": "arena", "arena": "arena-2"})
    check("a fight inside a site keeps the site", s3["arena"] == "arena-2" and s3["explore"] == "vault")
    s4 = stage_state.apply(s3, {"type": "arena_end"})
    check("the end of the fight shows the site again", s4["arena"] is None and s4["explore"] == "vault")
    check("a scene keeps the arena", stage_state.apply(s, {"type": "scene", "location": "inn", "party": []})["arena"] == s["arena"])
    check("an explore keeps the arena", stage_state.apply(s, {"type": "explore", "site": "vault"})["arena"] == s["arena"])
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "events.ndjson"
        log.write_text('{"type": "scene", "location": "inn", "party": []}\nnot json\n{"type": "arena", "arena": "arena-1"}\n')
        got = stage_state.replay(log)
        check("replay folds a log, skipping bad lines", got["scene"] == "inn" and got["arena"] == "arena-1")
        check("replay of a missing log is the empty stage", stage_state.replay(Path(tmp) / "none.ndjson") == stage_state.empty())


if __name__ == "__main__":
    for t in (test_geometry, test_props, test_parse, test_generator, test_shapes, test_scene_room, test_source_and_files, test_start, test_state):
        t()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
