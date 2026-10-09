"""The tile grid that the crawl and the combat board share: lines, sight and walking distance.

A grid is a list of rows of one-character tiles. This module does not know what a tile means:
each caller passes the tiles that block sight or that can be walked on. `crawl.py` walks 4
directions over its own tiles. The combat board (below, added later) walks 8 directions over its
own tiles. See combat-board.md.
"""

from __future__ import annotations

import io
import json
import math
import random
import re
from collections import deque
from functools import cache, lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data" / "crawl.json"
T = 32


def around4(x: int, y: int, w: int, h: int):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if 0 <= x + dx < w and 0 <= y + dy < h:
            yield x + dx, y + dy


def flood(grid, start: tuple[int, int], walkable) -> dict[tuple[int, int], int]:
    """Walking distance (4 directions) from start to every reachable cell."""
    h, w = len(grid), len(grid[0])
    dist = {start: 0}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for n in around4(x, y, w, h):
            if n not in dist and grid[n[1]][n[0]] in walkable:
                dist[n] = dist[(x, y)] + 1
                queue.append(n)
    return dist


def line(x0: int, y0: int, x1: int, y1: int):
    """Bresenham: the cells from (x0, y0) to (x1, y1)."""
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x1 > x0 else -1), (1 if y1 > y0 else -1)
    err = dx + dy
    while True:
        yield x0, y0
        if (x0, y0) == (x1, y1):
            return
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def sight(grid, x: int, y: int, radius: int, opaque) -> set[tuple[int, int]]:
    """Cells in sight: a line to each cell on the radius square, cut at the circle and the first opaque tile."""
    h, w = len(grid), len(grid[0])
    limit = radius * radius + radius
    seen = {(x, y)}
    edge = [(x + d, y - radius) for d in range(-radius, radius + 1)] + [(x + d, y + radius) for d in range(-radius, radius + 1)]
    edge += [(x - radius, y + d) for d in range(-radius, radius + 1)] + [(x + radius, y + d) for d in range(-radius, radius + 1)]
    for tx, ty in edge:
        for cx, cy in line(x, y, tx, ty):
            if not (0 <= cx < w and 0 <= cy < h) or (cx - x) ** 2 + (cy - y) ** 2 > limit:
                break
            seen.add((cx, cy))
            if (cx, cy) != (x, y) and grid[cy][cx] in opaque:
                break
    # Opaque tiles next to a seen open cell: without this, room corners stay dark.
    for cx, cy in list(seen):
        if grid[cy][cx] not in opaque:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] in opaque:
                        seen.add((nx, ny))
    return seen


# -- tiles -----------------------------------------------------------------


@cache
def data() -> dict:
    return json.loads(DATA_PATH.read_text())


def themes() -> dict:
    return data()["themes"]


@cache
def _variants(family: str) -> tuple[str, ...]:
    """The numbered tiles of a DCSS family, without the _new/_old duplicates."""
    from stage.assets import ensure_dcss

    folder, name = (ensure_dcss() / family).parent, Path(family).name
    pattern = re.compile(re.escape(name) + r"_?(\d*)\.png")
    found = [(int(m.group(1) or 0), p.name) for p in folder.glob("*.png") if (m := pattern.fullmatch(p.name))]
    return tuple(str(folder / n) for _, n in sorted(found))[:8]


def _floor_tiles(name: str) -> list:
    from PIL import Image

    if name.startswith("lpc:"):
        from stage import scenes

        return [scenes.surface_tile(name[4:], col, row) for row in (0, 1) for col in (0, 1)]
    return [Image.open(p).convert("RGBA") for p in _variants(name)]


def look_of(theme: str) -> dict:
    """The tiles of a theme: a wall family, a floor, an exit tile. An arena keeps its own copy (see `arena.create`)."""
    t = themes()[theme]
    return {"wall": t["wall"], "floor": t["floor"], "exit": t["exit"], "wall_variants": t.get("wall_variants", 8)}


def _walls(wall: str, n: int = 8) -> tuple[str, ...]:
    return _variants(wall)[:n]


def tile_counts(theme: str) -> dict:
    return look_counts(look_of(theme))


