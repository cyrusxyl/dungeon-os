"""The tile grid that the crawl and the combat board share, and the arena a fight is played in.

A grid is a list of rows of one-character tiles. The shared helpers (lines, sight, walking distance,
tile atlas) do not know what a tile means: each caller passes the tiles that block sight or that can be
walked on. `crawl.py` walks 4 directions over its own tiles. The arena (below) walks 8 directions over
its own tiles, and `stage/board.py` runs the rules on it. See combat-board.md.
"""

from __future__ import annotations

import io
import heapq
import json
import math
import random
import re
from collections import deque
from functools import cache, lru_cache
from pathlib import Path

from stage import cast, rooms

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
SIZES = tuple(rooms.CLASSES)
SHAPES = rooms.SHAPE_NAMES
LAYOUTS = ("open", "chokepoint", "pillars", "chasm")
LIGHTS = ("lit", "dim", "dark")
WHERES = ("party", "center", "foes")
HAZARDS = ("lava", "water")
WALL, FLOOR, DOOR, HAZARD, VOID = "#", ".", "d", "~", "-"  # the void is outside the room: never drawn, never walkable, blocks sight
STAND = {FLOOR, DOOR}  # tiles a unit can stand on; a prop on one may still block it
STEP_FT = (5, 7)  # feet for a straight step and a diagonal one
COVER_BONUS = {"none": 0, "half": 2, "three-quarters": 5}
DEFAULT_BOARD = {"blocks_move": True, "blocks_sight": False, "cover": "none", "hp": None, "tags": []}
ZONE_ROWS = ("back", "mid", "front")
MAX_TRIES = 60
SETTING_KEYS = ("reaction_seconds", "round_summary")
STYLES = ("aggressive", "sneaky", "cowardly", "skirmisher")


class ArenaError(ValueError):
    """A bad arena setting. The message says how to fix it."""


@cache
def arena_data() -> dict:
    return json.loads(ARENA_DATA_PATH.read_text())


@cache
def board_of(kind: str) -> dict:
    """What a prop does on the board: from its `board` entry in scenery.json, else the default (blocks movement, no cover;
    a prop that lies flat, such as a rug, blocks nothing)."""
    from stage import scenes

    prop = scenes.catalog()["props"].get(kind) or {}
    entry = prop.get("board") or {}
    return {**DEFAULT_BOARD, **({"blocks_move": False} if prop.get("flat") and not entry else {}), **entry}


def cheb(a, b) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def blocked_cells(a: dict) -> set[tuple[int, int]]:
    """Tiles no unit can enter: walls, hazards, and props that block movement."""
    out = {(x, y) for y, row in enumerate(a["grid"]) for x, c in enumerate(row) if c not in STAND}
    return out | {(p["x"], p["y"]) for p in a["props"] if board_of(p["kind"])["blocks_move"]}


def opaque_cells(a: dict) -> set[tuple[int, int]]:
    """Tiles that stop a line of sight: walls, the void and tall props."""
    out = {(x, y) for y, row in enumerate(a["grid"]) for x, c in enumerate(row) if c in (WALL, VOID)}
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


def shape_cells(shape: dict, origin, aim, size: tuple[int, int]) -> set[tuple[int, int]]:
    """The cells an area covers. `aim` is the center of a sphere or a cube, and the direction of a cone or a line from `origin`
    (a cone or a line starts next to the origin and never covers it). One tile is 5 ft."""
    w, h = size
    r = shape["size_ft"] // 5
    ox, oy = origin
    ax, ay = aim
    kind = shape["type"]
    inside = lambda c: 0 <= c[0] < w and 0 <= c[1] < h  # noqa: E731
    if kind == "single":
        return {tuple(aim)}
    if kind in ("sphere", "cylinder"):
        return {(x, y) for x in range(ax - r, ax + r + 1) for y in range(ay - r, ay + r + 1)
                if inside((x, y)) and math.hypot(x - ax, y - ay) <= r + 0.5}
    if kind == "cube":
        half = max(1, r) // 2
        return {(x, y) for x in range(ax - half, ax + half + 1) for y in range(ay - half, ay + half + 1) if inside((x, y))}
    dx, dy = ax - ox, ay - oy
    norm = math.hypot(dx, dy) or 1
    if kind == "line":
        cells = {(round(ox + dx / norm * i), round(oy + dy / norm * i)) for i in range(1, r + 1)}
        return {c for c in cells if inside(c)}
    # a cone: within `size` of the origin and within 26.5 degrees of the aim (a 53-degree spread)
    out = set()
    for x in range(ox - r, ox + r + 1):
        for y in range(oy - r, oy + r + 1):
            vx, vy = x - ox, y - oy
            dist = math.hypot(vx, vy)
            if inside((x, y)) and (vx or vy) and dist <= r + 0.5 and (vx * dx + vy * dy) / (dist * norm) >= math.cos(math.radians(26.6)):
                out.add((x, y))
    return out


