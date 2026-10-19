"""Compose a scene background from LPC tiles: templates, slots, zones, moods.

A scene spec is plain data, written by `dnd-cli scene set` to
`{campaign}/stage/scenes/<location-id>.json`:

    {"template": "chapel", "wall": "stone_dark", "mood": "dusk",
     "slots": {"wall_center": "bust"}, "add": [["barrel_pile", "back-right"]]}

The DM never gives a pixel position. A template fills the room and names a
default prop for some slots. The spec can change the wall or floor style,
replace or empty a slot, and add extra props into a zone; the composer finds
the spot. The browser draws a scene as a small isometric room (10 wide, 8 deep) on the renderer of the combat board:
`room()` gives its cells, props and wall decor, `room_png()` its floor and wall pictures.
"""

from __future__ import annotations

import hashlib
import io
import json
import random
import re
from functools import cache, lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

from stage import rooms
from stage.assets import ASSETS_DIR, ensure_dcss, ensure_tiles
from stage.creatures import recolor
from core.files import read_json, write_json

T = 32
ROWS = 6  # the rows of floor tiles the templates' `rows` count; a wall is WALL_ROWS of them high
WALL_ROWS = 3
CATALOG_PATH = Path(__file__).resolve().parent / "data" / "scenery.json"
POSES_PATH = CATALOG_PATH.with_name("prop_poses.json")
ATLAS_WIDTH = 1024
# Names of props that stand as they are in the isometric view. Only a fallback, for a prop with no pose record.
UPRIGHT = re.compile(
    "tree|pine|oak|bush|stump|plant|barrel|jar|bucket|mushroom|rock|stones|boulder|crystal|fire|brazier|lantern|torch"
    "|statue|bust|column|pillar|obelisk|grave|tomb|cross|sign|hay|sack|pots|cauldron|tripod|idol|well|fountain|basin"
    "|sundial|birdbath|scarecrow|stool|target|anvil|quiver|laundry|rope|reeds|bones|coins|twisted|pentagram|circle"
    "|banner|monument"
)
UPRIGHT_FIRST = re.compile("cloud|smoke|armor|suit|cactus|corn|hoard")

ROOM_W, ROOM_H = 10, 8  # the room of a scene in cells (see `_make_grid`)
# Where a wall slot hangs: the wall (n = north, w = west) and the place along it in cells (the centre of the piece).
WALL_AT = {"wall_left": ("w", 2.6), "wall_left2": ("n", 2.6), "wall_center": ("n", 5.4), "wall_right2": ("w", 5.6), "wall_right": ("n", 8.3)}
# How high above the floor a piece of wall decor hangs, in pixels: the first pattern that matches the name wins.
WALL_LIFT = ((r"door|fireplace|hearth|stove|dresser", 0), (r"window", 14), (r"cabinet", 18), (r"lantern|torch", 10), (r".", 6))
WALL_FACE = (48, 96)  # the rows of an LPC wall tile (96 high) a wall block of 48 shows: the lower half
WALL_CAP = 32  # the rows from the top of that tile that cover a wall block
WALL_SLOTS = ("wall_left", "wall_left2", "wall_center", "wall_right2", "wall_right")
ZONE_ROWS = ("back", "mid", "front")
ZONE_AT = {"left": 0.125, "center": 0.5, "right": 0.875}  # where a zone lies across the floor, as a fraction of its width
ZONES = [f"{row}_{col}" for row in ZONE_ROWS for col in ZONE_AT]
SLOTS = list(WALL_SLOTS) + ZONES


# The DM's study: the loading screen of the stage, while the DM works. Not a campaign scene.
FILLER = {
    "template": "house", "wall": "timber", "floor": "planks_dark", "mood": "torchlit",
    "slots": {"wall_left": "window_arched", "wall_center": "fireplace", "wall_right": "tapestry",
              "wall_left2": "cabinet", "wall_right2": "dresser", "back_left": "chests", "back_center": None,
              "back_right": "barrel_pile", "mid_center": "table_desk", "mid_left": None, "mid_right": None,
              "front_left": "plant", "front_right": "brazier"},
}
# DCSS item icons on the desk: (path under assets/dcss/item, prop, x, y of the icon's bottom centre in the prop's own picture).
FILLER_STUFF = (
    ("book/dark_brown_old.png", "table_desk", 12, 40), ("book/parchment.png", "table_desk", 13, 33), ("misc/misc_lamp.png", "table_desk", 90, 34),
    ("food/bread_ration.png", "table_desk", 48, 34), ("scroll/blank_paper.png", "table_desk", 32, 46), ("misc/misc_deck.png", "table_desk", 58, 38),
    ("potion/golden.png", "table_desk", 70, 46), ("potion/brown.png", "table_desk", 83, 48),
)


