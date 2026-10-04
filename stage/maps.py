"""Region and city maps: known places, routes, and where the party is.

A map file (`{campaign}/stage/maps/<map-id>.json`) holds places and routes.
The DM adds them with `dnd-cli map place`; a place it marks hidden stays off
the players' map until `map reveal`. A map with `"in": "<parent-map>"` is the
inside of the parent's place with the same id; a site is the inside of the
place with the site's id. Place ids are unique in the campaign and are also
scene location ids. See dungeon-crawl.md.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from stage import crawl

DIRS = {"n": (0, -1), "ne": (1, -1), "e": (1, 0), "se": (1, 1), "s": (0, 1), "sw": (-1, 1), "w": (-1, 0), "nw": (-1, -1)}
STEP = 2


class MapError(ValueError):
    """A bad map command. The message says how to fix it."""


def maps_dir(campaign_dir: Path) -> Path:
    return campaign_dir / "stage" / "maps"


def load(campaign_dir: Path, map_id: str) -> dict | None:
    if not crawl.ID_RE.match(map_id):
        return None
    try:
        return json.loads((maps_dir(campaign_dir) / f"{map_id}.json").read_text())
    except (OSError, ValueError):
        return None


def save(campaign_dir: Path, map_id: str, m: dict) -> Path:
    return crawl.write_json(maps_dir(campaign_dir) / f"{map_id}.json", m)


def all_maps(campaign_dir: Path) -> dict[str, dict]:
    out = {}
    for path in sorted(maps_dir(campaign_dir).glob("*.json")):
        m = load(campaign_dir, path.stem)
        if m is not None:
            out[path.stem] = m
    return out


def find_place(campaign_dir: Path, place_id: str) -> str | None:
    """The map that holds this place, if any."""
    return next((mid for mid, m in all_maps(campaign_dir).items() if place_id in m["places"]), None)


def _check_id(value: str, what: str) -> str:
    if not crawl.ID_RE.match(value):
        raise MapError(f"{what} {value!r}: use lower-case letters, digits, '-' or '_'.")
    return value


def _free_spot(m: dict, start: list[int], d: tuple[int, int]) -> list[int]:
    taken = {tuple(p["at"]) for p in m["places"].values()}
    x, y = start[0] + d[0] * STEP, start[1] + d[1] * STEP
    while (x, y) in taken:
        x, y = x + d[0], y + d[1]
    return [x, y]


def _route(m: dict, a: str, b: str) -> dict | None:
    return next((r for r in m["routes"] if {r["a"], r["b"]} == {a, b}), None)


def place(campaign_dir: Path, map_id: str, place_id: str, tokens: list[str]) -> dict:
    """Add a place (and its route from `from=`). Creates the map on its first place."""
    _check_id(map_id, "map id")
    _check_id(place_id, "place id")
    opts: dict[str, str] = {}
    for token in tokens:
        key, eq, value = token.partition("=")
        if not eq or key not in ("name", "icon", "from", "dir", "travel", "in", "hidden"):
            raise MapError(f"{token!r}: use name=, icon=, from=, dir=, travel=, in=, hidden=yes.")
        opts[key] = value
    m = load(campaign_dir, map_id) or {"name": crawl.title(map_id), "in": None, "places": {}, "routes": []}
    if place_id in m["places"]:
        raise MapError(f"{place_id!r} is already on {map_id}. Use `map route` or `map reveal` to change what is known.")
    other = find_place(campaign_dir, place_id)
    if other and other != map_id:
        raise MapError(f"{place_id!r} is already a place on the map {other!r}. A place id is on one map only.")
    if "in" in opts:
        parent = load(campaign_dir, _check_id(opts["in"], "in="))
        if parent is None or map_id not in parent["places"]:
            raise MapError(f"in={opts['in']}: first put the place {map_id!r} on the map {opts['in']!r}.")
        m["in"] = opts["in"]
        m["name"] = parent["places"][map_id]["name"]
    if m["places"]:
        if "from" not in opts or opts.get("dir") not in DIRS:
            raise MapError(f"a new place on {map_id} needs from=<place> and dir=<{'|'.join(DIRS)}>.")
        if opts["from"] not in m["places"]:
            raise MapError(f"from={opts['from']}: no such place on {map_id}. Places: {', '.join(m['places'])}.")
        at = _free_spot(m, m["places"][opts["from"]]["at"], DIRS[opts["dir"]])
    else:
        at = [0, 0]
    site = crawl.load(campaign_dir, place_id)
    # A site's place shows its theme (crypt, cave, ...); otherwise guess from the id.
    icon = opts.get("icon") or crawl.guess_icon(site["spec"]["theme"] if site else place_id, lambda _: False)
    if icon not in crawl.data()["icons"]:
        raise MapError(f"icon={icon}: use one of {', '.join(crawl.data()['icons'])}.")
    known = opts.get("hidden", "no").lower() not in ("yes", "true", "1")
    m["places"][place_id] = {
        "name": opts.get("name", "").replace("_", " ").strip() or (site and site["spec"].get("name")) or crawl.title(place_id),
        "icon": icon,
        "at": at,
        "known": known,
        "visited": False,
    }
    if "from" in opts:
        m["routes"].append({"a": opts["from"], "b": place_id, "travel": opts.get("travel", "").replace("_", " "), "known": known})
    save(campaign_dir, map_id, m)
    return m


def route(campaign_dir: Path, map_id: str, a: str, b: str, travel: str = "") -> dict:
    m = load(campaign_dir, map_id)
    if m is None:
        raise MapError(f"no map {map_id!r}.")
    for p in (a, b):
        if p not in m["places"]:
            raise MapError(f"no place {p!r} on {map_id}. Places: {', '.join(m['places'])}.")
    r = _route(m, a, b)
    if r is None:
        m["routes"].append({"a": a, "b": b, "travel": travel.replace("_", " "), "known": True})
    else:
        r["known"] = True
        r["travel"] = travel.replace("_", " ") or r["travel"]
    save(campaign_dir, map_id, m)
    return m


def reveal(campaign_dir: Path, map_id: str, place_id: str) -> dict:
    """Show a hidden place, with its routes to places the players know."""
    m = load(campaign_dir, map_id)
    if m is None or place_id not in m["places"]:
        raise MapError(f"no place {place_id!r} on the map {map_id!r}.")
    m["places"][place_id]["known"] = True
    for r in m["routes"]:
        if place_id in (r["a"], r["b"]) and all(m["places"][p]["known"] for p in (r["a"], r["b"])):
            r["known"] = True
    save(campaign_dir, map_id, m)
    return m


def visit(campaign_dir: Path, place_id: str) -> str | None:
    """Mark a place known and visited when the party is there. Returns its map."""
    map_id = find_place(campaign_dir, place_id)
    if map_id is None:
        return None
    m = load(campaign_dir, map_id)
    p = m["places"][place_id]
    if not (p["known"] and p["visited"]):
        p["known"] = p["visited"] = True
        save(campaign_dir, map_id, m)
    return map_id


def hint(campaign_dir: Path, place_id: str) -> str | None:
    """For a new place that is on no map: how to put it on one."""
    if find_place(campaign_dir, place_id):
        return None
    known = ", ".join(all_maps(campaign_dir)) or "none yet"
    return (f"Map: {place_id!r} is on no map. If the players can travel to it (not a room inside another place), "
            f"put it on one: uv run dnd-cli map place <map-id> {place_id} from=<place-id> dir=<n|ne|e|se|s|sw|w|nw> "
            f"(maps: {known}; see uv run dnd-cli map options).")


def chain(campaign_dir: Path, explore: str | None, place: dict | None) -> list[dict]:
    """The levels from the current one up: the site (if exploring), then the maps."""
    levels: list[dict] = []
    map_id = None
    if explore:
        levels.append({"kind": "site", "id": explore})
        map_id = find_place(campaign_dir, explore)
    if map_id is None and place:
        map_id = place.get("map")
    seen = set()
    while map_id and map_id not in seen:
        m = load(campaign_dir, map_id)
        if m is None:
            break
        seen.add(map_id)
        levels.append({"kind": "map", "id": map_id})
        map_id = m.get("in")
    return levels


def here(campaign_dir: Path, map_id: str, explore: str | None, place: dict | None) -> str | None:
    """The party's place on this map: the current place, or the place that holds it."""
    m = load(campaign_dir, map_id)
    if m is None:
        return None
    ids = [explore, place.get("place") if place else None]
    ids += [lvl["id"] for lvl in chain(campaign_dir, explore, place)]
    return next((i for i in ids if i and i in m["places"]), None)


