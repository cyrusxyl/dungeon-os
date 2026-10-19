"""The shapes of a combat room: a mask of floor cells, then the grid of a room with walls (see isometric-view.md).

A shape is a function (w, h, rng) -> rows of booleans. `mask` picks a size, makes the shape, keeps the largest connected
part, turns it at random (8 ways) and returns its cells. `grid_of` adds the walls: a wall `#` is a cell that touches
floor (8 neighbours); every other cell is the void `-` outside the room. Same rng, same room.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable

FLOOR, WALL, VOID = ".", "#", "-"
# Width and depth of a room by size class, as (low, high) pairs.
CLASSES = {"small": ((12, 15), (9, 11)), "medium": ((17, 22), (12, 15)), "large": ((24, 30), (16, 20))}
HALL = ((20, 27), (6, 8))
MIN_CAVE = (13, 10)
MIN_PART = 40  # the largest part of a shape must have at least max(this, 30% of its box)

Mask = list[list[bool]]


def rnd(v: float) -> int:
    """Round half up, as JavaScript does (Python rounds half to even)."""
    return math.floor(v + 0.5)


def ri(r: random.Random, a: float, b: float) -> int:
    """A whole number from a to b, both ends included (a and b may be fractions: the range then shrinks to whole numbers)."""
    lo, hi = math.ceil(a), math.floor(b)
    return r.randint(lo, max(lo, hi))


def _mk(w: int, h: int, f: Callable[[int, int], bool]) -> Mask:
    return [[bool(f(x, y)) for x in range(w)] for y in range(h)]


def _ellipse(w: int, h: int, x: int, y: int) -> float:
    return ((x + 0.5 - w / 2) / (w / 2)) ** 2 + ((y + 0.5 - h / 2) / (h / 2)) ** 2


def _full(w, h, r):
    return _mk(w, h, lambda x, y: True)


def _l(w, h, r):
    cw, ch = ri(r, w * 0.4, w * 0.55), ri(r, h * 0.4, h * 0.6)
    sx, sy = (0 if r.random() < 0.5 else w - cw), (0 if r.random() < 0.5 else h - ch)
    return _mk(w, h, lambda x, y: not (sx <= x < sx + cw and sy <= y < sy + ch))


def _t(w, h, r):
    cw, ch = rnd(w * 0.3), rnd(h * 0.55)
    return _mk(w, h, lambda x, y: not (y < ch and (x < cw or x >= w - cw)))


def _cross(w, h, r):
    cw, ch = rnd(w * 0.3), rnd(h * 0.3)
    return _mk(w, h, lambda x, y: not ((x < cw or x >= w - cw) and (y < ch or y >= h - ch)))


def _nave(w, h, r):
    t, tw = rnd(w * 0.5), max(3, rnd(w * 0.2))
    nh = max(3, rnd(h * 0.38))
    ty = rnd((h - nh) / 2)
    return _mk(w, h, lambda x, y: ty <= y < ty + nh or t <= x < t + tw)


def _u(w, h, r):
    nw, nd = rnd(w * 0.34), rnd(h * 0.58)
    sx = rnd((w - nw) / 2)
    return _mk(w, h, lambda x, y: not (sx <= x < sx + nw and y < nd))


def _hh(w, h, r):
    nw, nd = rnd(w * 0.34), rnd(h * 0.38)
    sx = rnd((w - nw) / 2)
    return _mk(w, h, lambda x, y: not (sx <= x < sx + nw and (y < nd or y >= h - nd)))


def _octagon(w, h, r):
    c = min(w, h) // 3
    return _mk(w, h, lambda x, y: min(x + y, w - 1 - x + y, x + h - 1 - y, w - 1 - x + h - 1 - y) >= c)


def _diamond(w, h, r):
    return _mk(w, h, lambda x, y: abs(x + 0.5 - w / 2) / (w / 2) + abs(y + 0.5 - h / 2) / (h / 2) <= 1)


def _ellipse_shape(w, h, r):
    return _mk(w, h, lambda x, y: _ellipse(w, h, x, y) <= 1)


def _ring(w, h, r):
    rad = min(w, h) * 0.22
    return _mk(w, h, lambda x, y: _ellipse(w, h, x, y) <= 1 and math.hypot(x + 0.5 - w / 2, (y + 0.5 - h / 2) * w / h) > rad)


def _twin(w, h, r):
    a = rnd(w * 0.38)
    h1, h2 = ri(r, h * 0.6, h), ri(r, h * 0.6, h)
    cy = rnd(h / 2) + ri(r, -1, 1)
    return _mk(w, h, lambda x, y: (x < a and (h - h1) / 2 <= y < (h + h1) / 2) or (x >= w - a and (h - h2) / 2 <= y < (h + h2) / 2)
               or (a <= x < w - a and y in (cy, cy + 1)))


def _zigzag(w, h, r):
    t, v = max(3, rnd(h / 3)), rnd(w * 0.66)
    return _mk(w, h, lambda x, y: (x < v and y < t) or (v - t <= x < v) or (x >= v - t and y >= h - t))


def _dogleg(w, h, r):
    a, b = rnd(w * 0.62), rnd(h * 0.62)
    return _mk(w, h, lambda x, y: (x < a and y < b) or (x >= w - a and y >= h - b))


def _blob(w, h, r):
    circles = [(r.random() * w, r.random() * h, min(w, h) * (0.25 + r.random() * 0.22)) for _ in range(ri(r, 4, 6))]
    return _mk(w, h, lambda x, y: any(math.hypot(x + 0.5 - cx, y + 0.5 - cy) <= rad for cx, cy, rad in circles))


def _cave(w, h, r):
    g = _mk(w, h, lambda x, y: 0 < x < w - 1 and 0 < y < h - 1 and r.random() < 0.57)
    for _ in range(4):
        old = g
        g = _mk(w, h, lambda x, y: sum(old[y + b][x + a] for a in (-1, 0, 1) for b in (-1, 0, 1) if 0 <= y + b < h and 0 <= x + a < w) >= 5)
    return g


SHAPES: dict[str, Callable[[int, int, random.Random], Mask]] = {
    "rect": _full, "hall": _full,  # a hall is a rect, long and thin (see `box`)
    "l": _l, "t": _t, "cross": _cross, "nave": _nave, "u": _u, "h": _hh, "octagon": _octagon, "diamond": _diamond,
    "ellipse": _ellipse_shape, "ring": _ring, "twin": _twin, "zigzag": _zigzag, "dogleg": _dogleg, "blob": _blob, "cave": _cave,
}
SHAPE_NAMES = tuple(SHAPES)


def box(shape: str, r: random.Random, size: str | None) -> tuple[str, int, int]:
    """The size class and the box (w, h) of a shape. With no class asked, one of the three at random."""
    cls = size or ("small", "medium", "large")[ri(r, 0, 2)]
    (w_lo, w_hi), (h_lo, h_hi) = HALL if shape == "hall" else CLASSES[cls]
    w, h = ri(r, w_lo, w_hi), ri(r, h_lo, h_hi)
    if shape == "cave":
        w, h = max(w, MIN_CAVE[0]), max(h, MIN_CAVE[1])
    return cls, w, h


def biggest(mask: Mask) -> list[tuple[int, int]]:
    """The largest part of a mask that holds together (4 directions)."""
    h, w = len(mask), len(mask[0])
    seen = [[False] * w for _ in range(h)]
    best: list[tuple[int, int]] = []
    for y in range(h):
        for x in range(w):
            if not mask[y][x] or seen[y][x]:
                continue
            part, stack = [(x, y)], [(x, y)]
            seen[y][x] = True
            while stack:
                cx, cy = stack.pop()
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        part.append((nx, ny))
                        stack.append((nx, ny))
            if len(part) > len(best):
                best = part
    return best


def turn(cells: list[tuple[int, int]], orient: int) -> list[tuple[int, int]]:
    """One of the 8 turns: bit 1 swaps the axes, bit 2 mirrors x, bit 4 mirrors y. The result starts at (1, 1): a border of 1 is left."""
    out = []
    for x, y in cells:
        if orient & 1:
            x, y = y, x
        if orient & 2:
            x = -x
        if orient & 4:
            y = -y
        out.append((x, y))
    x0, y0 = min(x for x, _ in out), min(y for _, y in out)
    return [(x - x0 + 1, y - y0 + 1) for x, y in out]


def mask(shape: str, r: random.Random, size: str | None = None, orient: int | None = None) -> tuple[list[tuple[int, int]], dict] | None:
    """The floor cells of a room of this shape, or None when this try gives a room that is too small or too broken.

    `size` is a class name or None (random). `orient` is 0 to 7, or None for a random turn. Second result: what was used.
    """
    cls, w, h = box(shape, r, size)
    cells = biggest(SHAPES[shape](w, h, r))
    if len(cells) < max(MIN_PART, 0.3 * w * h):
        return None
    turned = orient if orient is not None else ri(r, 0, 7)
    return turn(cells, turned), {"size": cls, "orient": turned}


def grid_of(cells: list[tuple[int, int]]) -> list[list[str]]:
    """Rows of characters: floor `.`, a wall `#` on every cell next to floor (8 neighbours), `-` for the void outside."""
    floor = set(cells)
    w, h = max(x for x, _ in floor) + 2, max(y for _, y in floor) + 2
    grid = [[VOID] * w for _ in range(h)]
    for x, y in floor:
        for a in (-1, 0, 1):
            for b in (-1, 0, 1):
                grid[y + b][x + a] = WALL
    for x, y in floor:
        grid[y][x] = FLOOR
    return grid