@cache
def _look_counts(wall: str, floor: str, n: int) -> dict:
    floors = 4 if floor.startswith("lpc:") else len(_variants(floor))
    return {"walls": len(_walls(wall, n)), "floors": floors, "pattern": floor.startswith("lpc:")}


def look_counts(look: dict) -> dict:
    return _look_counts(look["wall"], look["floor"], look.get("wall_variants", 8))


def atlas_png(theme: str) -> bytes:
    return atlas_for(look_of(theme))


def atlas_for(look: dict) -> bytes:
    return _atlas(look["wall"], look["floor"], look["exit"], look.get("wall_variants", 8))


@lru_cache(maxsize=32)
def _atlas(wall: str, floor: str, exit_tile: str, n: int) -> bytes:
    """Row 0: wall variants. Row 1: floor variants. Row 2: closed door, open door, exit."""
    from PIL import Image

    from stage.assets import ensure_dcss

    dcss = ensure_dcss()
    walls = [Image.open(p).convert("RGBA") for p in _walls(wall, n)]
    floors = _floor_tiles(floor)
    doors = data()["doors"]
    specials = [Image.open(dcss / p).convert("RGBA") for p in (doors["closed"], doors["open"], exit_tile)]
    floor0 = floors[0]
    img = Image.new("RGBA", (T * max(len(walls), len(floors), 3), T * 3))
    for row, tiles in enumerate((walls, floors, specials)):
        for i, tile in enumerate(tiles):
            if row == 2:
                # Doors and the exit stand on the floor.
                img.alpha_composite(floor0, (i * T, row * T))
            img.alpha_composite(tile.crop((0, 0, T, T)), (i * T, row * T))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@lru_cache(maxsize=64)
def icon_png(name: str) -> bytes | None:
    from PIL import Image

    from stage.assets import ensure_dcss

    rel = data()["icons"].get(name)
    if rel is None:
        return None
    buf = io.BytesIO()
    Image.open(ensure_dcss() / rel).convert("RGBA").save(buf, "PNG")
    return buf.getvalue()


def variant(x: int, y: int, n: int) -> int:
    """A stable tile variant per cell, variant 0 about half of the time. Same as variant() in CrawlView.tsx."""
    h = ((x * 374761393) & 0xFFFFFFFF) ^ ((y * 668265263) & 0xFFFFFFFF)
    k = (h ^ (h >> 13)) % (n * 2)
    return k if k < n else 0


# -- the combat arena ------------------------------------------------------
# One room, built for a fight. The DM gives words (layout, size, light, features); the stage makes
# the room from a seed. A unit walks 8 directions here, so these functions take the blocking tiles
# as arguments, as the crawl does. The arena file holds the whole layout and the positions.

ARENA_DATA_PATH = Path(__file__).resolve().parent / "data" / "arena.json"
SIZES = {"small": (12, 8), "medium": (16, 10)}
LAYOUTS = ("open", "chokepoint", "pillars", "chasm")
LIGHTS = ("lit", "dim", "dark")
WHERES = ("party", "center", "foes")
HAZARDS = ("lava", "water")
WALL, FLOOR, DOOR, HAZARD = "#", ".", "d", "~"
STAND = {FLOOR, DOOR}  # tiles a unit can stand on; a prop on one may still block it
COVER_BONUS = {"none": 0, "half": 2, "three-quarters": 5}
DEFAULT_BOARD = {"blocks_move": True, "blocks_sight": False, "cover": "none", "hp": None, "tags": []}
ZONE_ROW = {"back": "top", "mid": "middle", "front": "bottom"}
MAX_TRIES = 60


class ArenaError(ValueError):
    """A bad arena setting. The message says how to fix it."""


@cache
def arena_data() -> dict:
    return json.loads(ARENA_DATA_PATH.read_text())


def board_of(kind: str) -> dict:
    """What a prop does on the board: from its `board` entry in scenery.json, else the default (blocks movement, no cover)."""
    from stage import scenes

    entry = (scenes.catalog()["props"].get(kind) or {}).get("board") or {}
    return {**DEFAULT_BOARD, **entry}