class SceneError(ValueError):
    """A bad scene spec. The message says how to fix it."""


@cache
def catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text())


@cache
def _sheet(name: str) -> Image.Image:
    from PIL import Image
    if name.startswith("dcss:"):
        return Image.open(ensure_dcss() / name[5:]).convert("RGBA")
    ensure_tiles()
    img = Image.open(ASSETS_DIR / catalog()["sheets"][name]).convert("RGBA")
    if key := catalog().get("keys", {}).get(name):
        # Some packs fill unused cells with one flat colour: make it clear.
        r, g, b = key
        img.putdata([(0, 0, 0, 0) if px == (r, g, b, 255) else px for px in img.getdata()])
    return img


def _crop(sheet: str, rect: list[int]) -> Image.Image:
    c, r, w, h = rect
    return _sheet(sheet).crop((c * T, r * T, (c + w) * T, (r + h) * T))


@cache
def prop_image(name: str) -> Image.Image:
    from PIL import Image
    p = catalog()["props"][name]
    if "parts" in p:
        w, h = p["size"]
        img = Image.new("RGBA", (w * T, h * T))
        for part in p["parts"]:
            img.alpha_composite(_crop(part["sheet"], part["rect"]), (0, part.get("dy", 0) * T))
        return img
    if p["sheet"].startswith("dcss:"):
        return _sheet(p["sheet"]).copy()
    return _crop(p["sheet"], p["rect"])


@cache
def _poses() -> dict:
    return {k: v for k, v in json.loads(POSES_PATH.read_text()).items() if not k.startswith("_")}


@cache
def prop_box(name: str) -> tuple[int, int, int, int]:
    """The alpha box of a prop picture as (left, top, right, bottom). A clear picture gives a 1 x 1 box."""
    return prop_image(name).getchannel("A").getbbox() or (0, 0, 1, 1)


def prop_pose(name: str) -> dict:
    """The isometric pose of a prop (see isometric-view.md): {"pose": "upright"} or a band chain.

    Band rows count from the top of the picture cropped to its alpha box, as in the atlas. A prop with no
    record in `prop_poses.json` gets a guess from its flags, its name and its size.
    """
    if name not in catalog()["props"]:
        raise SceneError(f"prop {name!r} is not in the catalog.")
    if record := _poses().get(name):
        return {"width": 1, **record} if record["pose"] == "bands" else dict(record)
    p = catalog()["props"][name]
    left, top, right, bottom = prop_box(name)
    w, h = right - left, bottom - top
    one = lambda first: {"pose": "bands", "first": first, "splits": [], "bands": [[1, 0]], "width": 1}
    if p.get("flat"):
        return one("H")
    if p.get("on") == "wall":
        return one("V")
    if UPRIGHT_FIRST.search(name) or UPRIGHT.search(name) or h >= 1.7 * w:
        return {"pose": "upright"}
    thick = max(5, min(20, round(w * 0.3)))
    if w >= 1.3 * h:
        split = max(2, round(h * 0.3))
        return {"pose": "bands", "first": "H", "splits": [split], "width": 1,
                "bands": [[max(0.5, min(4, round(w * 0.3 / split, 2))), 0], [1, thick]]}
    return {"pose": "bands", "first": "V", "splits": [], "bands": [[1, thick]], "width": 1}


_atlas_stamp = None


