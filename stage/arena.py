"""The tile grid that the crawl and the combat board share: lines, sight and walking distance.

A grid is a list of rows of one-character tiles. This module does not know what a tile means:
each caller passes the tiles that block sight or that can be walked on. `crawl.py` walks 4
directions over its own tiles. The combat board (below, added later) walks 8 directions over its
own tiles. See combat-board.md.
"""

from __future__ import annotations

import io
import json
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