def cheb(a, b) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def blocked_cells(a: dict) -> set[tuple[int, int]]:
    """Tiles no unit can enter: walls, hazards, and props that block movement."""
    out = {(x, y) for y, row in enumerate(a["grid"]) for x, c in enumerate(row) if c not in STAND}
    return out | {(p["x"], p["y"]) for p in a["props"] if board_of(p["kind"])["blocks_move"]}


def opaque_cells(a: dict) -> set[tuple[int, int]]:
    """Tiles that stop a line of sight: walls and tall props."""
    out = {(x, y) for y, row in enumerate(a["grid"]) for x, c in enumerate(row) if c == WALL}
    return out | {(p["x"], p["y"]) for p in a["props"] if board_of(p["kind"])["blocks_sight"]}


def cover_cells(a: dict) -> dict[tuple[int, int], str]:
    return {(p["x"], p["y"]): c for p in a["props"] if (c := board_of(p["kind"])["cover"]) != "none"}


def between(a, b):
    """The cells strictly between two cells, on the line."""
    cells = list(line(a[0], a[1], b[0], b[1]))
    return cells[1:-1]


def clear_line(a, b, opaque) -> bool:
    return not any(c in opaque for c in between(a, b))


def cover_between(a, b, cover: dict) -> str:
    """The best cover on the line from a to b: none, half or three-quarters."""
    best = "none"
    for c in between(a, b):
        if COVER_BONUS[cover.get(c, "none")] > COVER_BONUS[best]:
            best = cover[c]
    return best


def reach(start, limit: int, blocked, size: tuple[int, int], occupied=frozenset()):
    """Walk 8 directions from start, up to `limit` steps: (distance by cell, previous cell by cell).

    A diagonal step needs both side cells free of blocking tiles. A unit cannot enter or pass an occupied cell.
    """
    w, h = size
    start = tuple(start)
    dist, prev, queue = {start: 0}, {}, deque([start])
    while queue:
        x, y = queue.popleft()
        if dist[(x, y)] >= limit:
            continue
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (x + dx, y + dy)
                if (dx or dy) and 0 <= n[0] < w and 0 <= n[1] < h and n not in dist and n not in blocked and n not in occupied:
                    if dx and dy and ((x + dx, y) in blocked or (x, y + dy) in blocked):
                        continue
                    dist[n] = dist[(x, y)] + 1
                    prev[n] = (x, y)
                    queue.append(n)
    return dist, prev


def path_from(prev: dict, start, target) -> list[tuple[int, int]]:
    """The steps from start to target (without start), from the `prev` map of `reach`."""
    out, cur = [], tuple(target)
    while cur != tuple(start):
        out.append(cur)
        cur = prev[cur]
    return out[::-1]


# -- the spec from the DM's tokens ------------------------------------------


def _where(word: str, what: str) -> tuple[str, str]:
    thing, at, where = word.partition("@")
    if not at or where not in WHERES:
        raise ArenaError(f"{what}={word}: write {what}=<thing>@<where>, where is one of {', '.join(WHERES)}.")
    return thing, where


def parse(tokens: list[str]) -> dict:
    """A spec from `key=value` tokens: layout=, size=, light=, ambush=, seed=, theme=, feature=, hazard=."""
    from stage import scenes

    spec: dict = {"features": [], "hazards": []}
    for token in tokens:
        key, eq, value = token.partition("=")
        key = key.strip().lower()
        if not eq:
            raise ArenaError(f"{token!r}: write key=value (layout=, size=, light=, ambush=, seed=, theme=, feature=, hazard=).")
        if key == "layout":
            if value not in LAYOUTS:
                raise ArenaError(f"layout= is one of {', '.join(LAYOUTS)}.")
            spec["layout"] = value
        elif key == "size":
            if value not in SIZES:
                raise ArenaError(f"size= is one of {', '.join(SIZES)}.")
            spec["size"] = value
        elif key == "light":
            if value not in LIGHTS:
                raise ArenaError(f"light= is one of {', '.join(LIGHTS)}.")
            spec["light"] = value
        elif key == "ambush":
            if value not in ("yes", "no"):
                raise ArenaError("ambush= is yes or no.")
            spec["ambush"] = value == "yes"
        elif key == "seed":
            if not value.isdigit():
                raise ArenaError("seed= is a whole number.")
            spec["seed"] = int(value)
        elif key == "theme":
            if value not in themes():
                raise ArenaError(f"no theme {value!r}. Themes: {', '.join(themes())}.")
            spec["theme"] = value
        elif key == "feature":
            thing, where = _where(value, "feature")
            if thing not in ("cover", "pillar", "barrels") and thing not in scenes.catalog()["props"]:
                raise ArenaError(f"feature={value}: the thing is cover, pillar, barrels, or a prop of the scene catalog.")
            spec["features"].append([thing, where])
        elif key == "hazard":
            thing, where = _where(value, "hazard")
            if thing not in HAZARDS:
                raise ArenaError(f"hazard={value}: the hazard is lava or water.")
            spec["hazards"].append([thing, where])
        else:
            raise ArenaError(f"unknown setting {key!r}. Use layout=, size=, light=, ambush=, seed=, theme=, feature=, hazard=.")
    return spec