@lru_cache(maxsize=1)
def _build_atlas(stamp: int) -> tuple[bytes, dict]:
    """Every prop picture, cropped to its alpha box, packed in rows on one sheet. Result: (png, {name: entry})."""
    from PIL import Image
    names = sorted(catalog()["props"], key=lambda n: (-prop_box(n)[3] + prop_box(n)[1], n))
    sheet_h = 0
    x = y = row_h = 0
    entries: dict[str, dict] = {}
    for name in names:
        img = prop_image(name)
        box = prop_box(name)
        w, h = box[2] - box[0], box[3] - box[1]
        if x + w > ATLAS_WIDTH:
            x, y, row_h = 0, y + row_h + 1, 0
        entries[name] = {"r": [x, y, w, h], "o": [box[0], box[1]], "size": list(img.size)}
        x += w + 1
        row_h = max(row_h, h)
        sheet_h = y + row_h
    sheet = Image.new("RGBA", (ATLAS_WIDTH, max(1, sheet_h)))
    for name, e in entries.items():
        left, top = e["o"]
        sheet.alpha_composite(prop_image(name).crop((left, top, left + e["r"][2], top + e["r"][3])), tuple(e["r"][:2]))
    buf = io.BytesIO()
    sheet.save(buf, "PNG")
    return buf.getvalue(), entries


def prop_atlas() -> tuple[int, bytes, dict]:
    """(stamp, png, entries). Entry: {"r": [x, y, w, h] in the sheet, "o": [x, y] of the crop in the full
    picture, "size": [w, h] of the full picture}. Rebuilt when the catalogue file changes."""
    global _atlas_stamp
    stamp = CATALOG_PATH.stat().st_mtime_ns
    if _atlas_stamp not in (None, stamp):
        for cached in (catalog, prop_image, prop_box, _sheet, _wall_width, _poses, _room_png, _build_atlas, props_info):
            cached.cache_clear()
    _atlas_stamp = stamp
    return (stamp, *_build_atlas(stamp))


def props_info() -> dict:
    """The body of GET /api/props: the atlas address and, for each prop, its rect, crop offset and pose."""
    return _props_info(prop_atlas()[0])


@lru_cache(maxsize=1)
def _props_info(stamp: int) -> dict:
    entries = _build_atlas(stamp)[1]
    return {"atlas": f"/asset/props.png?v={stamp}", "props": {n: {**e, "pose": prop_pose(n)} for n, e in entries.items()}}


def surface_tile(name: str, col: int, row: int) -> Image.Image:
    cat = catalog()
    if name in cat["floors"]:
        sheet, (c, r) = _origin(cat["floors"][name], "floors")
        return _crop(sheet, [c + col % 2, r + row % 2, 1, 1])
    ground = cat["grounds"][name]
    # Pick a variant per tile, stable for the same spot.
    pick = int(hashlib.md5(f"{name}{col},{row}".encode()).hexdigest(), 16) % len(ground["tiles"])
    c, r = ground["tiles"][pick]
    return _crop(ground["sheet"], [c, r, 1, 1])


def _origin(entry: list | dict, default_sheet: str) -> tuple[str, list[int]]:
    """A wall or floor entry is [col, row] on the default sheet, or {"sheet": name, "at": [col, row]}.

    A wall entry may add "width": 3 or 4, when the block's edge column is not a plain right edge,
    and "recolor": {"hue", "sat", "value"} to change its colours.
    """
    if isinstance(entry, dict):
        return entry["sheet"], entry["at"]
    return default_sheet, entry


@cache
def _wall_width(style: str) -> int:
    """3 or 4: some wall blocks have no separate right-edge column."""
    entry = catalog()["walls"][style]
    if isinstance(entry, dict) and "width" in entry:
        return entry["width"]
    sheet, (c, r) = _origin(entry, "walls")
    edge = _crop(sheet, [c + 3, r, 1, WALL_ROWS]).getchannel("A")
    return 4 if sum(edge.getdata()) > 0.8 * 255 * edge.width * edge.height else 3


def _wall_tile(style: str, col: int, first: int, last: int) -> Image.Image:
    sheet, (c, r) = _origin(catalog()["walls"][style], "walls")
    if _wall_width(style) == 4:
        offset = 0 if col == first else 3 if col == last else 1 + (col - first) % 2
    else:
        offset = 0 if col == first else 2 if col == last else 1
    tile = _crop(sheet, [c + offset, r, 1, WALL_ROWS])
    entry = catalog()["walls"][style]
    return recolor(tile, **entry["recolor"]) if isinstance(entry, dict) and "recolor" in entry else tile


