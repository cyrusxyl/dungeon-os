"""Checks for the isometric view data: prop poses, the prop atlas and their routes.

Run from the repo root:  .venv/bin/python tests/test_iso.py

Plain asserts so no test runner is needed.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from PIL import Image  # noqa: E402

from stage import scenes  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}{'' if cond or not detail else f'  ({detail})'}")


def test_catalogue_rects() -> None:
    print("catalogue: rects")
    props = scenes.catalog()["props"]
    check("pine_small is cut at the right place", props["pine_small"]["rect"] == [27, 15, 3, 4] and props["pine_small"]["sheet"] == "terrain")
    check("stump is cut at the right place", props["stump"]["rect"] == [12, 12, 2, 2] and props["stump"]["sheet"] == "terrain")
    bad = []
    for name, p in props.items():
        for part in p.get("parts", [p]):
            if "rect" not in part:
                continue
            sheet = scenes._sheet(part["sheet"])
            c, r, w, h = part["rect"]
            if w < 1 or h < 1 or c < 0 or r < 0 or (c + w) * scenes.T > sheet.width or (r + h) * scenes.T > sheet.height:
                bad.append(name)
    check(f"every rect has a size and lies inside its sheet {bad}", not bad)


def test_poses() -> None:
    print("poses: one record per prop")
    props = scenes.catalog()["props"]
    records = scenes._poses()
    check(f"every prop has a pose record {sorted(set(props) - set(records))}", set(props) <= set(records))
    check(f"no record is for an unknown prop {sorted(set(records) - set(props))}", set(records) <= set(props))
    kinds = [r["pose"] for r in records.values()]
    counts = {n: sum(len(r["bands"]) == n for r in records.values() if r["pose"] == "bands") for n in (1, 2, 3, 4)}
    check("the records are 284: 186 upright and 98 with bands", len(records) == 284 and kinds.count("upright") == 186 and kinds.count("bands") == 98)
    check("the band counts are 60, 25, 8 and 5", counts == {1: 60, 2: 25, 3: 8, 4: 5}, str(counts))
    bad = []
    for name, rec in records.items():
        if rec["pose"] not in ("upright", "bands"):
            bad.append(name)
            continue
        if rec["pose"] == "upright":
            continue
        _, top, _, bottom = scenes.prop_box(name)
        h = bottom - top
        splits = rec["splits"]
        ok = (rec["first"] in ("V", "H") and len(splits) == len(rec["bands"]) - 1 and 1 <= len(rec["bands"]) <= 4
              and all(0 <= a <= b <= h for a, b in zip([0, *splits], [*splits, h])) and all(len(b) == 2 and b[0] > 0 and b[1] >= 0 for b in rec["bands"]))
        if not ok:
            bad.append(name)
    # The renderer clamps close splits (at least 2 rows a band), as bands.js does: water_trough has [2, 2, 16].
    check(f"every record is well formed and every split is in range {bad}", not bad)
    check("a record is returned as it is, with the width filled in", scenes.prop_pose("chest") == {"pose": "upright"} and scenes.prop_pose("cabinet")["width"] == 0.8)
    try:
        scenes.prop_pose("no_such_prop")
        check("an unknown prop is an error", False)
    except scenes.SceneError:
        check("an unknown prop is an error", True)


def test_pose_fallback() -> None:
    print("poses: guess for a prop with no record")
    saved = dict(scenes._poses())
    scenes._poses().clear()
    try:
        props = scenes.catalog()["props"]
        flat = next(n for n, p in props.items() if p.get("flat"))
        wall = next(n for n, p in props.items() if p.get("on") == "wall" and not p.get("flat"))
        fall = {n: scenes.prop_pose(n) for n in props}
        check("a flat prop is one horizontal band", fall[flat]["first"] == "H" and fall[flat]["bands"] == [[1, 0]])
        check("a wall prop is one vertical band", fall[wall]["first"] == "V" and fall[wall]["bands"] == [[1, 0]])
        check("a tree is upright", fall["oak"] == {"pose": "upright"})
        check("every guess is valid", all(g["pose"] == "upright" or (len(g["splits"]) == len(g["bands"]) - 1) for g in fall.values()))
    finally:
        scenes._poses().update(saved)


def test_atlas() -> None:
    print("atlas: every prop in one picture")
    stamp, png, entries = scenes.prop_atlas()
    sheet = Image.open(io.BytesIO(png)).convert("RGBA")
    props = scenes.catalog()["props"]
    check("the atlas has every prop", set(entries) == set(props))
    check("every rect lies inside the sheet", all(e["r"][0] >= 0 and e["r"][1] >= 0 and e["r"][0] + e["r"][2] <= sheet.width and e["r"][1] + e["r"][3] <= sheet.height for e in entries.values()))
    boxes = [tuple(e["r"]) for e in entries.values()]
    overlap = any(a is not b and a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
                  for i, a in enumerate(boxes) for b in boxes[i + 1:])
    check("no two rects overlap", not overlap)
    bad = []
    for name in ("chest", "cabinet", "oak", "pine_small", "stump"):
        e = entries[name]
        full = scenes.prop_image(name)
        left, top = e["o"]
        want = full.crop((left, top, left + e["r"][2], top + e["r"][3]))
        x, y, w, h = e["r"]
        if sheet.crop((x, y, x + w, y + h)).tobytes() != want.tobytes() or e["size"] != list(full.size):
            bad.append(name)
    check(f"a rect holds the cropped picture, and the offset and size give the way back {bad}", not bad)
    check("the atlas is cached", scenes.prop_atlas()[1] is png and scenes.prop_atlas()[0] == stamp)
    info = scenes.props_info()
    check("the info has a pose for every prop", set(info["props"]) == set(props) and all("pose" in v for v in info["props"].values()))
    check("the info names the atlas", info["atlas"].startswith("/asset/props.png?v="))


def test_room() -> None:
    print("scene room: cells, wall decor, stand points, sheet")
    from stage import arena

    cat = scenes.catalog()
    bad, open_scenes = [], 0
    for name in cat["templates"]:
        spec = {"template": name}
        r = scenes.room(spec)
        walled = bool(scenes.resolve(spec)["walls"])
        open_scenes += not walled
        solid = [(p["x"], p["y"]) for p in r["props"] if not p["flat"]]
        floor = lambda x, y: r["grid"][y][x] == "."  # noqa: E731
        ok = (len(r["grid"]) == scenes.ROOM_H and all(len(row) == scenes.ROOM_W for row in r["grid"]) and r["open"] == (not walled)
              and all(floor(p["x"], p["y"]) for p in r["props"]) and len(set(solid)) == len(solid)
              and (walled or not r["decor"]) and all(cat["props"][d["kind"]].get("on") == "wall" and d["wall"] in "nw" and 0 <= d["t"] <= scenes.ROOM_W and d["lift"] >= 0 for d in r["decor"])
              and all((s["x"], s["y"]) in solid for s in r["stand"]) and all(cat["props"][p["kind"]].get("on") != "wall" for p in r["props"]))
        if walled:
            ok = ok and all(r["grid"][0][x] == "#" for x in range(scenes.ROOM_W)) and all(r["grid"][y][0] == "#" for y in range(scenes.ROOM_H))
        if not ok:
            bad.append(name)
    check(f"every template makes a room: cells in the grid, props on floor, one to a cell, wall decor only on walls {bad}", not bad)
    check("a scene with no walls is open floor", open_scenes > 5 and scenes.room({"template": "forest"})["grid"] == ["." * scenes.ROOM_W] * scenes.ROOM_H)
    check("a street has the walls of its houses, though a fight in it is on open ground", scenes.room({"template": "street"})["grid"][0] == "#" * scenes.ROOM_W
          and "street" in arena.arena_data()["open_templates"])

    # The study, as the demo placed it.
    study = scenes.room(scenes.FILLER, scenes.FILLER_STUFF)
    cells = {p["kind"]: (p["x"], p["y"]) for p in study["props"]}
    check("the study's props stand where the demo had them", cells == {"chests": (2, 2), "barrel_pile": (8, 2), "table_desk": (5, 4), "plant": (2, 6), "brazier": (8, 6), "cabinet": (2, 1), "dresser": (1, 5)}, str(cells))
    decor = {d["kind"]: (d["wall"], d["t"], d["lift"]) for d in study["decor"]}
    check("its wall decor hangs where the demo had it; furniture in a wall slot stands against the wall",
          decor == {"window_arched": ("w", 2.6, 14), "fireplace": ("n", 5.4, 0), "tapestry": ("n", 8.3, 6)}, str(decor))
    two = scenes.room({"template": "tavern", "add": [["barrel", "back_left"], ["barrel", "back_left"], ["barrel", "back_left"]]})
    cells = [(p["x"], p["y"]) for p in two["props"] if p["kind"] == "barrel"]
    check("props added to one zone stand on different cells, and not on a wall", len(set(cells)) == 3 and all(x >= 1 and y >= 1 for x, y in cells), str(cells))

    # Stand points: pixels of the prop's own picture, on opaque pixels; the cell is the prop's.
    hall = scenes.room({"template": "hall", "slots": {**{s: None for s in scenes.SLOTS}, "back_center": "throne"}})
    throne = hall["stand"][0]
    alpha = scenes.prop_image("throne").getchannel("A")
    check("a throne is a seat at the cell of its zone", (throne["x"], throne["y"]) == (5, 2) and throne["mode"] == "sit" and throne["slot"] == "back_center"
          and all(alpha.getpixel(tuple(pt)) for pt in throne["points"]))
    check("stand_points is the stand part of the room", scenes.stand_points({"template": "hall", "slots": {"back_center": "throne"}}) == scenes.room({"template": "hall", "slots": {"back_center": "throne"}})["stand"])

    # The sheet: the floor (a tile a cell), the wall faces and caps, the desk icons.
    sheet = Image.open(io.BytesIO(scenes.room_png(scenes.FILLER, scenes.FILLER_STUFF))).convert("RGBA")
    lay = study["sheet"]
    check("the sheet has the size the room says", sheet.size == (lay["w"], lay["h"]) and lay["w"] == scenes.ROOM_W * scenes.T)
    check("the floor part is solid", all(sheet.getpixel((x, y))[3] == 255 for x in (0, 150, 319) for y in (0, 100, 255)))
    face = sheet.crop((0, lay["north"][0], 32, lay["north"][0] + scenes.WALL_FACE[1] - scenes.WALL_FACE[0]))
    check("a wall face is 32 x 48 and opaque", face.size == (32, 48) and face.getchannel("A").getextrema()[0] == 255)
    check("every desk icon lies in the sheet", all(s["r"][1] + s["r"][3] <= lay["h"] and s["r"][0] + s["r"][2] <= lay["w"] and sheet.crop((s["r"][0], s["r"][1], s["r"][0] + s["r"][2], s["r"][1] + s["r"][3])).getchannel("A").getbbox()
                                                  for s in study["stuff"]))
    walls = sorted(cat["walls"])
    check("every wall style gives a north and a west strip", all(len(scenes._wall_strip({"walls": [w]}, west)) == (scenes.ROOM_H if west else scenes.ROOM_W) for w in walls for west in (False, True)))
    check("two wall styles share the north wall", len(scenes._wall_strip({"walls": ["timber", "stone_dark"]}, False)) == scenes.ROOM_W)
    rows = Image.open(io.BytesIO(scenes.room_png({"template": "dock"}))).convert("RGB")
    check("floor rows with their own surface differ from the rest", rows.getpixel((16, 7 * 32 + 16)) != rows.getpixel((16, 1 * 32 + 16)))


def test_shaped_scenes() -> None:
    print("scene room: any shape")
    from stage import rooms

    spec = scenes.build(["template=tavern", "shape=cross", "seed=4"], None)
    check("shape= and seed= are kept, the shape is checked", spec["shape"] == "cross" and spec["seed"] == 4
          and scenes.build(["shape=none"], spec)["shape"] == "fixed" and isinstance(scenes.build(["template=tavern", "shape=ring"], None)["seed"], int))
    for bad in (["template=tavern", "shape=donut"], ["template=tavern", "size=huge"], ["template=tavern", "seed=x"]):
        try:
            scenes.resolve(scenes.build(bad, None))
            check(f"{bad[1]} is refused", False)
        except scenes.SceneError:
            check(f"{bad[1]} is refused", True)
    # A new place gets a shape from the odds of its theme, with a seed it keeps; a saved place and `shape=fixed` keep the plain room.
    from stage import arena

    new = scenes.build(["template=chapel"], None)
    odds = arena.arena_data()["shapes"][arena.arena_data()["scene_looks"]["chapel"]]
    check("a new scene gets a shape from its theme and a seed", new["shape"] in odds and isinstance(new["seed"], int) and scenes.room(new)["shaped"])
    seen = {scenes.build(["template=tavern"], None)["shape"] for _ in range(60)}
    check("a tavern gets rect, L or T and nothing else", seen <= {"rect", "l", "t"} and len(seen) >= 2, str(seen))
    saved = {"template": "tavern", "slots": {}, "add": [], "mood": "day"}
    check("a saved place without a shape keeps its plain room when it changes", "shape" not in scenes.build(["mood=night"], saved) and not scenes.room(scenes.build(["mood=night"], saved))["shaped"])
    check("shape=fixed gives the plain 10 x 8 room", not scenes.room(scenes.build(["template=tavern", "shape=fixed"], None))["shaped"]
          and scenes.room(scenes.build(["template=tavern", "shape=fixed"], None))["w"] == scenes.ROOM_W)
    check("a new template on a place changes its shape too", "shape" in scenes.build(["template=forest"], saved))
    bad, made = [], 0
    for shape in rooms.SHAPE_NAMES:
        for template in ("tavern", "chapel", "forest", "cave"):
            for seed in (1, 2, 3):
                r = scenes.room({"template": template, "shape": shape, "seed": seed})
                made += 1
                grid, w, h = r["grid"], r["w"], r["h"]
                floor = {(x, y) for y in range(h) for x in range(w) if grid[y][x] == "."}
                solid = [(p["x"], p["y"]) for p in r["props"] if not p["flat"]]
                runs = scenes._wall_runs(grid) if not r["open"] else {}
                ok = (r["shaped"] and all(len(row) == w for row in grid) and set("".join(grid)) <= set("#.-") and len(floor) >= 40
                      and all(p in floor for p in solid) and len(set(solid)) == len(solid) and (r["open"] or "#" in "".join(grid))
                      and (not r["open"] or "#" not in "".join(grid)) and r["sheet"]["w"] >= w * scenes.T
                      and all(d["wall"] in runs and (d["wall"] == "n" and 0 <= d["line"] < h or d["wall"] == "w" and 0 <= d["line"] < w) for d in r["decor"]))
                if not ok:
                    bad.append((shape, template, seed))
    check(f"{made} shaped rooms: grid, props on floor, open scenes without walls, decor on a wall that faces in {bad[:4]}", not bad)
    again = scenes.room({"template": "tavern", "shape": "l", "seed": 9})
    check("the same seed gives the same room", again == scenes.room({"template": "tavern", "shape": "l", "seed": 9}) and again["grid"] != scenes.room({"template": "tavern", "shape": "l", "seed": 10})["grid"])
    png = Image.open(io.BytesIO(scenes.room_png({"template": "tavern", "shape": "cross", "seed": 4}))).convert("RGBA")
    big = scenes.room({"template": "tavern", "shape": "cross", "seed": 4})
    check("the sheet of a shaped room is as big as the room", png.size == (big["sheet"]["w"], big["sheet"]["h"]) and big["sheet"]["north"][0] == big["h"] * scenes.T)
    # A wall with floor beside or behind it is cut low and carries no decor: the notch (2, 2) and (3, 2) is not a run.
    notch = ["######", "#....#", "#.##.#", "#....#", "######"]
    check("wall runs: the longest north-facing run is the back wall, not the cut notch", scenes._wall_runs(notch)["n"] == (0, 1, 4) and scenes._wall_runs(notch)["w"] == (0, 1, 3))

async def routes() -> None:
    print("routes: /asset/props.png and /api/props")
    from stage.server import create_app
    from tests.test_stage import call

    app = create_app(None)
    status, headers, raw = await call(app, "GET", "/asset/props.png")
    check("the atlas route gives a PNG", status == 200 and raw[:8] == b"\x89PNG\r\n\x1a\n")
    status, _, raw = await call(app, "GET", "/api/props")
    body = json.loads(raw)
    check("the props route lists every prop", status == 200 and set(body["props"]) == set(scenes.catalog()["props"]))
    status, _, _ = await call(app, "GET", "/asset/prop/chest.png")
    check("the old prop route still works", status == 200)
    status, _, raw = await call(app, "GET", "/api/template/tavern?mood=night")
    room = json.loads(raw)
    check("a template has a room, with its mood", status == 200 and room["has_look"] and room["mood"] == "night" and room["decor"] and len(room["grid"]) == 8)
    status, _, raw = await call(app, "GET", "/asset/template/tavern/room.png")
    check("and a sheet", status == 200 and raw[:4] == b"\x89PNG")
    status, _, raw = await call(app, "GET", "/api/template/not_a_template")
    check("an unknown template has no look", status == 200 and json.loads(raw)["has_look"] is False)
    status, _, _ = await call(app, "GET", "/asset/template/not_a_template/room.png")
    check("an unknown template has no sheet", status == 404)
    status, _, raw = await call(app, "GET", "/api/filler")
    study = json.loads(raw)
    check("the study has a room with desk icons", status == 200 and len(study["stuff"]) == len(scenes.FILLER_STUFF) and any("lamp" in s["icon"] for s in study["stuff"]))
    status, _, raw = await call(app, "GET", "/asset/filler/room.png")
    check("and a sheet that holds them", status == 200 and raw[:4] == b"\x89PNG")
    for old in ("/asset/scene/x.png", "/asset/template/tavern.png", "/asset/filler.png"):
        status, _, _ = await call(app, "GET", old)
        check(f"the flat picture {old} is gone", status in (404, 405))


if __name__ == "__main__":
    for t in (test_catalogue_rects, test_poses, test_pose_fallback, test_atlas, test_room, test_shaped_scenes):
        t()
    asyncio.run(routes())
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