# -- where the fight starts: a site room, a saved scene, or nothing ----------


def source_of(campaign_dir: Path, stage: dict, spec: dict) -> dict:
    """What the arena looks like and holds: its tiles (a look), its prop family (decor), its shell and its scene props."""
    from stage import crawl, scenes

    cfg = arena_data()
    theme, props = spec.get("theme"), []
    if stage.get("explore") and (site := crawl.load(campaign_dir, stage["explore"])):
        theme = theme or site["spec"]["theme"]
        out = {"kind": "site", "id": stage["explore"], "look": look_of(theme), "shell": "room", "layout": "pillars"}
        out["decor"] = cfg["site_decor"].get(theme, "dungeon")
        return out
    scene = scenes.load(campaign_dir, stage["scene"]) if stage.get("scene") else None
    if scene and scene.get("template") in cfg["scene_looks"]:
        template = scene["template"]
        resolved = scenes.resolve(scene)
        walls = theme or cfg["scene_looks"][template]
        look = {**look_of(walls), "floor": "lpc:" + resolved["floor"]}
        for slot, name in resolved["slots"].items():
            props.append((name, slot))
        props += [(name, zone) for name, zone in resolved["add"]]
        out = {"kind": "scene", "id": stage["scene"], "look": look, "props": props}
        out["shell"] = "open" if template in cfg["open_templates"] else "room"
        out["decor"] = "forest" if out["shell"] == "open" else cfg["site_decor"].get(walls, "dungeon")
        out["layout"] = "open"
        return out
    theme = theme or "forest"
    return {"kind": "none", "id": None, "look": look_of(theme), "shell": "open", "layout": "open", "props": [],
            "decor": cfg["site_decor"].get(theme, "forest")}


# -- the generator -----------------------------------------------------------


