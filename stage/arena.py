"""The tile grid that the crawl and the combat board share: lines, sight and walking distance.

A grid is a list of rows of one-character tiles. This module does not know what a tile means:
each caller passes the tiles that block sight or that can be walked on. `crawl.py` walks 4
directions over its own tiles. The combat board (below, added later) walks 8 directions over its
own tiles. See combat-board.md.
"""

from __future__ import annotations

from collections import deque


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