def view(m: dict, map_id: str, here_id: str | None) -> dict:
    """Only what the players know."""
    places = {pid: p for pid, p in m["places"].items() if p["known"]}
    return {
        "id": map_id,
        "name": m["name"],
        "up": m.get("in"),
        "here": here_id,
        "places": [{"id": pid, **{k: p[k] for k in ("name", "icon", "at", "visited")}} for pid, p in places.items()],
        "routes": [
            {k: r[k] for k in ("a", "b", "travel")}
            for r in m["routes"]
            if r["known"] and r["a"] in places and r["b"] in places
        ],
    }


def shortest(m: dict, a: str, b: str) -> list[str] | None:
    """Fewest legs over known routes."""
    prev: dict = {a: None}
    queue = deque([a])
    while queue:
        cur = queue.popleft()
        if cur == b:
            out = []
            while cur is not None:
                out.append(cur)
                cur = prev[cur]
            return out[::-1]
        for r in m["routes"]:
            if r["known"] and cur in (r["a"], r["b"]):
                nxt = r["b"] if cur == r["a"] else r["a"]
                if nxt not in prev and m["places"][nxt]["known"]:
                    prev[nxt] = cur
                    queue.append(nxt)
    return None


def travel_prompt(m: dict, origin: str, dest: str) -> str:
    name = lambda pid: m["places"][pid]["name"]  # noqa: E731
    path = shortest(m, origin, dest)
    if path is None:
        way = "no known route; the party goes across country"
    else:
        legs = [(_route(m, x, y) or {}).get("travel") for x, y in zip(path, path[1:])]
        times = ", ".join(t for t in legs if t)
        way = " → ".join(name(p) for p in path) + (f" ({times})" if times else "")
    return (f"[map] The party travels from {name(origin)} to {name(dest)}: {way}. "
            f"Run the journey (encounter checks on the way), then show the arrival with `@scene {dest}`.")