def reach(start, limit: int, blocked, size: tuple[int, int], occupied=frozenset(), cost: tuple[int, int] = (1, 1)):
    """Walk 8 directions from start, up to `limit`: (distance by cell, previous cell by cell).

    `cost` is (straight step, diagonal step). The board uses (5, 7): 5 ft straight, 7 ft on the diagonal (5 x 1.4).
    A diagonal step needs both side cells free of blocking tiles. A unit cannot enter or pass an occupied cell.
    """
    w, h = size
    start = tuple(start)
    dist, prev, queue, done = {start: 0}, {}, [(0, start)], set()
    while queue:
        d, (x, y) = heapq.heappop(queue)
        if (x, y) in done:
            continue
        done.add((x, y))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (x + dx, y + dy)
                if (dx or dy) and 0 <= n[0] < w and 0 <= n[1] < h and n not in blocked and n not in occupied:
                    if dx and dy and ((x + dx, y) in blocked or (x, y + dy) in blocked):
                        continue
                    nd = d + cost[1 if dx and dy else 0]
                    if nd <= limit and nd < dist.get(n, limit + 1):
                        dist[n], prev[n] = nd, (x, y)
                        heapq.heappush(queue, (nd, n))
    return dist, prev


def step_cost(a, b) -> int:
    """The feet of one step between neighbouring cells."""
    return STEP_FT[1 if a[0] != b[0] and a[1] != b[1] else 0]


def path_from(prev: dict, start, target) -> list[tuple[int, int]]:
    """The steps from start to target (without start), from the `prev` map of `reach`."""
    out, cur = [], tuple(target)
    while cur != tuple(start):
        out.append(cur)
        cur = prev[cur]
    return out[::-1]


# -- the spec from the DM's tokens ------------------------------------------


def check_settings(values: dict) -> dict:
    """The combat settings in `values` (reaction_seconds: 0 to 60, 0 for no limit; round_summary: true or false), checked."""
    out = {}
    if "reaction_seconds" in values:
        n = values["reaction_seconds"]
        if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= 60:
            raise ArenaError("reaction_seconds is a whole number from 0 to 60 (0 is no limit).")
        out["reaction_seconds"] = n
    if "round_summary" in values:
        if not isinstance(values["round_summary"], bool):
            raise ArenaError("round_summary is true or false.")
        out["round_summary"] = values["round_summary"]
    return out


def _where(word: str, what: str) -> tuple[str, str]:
    thing, at, where = word.partition("@")
    if not at or where not in WHERES:
        raise ArenaError(f"{what}={word}: write {what}=<thing>@<where>, where is one of {', '.join(WHERES)}.")
    return thing, where


