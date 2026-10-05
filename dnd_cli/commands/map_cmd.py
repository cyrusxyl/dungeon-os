"""map command - region and city maps: places, routes, and what the players know"""

import sys

from dnd_cli.commands.show_cmd import notify_stage, run_stage
from stage import crawl, maps


def _updated(campaign_dir, map_id: str) -> None:
    notify_stage(campaign_dir, {"type": "map_updated", "map": map_id})


def _summary(map_id: str, m: dict) -> str:
    lines = [f"{map_id}: {m['name']}" + (f" (inside {m['in']})" if m.get("in") else "")]
    for pid, p in m["places"].items():
        state = "visited" if p["visited"] else "known" if p["known"] else "hidden"
        lines.append(f"  {pid} {p['icon']} at {p['at']} {state}")
    for r in m["routes"]:
        both = m["places"][r["a"]]["known"] and m["places"][r["b"]]["known"]
        lines.append(f"  {r['a']} - {r['b']} {r['travel'] or ''}{'' if both else ' hidden'}")
    return "\n".join(lines)


def execute_place(campaign, map_id: str, place_id: str, tokens: list[str]) -> int:
    def go(campaign_dir):
        m = maps.place(campaign_dir, map_id, place_id, tokens)
        _updated(campaign_dir, map_id)
        p = m["places"][place_id]
        print(f"Placed {place_id} on {map_id} at {p['at']} ({'known' if p['known'] else 'hidden'}).")
        return 0
    return run_stage(campaign, go, maps.MapError)


def execute_route(campaign, map_id: str, a: str, b: str, tokens: list[str]) -> int:
    def go(campaign_dir):
        travel = next((t.split("=", 1)[1] for t in tokens if t.startswith("travel=")), "")
        maps.route(campaign_dir, map_id, a, b, travel)
        _updated(campaign_dir, map_id)
        print(f"Route {a} - {b} is known.")
        return 0
    return run_stage(campaign, go, maps.MapError)


def execute_reveal(campaign, map_id: str, place_id: str) -> int:
    def go(campaign_dir):
        maps.reveal(campaign_dir, map_id, place_id)
        _updated(campaign_dir, map_id)
        print(f"{place_id} is now on the players' map.")
        return 0
    return run_stage(campaign, go, maps.MapError)


def execute_show(campaign, map_id: str | None) -> int:
    def go(campaign_dir):
        found = maps.all_maps(campaign_dir)
        if map_id is None:
            print("\n".join(_summary(k, v) for k, v in found.items()) or "No maps yet.")
            return 0
        if map_id not in found:
            print(f"No map {map_id!r}. Maps: {', '.join(found) or 'none'}.", file=sys.stderr)
            return 1
        print(_summary(map_id, found[map_id]))
        return 0
    return run_stage(campaign, go, maps.MapError)


def execute_options() -> int:
    print("Usage: uv run dnd-cli map place <map-id> <place-id> [name=<Name_With_Underscores>] [icon=<icon>] "
          "[from=<place-id> dir=<n|ne|e|se|s|sw|w|nw> travel=<2_days>] [in=<parent-map-id>] [hidden=yes]")
    print("  in= is the id of the parent map. That map must already hold a place with the same id as this map.")
    print("  Example: map place the-grove old-oak from=gate dir=n   (map the-grove is the place the-grove on map region)")
    print("       uv run dnd-cli map route <map-id> <place-a> <place-b> [travel=<3_days>]")
    print("       uv run dnd-cli map reveal <map-id> <place-id>")
    print("Icons: " + ", ".join(crawl.data()["icons"]))
    return 0
