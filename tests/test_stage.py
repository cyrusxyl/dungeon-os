"""Checks for the visual stage: beat parsing and the event log.

Run from the repo root:  .venv/bin/python tests/test_stage.py

Plain asserts so no test runner is needed.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from stage import beat, state
from view.settings import build_dm_command

PASS = 0
FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}")


def raises(fn) -> bool:
    try:
        fn()
    except beat.BeatError:
        return True
    return False


def test_parse() -> None:
    print("beat.parse")
    events = beat.parse(
        "@scene chapel-of-ilmater\n"
        "@enter sister-gareth right\n"
        "@narrate Candle smoke hangs\n"
        "under the low beams.\n"
        "\n"
        "@say sister-gareth happy What brings you here?\n"
        "@say goblin#2 Give us the coin!\n"
        "@choices Talk | Fight | Leave\n"
        "@exit sister-gareth\n"
        "@clear\n"
    )
    types = [e["type"] for e in events]
    check("all lines become events", types == ["scene", "enter", "narrate", "say", "say", "choices", "exit", "clear"])
    check("continuation joins the previous text", events[2]["text"] == "Candle smoke hangs under the low beams.")
    check("emotion is read when given", events[3]["emotion"] == "happy" and events[3]["text"] == "What brings you here?")
    check("emotion defaults to neutral", events[4]["emotion"] == "neutral" and events[4]["actor"] == "goblin#2")
    check("choices split on |", events[5]["options"] == ["Talk", "Fight", "Leave"])
    check("enter keeps position", events[1]["position"] == "right")
    check("a bare first line is narration", beat.parse("Rain falls.")[0] == {"type": "narrate", "text": "Rain falls."})
    check("an emotion word alone is text, not emotion",
          beat.parse("@say toblen happy")[0]["text"] == "happy")


def test_parse_errors() -> None:
    print("beat.parse errors")
    check("empty beat", raises(lambda: beat.parse("  \n")))
    check("unknown command", raises(lambda: beat.parse("@dance toblen")))
    check("say without text", raises(lambda: beat.parse("@say toblen")))
    check("bad id", raises(lambda: beat.parse("@enter Sister Gareth")))
    check("bad position", raises(lambda: beat.parse("@enter toblen upstairs")))
    check("one choice only", raises(lambda: beat.parse("@choices Leave")))


def test_append() -> None:
    print("beat.append")
    with tempfile.TemporaryDirectory() as tmp:
        campaign_dir = Path(tmp)
        beat.append(campaign_dir, beat.parse("@narrate One."))
        beat.append(campaign_dir, beat.parse("@narrate Two.\n@narrate Three."))
        lines = [json.loads(line) for line in beat.log_path(campaign_dir).read_text().splitlines()]
        check("appends one line per event", [e["text"] for e in lines] == ["One.", "Two.", "Three."])
        check("events of one call share a beat id", lines[1]["beat"] == lines[2]["beat"])


def test_state() -> None:
    print("state.apply")
    s = state.empty()
    for e in beat.parse(
        "@scene chapel\n@enter gareth right\n@say sireth angry Who are you?\n@choices A | B"
    ):
        s = state.apply(s, e)
    check("scene is set", s["scene"] == "chapel")
    check("enter keeps the given position", s["actors"]["gareth"]["position"] == "right")
    check("a speaker not on stage is put on a free spot", s["actors"]["sireth"]["position"] == "left")
    check("the speaker's emotion is kept", s["actors"]["sireth"]["emotion"] == "angry")
    check("choices are open", s["choices"]["options"] == ["A", "B"])
    s = state.apply(s, {"type": "narrate", "text": "Later."})
    check("a new story line closes the choices", s["choices"] is None)
    s = state.apply(s, {"type": "scene", "location": "street"})
    check("a new scene clears the actors", s["actors"] == {})
    s = state.apply(s, {"type": "dm_status", "status": "idle", "dm_text": "Beat shown."})
    check("DM text goes to the DM log, not the story log",
          s["dm_log"] == ["Beat shown."] and all(l.get("text") != "Beat shown." for l in s["log"]))
    check("seq counts every event", s["seq"] == 7)


def test_initial_prompt() -> None:
    print("build_dm_command initial_prompt")
    cmd = build_dm_command({"agent_framework": "claude", "model": "haiku"}, Path("/g"), "sid", initial_prompt="Start it's on")
    check("claude takes the prompt as a quoted positional argument", cmd[2].endswith("'Start it'\"'\"'s on'"))
    cmd = build_dm_command({"agent_framework": "gemini", "model": ""}, Path("/g"), "sid", initial_prompt="Go")
    check("gemini takes the prompt with -i", "-i Go" in cmd[2])


def test_actors() -> None:
    print("lpc / actors")
    from stage import actors, lpc
    from stage.assets import LPC_DIR

    if not (LPC_DIR / "sheet_definitions").is_dir():
        print("  skip (LPC art not fetched; run uv run dungeon-os once)")
        return
    spec = actors.build("sireth", ["name=Sireth", "body=female", "skin=blue", "eyes=red", "elven", "robe:dark_gray"])
    check("build sets name and body", spec["name"] == "Sireth" and spec["body"] == "female")
    check("a known spec validates clean", lpc.validate(spec) == [])
    check("'_' in a color matches a space", dict((i.id, c) for i, c in lpc.resolve(spec)[1])["robe"] == "dark gray")
    frame = lpc.render(spec, "down")
    check("render gives one 64x64 frame with pixels", frame.size == (64, 64) and frame.getbbox() is not None)
    check("portrait is 36x36", lpc.portrait(spec, "angry").size == (36, 36))
    check("an item for another body only warns", lpc.validate({"body": "male", "items": ["robe"]}) != [])
    try:
        lpc.validate({"body": "female", "items": ["robe:neon"]})
        check("a bad color raises", False)
    except lpc.ActorError:
        check("a bad color raises", True)
    check("later item of a type wins", lpc.normalize_items(["robe:white", "hair_bob", "robe:black"]) == ["robe:black", "hair_bob"])
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        check("goblin#2 falls back to the goblin preset", actors.load(d, "goblin#2")["name"] == "Goblin")
        actors.save(d, "goblin", {"name": "Snik", "body": "teen", "items": []})
        check("a campaign actor file beats the preset", actors.load(d, "goblin#2")["name"] == "Snik")
        check("an unknown kind has no look", actors.load(d, "stranger") is None)
    bad = [k for k, p in actors.presets().items() if lpc.validate(p)]
    check(f"every preset validates without warnings {bad}", not bad)


def test_scenes() -> None:
    print("scenes")
    from stage import scenes
    from stage.assets import TILES_DIR

    if not (TILES_DIR / "walls").is_dir():
        print("  skip (tiles not fetched; run uv run dungeon-os once)")
        return
    for name in scenes.catalog()["templates"]:
        img = scenes.render({"template": name})
        assert img.size == (scenes.W, scenes.H), name
    check("every template renders at 320x192", True)
    spec = scenes.build(["template=chapel", "mood=dusk", "wall_center=bust", "+barrel@back-right"], None)
    check("build keeps template, mood, slot and extra",
          spec["template"] == "chapel" and spec["mood"] == "dusk"
          and spec["slots"] == {"wall_center": "bust"} and spec["add"] == [["barrel", "back_right"]])
    spec = scenes.build(["back_left=none", "clear=add"], spec)
    check("a second build changes only what it names",
          spec["mood"] == "dusk" and spec["slots"]["back_left"] is None and spec["add"] == [])
    check("an emptied slot is gone from the resolved scene", scenes.resolve(spec)["slots"]["back_left"] is None)
    for bad, label in [(["template=palace"], "unknown template"), (["template=chapel", "wall=gold"], "unknown wall"),
                       (["template=chapel", "mood=spooky"], "unknown mood"), (["template=chapel", "+cow@back_left"], "unknown prop"),
                       (["template=chapel", "+barrel@upstairs"], "unknown zone"), (["mood=night"], "no template on a new scene")]:
        try:
            scenes.resolve(scenes.build(bad, None))
            check(f"{label} raises", False)
        except scenes.SceneError:
            check(f"{label} raises", True)
    try:
        scenes.resolve(scenes.build(["template=chapel", "+statue_of_ilmater@back_left"], None))
    except scenes.UnknownProp as e:
        check("an unknown prop names itself for the gap log", e.prop == "statue_of_ilmater")


def test_rolls() -> None:
    print("dice hook / roll state")
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage"))
    import hook

    out = {"stdout": "Rolled: 2d6: [6, 4]\nAdding: 10 + 3 = 13\n13\n"}
    e = hook.roll_event({"tool_input": {"command": "uv run roll 2d6+3 -v"}, "tool_response": out})
    check("a roll gives expr, total and faces",
          e == {"type": "roll", "expr": "2d6+3", "total": 13, "dice": [{"die": "2d6", "faces": [6, 4]}]})
    check("a # secret roll stays behind the screen",
          hook.roll_event({"tool_input": {"command": "uv run roll 1d20 -v  # secret"}, "tool_response": out}) is None)
    check("other commands are not rolls", hook.roll_event({"tool_input": {"command": "ls"}, "tool_response": out}) is None)
    check("plain-text tool output works too",
          hook.roll_event({"tool_input": {"command": "uv run roll 1d20 -v"}, "tool_output": "Rolled: 1d20: [20]\n20"})["total"] == 20)
    s = state.apply(state.empty(), e)
    check("the state keeps the last roll", s["last_roll"]["total"] == 13 and s["last_roll"]["seq"] == 1)


def test_local_only() -> None:
    print("server: local browser tab only")
    from stage.server import request_allowed

    local = {"host": "127.0.0.1:8000"}
    check("same-origin websocket is allowed", request_allowed("websocket", "GET", {**local, "origin": "http://127.0.0.1:8000"}))
    check("a websocket from another site is refused", not request_allowed("websocket", "GET", {**local, "origin": "https://evil.example"}))
    check("a websocket from another local port is refused", not request_allowed("websocket", "GET", {**local, "origin": "http://127.0.0.1:9999"}))
    check("a JSON POST from the tab is allowed",
          request_allowed("http", "POST", {**local, "origin": "http://127.0.0.1:8000", "content-type": "application/json"}))
    check("a text/plain POST is refused", not request_allowed("http", "POST", {**local, "content-type": "text/plain"}))
    check("a foreign Host (DNS rebinding) is refused", not request_allowed("http", "GET", {"host": "evil.example:8000"}))
    check("a GET with no Origin (page load, image) is allowed", request_allowed("http", "GET", {"host": "localhost:8000"}))


def _site(theme="dungeon", pois=(("altar", "far", "altar"),), seed=7, danger="none"):
    from stage import crawl

    spec = {"theme": theme, "size": "small", "seed": seed, "danger": danger,
            "pois": [{"id": i, "where": w, "icon": c} for i, w, c in pois]}
    return crawl.generate(spec)


def test_crawl() -> None:
    print("sites: generator, sight, walking")
    from stage import crawl

    ok = True
    for theme in ("dungeon", "house", "cave"):
        for seed in range(25):
            site = _site(theme, (("a", "near", "chest"), ("b", "mid", "chest"), ("c", "far", "chest"), ("d", "entrance", "chest")), seed)
            grid = site["grid"]
            dist = crawl._flood(grid, tuple(site["entrance"]))
            floors = [(x, y) for y, r in enumerate(grid) for x, c in enumerate(r) if c in crawl.WALKABLE]
            ok &= all(c in dist for c in floors)
            ok &= all(grid[p["y"]][p["x"]] == crawl.FLOOR and (p["x"], p["y"]) in dist for p in site["pois"].values())
    check("every floor cell and POI can be reached, POIs never on a wall or door", ok)
    check("the same seed gives the same layout", _site(seed=3)["grid"] == _site(seed=3)["grid"])
    site = _site(pois=(("near-thing", "near", "chest"), ("far-thing", "far", "chest")))
    depth = lambda pid: site["areas"][site["pois"][pid]["area"]]["depth"]  # noqa: E731
    check("a far POI is deeper than a near one", depth("far-thing") > depth("near-thing"))

    site = _site()
    crawl.arrive(site)
    check("arrival puts the party at the entrance", site["party"] == site["entrance"])
    view = crawl.view(site)
    hidden = all(c == " " for row, srow in zip(view["cells"], site["seen"]) for c, s in zip(row, srow) if s == "0")
    check("the view has no unseen cell", hidden and any(c == " " for row in view["cells"] for c in row))
    check("the view has no unfound POI", view["pois"] == [] and "altar" not in json.dumps(view))
    check("the view has no layout secrets", not {"grid", "areas", "area_of", "spec"} & set(view))

    # Walk toward the altar along the true path: it is found and the walk stops there.
    altar = site["pois"]["altar"]
    dist = crawl._flood(site["grid"], (altar["x"], altar["y"]))
    path, cur = [], tuple(site["party"])
    while dist[cur]:
        cur = min((n for n in crawl._around4(*cur, len(site["grid"][0]), len(site["grid"])) if n in dist), key=dist.get)
        path.append(cur)
    result = crawl.walk(site, path)
    check("a newly seen POI stops the walk", result["stopped"] == "poi" and result["pois"] == ["altar"]
          and len(result["path"]) < len(path))
    check("a found POI is in the view", [p["id"] for p in crawl.view(site)["pois"]] == ["altar"])
    check("the prompt names the found POI and how to resume",
          "altar" in crawl.prompt_found("crypt", site, ["altar"]) and "@explore crypt" in crawl.prompt_found("crypt", site, ["altar"]))
    check("walking into a wall is blocked", crawl.walk(site, [(0, 0)])["stopped"] == "blocked")
    check("a click path uses seen cells only", crawl.path_to(site, (altar["x"], altar["y"])) is not None
          or site["seen"][altar["y"]][altar["x"]] == "0")

    site = _site(pois=(), danger="high")
    crawl.arrive(site)
    grid = site["grid"]
    door = next((x, y) for y, r in enumerate(grid) for x, c in enumerate(r) if c == crawl.DOOR)
    d = crawl._flood(grid, door)
    path, cur = [], tuple(site["party"])
    while d[cur]:
        cur = min((n for n in crawl._around4(*cur, len(grid[0]), len(grid)) if n in d), key=d.get)
        path.append(cur)
    result = crawl.walk(site, path, roll=lambda n: 1)
    check("walking into a closed door opens it", result["stopped"] is None and site["grid"][door[1]][door[0]] == crawl.OPEN)
    site2 = _site(pois=(), danger="high")
    crawl.arrive(site2)
    hits = []
    far = max(range(len(site2["areas"])), key=lambda i: site2["areas"][i]["depth"])
    target = (site2["areas"][far]["cx"], site2["areas"][far]["cy"])
    d = crawl._flood(site2["grid"], target)
    path, cur = [], tuple(site2["party"])
    while d[cur]:
        cur = min((n for n in crawl._around4(*cur, len(site2["grid"][0]), len(site2["grid"])) if n in d), key=d.get)
        path.append(cur)
    result = crawl.walk(site2, path, roll=lambda n: hits.append(n) or 0)
    check("only first entry into a new area rolls (not the entrance area); a hit stops the walk",
          result["stopped"] == "wander" and hits == [3])

    is_actor = lambda k: k == "goblin"  # noqa: E731
    spec, new = crawl.build(["theme=crypt", "poi=goblin-camp@mid", "poi=old-well@near", "poi=thing@far:goblin"], None, is_actor)
    check("icons are guessed from the id", [p["icon"] for p in new] == ["goblin", "well", "goblin"])
    check("buildings default to no danger", crawl.build(["theme=house"], None, is_actor)[0]["danger"] == "none")
    for bad, label in [(["theme=moon"], "unknown theme"), (["theme=crypt", "poi=x@deep"], "bad depth"),
                       (["theme=crypt", "poi=x@far:dragonz"], "unknown icon"), (["size=small"], "no theme")]:
        try:
            crawl.build(bad, None, is_actor)
            check(f"{label} is refused", False)
        except crawl.SiteError:
            check(f"{label} is refused", True)
    try:
        crawl.build(["theme=cave"], spec, is_actor)
        check("a saved layout never changes", False)
    except crawl.SiteError:
        check("a saved layout never changes", True)


def test_maps() -> None:
    print("maps: places, reveals, travel")
    from stage import maps

    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp)
        maps.place(c, "coast", "city", ["icon=city", "name=Big_City"])
        maps.place(c, "coast", "tower", ["from=city", "dir=n", "travel=2_days"])
        maps.place(c, "coast", "ruin", ["from=tower", "dir=e", "travel=1_day"])
        maps.place(c, "coast", "lair", ["from=city", "dir=e", "travel=3_days", "hidden=yes"])
        maps.place(c, "city", "inn", ["in=coast", "icon=tavern"])
        m = maps.load(c, "coast")
        check("dir= lays places out on a grid", m["places"]["tower"]["at"] == [0, -2])
        view = maps.view(m, "coast", "city")
        check("a hidden place is not in the view", "lair" not in json.dumps(view))
        check("the city map is inside its place", maps.load(c, "city")["in"] == "coast" and maps.load(c, "city")["name"] == "Big City")
        for args, label in [(("coast", "inn", []), "a place id on two maps"), (("coast", "x", ["from=city"]), "no dir"),
                            (("nope", "y", ["in=coast"]), "in= without a parent place")]:
            try:
                maps.place(c, *args)
                check(f"{label} is refused", False)
            except maps.MapError:
                check(f"{label} is refused", True)
        maps.reveal(c, "coast", "lair")
        check("reveal shows the place and its route", "lair" in json.dumps(maps.view(maps.load(c, "coast"), "coast", None)))
        check("visit returns the map", maps.visit(c, "inn") == "city")
        place = {"map": "city", "place": "inn"}
        check("the level chain goes up", [l["id"] for l in maps.chain(c, None, place)] == ["city", "coast"])
        check("here on a parent map is the place that holds the party", maps.here(c, "coast", None, place) == "city")
        prompt = maps.travel_prompt(maps.load(c, "coast"), "city", "ruin")
        check("travel takes the known route and names the arrival scene",
              "Big City → Tower → Ruin" in prompt and "2 days, 1 day" in prompt and "@scene ruin" in prompt)


def test_explore_beat() -> None:
    print("@explore and map position")
    from dnd_cli.commands import show_cmd
    from stage import crawl, maps

    events = beat.parse("@explore crypt\n@explore crypt stairs-down")
    check("@explore parses", events == [{"type": "explore", "site": "crypt"}, {"type": "explore", "site": "crypt", "at": "stairs-down"}])
    s = state.empty()
    for e in [{"type": "scene", "location": "inn"}, {"type": "at", "map": "city", "place": "inn"}, {"type": "explore", "site": "crypt"}]:
        s = state.apply(s, e)
    check("the state knows the site and the place", s["explore"] == "crypt" and s["place"] == {"map": "city", "place": "inn"})
    check("@scene leaves the site", state.apply(s, {"type": "scene", "location": "x"})["explore"] is None)

    import io, sys as _sys
    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp)
        maps.place(c, "city", "crypt", [])
        site = _site(pois=(("stairs-down", "far", "stairs-down"),))
        crawl.save(c, "crypt", site)
        _sys.stdin = io.StringIO("@explore crypt stairs-down\n")
        rc = show_cmd.execute_beat(str(c), None)
        _sys.stdin = _sys.__stdin__
        lines = [json.loads(l) for l in beat.log_path(c).read_text().splitlines()]
        site = crawl.load(c, "crypt")
        p = site["pois"]["stairs-down"]
        check("@explore <site> <poi> puts the party at the POI", rc == 0 and site["party"] == [p["x"], p["y"]])
        check("a site that is a place moves the map marker", lines[1]["type"] == "at" and lines[1]["place"] == "crypt")


if __name__ == "__main__":
    test_parse()
    test_parse_errors()
    test_append()
    test_state()
    test_initial_prompt()
    test_actors()
    test_scenes()
    test_rolls()
    test_local_only()
    test_crawl()
    test_maps()
    test_explore_beat()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