def parse(tokens: list[str]) -> dict:
    """A spec from `key=value` tokens: layout=, shape=, size=, light=, ambush=, seed=, theme=, feature=, hazard=."""
    from stage import scenes

    spec: dict = {"features": [], "hazards": [], "settings": {}}
    for token in tokens:
        key, eq, value = token.partition("=")
        key = key.strip().lower()
        if not eq:
            raise ArenaError(f"{token!r}: write key=value (layout=, shape=, size=, light=, ambush=, seed=, theme=, feature=, hazard=).")
        if key == "layout":
            if value not in LAYOUTS:
                raise ArenaError(f"layout= is one of {', '.join(LAYOUTS)}.")
            spec["layout"] = value
        elif key == "shape":
            if value.lower() not in SHAPES:
                raise ArenaError(f"shape= is one of {', '.join(SHAPES)}.")
            spec["shape"] = value.lower()
        elif key == "size":
            if value not in SIZES:
                raise ArenaError(f"size= is one of {', '.join(SIZES)}.")
            spec["size"] = value
        elif key == "orient":
            if value not in tuple("01234567"):
                raise ArenaError("orient= is a number from 0 to 7 (how the room is turned; for tests).")
            spec["orient"] = int(value)
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
        elif key == "reaction_seconds":
            spec["settings"] |= check_settings({"reaction_seconds": int(value) if value.isdigit() else value})
        elif key == "style":
            if value not in STYLES:
                raise ArenaError(f"style= is one of {', '.join(STYLES)}.")
            spec["style"] = value
        elif key == "summary":
            if value not in ("on", "off"):
                raise ArenaError("summary= is on or off.")
            spec["settings"]["round_summary"] = value == "on"
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
            raise ArenaError(f"unknown setting {key!r}. Use layout=, shape=, size=, light=, ambush=, seed=, theme=, feature=, hazard=, summary=, reaction_seconds=, style=.")
    return spec


# -- where the fight starts: a site room, a saved scene, or nothing ----------


def source_of(campaign_dir: Path, stage: dict, spec: dict) -> dict:
    """What the arena looks like and holds: its tiles (a look), its prop family (decor), its shell and its scene props."""
    from stage import crawl, scenes

    cfg = arena_data()
    theme, props = spec.get("theme"), []
    if stage.get("explore") and (site := crawl.load(campaign_dir, stage["explore"])):
        theme = theme or site["spec"]["theme"]
        out = {"kind": "site", "id": stage["explore"], "theme": theme, "look": look_of(theme), "shell": "room", "layout": "pillars"}
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
        room = scenes.room(scene)
        actors = stage.get("actors") or {}
        placed = {i: {**a, **cast.place(room, actors, seed=stage["scene"]).get(i, {})} for i, a in actors.items()}  # the CLI may start a fight before the server has placed the last actor
        out = {"kind": "scene", "id": stage["scene"], "theme": walls, "look": look, "props": props, "room": room, "scene_spec": scene,
               "cast": [{"id": i, "side": a.get("side") or "neutral", "cell": a["cell"]} for i, a in placed.items() if a.get("cell")]}
        out["shell"] = "open" if template in cfg["open_templates"] else "room"
        out["decor"] = "forest" if out["shell"] == "open" else cfg["site_decor"].get(walls, "dungeon")
        out["layout"] = "open"
        return out
    theme = theme or "forest"
    return {"kind": "none", "id": None, "theme": theme, "look": look_of(theme), "shell": "open", "layout": "open", "props": [],
            "decor": cfg["site_decor"].get(theme, "forest")}


# -- the generator -----------------------------------------------------------