def generate(spec: dict, source: dict, n_party: int = 2, n_foes: int = 3) -> dict:
    """A new arena from its spec and its source: shell, layout, source props, DM features, starts. Same seed, same arena."""
    from stage import scenes

    spec = {"layout": source["layout"], "size": "medium", "light": "lit", "ambush": False, **spec}
    spec.setdefault("seed", random.randrange(1, 10**6))
    w, h = SIZES[spec["size"]]
    cx, my = w // 2, h // 2
    decor = arena_data()["decor"][source["decor"]]
    prop_catalog = scenes.catalog()["props"]
    for attempt in range(MAX_TRIES):
        rng = random.Random(f"{spec['seed']}:{attempt}")
        edits = attempt < MAX_TRIES * 2 // 3  # the last tries leave out the DM's features, so the arena still gets made
        features, hazards = (spec["features"], spec["hazards"]) if edits else ([], [])
        grid = [[WALL if x in (0, w - 1) or y in (0, h - 1) else FLOOR for x in range(w)] for y in range(h)]
        if source["shell"] == "room":
            grid[my][0] = grid[my][w - 1] = DOOR
        props: list[dict] = []
        taken: set[tuple[int, int]] = set()

        def free(x, y):
            return 1 <= x <= w - 2 and 1 <= y <= h - 2 and 3 <= x <= w - 4 and grid[y][x] == FLOOR and (x, y) not in taken

        def put(kind, x, y):
            if free(x, y):
                props.append({"id": f"{kind}#{sum(p['kind'] == kind for p in props) + 1}", "kind": kind, "x": x, "y": y})
                taken.add((x, y))

        def nearest(ax, ay, n):
            cells = [(x, y) for y in range(1, h - 1) for x in range(3, w - 3) if free(x, y)]
            return sorted(cells, key=lambda c: (math.hypot(c[0] - ax, c[1] - ay) + rng.random() * 0.8))[:n]

        layout = spec["layout"]
        if layout == "chokepoint":
            gap = my + rng.randint(-1, 1)
            for y in range(1, h - 1):
                if abs(y - gap) > 1:
                    grid[y][cx] = WALL
            put(rng.choice(decor["cover"]), cx - 2, 2)
            put(rng.choice(decor["cover"]), cx + 2, h - 3)
        elif layout == "pillars":
            for x in (cx - 3, cx, cx + 3):
                for y in (2, my, h - 3):
                    if not (x == cx and y == my) and rng.random() > 0.2:
                        put(decor["pillar"], x, y)
        elif layout == "chasm":
            gap = my - 1 + rng.randint(0, 1)
            for x in (cx, cx + 1):
                for y in range(1, h - 1):
                    grid[y][x] = FLOOR if gap <= y <= gap + 1 else HAZARD
        else:
            for _ in range(3 + rng.randint(0, 2)):
                put(rng.choice(decor["obstacles"]), rng.randint(3, w - 4), rng.randint(1, h - 2))
        for _ in range(2):
            put(rng.choice(decor["small"]), rng.randint(3, w - 4), rng.randint(1, h - 2))
        for name, slot in source.get("props", []):
            entry = prop_catalog.get(name) or {}
            if entry.get("on") == "wall" or entry.get("flat") or "_" not in slot or slot.split("_")[0] not in ZONE_ROW:
                continue
            row, col = slot.split("_", 1)
            y = {"back": 2, "mid": my, "front": h - 3}[row]
            x = {"left": 3, "center": cx, "right": w - 4}.get(col, cx)
            for dx in range(2):
                if free(x + dx, y):
                    put(name, x + dx, y)
                    break
        for thing, where in features:
            ax = {"party": 3, "center": cx, "foes": w - 4}[where]
            kind = rng.choice(decor["cover"]) if thing == "cover" else decor["pillar"] if thing == "pillar" else "barrel" if thing == "barrels" else thing
            for x, y in nearest(ax, my + rng.randint(-1, 1), 2 if thing == "barrels" else 1):
                put(kind, x, y)
        for _kind, where in hazards:
            ax = {"party": 3, "center": cx, "foes": w - 4}[where]
            for x, y in nearest(ax, my + rng.randint(-1, 1), 4):
                grid[y][x] = HAZARD
        items = []
        spots = nearest(4.5, my, 4)
        if spots:
            x, y = spots[rng.randrange(len(spots))]
            items.append({"id": "item#1", "name": decor["item"], "x": x, "y": y})
        a = {"w": w, "h": h, "grid": ["".join(r) for r in grid], "props": props, "items": items}
        blocked = blocked_cells(a)
        free_tiles = [(x, y) for y in range(h) for x in range(w) if (x, y) not in blocked]

        def pick(ax, ay, n, lo, hi, avoid):
            cells = [(x, y) for y in range(1, h - 1) for x in range(lo, hi + 1)
                     if (x, y) not in blocked and (x, y) not in avoid and grid[y][x] == FLOOR]
            return sorted(cells, key=lambda c: math.hypot(c[0] - ax, c[1] - ay) + rng.random() * 0.6)[:n]

        party = pick(2, my, n_party, 1, 3, set())
        if spec["ambush"] and n_foes >= 3:
            top = pick(cx - 2, 1, 1, 1, w - 2, set(party))
            bottom = pick(cx + 2, h - 2, 1, 1, w - 2, set(party) | set(top))
            rest = pick(w - 3, my, n_foes - 2, w - 5, w - 2, set(party) | set(top) | set(bottom))
            foes = top + bottom + rest
        else:
            foes = pick(w - 3, my, n_foes, w - 5, w - 2, set(party))
        if len(party) < n_party or len(foes) < n_foes:
            continue
        foes.sort(key=lambda p: min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in party))
        dist, _ = reach(party[0], w * h, blocked, (w, h))
        if not all(p in dist for p in party + foes) or len(dist) < 0.9 * len(free_tiles):
            continue
        a.update(
            spec={**spec, "features": spec["features"], "source": source["kind"], "source_id": source["id"], "decor": source["decor"]},
            look=source["look"], starts={"party": [list(p) for p in party], "foes": [list(p) for p in foes]},
            units={}, seen=["0" * w for _ in range(h)])
        return a
    raise ArenaError("could not make this arena; try another seed=.")


