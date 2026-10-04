"""Sites: generated buildings and dungeons that the party walks through.

The DM sets a site with `dnd-cli site set` (a theme, a size, and points of
interest by depth). This module makes the layout from a seed, places the
points of interest, and does the sight and the walking. It never calls the DM:
the stage server sends the prompts that `walk` asks for. See dungeon-crawl.md.

A site file (`{campaign}/stage/sites/<id>.json`) holds the whole layout, so it
is secret. `view` gives the browser only what the party has seen.
"""

from __future__ import annotations

import io
import json
import random
import re
from collections import deque
from functools import cache, lru_cache
from pathlib import Path

from stage.beat import SLUG_RE, title
from stage.files import read_json, write_json

DATA_PATH = Path(__file__).resolve().parent / "data" / "crawl.json"
_DUNGEON_SIZES = {"small": (32, 22), "medium": (44, 30), "large": (60, 40)}
SIZES = {
    "rooms": _DUNGEON_SIZES,
    "cave": _DUNGEON_SIZES,
    "building": {"small": (20, 14), "medium": (28, 19), "large": (38, 25)},
}
DANGER = {"none": 0, "low": 8, "mid": 5, "high": 3}
WHERE = ("entrance", "near", "mid", "far", "any")
RADIUS = 8
WALL, FLOOR, DOOR, OPEN, EXIT = "#", ".", "+", "'", "<"
WALKABLE = {FLOOR, DOOR, OPEN, EXIT}
OPAQUE = {WALL, DOOR}
STEPS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
T = 32


class SiteError(ValueError):
    """A bad site spec. The message says how to fix it."""


class _Retry(Exception):
    """A generator attempt failed; try the next sub-seed."""


@cache
def data() -> dict:
    return json.loads(DATA_PATH.read_text())


def themes() -> dict:
    return data()["themes"]


# -- generators ----------------------------------------------------------
# Each returns (grid, areas, entrance). grid is a list of row lists; an area
# is {"cells": [...], "cx", "cy"} with a floor center.


def _blank(w: int, h: int) -> list[list[str]]:
    return [[WALL] * w for _ in range(h)]


def _bsp(rng: random.Random, rect: tuple, min_size: int) -> dict:
    x, y, w, h = rect
    can_x, can_y = w >= 2 * min_size, h >= 2 * min_size
    if not (can_x or can_y):
        return {"rect": rect}
    cut_x = can_x and (not can_y or w > h * 1.25 or (h <= w * 1.25 and rng.random() < 0.5))
    if cut_x:
        s = rng.randint(min_size, w - min_size)
        kids = ((x, y, s, h), (x + s, y, w - s, h))
    else:
        s = rng.randint(min_size, h - min_size)
        kids = ((x, y, w, s), (x, y + s, w, h - s))
    return {"rect": rect, "cut": (cut_x, s), "kids": tuple(_bsp(rng, k, min_size) for k in kids)}


def _leaves(node: dict) -> list[dict]:
    return [node] if "kids" not in node else _leaves(node["kids"][0]) + _leaves(node["kids"][1])


def _center(area: dict) -> tuple[int, int]:
    return area["cx"], area["cy"]