def _suggest(name: str, options) -> str:
    from rapidfuzz import process

    best = process.extract(name, list(options), limit=3)
    return ", ".join(b[0] for b in best)


def resolve(spec: dict) -> dict:
    """Merge the template with the spec's changes; raise SceneError if anything is unknown."""
    cat = catalog()
    template_name = spec.get("template")
    if template_name not in cat["templates"]:
        raise SceneError(f"template {template_name!r} is not one of {', '.join(cat['templates'])}.")
    t = cat["templates"][template_name]
    wall = spec.get("wall", t.get("wall"))
    out = {
        "walls": wall if isinstance(wall, list) else [wall] if wall else [],
        "floor": spec.get("floor", t["floor"]),
        "rows": dict(t.get("rows", {})),
        "slots": {**t.get("slots", {}), **spec.get("slots", {})},
        "add": list(spec.get("add", [])),
        "mood": spec.get("mood") or t.get("mood") or "day",
        "shape": spec.get("shape"), "seed": spec.get("seed"), "size": spec.get("size"),
    }
    if out["shape"] == "fixed":
        out["shape"] = None  # the plain 10 x 8 room
    if out["shape"] is not None and out["shape"] not in rooms.SHAPE_NAMES:
        raise SceneError(f"shape {out['shape']!r} is not one of fixed, {', '.join(rooms.SHAPE_NAMES)}.")
    if out["size"] is not None and out["size"] not in rooms.CLASSES:
        raise SceneError(f"size {out['size']!r} is not one of {', '.join(rooms.CLASSES)}.")
    if out["shape"] is not None and not isinstance(out["seed"], int):
        raise SceneError("a shaped room needs a seed (a whole number); `scene set` adds one.")
    surfaces = {**cat["floors"], **cat["grounds"]}
    for w in out["walls"]:
        if w not in cat["walls"]:
            raise SceneError(f"wall {w!r} is not known. Close: {_suggest(w, cat['walls'])}.")
    for s in [out["floor"], *out["rows"].values()]:
        if s not in surfaces:
            raise SceneError(f"floor {s!r} is not known. Close: {_suggest(s, surfaces)}.")
    if out["mood"] not in cat["moods"]:
        raise SceneError(f"mood {out['mood']!r} is not one of {', '.join(cat['moods'])}.")
    for slot in out["slots"]:
        if slot not in SLOTS:
            raise SceneError(f"slot {slot!r} is not one of {', '.join(SLOTS)}.")
    for _, zone in out["add"]:
        if zone not in ZONES:
            raise SceneError(f"zone {zone!r} is not one of {', '.join(ZONES)}.")
    for prop in [*filter(None, out["slots"].values()), *(p for p, _ in out["add"])]:
        if prop not in cat["props"]:
            raise UnknownProp(prop, f"prop {prop!r} is not in the catalog. Close: {_suggest(prop, cat['props'])}.")
    return out


class UnknownProp(SceneError):
    def __init__(self, prop: str, message: str):
        super().__init__(message)
        self.prop = prop


