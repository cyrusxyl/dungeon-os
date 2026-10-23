"""Blocks: low walls, ledges and stubs that stand in a room for variety, cover and sight lines (see blocks.md).

A block is a few cells of one or more heights. Each cell is a prop of the room, of kind `block_low`, `block_half`, `block_tall`
or `block_pillar`. The room is made in two sizes (see compact-set.md): the blocks are made for the full room, and the story set
shows the same blocks at their scaled places, as one cell each.

Pure functions: they read a room grid and give cells. `scenes.room` calls them. The same seed gives the same blocks.
"""

from __future__ import annotations

import random

TIERS = ("block_low", "block_half", "block_tall", "block_pillar")
PIXELS = {"block_low": 14, "block_half": 28, "block_tall": 48, "block_pillar": 64}  # the height drawn (stage/web/src/lib/blocks.ts has the same)
FEET = {"block_low": 3, "block_half": 5, "block_tall": 10, "block_pillar": 15}
# What a block does on the board (stage/arena.py `board_of`). Low and half blocks give cover. Tall ones stop sight.
BOARD = {
    "block_low": {"blocks_move": True, "blocks_sight": False, "cover": "half"},
    "block_half": {"blocks_move": True, "blocks_sight": False, "cover": "three-quarters"},
    "block_tall": {"blocks_move": True, "blocks_sight": True, "cover": "three-quarters"},
    "block_pillar": {"blocks_move": True, "blocks_sight": True, "cover": "three-quarters"},
}
MIXES = ("mixed", "low", "tall")
HUG = 0.45  # the share of blocks that stand against a wall
Cell = tuple[int, int]


def is_block(kind: str) -> bool:
    return kind in BOARD


def default_count(floor_cells: int, density: float) -> int:
    """How many blocks a room gets when the DM does not say: one for each `density` floor cells."""
    return max(0, round(floor_cells / density))


def _tier(r: random.Random, mix: str) -> str:
    v = r.random()
    if mix == "low":
        return "block_low" if v < 0.7 else "block_half"
    if mix == "tall":
        return "block_tall" if v < 0.7 else "block_half"
    return "block_low" if v < 0.38 else "block_half" if v < 0.72 else "block_tall"


def _shape(r: random.Random, mix: str) -> list[tuple[int, int, str]]:
    """The cells of one block, as (dx, dy, kind), from the first cell."""
    a, b = _tier(r, mix), _tier(r, mix)
    low, high = sorted((a, b), key=TIERS.index)
    library = [
        [(0, 0, a)],
        [(0, 0, a)],
        [(0, 0, a), (1, 0, a)],
        [(0, 0, a), (1, 0, a), (2, 0, a)],
        [(0, 0, a), (1, 0, a), (0, 1, a), (1, 1, a)],
        [(0, 0, a), (1, 0, a), (0, 1, a)],
        [(0, 0, low), (1, 0, high)],
        [(0, 0, "block_low"), (1, 0, "block_half")] + ([] if mix == "low" else [(2, 0, "block_tall")]),
        [(0, 0, "block_half" if mix == "low" else "block_pillar")],
    ]
    cells = r.choice(library)
    return [(y, x, k) for x, y, k in cells] if r.random() < 0.5 else cells  # lie along either axis


def _joined(free: set[Cell]) -> bool:
    """True when the free cells are one piece (4 directions)."""
    if not free:
        return True
    start = next(iter(free))
    seen, stack = {start}, [start]
    while stack:
        x, y = stack.pop()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n in free and n not in seen:
                seen.add(n)
                stack.append(n)
    return len(seen) == len(free)


def _zone(cells) -> set[Cell]:
    """The cells and their 8 neighbours: the room a block keeps around what is there."""
    return {(x + dx, y + dy) for x, y in cells for dx in (-1, 0, 1) for dy in (-1, 0, 1)}


def generate(grid: list[str], taken: set[Cell], keep_clear: set[Cell], seed: int, count: int, mix: str = "mixed") -> list[list[tuple[int, int, str]]]:
    """`count` blocks for a room. `taken`: floor cells that hold props. `keep_clear`: cells no block may cover (the front of a door).

    A block keeps one cell from every other block, from every prop and from `keep_clear`. About half of them stand against a wall.
    The floor that is left must stay in one piece. Result: a list of blocks, each a list of (x, y, kind). Fewer than `count` when
    the room has no more room.
    """
    r = random.Random(f"blocks:{seed}")
    floor = {(x, y) for y, row in enumerate(grid) for x, c in enumerate(row) if c == "."}
    held = set(taken)
    zone = _zone(held | keep_clear)
    out: list[list[tuple[int, int, str]]] = []
    for _ in range(count):
        for _try in range(40):
            shape = _shape(r, mix if mix in MIXES else "mixed")
            hug = r.random() < HUG
            spots = []
            for ax, ay in floor:
                cells = [(ax + dx, ay + dy) for dx, dy, _k in shape]
                if not all(c in floor and c not in zone for c in cells):
                    continue
                walled = any((c[0] + dx, c[1] + dy) not in floor for c in cells for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
                if walled == hug:
                    spots.append((ax, ay))
            if not spots:
                continue
            ax, ay = r.choice(sorted(spots))
            cells = [(ax + dx, ay + dy) for dx, dy, _k in shape]
            if not _joined(floor - held - set(cells)):
                continue
            held |= set(cells)
            zone |= _zone(cells)
            out.append([(ax + dx, ay + dy, k) for dx, dy, k in shape])
            break
    return out


def fit(blocks: list[list[tuple[int, int, str]]], scale, grid: list[str], taken: set[Cell], keep_clear: set[Cell]) -> list[list[tuple[int, int, str]]]:
    """The blocks of a big room shown in a small one: each block becomes one cell, at the scaled place of its middle, as high as its
    highest cell. `scale` maps a cell of the big room to a cell of the small one (`cast.scale_cell`). A block that has no free cell
    there, or that would shut off the floor, is left out. The tall and the big ones go first."""
    floor = {(x, y) for y, row in enumerate(grid) for x, c in enumerate(row) if c == "."}
    held = set(taken)
    zone = _zone(held | keep_clear)
    order = sorted(blocks, key=lambda b: (-max(TIERS.index(k) for _x, _y, k in b), -len(b)))
    out = []
    for b in order:
        mx, my = round(sum(x for x, _y, _k in b) / len(b)), round(sum(y for _x, y, _k in b) / len(b))
        cell = scale((mx, my))
        kind = max((k for _x, _y, k in b), key=TIERS.index)
        if cell not in floor or cell in zone:
            continue
        if not _joined(floor - held - {cell}):
            continue
        held.add(cell)
        zone |= _zone([cell])
        out.append([(cell[0], cell[1], kind)])
    return out