START_GAP = 7  # the two start zones lie at least this far apart
KEEP_OFF = 3  # props stay this far from a start zone
SPACING = 2  # decor props are more than this far from each other (Chebyshev)
AROUND = [(dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]


def pick_shape(theme: str, seed: int) -> str:
    """A shape for a theme from the odds in arena.json. The seed decides."""
    odds = arena_data()["shapes"]
    table = odds.get(theme) or odds["default"]
    return random.Random(f"shape:{seed}").choices(list(table), weights=list(table.values()))[0]


def _cut(floor: list[tuple[int, int]], thick: int, rng: random.Random, grid: list[list[str]]) -> list[tuple[int, int]]:
    """The cells of a wall that cuts the room across its shorter side at the centroid, leaving a gap of 3 cells.

    `thick` is 1 for a wall, 2 for a chasm. The gap lies on floor, nearest the centroid, so both sides stay joined. Where the
    centroid lies on a passage no wider than the gap (an H or a pair of rooms), the line moves along the room to the first place
    where it cuts something.
    """
    xs, ys = [x for x, _ in floor], [y for _, y in floor]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    wide = max(xs) - min(xs) >= max(ys) - min(ys)
    centre, aim = (cx, cy) if wide else (cy, cx)
    along = range(len(grid)) if wide else range(len(grid[0]))
    at = lambda line, pos: (line, pos) if wide else (pos, line)  # noqa: E731
    for shift in (0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6):
        line = int(centre) + shift
        spots = [pos for pos in along if grid[at(line, pos)[1]][at(line, pos)[0]] == FLOOR]
        if not spots:
            continue
        mid = min(spots, key=lambda pos: abs(pos - aim - rng.randint(-1, 1)))
        out = []
        for i in range(thick):
            for pos in along:
                x, y = at(line + i, pos)
                if 0 <= y < len(grid) and 0 <= x < len(grid[0]) and grid[y][x] == FLOOR and abs(pos - mid) > 1:
                    out.append((x, y))
        if out:
            return out
    return []


def _prop_id(props: list[dict], kind: str) -> str:
    return f"{kind}#{sum(p['kind'] == kind for p in props) + 1}"


def _feature_kind(thing: str, decor: dict, rng: random.Random) -> str:
    """The prop a DM feature word means: cover, a pillar, barrels, or the name of a prop."""
    return rng.choice(decor["cover"]) if thing == "cover" else decor["pillar"] if thing == "pillar" else "barrel" if thing == "barrels" else thing


def room_board(room: dict) -> dict:
    """A scene room as a bare board, the shape the walking and sight rules read: {"w", "h", "grid", "props", "items"}. Each prop gets an id."""
    props: list[dict] = []
    for p in room["props"]:
        props.append({"id": _prop_id(props, p["kind"]), "kind": p["kind"], "x": p["x"], "y": p["y"], "flat": bool(p.get("flat"))})
    return {"w": len(room["grid"][0]), "h": len(room["grid"]), "grid": list(room["grid"]), "props": props, "items": []}


def _in_room(spec: dict, source: dict, party_ids: list[str], foe_ids: list[str]) -> dict | None:
    """The arena in the room of the scene: its grid and its props as they are, the party and the foes on the cells where the scene
    cast stands them (a cell a prop blocks is given up for the nearest free one). None when the starts cannot reach each other."""
    room = source["room"]
    grid = [list(row) for row in room["grid"]]
    w, h = len(grid[0]), len(grid)
    floor = [(x, y) for y in range(h) for x in range(w) if grid[y][x] == FLOOR]
    a = room_board(room)
    props = a["props"]
    blocked = blocked_cells(a)
    cells = {c["id"]: tuple(c["cell"]) for c in source["cast"]}
    taken: set[tuple[int, int]] = set()
    dist = lambda p, q: math.hypot(p[0] - q[0], p[1] - q[1])  # noqa: E731

    def start(want, near) -> tuple[int, int] | None:
        """The cell the cast gave, else the free cell nearest `near`."""
        ok = [c for c in floor if c not in blocked and c not in taken]
        if not ok:
            return None
        pick = want if want in ok else min(ok, key=lambda c: (dist(c, near), c))
        taken.add(pick)
        return pick

    seed_rng = random.Random(f"scene:{spec['seed']}")
    party = []
    centre = (sum(x for x, _ in floor) / len(floor), sum(y for _, y in floor) / len(floor))
    # A party member the scene did not place comes to where the party stands (else the left of the screen).
    side_of = {c["id"]: c["side"] for c in source["cast"]}
    home = cast.centre([cells[i] for i in cells if side_of[i] in ("party", "ally")]) or min(floor, key=lambda c: (c[0] - c[1], c))
    for pid in party_ids:
        c = start(cells.get(pid), party[-1] if party else home)
        party.append(c)
    if None in party:
        return None
    heart = (sum(x for x, _ in party) / len(party), sum(y for _, y in party) / len(party)) if party else centre
    far = max(floor, key=lambda c: (dist(c, heart), c))
    foes = []
    # A foe the DM names anew (a guard for the silhouettes that stood there) takes the cell of a hostile actor that is not in the fight.
    spare = [cells[c["id"]] for c in source["cast"] if c["side"] == "hostile" and c["id"] not in foe_ids and c["id"] not in party_ids]
    for fid in foe_ids:
        want = cells.get(fid) or (spare.pop(0) if spare else None)
        foes.append(start(want, want or far))
    if None in foes:
        return None
    anchor = {"party": heart, "center": centre, "foes": far}
    decor = arena_data()["decor"][source["decor"]]

    def nearest(where, n):
        ok = [c for c in floor if c not in blocked and c not in taken]
        return sorted(ok, key=lambda c: dist(c, where) + seed_rng.random() * 0.8)[:n]

    for thing, where in spec["features"]:
        kind = _feature_kind(thing, decor, seed_rng)
        for c in nearest(anchor[where], 2 if thing == "barrels" else 1):
            props.append({"id": _prop_id(props, kind), "kind": kind, "x": c[0], "y": c[1]})
            taken.add(c)
            if board_of(kind)["blocks_move"]:
                blocked.add(c)
    for _kind, where in spec["hazards"]:
        for x, y in nearest(anchor[where], 4):
            grid[y][x] = HAZARD
            blocked.add((x, y))
    spots = nearest(centre, 4)
    if spots:
        x, y = spots[seed_rng.randrange(len(spots))]
        a["items"].append({"id": "item#1", "name": decor["item"], "x": x, "y": y})
    a["grid"] = ["".join(r) for r in grid]
    free_tiles = {(x, y) for y in range(h) for x in range(w) if (x, y) not in blocked}
    if not party or not foes or not all(p in free_tiles for p in party + foes):
        return None
    reach_from = _reach4(free_tiles, party[0])
    if not all(p in reach_from for p in party + foes):
        return None
    ignored = [k for k in ("shape", "size", "orient", "layout") if k in spec and not (k == "layout" and spec[k] == "open")]
    a.update(
        spec={**spec, "shape": "scene", "size": "scene", "orient": 0, "layout": "open", "ignored": ignored, "source": source["kind"],
              "source_id": source["id"], "decor": source["decor"]},
        look=source["look"], starts={"party": [list(p) for p in party], "foes": [list(p) for p in foes]},
        units={}, seen=["0" * w for _ in range(h)], room=room, scene_spec=source["scene_spec"])
    return a


def generate(spec: dict, source: dict, n_party: int = 2, n_foes: int = 3, party_ids: list[str] | None = None, foe_ids: list[str] | None = None) -> dict:
    """A new arena from its spec and its source: room shape, layout, source props, DM features, starts. Same seed, same arena.

    The room is a mask of floor cells (`stage/rooms.py`). The party starts at the floor cell farthest from the centre, the foes
    at the cell farthest from that one. A prop stands only where all 8 neighbours are floor. Floor not taken by props must be one
    connected area.
    """
    from stage import scenes

    spec = {"layout": source["layout"], "light": "lit", "ambush": False, **spec}
    spec.setdefault("seed", random.randrange(1, 10**6))
    if source.get("room"):
        a = _in_room(spec, source, party_ids or [f"party{i}" for i in range(n_party)], foe_ids or [f"foe{i}" for i in range(n_foes)])
        if a:
            return a
        spec = {**spec, "fallback": "the scene room had no room for the fight, so the stage built another room"}
    asked = spec.get("shape")
    shape = asked or pick_shape(source.get("theme", "forest"), spec["seed"])
    decor = arena_data()["decor"][source["decor"]]
    prop_catalog = scenes.catalog()["props"]
    for attempt in range(MAX_TRIES):
        # The last tries leave out the DM's features, and (when the DM did not ask for a shape) the shape, so the arena still gets made.
        edits = attempt < MAX_TRIES * 2 // 3
        now = shape if asked or edits else "rect"
        rng = random.Random(f"{now}:{spec['seed']}:{attempt}")
        features, hazards = (spec["features"], spec["hazards"]) if edits else ([], [])
        made = rooms.mask(now, rng, spec.get("size"), spec.get("orient"))
        if not made:
            continue
        cells, used = made
        grid = rooms.grid_of(cells)
        w, h = len(grid[0]), len(grid)
        floor = sorted(cells)
        mx, my = sum(x for x, _ in floor) / len(floor), sum(y for _, y in floor) / len(floor)
        a_cell = max(floor, key=lambda c: math.hypot(c[0] - mx, c[1] - my))
        b_cell = max(floor, key=lambda c: math.hypot(c[0] - a_cell[0], c[1] - a_cell[1]))
        if math.hypot(b_cell[0] - a_cell[0], b_cell[1] - a_cell[1]) < START_GAP:
            continue
        anchor = {"party": a_cell, "center": (mx, my), "foes": b_cell}
        props: list[dict] = []
        taken: set[tuple[int, int]] = set()

        def surround(c) -> int:
            return sum(grid[c[1] + dy][c[0] + dx] == FLOOR for dx, dy in AROUND)

        def free(c, spaced=False) -> bool:
            """Floor with floor all around it, off the start zones, and (for decor) away from other props."""
            return (grid[c[1]][c[0]] == FLOOR and c not in taken and surround(c) == 9
                    and all(math.hypot(c[0] - o[0], c[1] - o[1]) >= KEEP_OFF for o in (a_cell, b_cell))
                    and (not spaced or all(cheb(c, t) > SPACING for t in taken)))

        def put(kind, c, spaced=False):
            if free(c, spaced):
                props.append({"id": _prop_id(props, kind), "kind": kind, "x": c[0], "y": c[1]})
                taken.add(c)

        def nearest(where, n, tight=True):
            """The cells nearest a point where a prop may stand (`tight`: with floor all around), a little shaken by the seed."""
            ok = [c for c in floor if (free(c) if tight else grid[c[1]][c[0]] == FLOOR and c not in taken)]
            return sorted(ok, key=lambda c: math.hypot(c[0] - where[0], c[1] - where[1]) + rng.random() * 0.8)[:n]

        def scatter(kinds, n, spaced=False):
            ok = [c for c in floor if free(c, spaced)]
            rng.shuffle(ok)
            for kind, c in zip((rng.choice(kinds) for _ in range(n)), ok):
                put(kind, c, spaced)

        layout = spec["layout"]
        if layout == "chokepoint":
            for x, y in _cut(floor, 1, rng, grid):
                grid[y][x] = WALL
            for side in (-1, 1):
                for c in nearest((mx + side * 2, my + side * 3), 1):
                    put(rng.choice(decor["cover"]), c)
        elif layout == "pillars":
            for dx in (-3, 0, 3):
                for dy in (-3, 0, 3):
                    if (dx or dy) and rng.random() > 0.2:
                        put(decor["pillar"], (round(mx) + dx, round(my) + dy), True)
        elif layout == "chasm":
            for x, y in _cut(floor, 2, rng, grid):
                grid[y][x] = HAZARD
        else:
            scatter(decor["obstacles"], 3 + rng.randint(0, 2), True)
        scatter(decor["small"], 2)
        lo_x, hi_x, lo_y, hi_y = min(x for x, _ in floor), max(x for x, _ in floor), min(y for _, y in floor), max(y for _, y in floor)
        for name, slot in source.get("props", []):
            entry = prop_catalog.get(name) or {}
            if entry.get("on") == "wall" or entry.get("flat") or "_" not in slot or slot.split("_")[0] not in ZONE_ROWS:
                continue
            row, col = slot.split("_", 1)
            fy = {"back": 0.2, "mid": 0.5, "front": 0.8}[row]
            fx = {"left": 0.2, "center": 0.5, "right": 0.8}.get(col, 0.5)
            for c in nearest((lo_x + (hi_x - lo_x) * fx, lo_y + (hi_y - lo_y) * fy), 1):
                put(name, c)
        for thing, where in features:
            kind = _feature_kind(thing, decor, rng)
            for c in nearest(anchor[where], 2 if thing == "barrels" else 1):
                put(kind, c)
        for _kind, where in hazards:
            for x, y in nearest(anchor[where], 4):
                grid[y][x] = HAZARD
        items = []
        spots = nearest(anchor["center"], 4, tight=False)
        if spots:
            x, y = spots[rng.randrange(len(spots))]
            items.append({"id": "item#1", "name": decor["item"], "x": x, "y": y})
        if source["shell"] == "room":
            # A door in the wall cell nearest each start zone: a wall that touches floor on one side.
            for target in (a_cell, b_cell):
                walls = [(x, y) for y in range(h) for x in range(w) if grid[y][x] == WALL
                         and any(0 <= x + dx < w and 0 <= y + dy < h and grid[y + dy][x + dx] == FLOOR for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
                if walls:
                    x, y = min(walls, key=lambda c: (math.hypot(c[0] - target[0], c[1] - target[1]), c))
                    grid[y][x] = DOOR
        a = {"w": w, "h": h, "grid": ["".join(r) for r in grid], "props": props, "items": items}
        blocked = blocked_cells(a)
        free_tiles = {(x, y) for y in range(h) for x in range(w) if (x, y) not in blocked}

        def pick(where, n, avoid):
            ok = [c for c in floor if c not in blocked and c not in avoid and grid[c[1]][c[0]] == FLOOR]
            return sorted(ok, key=lambda c: math.hypot(c[0] - where[0], c[1] - where[1]) - (1.5 if surround(c) == 9 else 0))[:n]

        party = pick(a_cell, n_party, set())
        if spec["ambush"] and n_foes >= 3:
            # Two foes on the flanks: the cells halfway along the way between the zones that lie farthest to each side of it.
            ax, ay, bx, by = *a_cell, *b_cell
            length = math.hypot(bx - ax, by - ay)
            side = lambda c: ((c[0] - ax) * (by - ay) - (c[1] - ay) * (bx - ax)) / length  # noqa: E731
            along = lambda c: ((c[0] - ax) * (bx - ax) + (c[1] - ay) * (by - ay)) / length / length  # noqa: E731
            mid = [c for c in pick(a_cell, len(floor), set(party)) if 0.3 <= along(c) <= 0.7]
            flanks = [max(mid, key=side), min(mid, key=side)] if mid else []
            flanks = flanks if len(flanks) == 2 and flanks[0] != flanks[1] else []
            rest = pick(b_cell, n_foes - len(flanks), set(party) | set(flanks))
            foes = flanks + rest
        else:
            foes = pick(b_cell, n_foes, set(party))
        if len(party) < n_party or len(foes) < n_foes:
            continue
        # The first of the party stands where it has room: a free cell beside it that no one of its side holds, one of them straight
        # on (an attack on a creature next to it needs that). The cell on the edge of the group has the most.
        beside = lambda c: sum((c[0] + dx, c[1] + dy) in free_tiles and (c[0] + dx, c[1] + dy) not in party for dx, dy in AROUND if dx or dy) + 3 * any(  # noqa: E731
            (c[0] + dx, c[1] + dy) in free_tiles and (c[0] + dx, c[1] + dy) not in party for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        party.sort(key=lambda c: -beside(c))
        if beside(party[0]) < 4:
            continue
        foes.sort(key=lambda p: min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in party))
        if not _joined(free_tiles, party[0]) or not all(p in free_tiles for p in party + foes):
            continue
        a.update(
            spec={**spec, "shape": now, "size": used["size"], "orient": used["orient"], "source": source["kind"], "source_id": source["id"],
                  "decor": source["decor"]},
            look=source["look"], starts={"party": [list(p) for p in party], "foes": [list(p) for p in foes]},
            units={}, seen=["0" * w for _ in range(h)])
        return a
    raise ArenaError("could not make this arena; try another seed=.")


def _reach4(cells: set[tuple[int, int]], start) -> set[tuple[int, int]]:
    """The cells that can be reached from start by steps in 4 directions over `cells`."""
    seen, stack = {tuple(start)}, [tuple(start)]
    while stack:
        x, y = stack.pop()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n in cells and n not in seen:
                seen.add(n)
                stack.append(n)
    return seen


def _joined(cells: set[tuple[int, int]], start) -> bool:
    """True when every cell can be reached from start by steps in 4 directions over the cells."""
    return len(_reach4(cells, start)) == len(cells)


# -- files --------------------------------------------------------------------


def arenas_dir(campaign_dir: Path) -> Path:
    return campaign_dir / "stage" / "arenas"


def load(campaign_dir: Path, arena_id: str) -> dict | None:
    from core.files import read_json

    return read_json(arenas_dir(campaign_dir) / f"{arena_id}.json") if re.fullmatch(r"[a-z0-9-]+", arena_id) else None


def save(campaign_dir: Path, arena_id: str, a: dict) -> Path:
    from core.files import write_json

    return write_json(arenas_dir(campaign_dir) / f"{arena_id}.json", a)


def new_id(campaign_dir: Path) -> str:
    folder = arenas_dir(campaign_dir)
    return f"arena-{len(list(folder.glob('arena-*.json'))) + 1 if folder.is_dir() else 1}"


# -- the preview ---------------------------------------------------------------


@lru_cache(maxsize=64)
def prop_png(kind: str) -> bytes:
    """A prop as one picture for the board: the scene sprite, scaled down so it does not cover its neighbors."""
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
            if c == VOID:
                continue
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
