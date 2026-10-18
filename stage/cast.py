"""Where each actor stands in a scene room, in cells. A port of `stage/web/src/lib/layout.ts`: keep the two the same.

`stage/web/check/layout_cases.json` holds inputs and the cells the TypeScript gives; both languages are tested against it.
On the screen a cell (x, y) lies at s = x - y across and d = x + y deep. The party takes the left of the screen, the hostile
the right, the others the back or beside the party. Same inputs, same cells.
"""

from __future__ import annotations

RANK = {"far-left": 0, "left": 1, "center": 2, "right": 3, "far-right": 4}
ROW_DEPTH = {"back": 0.27, "mid": 0.48, "front": 0.69}  # the fraction of the way from the back of the floor to the front


def _targets(n: int, span: tuple[float, float], rows: list[str], depth) -> list[tuple[float, float]]:
    """Spread n actors over the rows: the rows alternate, and a later row is staggered so heads show between bodies."""
    s0, s1 = span
    cols = max(1, -(-n // len(rows)))
    step = (s1 - s0) / cols
    out = []
    for i in range(n):
        r = i % len(rows)
        out.append((s0 + step * (i // len(rows) + 0.5) + (min(step / 2, 0.75) if r else 0), depth(ROW_DEPTH[rows[r]])))
    return out


def layout(actors: dict[str, dict], stand: list[dict], room: dict) -> list[dict]:
    """The place of every actor: [{"id", "side", "cell", "facing", "sit", "onProp", "spot"?}], back to front.

    `actors`: id -> {"side", "position", "on"}. `stand`: the stand entries of the room. `room`: {"grid", "props"}.
    """
    placed: list[dict] = []
    used: dict[str, int] = {}
    rest: list[tuple[str, dict]] = []
    taken = {(p["x"], p["y"]) for p in room["props"] if not p.get("flat")}
    for aid, a in actors.items():
        spot = next((s for s in stand if s["slot"] == a.get("on")), None) if a.get("on") else None
        n = used.get(spot["slot"], 0) if spot else 0
        if spot and n < len(spot["points"]):
            used[spot["slot"]] = n + 1
            placed.append({"id": aid, "side": a.get("side") or "neutral", "cell": [spot["x"], spot["y"]], "facing": "down", "sit": spot["mode"] == "sit",
                           "onProp": True, "spot": {"stand": spot, "point": spot["points"][n]}})
            taken |= {(spot["x"] + dx, spot["y"] + dy) for dx, dy in ((1, 0), (0, 1), (1, 1))}  # keep clear of someone on a prop
        else:
            rest.append((aid, a))
    floor = [(x, y) for y, row in enumerate(room["grid"]) for x, c in enumerate(row) if c == "." and (x, y) not in taken]
    if floor:
        ss, ds = [x - y for x, y in floor], [x + y for x, y in floor]
        s_lo, s_hi, d_lo, d_hi = min(ss), max(ss), min(ds), max(ds)
    else:
        s_lo = s_hi = d_lo = d_hi = 0
    mid, half = (s_lo + s_hi) / 2, (s_hi - s_lo) / 2
    across = lambda a, b: (mid + half * a, mid + half * b)  # noqa: E731
    depth = lambda f: d_lo + f * (d_hi - d_lo)  # noqa: E731

    side = lambda a: a.get("side") or "neutral"  # noqa: E731
    pick = lambda f: [aid for aid, a in sorted((r for r in rest if f(r[1])), key=lambda r: RANK.get(r[1].get("position") or "center", 2))]  # noqa: E731
    party = pick(lambda a: side(a) in ("party", "ally"))
    hostile = pick(lambda a: side(a) == "hostile")
    neutral = pick(lambda a: side(a) == "neutral")
    rows = lambda n: ["front", "mid", "back"] if n > 8 else ["front", "mid"]  # noqa: E731
    beside = not hostile and bool(party)  # neutrals stand beside the party when no one opposes it

    wanted: dict[str, tuple[float, float]] = {}
    for ids, targets in ((party, _targets(len(party), across(-0.92, -0.08), rows(len(party)), depth)),
                         (hostile, _targets(len(hostile), across(0.08, 0.92), rows(len(hostile)), depth)),
                         (neutral, _targets(len(neutral), across(0.08, 0.92), rows(len(neutral)), depth) if beside
                          else _targets(len(neutral), across(-0.45, 0.45), ["back"], depth))):
        wanted.update(zip(ids, targets))

    free = set(floor)
    at: dict[str, tuple[int, int]] = {}
    for aid, (s, d) in sorted(wanted.items(), key=lambda kv: (kv[1][1], kv[1][0])):
        best, cost = None, float("inf")
        for x, y in floor:
            if (x, y) not in free:
                continue
            c = (x - y - s) ** 2 + 0.8 * (x + y - d) ** 2
            if c < cost:
                best, cost = (x, y), c
        if best:
            free.discard(best)
            at[aid] = best
    for aid, a in rest:
        if aid not in at:
            continue
        s = side(a)
        facing = "right" if s in ("party", "ally") else "left" if s == "hostile" or beside else "down"
        placed.append({"id": aid, "side": s, "cell": list(at[aid]), "facing": facing, "sit": False, "onProp": False})
    return sorted(placed, key=lambda p: p["cell"][0] + p["cell"][1])