def _placed(r: dict) -> list[tuple[str, str, int]]:
    """Every prop of a resolved spec as (name, slot, nudge), in drawing order: wall, flat, then back to front."""
    cat = catalog()
    placed = [(name, slot, 0) for slot, name in r["slots"].items() if name]
    per_zone: dict[str, int] = {}
    for name, zone in r["add"]:
        n = per_zone.get(zone, 0) + (1 if r["slots"].get(zone) else 0)
        per_zone[zone] = per_zone.get(zone, 0) + 1
        nudge = 0 if n == 0 else ((n + 1) // 2) * (1 if n % 2 else -1)
        placed.append((name, zone, nudge))

    def order(entry):
        name, slot, _ = entry
        if slot in WALL_SLOTS:
            return (0, 0)
        if cat["props"][name].get("flat"):
            return (1, 0)
        return (2, ZONE_ROWS.index(slot.split("_")[0]))

    return sorted(placed, key=order)


ROW_AT = {"back": 1 / 6, "mid": 0.5, "front": 5 / 6}  # and along its depth
# Where wall slots hang on a room of any shape: the wall and the place along its longest run, as a fraction of the run.
SHAPED_AT = {"wall_left": ("w", 0.325), "wall_left2": ("n", 0.26), "wall_center": ("n", 0.54), "wall_right2": ("w", 0.7), "wall_right": ("n", 0.83)}


def _nearest(floor: list[tuple[int, int]], taken: set, want: tuple[float, float]) -> tuple[int, int]:
    """The free floor cell nearest a point."""
    return min((c for c in floor if c not in taken), key=lambda c: (abs(c[0] - want[0]) + abs(c[1] - want[1]), c))


def _wall_runs(grid: list[str]) -> dict[str, tuple[int, int, int]]:
    """The longest run of wall that faces into the room and is not cut low (see isometric-view.md, "Wall cut rule"): north-facing
    (floor below it) and west-facing (floor to its right). Result: {"n": (row, first x, cells), "w": (column, first y, cells)}."""
    h, w = len(grid), len(grid[0])
    at = lambda x, y: grid[y][x] if 0 <= x < w and 0 <= y < h else None  # noqa: E731
    low = lambda x, y: any(at(x + dx, y + dy) in (".", " ") for dx, dy in ((-1, 0), (0, -1), (-1, -1)))  # noqa: E731
    best: dict[str, tuple[int, int, int]] = {}
    for key, cells in (("n", [(y, [x for x in range(w) if at(x, y) == "#" and at(x, y + 1) == "." and not low(x, y)]) for y in range(h)]),
                       ("w", [(x, [y for y in range(h) if at(x, y) == "#" and at(x + 1, y) == "." and not low(x, y)]) for x in range(w)])):
        for line, along in cells:
            run: list[int] = []
            for v in [*along, None]:
                if v is not None and run and v == run[-1] + 1:
                    run.append(v)
                    continue
                if run and len(run) > best.get(key, (0, 0, 0))[2]:
                    best[key] = (line, run[0], len(run))
                run = [v] if v is not None else []
    return best


def _make_grid(r: dict, walled: bool) -> list[str]:
    """The rows of the room: the fixed 10 x 8 room (with walls, the north row and the west column are wall, and a south row and
    an east column are added as the low rim that the view cuts), or a shaped one."""
    if not r.get("shape"):
        n = 1 if walled else 0
        return ["".join("#" if walled and (x == 0 or y == 0 or x == ROOM_W or y == ROOM_H) else "." for x in range(ROOM_W + n)) for y in range(ROOM_H + n)]
    for attempt in range(60):
        made = rooms.mask(r["shape"], random.Random(f"{r['shape']}:{r['seed']}:{attempt}"), r.get("size"))
        if made:
            rows = ["".join(row) for row in rooms.grid_of(made[0])]
            return rows if walled else [row.replace("#", "-") for row in rows]  # an open scene has no wall blocks
    raise SceneError(f"could not make a {r['shape']} room; try another seed=.")


def _lift(name: str) -> int:
    return next(px for pattern, px in WALL_LIFT if re.search(pattern, name))


def _icon(path: str) -> Image.Image:
    """A DCSS item icon cropped to its alpha box."""
    from PIL import Image
    icon = Image.open(ensure_dcss() / "item" / path).convert("RGBA")
    return icon.crop(icon.getchannel("A").getbbox())


def room(spec: dict, stuff: tuple = ()) -> dict:
    """A scene as an isometric room, for the browser (see isometric-view.md).

    The room is 10 x 8 cells, walled as `_make_grid` says; an open scene (a street,
    a forest) has floor everywhere. A scene with `shape=` has a room of that shape (`stage/rooms.py`), walled all round, with
    the void `-` outside. Floor props stand on cells by their zone; wall props hang on a wall at a place along it (`t`, in cells,
    on the wall `line`) and a height (`lift`, px). A prop with a stand point is listed in `stand`: the points are in pixels of
    the prop's own picture, the cell is the prop's. `stuff` (the desk clutter of the study): (icon path, prop, x, y).
    """
    r = resolve(spec)
    cat = catalog()
    walled = bool(r["walls"])
    grid = _make_grid(r, walled)
    w, h = len(grid[0]), len(grid)
    floor = [(x, y) for y in range(h) for x in range(w) if grid[y][x] == "."]
    x0, x1, y0, y1 = min(x for x, _ in floor), max(x for x, _ in floor), min(y for _, y in floor), max(y for _, y in floor)
    runs = _wall_runs(grid) if walled else {}
    taken: set[tuple[int, int]] = set()
    props, decor, standing = [], [], []
    for name, slot, nudge in _placed(r):
        if slot in WALL_SLOTS:
            if not walled:
                continue
            wall, frac = SHAPED_AT[slot]
            if r.get("shape"):
                if wall not in runs:
                    continue
                line, first, count = runs[wall]
                along = first + frac * count
            else:
                (wall, along), line = WALL_AT[slot], 0
            if cat["props"][name].get("on") == "wall":
                decor.append({"kind": name, "slot": slot, "wall": wall, "t": along, "line": line, "lift": _lift(name)})
                continue
            # Furniture in a wall slot (a cabinet, a dresser) stands on the floor against that wall, in its tuned pose.
            x, y = _nearest(floor, taken, (int(along), line + 1) if wall == "n" else (line + 1, int(along)))
            taken.add((x, y))
            props.append({"kind": name, "slot": slot, "x": x, "y": y, "flat": False})
            continue
        row, col = slot.split("_")
        x, y = _nearest(floor, taken, (x0 + ZONE_AT[col] * (x1 - x0) + nudge, y0 + ROW_AT[row] * (y1 - y0)))
        flat = bool(cat["props"][name].get("flat"))
        if not flat:
            taken.add((x, y))
        props.append({"kind": name, "slot": slot, "x": x, "y": y, "flat": flat})
        if stand := cat["props"][name].get("stand"):
            standing.append({"slot": slot, "prop": name, "mode": stand["mode"], "points": stand["at"], "x": x, "y": y})
    face, cap = WALL_FACE[1] - WALL_FACE[0], WALL_CAP
    sheet_h = h * T + 2 * (face + cap)
    sheet = {"w": max(w, ROOM_W) * T, "h": sheet_h + (T if stuff else 0), "north": [h * T, h * T + face], "west": [h * T + face + cap, h * T + 2 * face + cap],
             "stuff": sheet_h}
    placed, x = [], 0
    for path, prop, px, py in stuff:
        icon = _icon(path)
        placed.append({"icon": path, "r": [x, sheet_h, icon.width, icon.height], "on": prop, "at": [px, py]})
        x += icon.width + 1
    return {"w": w, "h": h, "grid": grid, "open": not walled, "shaped": bool(r.get("shape")), "mood": r["mood"], "props": props, "decor": decor,
            "stand": standing, "stuff": placed, "sheet": sheet, "walls": len(r["walls"])}


def stand_points(spec: dict) -> list[dict]:
    """Where an actor can stand or sit on each prop that allows it. Each entry: {"slot", "prop", "mode", "points", "x", "y"}.

    A prop's `stand` entry in scenery.json gives its mode and its points in the prop picture's own pixels: `sit` (the point is the
    hip: the stage cuts the sprite there, because LPC has no sitting pose) or `on` (the point is the feet). `x`, `y` is the cell of
    the prop. The slot is where the prop stands, so the DM writes `@enter <actor> on <slot>`.
    """
    return room(spec)["stand"]


def _wall_strip(r: dict, west: bool) -> list[Image.Image]:
    """The wall tiles of the north wall (10 of them) or the west wall (8), as LPC tiles of 32 x 96."""
    walls = r["walls"]
    if west:
        return [_wall_tile(walls[0], y, -1, -1) for y in range(ROOM_H)]
    span = ROOM_W // len(walls)
    out = []
    for i, style in enumerate(walls):
        first = i * span
        last = ROOM_W - 1 if i == len(walls) - 1 else first + span - 1
        out += [_wall_tile(style, col, first, last) for col in range(first, last + 1)]
    return out


@lru_cache(maxsize=64)
def _room_png(spec_json: str, stuff: tuple) -> bytes:
    from PIL import Image
    spec = json.loads(spec_json)
    r = resolve(spec)
    made = room(spec, stuff)
    layout, w, h = made["sheet"], made["w"], made["h"]
    img = Image.new("RGBA", (layout["w"], layout["h"]))
    walled = bool(r["walls"])
    for y in range(h):
        # The old stage had 6 rows of floor tiles (3 with walls): each row of cells takes the surface of the row it stands for.
        old = WALL_ROWS + max(0, y - 1) * (ROWS - WALL_ROWS) // (h - 1) if walled else y * ROWS // h
        surface = r["rows"].get(str(old), r["floor"])
        for x in range(w):
            img.alpha_composite(surface_tile(surface, x, y), (x * T, y * T))
    if walled:
        for west, (face_y, cap_y) in ((False, layout["north"]), (True, layout["west"])):
            for i, tile in enumerate(_wall_strip(r, west)):
                img.alpha_composite(tile.crop((0, WALL_FACE[0], T, WALL_FACE[1])), (i * T, face_y))
                img.alpha_composite(tile.crop((0, 0, T, WALL_CAP)), (i * T, cap_y))
    x = 0
    for path, _prop, _x, _y in stuff:
        icon = _icon(path)
        img.alpha_composite(icon, (x, layout["stuff"]))
        x += icon.width + 1
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def room_png(spec: dict, stuff: tuple = ()) -> bytes:
    """The pictures of `room(spec, stuff)`: the floor (10 x 8 tiles), then the wall faces and caps, then the stuff icons."""
    return _room_png(json.dumps(spec, sort_keys=True), stuff)


def scenes_dir(campaign_dir: Path) -> Path:
    return campaign_dir / "stage" / "scenes"


def load(campaign_dir: Path, location: str) -> dict | None:
    return read_json(scenes_dir(campaign_dir) / f"{location}.json")


def save(campaign_dir: Path, location: str, spec: dict) -> Path:
    return write_json(scenes_dir(campaign_dir) / f"{location}.json", spec, indent=2)


def build(tokens: list[str], current: dict | None) -> dict:
    """Make a spec from tokens: template= wall= floor= mood= shape= (a new place gets one from its theme; `fixed` is the plain room) seed= size= <slot>=<prop|none> +<prop>@<zone> clear=add."""
    spec = json.loads(json.dumps(current or {}))
    spec.setdefault("slots", {})
    spec.setdefault("add", [])
    for token in tokens:
        if token.startswith("+"):
            prop, at, zone = token[1:].partition("@")
            if not at:
                raise SceneError(f"{token!r}: write an extra prop as +<prop>@<zone>, for example +barrel@back_right.")
            spec["add"].append([prop, zone.replace("-", "_")])
            continue
        key, eq, value = token.partition("=")
        if not eq:
            raise SceneError(f"{token!r}: use key=value (template=, wall=, floor=, mood=, shape=, seed=, size=, <slot>=<prop>) or +<prop>@<zone>.")
        key = key.replace("-", "_")
        if key == "template":
            spec = {"template": value, "slots": {}, "add": [], **({"mood": spec["mood"]} if "mood" in spec else {})}
        elif key == "shape":
            if value in ("none", "fixed", ""):
                spec["shape"] = "fixed"
                spec.pop("seed", None)
            else:
                spec["shape"] = value.lower()
                spec.setdefault("seed", random.randrange(1, 10**6))
        elif key == "seed":
            if not value.isdigit():
                raise SceneError("seed= is a whole number.")
            spec["seed"] = int(value)
        elif key == "size":
            spec["size"] = None if value in ("none", "") else value
            if spec["size"] is None:
                spec.pop("size")
        elif key in ("wall", "floor", "mood"):
            spec[key] = value.split(",") if key == "wall" and "," in value else value
        elif key == "clear" and value == "add":
            spec["add"] = []
        elif key in SLOTS:
            spec["slots"][key] = None if value in ("none", "") else value
        else:
            raise SceneError(f"unknown setting {key!r}. Slots: {', '.join(SLOTS)}.")
    if "template" not in spec:
        raise SceneError("a new scene needs template=<name>. Templates: " + ", ".join(catalog()["templates"]))
    if "shape" not in spec and (current is None or any(t.startswith("template=") for t in tokens)):
        # A new place gets a room of a shape the theme likes, from a seed it keeps. A saved place keeps its room.
        from stage import arena

        spec["seed"] = random.randrange(1, 10**6)
        spec["shape"] = arena.pick_shape(arena.arena_data()["scene_looks"].get(spec["template"], "dungeon"), spec["seed"])
    return spec