# -- files --------------------------------------------------------------------


def arenas_dir(campaign_dir: Path) -> Path:
    return campaign_dir / "stage" / "arenas"


def load(campaign_dir: Path, arena_id: str) -> dict | None:
    from stage.files import read_json

    return read_json(arenas_dir(campaign_dir) / f"{arena_id}.json") if re.fullmatch(r"[a-z0-9-]+", arena_id) else None


def save(campaign_dir: Path, arena_id: str, a: dict) -> Path:
    from stage.files import write_json

    return write_json(arenas_dir(campaign_dir) / f"{arena_id}.json", a)


def new_id(campaign_dir: Path) -> str:
    folder = arenas_dir(campaign_dir)
    return f"arena-{len(list(folder.glob('arena-*.json'))) + 1 if folder.is_dir() else 1}"


# -- the preview ---------------------------------------------------------------


def prop_png(kind: str) -> bytes:
    """A prop as one picture for the board: the scene sprite, scaled down so it does not cover its neighbors."""
    return _prop_png(kind)


@lru_cache(maxsize=64)
def _prop_png(kind: str) -> bytes:
    from stage import scenes

    img = scenes.prop_image(kind).convert("RGBA")
    box = img.getchannel("A").getbbox()
    if box:
        img = img.crop(box)
    scale = min(1.0, T * 1.25 / img.width, T * 1.9 / img.height)
    if scale < 1.0:
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def render_full(a: dict, units: dict | None = None):
    """The whole arena with props, items, and the start tiles, for the DM's preview (never sent to players)."""
    from PIL import Image, ImageDraw

    atlas = Image.open(io.BytesIO(atlas_for(a["look"])))
    counts = look_counts(a["look"])
    img = Image.new("RGBA", (a["w"] * T, a["h"] * T), (0, 0, 0, 255))

    def tile(col: int, row: int):
        return atlas.crop((col * T, row * T, (col + 1) * T, (row + 1) * T))

    hazard = icon_png("water" if a["spec"]["decor"] == "forest" else "lava")
    for y, row in enumerate(a["grid"]):
        for x, c in enumerate(row):
            if c == WALL:
                img.alpha_composite(tile(variant(x, y, counts["walls"]), 0), (x * T, y * T))
                continue
            f = (x % 2) + (y % 2) * 2 if counts["pattern"] else variant(x, y, counts["floors"])
            img.alpha_composite(tile(f, 1), (x * T, y * T))
            if c == DOOR:
                img.alpha_composite(tile(1, 2), (x * T, y * T))
            elif c == HAZARD and hazard:
                img.alpha_composite(Image.open(io.BytesIO(hazard)).convert("RGBA").crop((0, 0, T, T)), (x * T, y * T))
    draw = ImageDraw.Draw(img)
    for p in a["props"]:
        sprite = Image.open(io.BytesIO(prop_png(p["kind"])))
        img.alpha_composite(sprite, (p["x"] * T + (T - sprite.width) // 2, (p["y"] + 1) * T - sprite.height))
    for it in a["items"]:
        draw.ellipse((it["x"] * T + 10, it["y"] * T + 10, it["x"] * T + 22, it["y"] * T + 22), fill=(127, 178, 214, 255), outline=(232, 244, 255, 255))
    for side, color in (("party", (95, 168, 224, 255)), ("foes", (229, 83, 79, 255))):
        for x, y in a["starts"][side]:
            draw.rectangle((x * T + 2, y * T + 2, x * T + 29, y * T + 29), outline=color, width=2)
    return img