def _gen_rooms(rng: random.Random, w: int, h: int):
    """Rooms in BSP leaves, joined by L-shaped corridors; doors where a corridor meets a room."""
    grid = _blank(w, h)
    tree = _bsp(rng, (0, 0, w, h), 9)
    for leaf in _leaves(tree):
        lx, ly, lw, lh = leaf["rect"]
        rw = rng.randint(4, max(4, lw - 3))
        rh = rng.randint(3, max(3, lh - 3))
        rx = rng.randint(lx + 1, lx + lw - rw - 1)
        ry = rng.randint(ly + 1, ly + lh - rh - 1)
        leaf["room"] = (rx, ry, rw, rh)
        for yy in range(ry, ry + rh):
            for xx in range(rx, rx + rw):
                grid[yy][xx] = FLOOR

    def connect(node: dict) -> None:
        if "kids" not in node:
            return
        a, b = node["kids"]
        connect(a)
        connect(b)
        ra = [l["room"] for l in _leaves(a)]
        rb = [l["room"] for l in _leaves(b)]
        pa, pb = min(
            ((p, q) for p in ra for q in rb),
            key=lambda pq: abs(pq[0][0] + pq[0][2] / 2 - pq[1][0] - pq[1][2] / 2)
            + abs(pq[0][1] + pq[0][3] / 2 - pq[1][1] - pq[1][3] / 2),
        )
        (x1, y1), (x2, y2) = _room_center(pa), _room_center(pb)
        corner = (x2, y1) if rng.random() < 0.5 else (x1, y2)
        for (ax, ay), (bx, by) in (((x1, y1), corner), (corner, (x2, y2))):
            for xx in range(min(ax, bx), max(ax, bx) + 1):
                for yy in range(min(ay, by), max(ay, by) + 1):
                    grid[yy][xx] = FLOOR

    connect(tree)
    rooms = [l["room"] for l in _leaves(tree)]
    for rx, ry, rw, rh in rooms:
        ring = [(xx, ry - 1) for xx in range(rx, rx + rw)] + [(xx, ry + rh) for xx in range(rx, rx + rw)]
        ring += [(rx - 1, yy) for yy in range(ry, ry + rh)] + [(rx + rw, yy) for yy in range(ry, ry + rh)]
        for xx, yy in ring:
            if grid[yy][xx] != FLOOR or any(grid[ny][nx] == DOOR for nx, ny in _around4(xx, yy, w, h)):
                continue
            # A door only in a gap of the wall, never in an open side.
            if (grid[yy][xx - 1] == WALL and grid[yy][xx + 1] == WALL) or (grid[yy - 1][xx] == WALL and grid[yy + 1][xx] == WALL):
                grid[yy][xx] = DOOR
    areas = []
    for rx, ry, rw, rh in rooms:
        cells = [(xx, yy) for yy in range(ry, ry + rh) for xx in range(rx, rx + rw)]
        cx, cy = _room_center((rx, ry, rw, rh))
        areas.append({"cells": cells, "cx": cx, "cy": cy})
    start = max(areas, key=lambda a: (a["cy"], -abs(a["cx"] - w // 2)))
    return grid, areas, _center(start)


def _room_center(room: tuple) -> tuple[int, int]:
    rx, ry, rw, rh = room
    return rx + rw // 2, ry + rh // 2


def _gen_building(rng: random.Random, w: int, h: int):
    """Rooms that share walls (BSP with no margin), one door per split; the front door is in the bottom wall."""
    grid = _blank(w, h)
    # Rects are on the wall lattice: walls at x and x+w, the inside between.
    tree = _bsp(rng, (0, 0, w - 1, h - 1), 5)
    leaves = _leaves(tree)
    for leaf in leaves:
        lx, ly, lw, lh = leaf["rect"]
        for yy in range(ly + 1, ly + lh):
            for xx in range(lx + 1, lx + lw):
                grid[yy][xx] = FLOOR

    def doors(node: dict) -> None:
        if "kids" not in node:
            return
        x, y, nw, nh = node["rect"]
        cut_x, s = node["cut"]
        if cut_x:
            line = x + s
            options = [(line, yy) for yy in range(y + 1, y + nh) if grid[yy][line - 1] == FLOOR and grid[yy][line + 1] == FLOOR]
        else:
            line = y + s
            options = [(xx, line) for xx in range(x + 1, x + nw) if grid[line - 1][xx] == FLOOR and grid[line + 1][xx] == FLOOR]
        if not options:
            raise _Retry
        dx, dy = rng.choice(options)
        grid[dy][dx] = DOOR
        for kid in node["kids"]:
            doors(kid)

    doors(tree)
    areas = []
    for lx, ly, lw, lh in (l["rect"] for l in leaves):
        cells = [(xx, yy) for yy in range(ly + 1, ly + lh) for xx in range(lx + 1, lx + lw)]
        areas.append({"cells": cells, "cx": lx + lw // 2, "cy": ly + lh // 2})
    bottom = [a for a in areas if max(c[1] for c in a["cells"]) == h - 2]
    front = rng.choice(bottom)
    xs = sorted({c[0] for c in front["cells"]})
    ex = xs[len(xs) // 2]
    grid[h - 1][ex] = EXIT
    return grid, areas, (ex, h - 1)


def _gen_cave(rng: random.Random, w: int, h: int):
    """Cellular automaton; keep the largest region; areas grow from spread-out seeds."""
    grid = _blank(w, h)
    for yy in range(1, h - 1):
        for xx in range(1, w - 1):
            grid[yy][xx] = WALL if rng.random() < 0.45 else FLOOR
    for _ in range(5):
        nxt = _blank(w, h)
        for yy in range(1, h - 1):
            for xx in range(1, w - 1):
                walls = sum(grid[yy + dy][xx + dx] == WALL for dy in (-1, 0, 1) for dx in (-1, 0, 1))
                nxt[yy][xx] = WALL if walls >= 5 else FLOOR
        grid = nxt
    floors = [(xx, yy) for yy in range(h) for xx in range(w) if grid[yy][xx] == FLOOR]
    regions, done = [], set()
    for cell in floors:
        if cell not in done:
            region = set(_flood(grid, cell))
            done |= region
            regions.append(region)
    if not regions:
        raise _Retry
    keep = max(regions, key=len)
    if len(keep) < 0.3 * (w - 2) * (h - 2):
        raise _Retry
    for xx, yy in floors:
        if (xx, yy) not in keep:
            grid[yy][xx] = WALL
    cells = sorted(keep)
    seeds = [rng.choice(cells)]
    count = max(5, min(14, len(cells) // 70))
    while len(seeds) < count:
        sample = rng.sample(cells, min(200, len(cells)))
        seeds.append(max(sample, key=lambda c: min((c[0] - s[0]) ** 2 + (c[1] - s[1]) ** 2 for s in seeds)))
    owner: dict[tuple, int] = {s: i for i, s in enumerate(seeds)}
    queue = deque(seeds)
    while queue:
        cx, cy = queue.popleft()
        for n in _around4(cx, cy, w, h):
            if n in keep and n not in owner:
                owner[n] = owner[(cx, cy)]
                queue.append(n)
    areas = [{"cells": [c for c in cells if owner.get(c) == i], "cx": s[0], "cy": s[1]} for i, s in enumerate(seeds)]
    start = max(areas, key=lambda a: a["cy"])
    return grid, areas, _center(start)


GENERATORS = {"rooms": _gen_rooms, "building": _gen_building, "cave": _gen_cave}


# -- grid helpers ----------------------------------------------------------


def _around4(x: int, y: int, w: int, h: int):
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if 0 <= x + dx < w and 0 <= y + dy < h:
            yield x + dx, y + dy


def _flood(grid, start: tuple[int, int]) -> dict[tuple[int, int], int]:
    """Walking distance from start to every reachable cell."""
    h, w = len(grid), len(grid[0])
    dist = {start: 0}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for n in _around4(x, y, w, h):
            if n not in dist and grid[n[1]][n[0]] in WALKABLE:
                dist[n] = dist[(x, y)] + 1
                queue.append(n)
    return dist


def _line(x0: int, y0: int, x1: int, y1: int):
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


def visible(grid, x: int, y: int, radius: int = RADIUS) -> set[tuple[int, int]]:
    """Cells in sight: a line to each cell on the radius square, cut at the circle and the first wall.

    In a doorway (a gap in a wall line), the party also sees what the floor
    cells next to it see; else every line along the inside of the wall is cut.
    """
    seen = _sight(grid, x, y, radius)
    if grid[y][x] in (OPEN, EXIT):
        for nx, ny in _around4(x, y, len(grid[0]), len(grid)):
            if grid[ny][nx] == FLOOR:
                seen |= _sight(grid, nx, ny, radius - 1)
    return seen


def _sight(grid, x: int, y: int, radius: int) -> set[tuple[int, int]]:
    h, w = len(grid), len(grid[0])
    limit = radius * radius + radius
    seen = {(x, y)}
    edge = [(x + d, y - radius) for d in range(-radius, radius + 1)] + [(x + d, y + radius) for d in range(-radius, radius + 1)]
    edge += [(x - radius, y + d) for d in range(-radius, radius + 1)] + [(x + radius, y + d) for d in range(-radius, radius + 1)]
    for tx, ty in edge:
        for cx, cy in _line(x, y, tx, ty):
            if not (0 <= cx < w and 0 <= cy < h) or (cx - x) ** 2 + (cy - y) ** 2 > limit:
                break
            seen.add((cx, cy))
            if (cx, cy) != (x, y) and grid[cy][cx] in OPAQUE:
                break
    # Walls next to a seen floor cell: without this, room corners stay dark.
    for cx, cy in list(seen):
        if grid[cy][cx] not in OPAQUE:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] in OPAQUE:
                        seen.add((nx, ny))
    return seen


# -- sites -----------------------------------------------------------------


def generate(spec: dict, pois: list[dict]) -> dict:
    """A new site from its spec: layout, areas with depth, points of interest, party outside."""
    theme = themes()[spec["theme"]]
    style = theme["style"]
    w, h = SIZES[style][spec["size"]]
    for attempt in range(50):
        rng = random.Random(f"{spec['seed']}:{attempt}")
        try:
            grid, areas, entrance = GENERATORS[style](rng, w, h)
        except _Retry:
            continue
        ex, ey = entrance
        grid[ey][ex] = EXIT
        dist = _flood(grid, entrance)
        floor = [(xx, yy) for yy in range(h) for xx in range(w) if grid[yy][xx] in WALKABLE]
        if any(c not in dist for c in floor) or any(_center(a) not in dist for a in areas):
            continue
        break
    else:
        raise SiteError("could not make this layout; try another seed=.")
    area_of = [[-1] * w for _ in range(h)]
    for i, a in enumerate(areas):
        for cx, cy in a["cells"]:
            area_of[cy][cx] = i
    site = {
        "spec": spec,
        "grid": ["".join(row) for row in grid],
        "areas": [{"cx": a["cx"], "cy": a["cy"], "depth": dist[_center(a)]} for a in areas],
        "area_of": area_of,
        "entrance": list(entrance),
        "start_area": area_of[ey][ex] if area_of[ey][ex] >= 0 else _nearest_area(areas, entrance),
        "pois": {},
        "party": None,
        "seen": ["0" * w for _ in range(h)],
        "entered": [],
    }
    add_pois(site, pois, random.Random(f"{spec['seed']}:pois"))
    return site


def _nearest_area(areas: list[dict], cell: tuple[int, int]) -> int:
    return min(range(len(areas)), key=lambda i: abs(areas[i]["cx"] - cell[0]) + abs(areas[i]["cy"] - cell[1]))


def _band(site: dict, where: str) -> list[int]:
    start = site["start_area"]
    if where == "entrance":
        return [start]
    ranked = sorted((i for i in range(len(site["areas"])) if i != start), key=lambda i: site["areas"][i]["depth"])
    if not ranked:
        return [start]
    third = max(1, len(ranked) // 3)
    if where == "near":
        return ranked[:third]
    if where == "far":
        return ranked[::-1][:third]
    if where == "mid":
        return ranked[third:len(ranked) - third] or ranked
    return ranked


def _area_seen(site: dict, i: int) -> bool:
    a = site["areas"][i]
    return site["seen"][a["cy"]][a["cx"]] == "1"


def add_pois(site: dict, pois: list[dict], rng: random.Random) -> None:
    """Place each point of interest in a free, unseen area of its depth band, near the area center."""
    used = {site["area_of"][p["y"]][p["x"]] for p in site["pois"].values()}
    taken = {(p["x"], p["y"]) for p in site["pois"].values()} | {tuple(site["entrance"])}
    for poi in pois:
        band = [i for i in _band(site, poi["where"]) if not _area_seen(site, i)] or _band(site, poi["where"])
        anywhere = [i for i in _band(site, "any") if i not in used and not _area_seen(site, i)]
        tiers = [[i for i in band if i not in used], anywhere, band]
        choices = next(t for t in tiers if t)
        area = choices[0] if poi["where"] == "far" else rng.choice(choices)
        a = site["areas"][area]
        cells = [
            (x, y)
            for y, row in enumerate(site["area_of"])
            for x, owner in enumerate(row)
            if owner == area and site["grid"][y][x] == FLOOR and (x, y) not in taken
        ]
        if not cells:
            raise SiteError(f"no room left for the point of interest {poi['id']!r}.")
        x, y = min(cells, key=lambda c: (abs(c[0] - a["cx"]) + abs(c[1] - a["cy"]), c))
        site["pois"][poi["id"]] = {"x": x, "y": y, "where": poi["where"], "icon": poi["icon"], "found": False}
        used.add(area)
        taken.add((x, y))


def _see(site: dict) -> set[tuple[int, int]]:
    """Mark what the party sees now as seen; return it."""
    x, y = site["party"]
    vis = visible(site["grid"], x, y)
    rows = [list(r) for r in site["seen"]]
    for cx, cy in vis:
        rows[cy][cx] = "1"
    site["seen"] = ["".join(r) for r in rows]
    return vis


def arrive(site: dict, at: str | None = None) -> None:
    """Put the party in the site: at a POI, at the entrance, or where it stood last.

    Points of interest in sight on arrival are found without a prompt: the DM
    is telling the arrival in that same turn.
    """
    if at and at != "entrance":
        if at not in site["pois"]:
            raise SiteError(f"no point of interest {at!r} in this site. Points: {', '.join(site['pois']) or 'none'}.")
        p = site["pois"][at]
        site["party"] = [p["x"], p["y"]]
    elif at == "entrance" or site["party"] is None:
        site["party"] = list(site["entrance"])
    x, y = site["party"]
    area = site["area_of"][y][x]
    if area >= 0 and area not in site["entered"]:
        site["entered"].append(area)
    if site["start_area"] not in site["entered"]:
        site["entered"].append(site["start_area"])
    vis = _see(site)
    for p in site["pois"].values():
        if (p["x"], p["y"]) in vis:
            p["found"] = True


def path_to(site: dict, target: tuple[int, int]) -> list[tuple[int, int]] | None:
    """Shortest walk over seen, walkable cells (4 directions), without the start cell.

    To a found POI, the walk ends next to it, and not below it: the party
    sprite would hide it.
    """
    if any((p["x"], p["y"]) == target and p["found"] for p in site["pois"].values()):
        if max(abs(target[0] - site["party"][0]), abs(target[1] - site["party"][1])) <= 1:
            return []
        tx, ty = target
        options = []
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            path = _path(site, (tx + dx, ty + dy))
            if path is not None:
                options.append((dy == 1, len(path), path))
        return min(options)[2] if options else None
    return _path(site, target)


def _path(site: dict, target: tuple[int, int]) -> list[tuple[int, int]] | None:
    grid, seen = site["grid"], site["seen"]
    h, w = len(grid), len(grid[0])
    start = tuple(site["party"])
    prev: dict = {start: None}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        if cur == target:
            out = []
            while cur != start:
                out.append(cur)
                cur = prev[cur]
            return out[::-1]
        for n in _around4(cur[0], cur[1], w, h):
            if n not in prev and grid[n[1]][n[0]] in WALKABLE and seen[n[1]][n[0]] == "1":
                prev[n] = cur
                queue.append(n)
    return None


def walk(site: dict, path: list[tuple[int, int]], roll=None) -> dict:
    """Walk step by step. Stop at a wall, at a newly seen POI, or at a wandering-encounter hit.

    `roll(n)` returns 0 for a hit with chance 1 in n (default: random).
    """
    roll = roll or (lambda n: random.randrange(n))
    grid = [list(r) for r in site["grid"]]
    h, w = len(grid), len(grid[0])
    chance = DANGER.get(site["spec"].get("danger", "none"), 0)
    moved: list[list[int]] = []
    result = {"path": moved, "stopped": None}
    for x, y in path:
        px, py = site["party"]
        if abs(x - px) + abs(y - py) != 1 or not (0 <= x < w and 0 <= y < h) or grid[y][x] not in WALKABLE:
            result["stopped"] = "blocked"
            break
        if grid[y][x] == DOOR:
            grid[y][x] = OPEN
            site["grid"] = ["".join(r) for r in grid]
        site["party"] = [x, y]
        moved.append([x, y])
        vis = _see(site)
        new = [pid for pid, p in site["pois"].items() if not p["found"] and (p["x"], p["y"]) in vis]
        if new:
            for pid in new:
                site["pois"][pid]["found"] = True
            result.update(stopped="poi", pois=new)
            break
        area = site["area_of"][y][x]
        if area >= 0 and area not in site["entered"]:
            site["entered"].append(area)
            if chance and roll(chance) == 0:
                result["stopped"] = "wander"
                break
    return result


def view(site_id: str, site: dict) -> dict:
    """What the browser may know: seen cells, visible cells, found POIs, the party."""
    grid, seen = site["grid"], site["seen"]
    cells = ["".join(c if s == "1" else " " for c, s in zip(row, srow)) for row, srow in zip(grid, seen)]
    h, w = len(grid), len(grid[0])
    vis = visible(grid, *site["party"]) if site["party"] else set()
    rows = [["0"] * w for _ in range(h)]
    for x, y in vis:
        rows[y][x] = "1"
    # An object icon, or an actor kind shown as its sprite.
    url = lambda icon: f"/asset/icon/{icon}.png" if icon in data()["icons"] else f"/asset/actor/{icon}/full.png"  # noqa: E731
    pois = [
        {"id": pid, "name": title(pid), "x": p["x"], "y": p["y"], "url": url(p["icon"])}
        for pid, p in site["pois"].items()
        if p["found"]
    ]
    return {
        "id": site_id,
        "name": site_name(site_id, site),
        "theme": site["spec"]["theme"],
        "w": w,
        "h": h,
        "cells": cells,
        "visible": ["".join(r) for r in rows],
        "party": site["party"],
        "entrance": site["entrance"],
        "pois": pois,
        "tiles": tile_counts(site["spec"]["theme"]),
    }


def site_name(site_id: str, site: dict) -> str:
    return site["spec"].get("name") or title(site_id)


# -- prompts to the DM -----------------------------------------------------
# These reach the DM's terminal, which the console drawer shows: they name
# only what the party has found.


def _resume(site_id: str) -> str:
    return (f"Do not describe exits or passages: the players see the map and walk by themselves. "
            f"If you switch to an `@scene`, send `@explore {site_id}` when it is over.")


def prompt_found(site_id: str, site: dict, poi_ids: list[str]) -> str:
    names = ", ".join(f"{title(p)} ({p})" for p in poi_ids)
    return f"[explore] {site_name(site_id, site)}: the party sees {names}. Show what they find. {_resume(site_id)}"


def prompt_wander(site_id: str, site: dict) -> str:
    danger = site["spec"].get("danger", "none")
    return (f"[explore] {site_name(site_id, site)}: a wandering encounter check hit (danger {danger}). "
            f"Run a wandering encounter, or show that nothing comes. {_resume(site_id)}")


def prompt_examine(site_id: str, site: dict, poi_id: str) -> str:
    return (f"[explore] {site_name(site_id, site)}: the party examines {title(poi_id)} ({poi_id}). "
            f"Show what they find. {_resume(site_id)}")


def prompt_leave(site_id: str, site: dict) -> str:
    return (f"[explore] {site_name(site_id, site)}: the party leaves by the entrance. "
            "Show where they go next with `@scene <location-id>`.")


# -- spec from DM tokens ---------------------------------------------------


def guess_icon(poi_id: str, is_actor) -> str:
    """An icon from the words of the id: an object icon, else an actor kind, else a mark."""
    icons, words = data()["icons"], data()["icon_words"]
    parts = poi_id.split("-")
    for part in parts:
        if part in icons:
            return part
        if part in words:
            return words[part]
    for part in parts:
        if is_actor(part):
            return part
    return "mark"


def parse_poi(value: str, is_actor) -> dict:
    pid, at, rest = value.partition("@")
    where, _, icon = rest.partition(":")
    if not SLUG_RE.match(pid) or not at:
        raise SiteError(f"poi={value}: write poi=<id>@<where>[:<icon>], for example poi=dragon-altar@far:altar.")
    if where not in WHERE:
        raise SiteError(f"poi={value}: where is one of {', '.join(WHERE)}.")
    if icon and icon not in data()["icons"] and not is_actor(icon):
        raise SiteError(f"poi={value}: no icon or actor {icon!r}. Icons: {', '.join(data()['icons'])}; "
                        "or an actor kind such as goblin.")
    return {"id": pid, "where": where, "icon": icon or guess_icon(pid, is_actor)}


def build(tokens: list[str], current: dict | None, is_actor, poi_ids=()) -> tuple[dict, list[dict]]:
    """A spec from `key=value` tokens, and the POIs it adds. A saved layout never changes.

    `poi_ids` are the points of interest the site has already.
    """
    spec = dict(current or {})
    new: list[dict] = []
    for token in tokens:
        key, eq, value = token.partition("=")
        key = key.strip().lower()
        if not eq:
            raise SiteError(f"{token!r}: write key=value (theme=, size=, danger=, name=, seed=, poi=).")
        if key in ("theme", "size", "seed") and current is not None:
            raise SiteError(f"{key}= is part of the layout, and a saved layout never changes. "
                            "For a different layout, set a new site id.")
        if key == "theme":
            if value not in themes():
                raise SiteError(f"no theme {value!r}. Themes: {', '.join(themes())}.")
            spec["theme"] = value
        elif key == "size":
            if value not in _DUNGEON_SIZES:
                raise SiteError("size= is small, medium or large.")
            spec["size"] = value
        elif key == "seed":
            if not value.isdigit():
                raise SiteError("seed= is a whole number.")
            spec["seed"] = int(value)
        elif key == "danger":
            if value not in DANGER:
                raise SiteError(f"danger= is one of {', '.join(DANGER)}.")
            spec["danger"] = value
        elif key == "name":
            spec["name"] = value.replace("_", " ").strip()
        elif key == "poi":
            poi = parse_poi(value, is_actor)
            if poi["id"] in poi_ids or any(p["id"] == poi["id"] for p in new):
                raise SiteError(f"the point of interest {poi['id']!r} is already in this site.")
            new.append(poi)
        else:
            raise SiteError(f"unknown setting {key!r}. Use theme=, size=, danger=, name=, seed=, poi=.")
    if "theme" not in spec:
        raise SiteError(f"give theme=. Themes: {', '.join(themes())}.")
    spec.setdefault("size", "medium")
    spec.setdefault("seed", random.randrange(1, 10**6))
    spec.setdefault("danger", themes()[spec["theme"]]["danger"])
    return spec, new


# -- files -----------------------------------------------------------------


def sites_dir(campaign_dir: Path) -> Path:
    return campaign_dir / "stage" / "sites"


def load(campaign_dir: Path, site_id: str) -> dict | None:
    return read_json(sites_dir(campaign_dir) / f"{site_id}.json") if SLUG_RE.match(site_id) else None


def save(campaign_dir: Path, site_id: str, site: dict) -> Path:
    """Write by rename: the stage server and the CLI both write site files."""
    return write_json(sites_dir(campaign_dir) / f"{site_id}.json", site)


# -- tiles -----------------------------------------------------------------


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


def _walls(theme: str) -> tuple[str, ...]:
    t = themes()[theme]
    return _variants(t["wall"])[: t.get("wall_variants", 8)]


@cache
def tile_counts(theme: str) -> dict:
    t = themes()[theme]
    floors = 4 if t["floor"].startswith("lpc:") else len(_variants(t["floor"]))
    return {"walls": len(_walls(theme)), "floors": floors, "pattern": t["floor"].startswith("lpc:")}


@lru_cache(maxsize=16)
def atlas_png(theme: str) -> bytes:
    """Row 0: wall variants. Row 1: floor variants. Row 2: closed door, open door, exit."""
    from PIL import Image

    from stage.assets import ensure_dcss

    t = themes()[theme]
    dcss = ensure_dcss()
    walls = [Image.open(p).convert("RGBA") for p in _walls(theme)]
    floors = _floor_tiles(t["floor"])
    doors = data()["doors"]
    specials = [Image.open(dcss / p).convert("RGBA") for p in (doors["closed"], doors["open"], t["exit"])]
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


def render_full(site: dict):
    """The whole layout with every point of interest, for the DM's preview (never sent to players)."""
    from PIL import Image

    atlas = Image.open(io.BytesIO(atlas_png(site["spec"]["theme"])))
    counts = tile_counts(site["spec"]["theme"])
    grid = site["grid"]
    h, w = len(grid), len(grid[0])
    img = Image.new("RGBA", (w * T, h * T), (0, 0, 0, 255))

    def tile(col: int, row: int):
        return atlas.crop((col * T, row * T, (col + 1) * T, (row + 1) * T))

    for y, line in enumerate(grid):
        for x, c in enumerate(line):
            if c == WALL:
                near_floor = any(
                    0 <= x + dx < w and 0 <= y + dy < h and grid[y + dy][x + dx] in WALKABLE
                    for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                )
                if near_floor:
                    img.alpha_composite(tile(variant(x, y, counts["walls"]), 0), (x * T, y * T))
            else:
                f = (x % 2) + (y % 2) * 2 if counts["pattern"] else variant(x, y, counts["floors"])
                img.alpha_composite(tile(f, 1), (x * T, y * T))
                special = {DOOR: 0, OPEN: 1, EXIT: 2}.get(c)
                if special is not None:
                    img.alpha_composite(tile(special, 2), (x * T, y * T))
    for p in site["pois"].values():
        icon = icon_png(p["icon"])
        if icon:
            img.alpha_composite(Image.open(io.BytesIO(icon)).convert("RGBA").crop((0, 0, T, T)), (p["x"] * T, p["y"] * T))
        else:
            img.paste((220, 60, 60, 255), (p["x"] * T + 8, p["y"] * T + 8, p["x"] * T + 24, p["y"] * T + 24))
    return img
