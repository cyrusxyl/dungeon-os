"""Checks for the visual stage: beat parsing and the event log.

Run from the repo root:  .venv/bin/python tests/test_stage.py

Plain asserts so no test runner is needed.
"""

from __future__ import annotations

import json
import time
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


def raises(fn, exc=beat.BeatError) -> bool:
    try:
        fn()
    except exc:
        return True
    return False


def fixture_campaign(tmp) -> Path:
    """A copy of the example campaign with its committed files (a test may have changed the checkout)."""
    import shutil
    import subprocess

    src = Path(__file__).parent / "fixtures" / "example-campaign"
    c = Path(tmp) / "camp"
    shutil.copytree(src, c, ignore=shutil.ignore_patterns("stage", ".cache"))
    for rel in subprocess.run(["git", "ls-files", "."], cwd=src, capture_output=True, text=True).stdout.split():
        got = subprocess.run(["git", "show", f"HEAD:./{rel}"], cwd=src, capture_output=True)
        if got.returncode == 0:
            (c / rel).write_bytes(got.stdout)
    return c


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
    cmd = build_dm_command({"agent_framework": "agy", "model": ""}, Path("/g"), "sid", initial_prompt="Go")
    check("agy takes the prompt with -i", "-i Go" in cmd[2])


def _raises_actor(fn) -> bool:
    from stage import lpc

    try:
        fn()
    except lpc.ActorError:
        return True
    return False


def test_actors() -> None:
    print("lpc / actors")
    from stage import actors, lpc
    from stage.assets import LPC_DIR

    if not (LPC_DIR / "sheet_definitions").is_dir():
        print("  skip (LPC art not fetched; run uv run dungeon-os once)")
        return
    spec = actors.build("sireth", ["name=Sireth", "body=female", "skin=blue", "eyes=red", "elven", "robe:dark_gray", "hair_long:white"])
    for bad, want in [("tiara", "formal_tiara"), ("hat_formla", "hat_formal_crown")]:
        try:
            lpc._item(bad)
            check(f"{bad} resolves", bad == "tiara")
        except lpc.ActorError as e:
            check(f"unknown item {bad} suggests close names and a type", want in str(e) and "actor options hat" in str(e))
    try:
        lpc.validate({"items": ["hair_braid:platnum"]})
        check("a bad color is refused", False)
    except lpc.ActorError as e:
        check("a bad color names the closest first", "platnum: use platinum" in str(e))
    check("silver is an alias of platinum", lpc.validate({"items": ["hair_braid:silver"]}) is not None)
    check("build sets name and body", spec["name"] == "Sireth" and spec["body"] == "female")
    check("a known spec validates clean", lpc.validate(spec) == [])
    check("a look with no hair or headwear warns that it is bald",
          any("bald" in w for w in lpc.validate({"body": "female", "items": ["robe:dark_gray"]})))
    check("an item for the other sex is swapped for its twin",
          lpc.sex_fixed(["heads_human_male_elderly", "hair_long:white"], "female")[0] == "heads_human_female_elderly")
    notes = []
    check("a skin that does not fit the race is replaced, with a note",
          actors.build("x", ["race=drow", "skin=dark_green"], None, None, notes)["skin"] == "blue" and notes)
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
    root = Path(actors.ensure_dcss())
    stems = actors.dcss_monsters()
    missing = [k for k, v in actors.monster_aliases().items() if not (root / v).is_file() and v not in stems]
    check(f"every monster alias points at a tile {missing}", not missing)
    check("D&D names find a tile", all(actors.find_tile(n) for n in ["owlbear", "giant-spider", "dire-wolf", "mimic", "beholder", "young red dragon"]))
    check("size words are ignored", actors.find_tile("giant-spider") == actors.find_tile("spider"))
    from stage import creatures

    cat = creatures.catalog()
    check("every creature file exists", all((creatures.TILES_DIR / c["file"]).is_file() for c in cat.values()))
    check("every creature name points at a creature", all(v in cat for v in creatures.names().values()))
    ok = all(creatures.frame(creatures.PREFIX + cid, f).getbbox() for cid in cat for f in ("down", "up", "left", "right"))
    check("every creature draws in all four facings", ok)
    check("a left-facing creature is the right-facing one, flipped",
          list(creatures.frame("creature:lion", "left").getdata()) != list(creatures.frame("creature:lion", "right").getdata()))
    check("animals beat DCSS tiles of the same name", actors.find_tile("bear") == "creature:bear_grizzly")
    check("an animal is drawn at its size, in a square frame",
          actors._tile_frame({"tile": "creature:cow"}).size[0] == actors._tile_frame({"tile": "creature:cow"}).size[1] >= 64)
    check("a dragon has a bigger frame than a goblin",
          actors._tile_frame({"tile": actors.find_tile("dragon")}).width > actors._tile_frame({"tile": actors.find_tile("goblin")}).width)
    import io

    from PIL import Image

    portrait = Image.open(io.BytesIO(actors.png({"tile": actors.find_tile("dragon")}, "portrait")))
    check("the portrait of a huge monster stays one tile", max(portrait.size) <= 32)
    check("scale= is checked", all(_raises_actor(lambda v=v: actors.build("x", ["tile=ogre", f"scale={v}"])) for v in ("5", "huge")))
    check("scale= sets the size of a tile", actors.build("x", ["scale=2", "tile=goblin"])["scale"] == 2)
    check("a person is not matched to a monster", actors.find_tile("sister-gareth") is None)
    sizes = actors.sizes()
    bad = [k for k in sizes["stems"] if k not in stems and k not in creatures.catalog()]
    check(f"every size names a real tile {bad}", not bad)
    bad = [k for k in sizes["folders"] if k and not (root / "monster" / k).is_dir()]
    check(f"every size folder exists {bad}", not bad)
    check("every size is a known scale", all(v in actors.SCALES for v in (*sizes["stems"].values(), *sizes["folders"].values())))
    check("an alias never shadows a preset kind", not [k for k in actors.monster_aliases() if k in actors.presets()])
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        check("a preset kind with a size word gets no tile", actors.load(d, "young-goblin#1") is None)
        check("a beast with a size word gets a tile", (actors.load(d, "giant-spider#1") or {}).get("tile", "").endswith("spider.png"))


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
    cat = scenes.catalog()
    bad = []
    for name in cat["props"]:
        try:
            scenes.prop_image(name)
        except Exception as e:  # a bad sheet, path or rect
            bad.append(f"{name}: {e}")
    check(f"every prop loads {bad}", not bad)
    flat = [n for n, p in cat["props"].items() if "rect" in p and p["rect"][2] * p["rect"][3] == 0]
    check("no prop has an empty rect", not flat)
    empty = [n for n in cat["props"] if scenes.prop_image(n).getchannel("A").getbbox() is None]
    check(f"no prop is fully transparent {empty}", not empty)
    surfaces = [(s, c, r) for s in (*cat["floors"], *cat["grounds"]) for c in range(2) for r in range(2)]
    check("every floor and ground makes a tile", all(scenes.surface_tile(s, c, r).size == (scenes.T, scenes.T) for s, c, r in surfaces))
    check("every wall makes a tile", all(scenes._wall_tile(w, 1, 0, 9).size == (scenes.T, scenes.T * scenes.WALL_ROWS) for w in cat["walls"]))
    for mood in cat["moods"]:
        scenes.render({"template": "street", "mood": mood})
    check("every mood renders", True)
    skill = (Path(__file__).resolve().parent.parent / "game" / ".claude" / "skills" / "stage" / "SKILL.md").read_text()
    missing = [n for n in (*cat["templates"], *cat["moods"]) if f"`{n}`" not in skill]
    check(f"the DM skill names every template and mood {missing}", not missing)
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
    check("the state keeps the roll", s["rolls"][-1]["total"] == 13 and s["rolls"][-1]["seq"] == 1)
    for _ in range(8):
        s = state.apply(s, {**e, "detail": {"kind": "check"}})
    check("the roll queue is short and keeps the detail", len(s["rolls"]) == state.ROLL_LIMIT and s["rolls"][-1]["detail"] == {"kind": "check"})

    print("agy hook payloads")
    check("agy PreInvocation means busy", hook.from_agy("PreInvocation", {})[0] == "UserPromptSubmit")
    check("agy Stop stays Stop when idle", hook.from_agy("Stop", {"fullyIdle": True})[0] == "Stop")
    check("agy Stop is ignored while not idle", hook.from_agy("Stop", {"fullyIdle": False})[0] == "")
    name, data = hook.from_agy("PreToolUse", {"toolCall": {"name": "run_command", "args": {"CommandLine": "uv run dnd-cli scene set x"}}})
    check("agy run_command reads as a Bash command",
          name == "PreToolUse" and hook.activity_label(data["tool_name"], data["tool_input"]) == "Painting the scene")


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

    # A home server: the owner names the hosts the browser may use (--allow-host).
    import asyncio

    from stage.server import LOCAL_HOSTS, LocalOnly

    pi = frozenset(LOCAL_HOSTS) | {"192.168.1.217", "pi.example.ts.net"}
    home = {"host": "192.168.1.217:3842"}
    check("an allowed host is accepted", request_allowed("http", "GET", home, pi))
    check("an allowed host is not accepted by default", not request_allowed("http", "GET", home))
    check("an allowed host is matched in any case", request_allowed("http", "GET", {"host": "PI.example.ts.net"}, pi))
    check("same-origin websocket on an allowed host is accepted",
          request_allowed("websocket", "GET", {**home, "origin": "http://192.168.1.217:3842"}, pi))
    check("an Origin from another allowed host is refused",
          not request_allowed("websocket", "GET", {**home, "origin": "http://pi.example.ts.net:3842"}, pi))
    check("a foreign Host is still refused with allowed hosts", not request_allowed("http", "GET", {"host": "evil.example:3842"}, pi))

    import socket

    from view import launch

    class Probe:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def connect(self, addr): self.addr = addr
        def getsockname(self): return ("192.168.1.50", 5555)

    real_socket, real_name = launch.socket.socket, launch.socket.gethostname
    launch.socket.socket, launch.socket.gethostname = Probe, lambda: "pi4"
    try:
        check("--lan allows the address, the name and the .local name", launch.lan_hosts() == ["192.168.1.50", "pi4", "pi4.local"])

        def no_route(*a):
            raise OSError("no route")
        Probe.connect = no_route
        check("--lan without a network route still allows the names", launch.lan_hosts() == ["pi4", "pi4.local"])
    finally:
        launch.socket.socket, launch.socket.gethostname = real_socket, real_name

    async def run_middleware(hosts, host):
        seen = []

        async def inner(scope, receive, send):
            seen.append(True)

        async def send(msg):
            seen.append(msg.get("status"))

        scope = {"type": "http", "method": "GET", "headers": [(b"host", host.encode())]}
        await LocalOnly(inner, hosts)(scope, None, send)
        return seen

    check("the middleware passes an allowed host", asyncio.run(run_middleware(pi, "192.168.1.217:3842")) == [True])
    check("the middleware answers 403 to a foreign host", asyncio.run(run_middleware(pi, "evil.example:3842")) == [403, None])


def _site(theme="dungeon", pois=(("altar", "far", "altar"),), seed=7, danger="none"):
    from stage import crawl

    spec = {"theme": theme, "size": "small", "seed": seed, "danger": danger}
    return crawl.generate(spec, [{"id": i, "where": w, "icon": c} for i, w, c in pois])


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
    for theme in crawl.themes():
        _site(theme, (("a", "far", "chest"),), 1)
        assert crawl.atlas_png(theme)
    check("every theme makes a site and an atlas", True)
    check("every icon is a tile", all(crawl.icon_png(name) for name in crawl.data()["icons"]))
    check("every icon word points at an icon", all(v in crawl.data()["icons"] for v in crawl.data()["icon_words"].values()))
    check("the same seed gives the same layout", _site(seed=3)["grid"] == _site(seed=3)["grid"])
    site = _site(pois=(("near-thing", "near", "chest"), ("far-thing", "far", "chest")))
    area = lambda pid: site["area_of"][site["pois"][pid]["y"]][site["pois"][pid]["x"]]  # noqa: E731
    depth = lambda pid: site["areas"][area(pid)]["depth"]  # noqa: E731
    check("a far POI is deeper than a near one", depth("far-thing") > depth("near-thing"))

    site = _site()
    crawl.arrive(site)
    check("arrival puts the party at the entrance", site["party"] == site["entrance"])
    view = crawl.view("crypt", site)
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
    check("a found POI is in the view", [p["id"] for p in crawl.view("crypt", site)["pois"]] == ["altar"])
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
        try:
            maps.place(c, "nope", "y", ["in=coast"])
        except maps.MapError as e:
            check("in= error says what in= is", "id of the parent map" in str(e) and "map place coast nope" in str(e))
        from dnd_cli.commands.map_cmd import _summary
        check("map show works on routes with no known key", "city - tower 2 days" in _summary("coast", maps.load(c, "coast"))
              and "city - lair 3 days hidden" in _summary("coast", maps.load(c, "coast")))
        maps.reveal(c, "coast", "lair")
        check("reveal shows the place and its route", "lair" in json.dumps(maps.view(maps.load(c, "coast"), "coast", None)))
        found = maps.all_maps(c)
        check("visit returns the map", maps.visit(c, found, "inn") == "city")
        place = {"map": "city", "place": "inn"}
        check("the level chain goes up", [l["id"] for l in maps.chain(found, None, place)] == ["city", "coast"])
        check("here on a parent map is the place that holds the party", maps.here(found, "coast", None, place) == "city")
        check("a site level sits on top of the chain", [l["id"] for l in maps.chain(found, "crypt", place)] == ["crypt", "city", "coast"])
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
    room = state.apply(state.apply(state.empty(), {"type": "scene", "location": "inn"}), {"type": "enter", "actor": "pc"})
    check("@scene of the same place keeps who is on stage",
          "pc" in state.apply(room, {"type": "scene", "location": "inn"})["actors"])
    check("@scene of a new place starts empty", not state.apply(room, {"type": "scene", "location": "road"})["actors"])

    import io, sys as _sys
    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp)
        maps.place(c, "city", "crypt", [])
        (c / "state.json").write_text('{"location": "somewhere"}')
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
        _sys.stdin = io.StringIO("@explore crypt stairs-down\n")
        show_cmd.execute_beat(str(c), None)
        _sys.stdin = _sys.__stdin__
        check("a resent beat is not shown twice", len(beat.log_path(c).read_text().splitlines()) == len(lines))
        check("state.json follows the map", json.loads((c / "state.json").read_text())["location"] == "Crypt, City")


def test_session_brief() -> None:
    print("session brief")
    from dnd_cli.commands.session_cmd import brief

    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp)
        (c / "characters").mkdir()
        (c / "players").mkdir()
        (c / "state.json").write_text('{"location": "Inn"}')
        (c / "characters" / "aria.json").write_text('{"name": "Aria", "class": "Fighter", "level": 2, "hp": {"current": 5, "max": 12, "temp": 0}}')
        text = brief(c)
        check("the brief has state, party and HP", '"location":"Inn"' in text and "Aria" in text and "HP 5/12" in text)
        check("the brief says what to do when canon or the story bible is missing",
              "canon init" in text and "Campaign Story Bible" in text)


def test_cli_defaults_and_races() -> None:
    print("cli defaults, races")
    import os
    from dnd_cli.__main__ import fill_defaults
    from stage import actors

    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp) / "camp"
        (c / "stage").mkdir(parents=True)
        (c / "canon.json").write_text('{"last_session_written": 4}')
        os.environ["DUNGEON_STAGE_LOG"] = str(c / "stage" / "events.ndjson")
        try:
            check("canon gets the stage campaign and the current session",
                  fill_defaults(["canon", "add-fact", "DM", "x"]) == ["canon", "add-fact", str(c), "5", "DM", "x"])
            check("character gets the stage campaign",
                  fill_defaults(["character", "heal", "sireth", "3"]) == ["character", "heal", str(c), "sireth", "3"])
            check("explicit arguments stay", fill_defaults(["canon", "show", str(c)]) == ["canon", "show", str(c)])
        finally:
            del os.environ["DUNGEON_STAGE_LOG"]
    drow = actors.build("x", ["race=drow", "eyes=green"], None)
    check("race= adds features; the DM's own settings win",
          drow["skin"] == "blue" and drow["eyes"] == "green" and "elven" in drow["items"])
    check("race heads follow the body", "heads_lizard_female" in actors.build("x", ["body=female"], None, "dragonborn")["items"])
    check("a sheet's race text maps to a race", actors.race_of("Drow (High Elf)") == "drow" and actors.race_of("Half-Elf") == "half-elf")


HOST_DEVICE = "host-device-0000000000"


async def call(app, method, target, body=None, device=HOST_DEVICE):
    """One request straight into the ASGI app (no httpx needed): (status, content type, bytes)."""
    path, _, query = target.partition("?")
    data = json.dumps(body).encode() if body is not None else b""
    headers = [(b"host", b"localhost"), (b"content-type", b"application/json")]
    if device:
        headers.append((b"x-device", device.encode()))
    scope = {"type": "http", "method": method, "path": path, "query_string": query.encode(), "headers": headers,
             "scheme": "http", "http_version": "1.1"}
    out = {"body": b""}
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            await asyncio.sleep(10)
        sent = True
        return {"type": "http.request", "body": data, "more_body": False}

    async def send(msg):
        if msg["type"] == "http.response.start":
            out["status"] = msg["status"]
            out["type"] = dict(msg["headers"]).get(b"content-type", b"").decode()
        else:
            out["body"] += msg.get("body", b"")
    await app(scope, receive, send)
    return out["status"], out["type"], out["body"]

async def api(app, method, target, body=None, device=HOST_DEVICE):
    status, _, raw = await call(app, method, target, body, device)
    return status, json.loads(raw)


def test_creator() -> None:
    print("creator: first prompt, snapshot, queue, routes")
    import asyncio
    import shutil
    import sys

    from dnd_cli.commands import rules_cmd
    from stage import server
    from stage.server import Stage, create_app, stage_first_prompt

    sys.path.insert(0, str(Path(__file__).parent))
    import test_creation as tc

    def camp(tmp, config=None, story=False, sheets=()):
        c = Path(tmp) / f"c{len(list(Path(tmp).iterdir()))}"
        (c / "characters").mkdir(parents=True)
        (c / "config.json").write_text(json.dumps(config or {}))
        (c / "state.json").write_text("{}")
        if story:
            (c / "dm_story.md").write_text("secret")
        for i in sheets:
            (c / "characters" / f"{i}.json").write_text("{}")
        return c

    with tempfile.TemporaryDirectory() as tmp:
        world = stage_first_prompt(camp(tmp, {"pitch": "Dwarf miners", "party": "create"}))
        check("no story bible: new world, no beat, no characters, no name, World ready",
              "worldbuilding" in world and "Dwarf miners" in world and "Show no beat" in world
              and "Make no characters" in world and "player name" in world and 'World ready.' in world)
        pre = stage_first_prompt(camp(tmp, {"pitch": "Karlach and Wyll, level 7", "party": "premade"}))
        check("premade: world, then the characters from the pitch", "Karlach and Wyll" in pre and "character new" in pre
              and "level-up" in pre and "--asi" in pre and "actor set" in pre and "World ready" not in pre
              and "do not run `canon init`" in pre and "race=drow" in pre and "world/" in pre)
        check("the story exists, no sheets: wait on the creation screen",
              "creation screen" in stage_first_prompt(camp(tmp, {"party": "create"}, story=True)))
        check("the story exists, premade, no sheets: the normal prompt",
              "session brief" in stage_first_prompt(camp(tmp, {"party": "premade"}, story=True)))
        normal = stage_first_prompt(camp(tmp, {}, story=True, sheets=["a"]))
        check("the story and a sheet: the normal prompt", "session brief" in normal and "show beat" in normal)
        check("every prompt is one paragraph", all("\n" not in x for x in (world, pre, normal)))

        c = camp(tmp, {"party": "create"})
        st = Stage(c, ["cat"])
        snap = lambda: st.snapshot()["state"]
        check("no sheets: creating, party_mode create", snap()["creating"] is True and snap()["party_mode"] == "create")
        (c / "characters" / "a.json").write_text("{}")
        check("the first sheet does not close the creator", snap()["creating"] is True)
        st.close_creator()
        check("done: one prompt for the first party", snap()["creating"] is False and len(st.pending) == 1
              and "first beat" in st.pending.pop())
        check("a restart with a sheet: not creating", Stage(c, ["cat"]).snapshot()["state"]["creating"] is False)
        st.open_creator()
        check("opened: creating", snap()["creating"] is True)
        st.close_creator()
        check("no new character: no prompt", st.pending == [] and snap()["creating"] is False)
        (c / "characters" / "b.json").write_text("{}")
        st.open_creator()
        (c / "characters" / "c.json").write_text("{}")
        st.close_creator()
        check("a joiner: one prompt, new id only, level-up", len(st.pending) == 1 and "`c`" in st.pending[0]
              and "`b`" not in st.pending[0] and "level-up" in st.pending[0] and "\n" not in st.pending[0])
        c2 = camp(tmp, {"party": "create"})
        st2 = Stage(c2, ["cat"])
        (c2 / "characters" / "x.json").write_text("{}")
        st2.close_creator()
        check("first party: open the first scene", "first beat" in st2.pending[0] and "level-up" not in st2.pending[0])
        c3 = camp(tmp, {"party": "create"})
        (c3 / "stage" / "scenes").mkdir(parents=True)
        (c3 / "stage" / "scenes" / "old.json").write_text("{}")
        time.sleep(0.02)
        (c3 / "stage" / "scenes" / "start.json").write_text("{}")
        st3 = Stage(c3, ["cat"])
        (c3 / "characters" / "x.json").write_text("{}")
        st3.close_creator()
        st3.fold(st3.read_new_events())
        check("Begin shows the newest scene with the party at once",
              st3.state["scene"] == "start" and "x" in st3.state["actors"])
        st3.open_creator()
        (c3 / "characters" / "y.json").write_text("{}")
        before = st3.log_path.read_text()
        st3.close_creator()
        check("a joiner does not reset the scene", st3.log_path.read_text() == before)
        pm = Stage(camp(tmp, {"party": "premade"}), ["cat"])
        check("premade with no sheets: not creating", pm.snapshot()["state"]["creating"] is False
              and pm.snapshot()["state"]["party_mode"] == "premade")

        async def queue():
            q = Stage(camp(tmp), ["cat"])
            sent = []

            async def fake(text):
                sent.append(text)
                q.state["dm"] = {"status": "busy"}
            q.submit = fake
            q.pending = ["one", "two"]
            q.state["dm"] = {"status": "busy"}
            task = asyncio.ensure_future(q.tail())
            await asyncio.sleep(0.4)
            check("the queue waits while the DM is busy", sent == [])
            q.state["dm"] = {"status": "idle"}
            await asyncio.sleep(0.4)
            check("one prompt per idle, never two at once", sent == ["one"])
            q.state["dm"] = {"status": "idle"}
            await asyncio.sleep(0.4)
            task.cancel()
            check("the next prompt follows the next idle", sent == ["one", "two"] and q.pending == [])
        asyncio.run(queue())

        async def routes():
            saved = rules_cmd._api
            try:
                rules_cmd._api = lambda ep: (_ for _ in ()).throw(tc.combat.RulesError("down"))
                app = create_app(None)
                await app.state.table.start(camp(tmp, {"party": "create"}), ["cat"])
                status, r = await api(app, "GET", "/api/creation/options")
                check("options: 503 with the message when the API is down", status == 503 and "cannot be reached" in r["error"])
                await app.state.table.stop()
                rules_cmd._api = tc.fetch
                c = camp(tmp, {"party": "create"})
                app = create_app(None)
                stage = await app.state.table.start(c, ["cat"])
                await api(app, "GET", "/api/me")  # the first device is the host
                status, r = await api(app, "GET", "/api/creation/options")
                check("options: served and memoized", status == 200 and r["classes"][0]["index"] == "fighter")
                look = {"race": "elf", "body": "female", "skin": "light", "eyes": "green", "hair": "hair_long:blonde"}
                body = {"player_name": "Cyrus", "name": "Lyra Moon", "race": "elf", "subrace": "", "class": "fighter",
                        "background": "acolyte", "background_skills": [], "scores": [15, 14, 13, 12, 10, 8],
                        "assign": ["str", "dex", "con", "int", "wis", "cha"], "bonus_abilities": [],
                        "skills": ["athletics", "survival"], "cantrips": [], "spells": [],
                        "equipment": ["longsword", "longsword", "shield", "explorers-pack"], "alignment": "Neutral Good",
                        "personality_traits": "Calm", "ideals": "Truth", "bonds": "Home", "flaws": "Proud",
                        "backstory": "Born far away.", "hooks": {"past": "the old mentor", "problem": "a debt"}, "look": look}
                post = lambda path, b: api(app, "POST", path, b)
                status, r = await post("/api/creation/character", body)
                check("character: id and lines", status == 200 and r["id"] == "lyra-moon"
                      and r["lines"][0].startswith("Lyra Moon: Elf Fighter 1") and len(r["lines"]) == 1)
                sheet = json.loads((c / "characters" / "lyra-moon.json").read_text())
                inv = {i["name"]: i["quantity"] for i in sheet["inventory"]}
                check("sheet: story fields, hooks, equipment quantity",
                      sheet["bonds"] == "Home" and sheet["backstory"] == "Born far away." and sheet["hooks"]["past"] == "the old mentor"
                      and inv["Longsword"] == 2)
                spec = json.loads((c / "stage" / "actors" / "lyra-moon.json").read_text())
                check("the look is saved: race, picks, class outfit",
                      spec["body"] == "female" and spec["eyes"] == "green" and "hair_long:blonde" in spec["items"]
                      and "elven" in spec["items"] and "chainmail" in spec["items"] and spec["name"] == "Lyra Moon")
                check("player file and party", (c / "players" / "cyrus.json").exists()
                      and "lyra-moon" in json.loads((c / "state.json").read_text())["party_members"])
                check("the stage hears about the look", "actor_updated" in (c / "stage" / "events.ndjson").read_text())
                status, r = await post("/api/creation/character", body)
                check("a second character of the same name gets -2", r["id"] == "lyra-moon-2")
                (c / "stage" / "actors" / "npc-zed.json").write_text('{"name": "Zed", "body": "male", "items": []}')
                status, r = await post("/api/creation/character", {**body, "name": "Npc Zed"})
                check("an id taken by an NPC look gets -2", status == 200 and r["id"] == "npc-zed-2")
                status, r = await post("/api/creation/character", {**body, "name": "Bad", "skills": ["athletics"]})
                check("a bad choice is 400 and writes nothing", status == 400 and "picks 2" in r["error"]
                      and not (c / "characters" / "bad.json").exists())
                status, r = await post("/api/creation/character", {**body, "name": "Hal", "race": "half-elf",
                                                                   "bonus_abilities": ["strength", "constitution"]})
                check("full-name bonus abilities work", status == 200)
                status, r = await post("/api/creation/character", {**body, "name": "Odd", "look": {**look, "race": "ent"}})
                check("a bad look is 400 and writes nothing", status == 400 and not (c / "characters" / "odd.json").exists())
                stage.seen_ids = []
                status, r = await post("/api/creation/done", {})
                check("done: creating false, one prompt", r == {"ok": True} and len(stage.pending) == 1
                      and "lyra-moon" in stage.pending[0])
                status, r = await post("/api/creation/open", {})
                check("open: creating true", r == {"ok": True} and stage.snapshot()["state"]["creating"] is True)
                q = "race=elf&body=female&skin=light&eyes=green&hair=hair_long:blonde&class=wizard"
                status, kind, png = await call(app, "GET", f"/asset/look.png?{q}")
                check("look preview is a PNG and saves nothing", status == 200 and png[:4] == b"\x89PNG"
                      and not (c / "stage" / "actors" / "preview.json").exists())
                check("look preview 404 for an unknown race", (await call(app, "GET", "/asset/look.png?race=ent"))[0] == 404)
                status, r = await api(app, "POST", "/api/game/start", {"new_name": "x", "party": "premade"})
                check("game start: premade needs a pitch", status == 400)
                await app.state.table.stop()
            finally:
                rules_cmd._api = saved
        asyncio.run(routes())


def test_seats() -> None:
    print("seats and host: who may do what")

    import asyncio
    import shutil
    import subprocess

    from dnd_cli import character, combat
    from stage.seats import SeatError, Seats, sid
    from stage.server import create_app

    seats = Seats()
    check("no host at first", not seats.is_host("a" * 16))
    check("the first device to ask is the host", seats.ensure_host("a" * 16) and not seats.ensure_host("b" * 16))
    seats.claim("a" * 16, "aragorn", "Alex")
    check("a seat is taken", seats.owns("a" * 16, "aragorn") and not seats.owns("b" * 16, "aragorn"))
    check("a second device cannot take it", raises(lambda: seats.claim("b" * 16, "aragorn", "Sam"), SeatError))
    check("one device may hold two seats", seats.claim("a" * 16, "legolas") is None and seats.mine("a" * 16) == ["aragorn", "legolas"])
    check("a device cannot free another's seat", raises(lambda: seats.release("b" * 16, "aragorn"), SeatError))
    seats.claim("b" * 16, "gimli", "Sam")
    seats.release("a" * 16, "gimli")  # the host frees a seat
    check("the host frees any seat", "gimli" not in seats.owners)
    seats.set_away("a" * 16, "aragorn", True)
    check("away is kept, and cleared with the seat", seats.public()["seats"][0]["away"] is True)
    seats.release("a" * 16, "aragorn")
    check("a freed seat is not away", "aragorn" not in seats.away)
    check("the public view has no device token", "a" * 16 not in json.dumps(seats.public()) and sid("a" * 16) == seats.public()["host"])
    check("a wrong host code is refused", raises(lambda: seats.take_host("b" * 16, "WXYZ" if seats.code != "WXYZ" else "ABCD"), SeatError))
    old = seats.code
    seats.take_host("b" * 16, old.lower())
    check("the right code gives the host over, once", seats.is_host("b" * 16) and seats.code != old)

    import stage.seats as seats_module

    now = [1000.0]
    real_time, seats_module.time = seats_module.time, type("T", (), {"monotonic": staticmethod(lambda: now[0])})
    try:
        locked = Seats()
        locked.ensure_host("a" * 16)
        for _ in range(5):
            raises(lambda: locked.take_host("b" * 16, "????"), SeatError)
        good = locked.code
        check("five wrong codes lock the door, even for the right code", raises(lambda: locked.take_host("b" * 16, good), SeatError) and locked.is_host("a" * 16))
        now[0] += 61
        locked.take_host("b" * 16, good)
        check("the door opens again after a minute", locked.is_host("b" * 16))
    finally:
        seats_module.time = real_time

    with tempfile.TemporaryDirectory() as tmp:
        c = fixture_campaign(tmp)
        st = combat.load_state(c)
        st["active_encounter"] = {"type": "combat", "round": 1, "participants": ["aragorn", "legolas"], "current_turn": "aragorn",
                                  "initiative_order": [{"name": "aragorn", "initiative": 15, "bonus": 1}, {"name": "legolas", "initiative": 5, "bonus": 3}],
                                  "conditions": {}, "monsters": {}}
        combat.save_state(c, st)
        A, B, G = "device-alex-00000000", "device-sam-000000000", "device-guest-0000000"

        async def routes():
            app = create_app(None)
            stage = await app.state.table.start(c, ["cat"])
            sent = []

            async def fake(text):
                sent.append(text)
            stage.submit = fake
            stage.state["dm"] = {"status": "idle"}
            get = lambda path, d=A: api(app, "GET", path, device=d)

            def set_turn(cid):
                st = combat.load_state(c)
                st["active_encounter"]["current_turn"] = cid
                combat.save_state(c, st)
            post = lambda path, b, d=A: api(app, "POST", path, b, device=d)

            status, r = await api(app, "GET", "/api/me", device=None)
            check("no device id: refused", status == 403)
            status, r = await api(app, "GET", "/api/me", device="short")
            check("a bad device id: refused", status == 403)
            status, r = await get("/api/me")
            check("the first device is the host and sees the code", status == 200 and r["host"] and len(r["host_code"]) == 4)
            code = r["host_code"]
            status, r = await get("/api/me", B)
            check("the second device is a guest with no code", not r["host"] and r["host_code"] is None and r["sid"] == sid(B))
            check("the snapshot names the host by sid, not by token",
                  stage.snapshot()["state"]["host"] == sid(A) and A not in json.dumps(stage.snapshot()))

            status, r = await post("/api/action", {"who": "aragorn", "action": "dash"})
            check("no seat: no action", status == 403)
            status, r = await post("/api/seat/claim", {"who": "aragorn", "name": "Alex"})
            check("a seat is claimed", status == 200 and stage.seats.owns(A, "aragorn"))
            status, r = await post("/api/seat/claim", {"who": "aragorn", "name": "Sam"}, B)
            check("a taken seat is refused", status == 403 and "Alex" in r["error"])
            status, r = await post("/api/seat/claim", {"who": "../x"}, B)
            check("a seat for no character is 404", status == 404)
            status, r = await post("/api/action", {"who": "aragorn", "action": "dash"}, B)
            check("another player cannot act for the character", status == 403 and not sent)
            status, r = await post("/api/end-turn", {"who": "aragorn"}, B)
            check("another player cannot end the turn", status == 403)
            status, r = await post("/api/resource", {"who": "aragorn", "name": "Second Wind"}, B)
            check("another player cannot spend a resource", status == 403)
            status, r = await post("/api/effects", {"who": "aragorn", "from": "aragorn", "effect": "bless"}, B)
            check("another player cannot cast for the owner", status == 403)
            status, r = await post("/api/action", {"who": "aragorn", "action": "dash"})
            check("the owner acts", status == 200 and sent)

            status, r = await post("/api/input", {"text": "I open the door"}, G)
            check("a guest with no seat cannot talk to the DM", status == 403)
            sent.clear()
            await post("/api/input", {"text": "I open the door"})
            check("a player's line is tagged with player and character", sent == ["[Alex as Aragorn] I open the door"])
            sent.clear()
            await post("/api/seat/claim", {"who": "legolas", "name": "Alex"})
            set_turn("legolas")
            status, r = await post("/api/input", {"text": "hi", "who": "gimli"})
            check("a line for a character that is not yours is refused", status == 403)
            status, r = await post("/api/input", {"text": "hi", "who": "legolas"})
            check("with two seats the player says which one", status == 200 and sent == ["[Alex as Legolas] hi"])
            await post("/api/seat/release", {"who": "legolas"})

            for path in ("/api/game/save", "/api/restart", "/api/game/quit"):
                status, r = await post(path, {}, B)
                check(f"a guest cannot use {path}", status == 403)
            status, r = await post("/api/game/start", {"campaign": "x"}, B)
            check("a guest cannot start another game", status == 403)
            status, r = await post("/api/settings", {"agent_framework": "claude"}, B)
            check("a guest cannot change settings", status == 403)
            status, r = await post("/api/campaign/delete", {"campaign": "x"}, B)
            check("a guest cannot delete a campaign", status == 403)
            status, r = await post("/api/game/load", {"campaign": "x", "save": "y"}, B)
            check("a guest cannot load a save", status == 403)
            status, r = await post("/api/creation/done", {}, B)
            check("a guest cannot close another's creator", status == 403)
            status, r = await post("/api/site/x/move", {"dir": "n"}, G)
            check("a guest with no seat cannot walk the party", status == 403)
            status, r = await post("/api/map/travel", {"map": "x", "to": "y"}, G)
            check("a guest with no seat cannot travel", status == 403)

            async def socket(path, device):
                """Open a websocket straight on the app; the messages the server sent."""
                sent_msgs = []
                inbox = [{"type": "websocket.connect"}]

                async def receive():
                    if inbox:
                        return inbox.pop(0)
                    return {"type": "websocket.disconnect", "code": 1000}

                async def send(msg):
                    sent_msgs.append(msg)
                scope = {"type": "websocket", "path": path, "query_string": f"d={device}".encode(), "scheme": "ws",
                         "headers": [(b"host", b"localhost")], "subprotocols": []}
                await app(scope, receive, send)
                return sent_msgs
            closed = [m for m in await socket("/ws/pty", B) if m["type"] == "websocket.close"]
            check("a guest's console socket is closed (1008)", closed and closed[0]["code"] == 1008)
            check("the host's console socket stays open", not [m for m in await socket("/ws/pty", A) if m["type"] == "websocket.close" and m.get("code") == 1008])
            status, r = await post("/api/host/claim", {"code": "ZZZZ" if code != "ZZZZ" else "AAAA"}, B)
            check("a wrong host code is refused", status == 403 and stage.seats.is_host(A))
            status, r = await post("/api/host/claim", {"code": code}, B)
            check("the table screen takes the host with the code", status == 200 and stage.seats.is_host(B) and not stage.seats.is_host(A))
            status, r = await post("/api/game/save", {}, A)
            check("the old host is a guest now", status == 403)
            status, r = await post("/api/seat/release", {"who": "aragorn"}, B)
            check("the new host frees a seat", status == 200 and not stage.seats.owns(A, "aragorn"))
            status, r = await post("/api/action", {"who": "aragorn", "action": "dash"}, B)
            check("the host has no seat by being host", status == 403)

            status, r = await post("/api/seat/claim", {"who": "aragorn", "name": "Sam"}, B)
            status, r = await post("/api/seat/away", {"who": "aragorn", "away": True}, G)
            check("only the owner or host sets away", status == 403)
            status, r = await post("/api/seat/away", {"who": "aragorn", "away": True}, B)
            check("away shows to everyone", status == 200 and stage.snapshot()["state"]["seats"][0]["away"] is True)
            status, r = await post("/api/creation/open", {}, B)
            check("the host opens the creator", status == 200 and stage.creator == B)
            status, r = await post("/api/creation/open", {}, A)
            check("a second device cannot open it over the first", status == 409 and stage.creator == B)
            status, r = await post("/api/creation/done", {}, A)
            check("and cannot close it", status == 403)
            status, r = await post("/api/creation/done", {}, B)
            check("the opener closes it", status == 200 and not stage.opened and stage.creator is None)
            await post("/api/creation/open", {}, A)
            status, r = await post("/api/creation/open", {}, B)
            check("the host cannot open it over a player either", status == 409 and stage.creator == A)
            status, r = await post("/api/creation/done", {}, B)
            check("but the host can close a creator that a dead phone left open", status == 200 and not stage.opened)

            sent.clear()
            await post("/api/input", {"text": "End the session now", "as_host": True}, B)
            check("a host control reaches the DM untagged", sent == ["End the session now"])
            sent.clear()
            await post("/api/input", {"text": "hello", "as_host": True}, A)
            check("a guest cannot send untagged lines", sent == [])
            await post("/api/seat/claim", {"who": "legolas", "name": "Alex"}, A)
            set_turn("legolas")
            await post("/api/input", {"text": "hello", "as_host": True}, A)
            check("as_host from a non-host stays tagged", sent == ["[Alex as Legolas] hello"])
            await app.state.table.stop()
        asyncio.run(routes())


def test_table_talk() -> None:
    print("several players: whispers, awaited answers, turn rules")
    import asyncio
    import shutil
    import subprocess

    from dnd_cli import combat
    from stage.server import create_app

    check("@whisper parses and continues on the next line", beat.parse("@whisper cassara A key.\nIt bears your sigil.") == [
        {"type": "whisper", "who": "cassara", "text": "A key. It bears your sigil."}])
    check("@choices-for names the player character", beat.parse("@choices-for sireth Grab it | Leave it") == [
        {"type": "choices", "who": "sireth", "options": ["Grab it", "Leave it"]}])
    check("@await takes all or a character", [e["who"] for e in beat.parse("@await all\n@await sireth")] == ["all", "sireth"])
    check("bad table-talk lines are refused", all(raises(lambda t=t: beat.parse(t)) for t in (
        "@whisper cassara", "@whisper", "@choices-for sireth One", "@choices-for", "@await")))
    s = state.apply(state.empty(), {"type": "whisper", "who": "cassara", "text": "A key."})
    check("a whisper is private state, not log", s["private"] == [{"who": "cassara", "text": "A key.", "seq": 1}] and s["log"] == [])
    s = state.apply(s, {"type": "await", "who": "all"})
    check("an await survives a busy DM and a whisper", s["await"]["who"] == "all"
          and state.apply(s, {"type": "dm_status", "status": "busy"})["await"] is not None
          and state.apply(s, {"type": "whisper", "who": "x", "text": "y"})["await"] is not None)
    check("the DM's story, or the answers going out, end the await", all(state.apply(s, e)["await"] is None for e in (
        {"type": "narrate", "text": "x"}, {"type": "say", "actor": "a", "text": "x"}, {"type": "scene", "location": "x"}, {"type": "await_done"})))
    check("an await at the end of a beat stays", [state.apply(state.empty(), e) for e in beat.parse("@narrate Hi\n@await all")][-1]["await"] is not None
          and state.apply(state.apply(state.empty(), {"type": "narrate", "text": "Hi"}), {"type": "await", "who": "all"})["await"]["who"] == "all")
    check("targeted choices keep who", state.apply(state.empty(), {"type": "choices", "who": "sireth", "options": ["a", "b"]})["choices"]["who"] == "sireth")

    with tempfile.TemporaryDirectory() as tmp:
        c = fixture_campaign(tmp)
        A, B, G = "device-alex-00000000", "device-sam-000000000", "device-guest-0000000"

        async def routes():
            app = create_app(None)
            stage = await app.state.table.start(c, ["cat"])
            sent = []

            async def fake(text):
                sent.append(text)
            stage.submit = fake
            post = lambda path, b, d=A: api(app, "POST", path, b, device=d)
            await api(app, "GET", "/api/me", device=A)  # A is the host
            stage.seats.claim(A, "aragorn", "Alex")
            stage.seats.claim(B, "legolas", "Sam")
            idle = lambda: stage.fold([{"type": "dm_status", "status": "idle"}])
            busy = lambda: stage.fold([{"type": "dm_status", "status": "busy"}])
            idle()

            stage.fold([{"type": "whisper", "who": "legolas", "text": "A key."},
                        {"type": "choices", "who": "legolas", "options": ["Take", "Leave"]},
                        {"type": "dm_status", "status": "idle", "dm_text": "secret DM notes"}])
            a, b, nobody = (stage.snapshot(d)["state"] for d in (A, B, None))
            check("a whisper reaches only its player", b["private"][0]["text"] == "A key." and a["private"] == [] and nobody["private"] == [])
            check("targeted choices reach only their player", b["choices"]["options"] == ["Take", "Leave"] and a["choices"] is None and nobody["choices"] is None)
            check("the DM's log reaches only the host", a["dm_log"] == ["secret DM notes"] and b["dm_log"] == [] and nobody["dm_log"] == [])
            check("the public log holds no whisper", all("key" not in json.dumps(x).lower() for x in (a["log"], b["log"])))

            stage.fold([{"type": "await", "who": "all"}])
            status, r = await post("/api/input", {"text": "I search"}, B)
            check("an answer is held while others are awaited", status == 200 and r.get("queued") and sent == [])
            aw = stage.snapshot(A)["state"]["awaiting"]
            check("everyone sees who answered, not what", aw == {"who": "all", "waiting": ["aragorn"], "answered": ["legolas"]}
                  and "I search" not in json.dumps(stage.snapshot(A)))
            await post("/api/input", {"text": "I guard"}, A)
            check("the last answer sends one prompt with both players", len(sent) == 1 and "answer together" in sent[0]
                  and "[Sam as Legolas] I search" in sent[0] and "[Alex as Aragorn] I guard" in sent[0] and not stage.intents)
            check("the await ends when the answers go out", stage.snapshot(A)["state"]["awaiting"] is None)
            busy()

            sent.clear(); idle()
            stage.fold([{"type": "await", "who": "all"}])
            await post("/api/input", {"text": "I wait"}, B)
            status, r = await post("/api/send-now", {}, G)
            check("a guest cannot force the answers", status == 403)
            status, r = await post("/api/send-now", {}, A)
            check("the host sends what was collected", status == 200 and len(sent) == 1 and "[Sam as Legolas] I wait" in sent[0] and "Alex" not in sent[0])
            idle()
            status, r = await post("/api/send-now", {}, A)
            check("nothing to send is refused", status == 409)

            sent.clear()
            stage.fold([{"type": "await", "who": "all"}])
            await post("/api/input", {"text": "I scout"}, B)
            await post("/api/seat/away", {"who": "aragorn", "away": True}, A)
            check("an away player is not awaited: the last answer goes out", len(sent) == 1 and "[Sam as Legolas] I scout" in sent[0]
                  and "Away, skip their turns: Aragorn" in sent[0])
            await post("/api/seat/away", {"who": "aragorn", "away": False}, A)
            busy(); idle()

            sent.clear()
            stage.fold([{"type": "await", "who": "all"}])
            await post("/api/input", {"text": "I hold"}, B)
            status, r = await post("/api/input", {"text": "psst", "whisper": True}, B)
            check("a whisper under an awaited round goes out, and keeps the answers held",
                  status == 200 and sent == ["[Sam as Legolas, private] psst"] and stage.intents == {"legolas": "I hold"})
            busy(); idle()
            check("the DM going busy and idle keeps the await and the held answer", stage.state["await"] is not None and stage.intents == {"legolas": "I hold"})
            sent.clear()
            await post("/api/input", {"text": "I guard"}, A)
            check("then the last answer sends both together", len(sent) == 1 and "I hold" in sent[0] and "I guard" in sent[0])
            stage.fold([{"type": "narrate", "text": "The door opens."}])
            idle()

            stage.seats.owners["aragorn"] = B  # solo: one device plays both characters
            sent.clear()
            stage.fold([{"type": "await", "who": "all"}])
            await post("/api/input", {"text": "we go in", "who": "legolas"}, B)
            check("one device with two seats answers once", len(sent) == 1 and "[Sam as Legolas] we go in" in sent[0]
                  and stage.snapshot(B)["state"]["awaiting"] is None)
            stage.seats.owners["aragorn"] = A
            stage.fold([{"type": "narrate", "text": "x"}])
            idle()

            stage.seats.claim(G, "gimli", "Gus")
            stage.fold([{"type": "await", "who": "gimli"}])
            stage.seats.release(G, "gimli")
            sent.clear()
            status, r = await post("/api/input", {"text": "free"}, B)
            check("an awaited character nobody plays locks no one out", status == 200 and sent == ["[Sam as Legolas] free"])
            stage.fold([{"type": "narrate", "text": "x"}])

            sent.clear()
            stage.fold([{"type": "await", "who": "aragorn"}])
            status, r = await post("/api/input", {"text": "me first"}, B)
            check("only the awaited player may answer", status == 409 and "waits for Aragorn" in r["error"] and sent == [])
            status, r = await post("/api/input", {"text": "psst", "whisper": True}, B)
            check("a whisper to the DM is always allowed", status == 200 and sent == ["[Sam as Legolas, private] psst"])
            status, r = await post("/api/input", {"text": "my answer"}, A)
            check("the awaited player answers at once, tagged", status == 200 and sent[-1] == "[Alex as Aragorn] my answer"
                  and stage.state["await"] is None)
            busy(); idle()

            stage.state["dm"] = {"status": "busy"}
            status, r = await post("/api/input", {"text": "now?"}, A)
            check("a busy DM refuses a line", status == 409)
            idle()

            st = combat.load_state(c)
            st["active_encounter"] = {"type": "combat", "round": 1, "participants": ["aragorn", "legolas"], "current_turn": "aragorn",
                                      "initiative_order": [{"name": "aragorn", "initiative": 15, "bonus": 1}, {"name": "legolas", "initiative": 5, "bonus": 3}],
                                      "conditions": {}, "monsters": {}}
            combat.save_state(c, st)
            sent.clear()
            status, r = await post("/api/input", {"text": "I shoot"}, B)
            check("in a combat only the player on turn may speak", status == 409 and "Aragorn's turn" in r["error"])
            status, r = await post("/api/input", {"text": "psst", "whisper": True}, B)
            check("but anyone may whisper to the DM", status == 200)
            status, r = await post("/api/input", {"text": "I swing"}, A)
            check("the player on turn speaks", status == 200 and sent[-1] == "[Alex as Aragorn] I swing")

            await post("/api/seat/away", {"who": "legolas", "away": True}, B)
            sent.clear()
            status, r = await post("/api/end-turn", {"who": "aragorn"}, A)
            check("an away player's turn is skipped", status == 200 and any("Legolas is away" in x for x in r["lines"])
                  and combat.load_state(c)["active_encounter"]["current_turn"] == "aragorn" and "Away, skip their turns: Legolas" in sent[-1])
            await app.state.table.stop()
        asyncio.run(routes())


def test_activity() -> None:
    print("dm activity feed")
    import hook, io, os, sys as _sys
    label = hook.activity_label
    check("skills", label("Skill", {"skill": "worldbuilding"}) == "Studying the art of worldbuilding"
          and label("Skill", {"skill": "stage"}) == "Rehearsing the stagecraft"
          and label("Skill", {"skill": "character-creation"}) == "Opening the rulebooks"
          and label("Skill", {"skill": "combat"}) is None)
    check("files", label("Write", {"file_path": "/g/campaigns/x/dm_story.md"}) == "Writing the story bible"
          and label("Edit", {"file_path": "/g/campaigns/x/world/locations/A.md"}) == "Writing the lore"
          and label("Write", {"file_path": "/tmp/x.py"}) is None)
    for cmd, want in [
        ("uv run dnd-cli session brief 2>&1 | head -50", "Reading the campaign notes"),
        ('uv run dnd-cli canon add-villain "The Envoy" "Recruit"', "Casting the villains"),
        ('uv run dnd-cli canon add-clock "The Envoy" "Gate" 6', "Winding the villain clocks"),
        ('uv run dnd-cli canon add-fact DM "A seal"', "Pinning down the facts"),
        ('uv run dnd-cli canon touch-clock "Voss" "Leak"', "Pinning down the facts"),
        ("uv run dnd-cli scene set druid-clearing template=forest", "Painting the scene"),
        ("uv run dnd-cli map place underdark deepvale-settlement name=D", "Drawing the map"),
        ("uv run dnd-cli actor set minthara name=Minthara", "Dressing the cast"),
        ("uv run dnd-cli site set crypt theme=dungeon", "Digging the dungeon"),
        ("uv run dnd-cli character new menzoberranzan minthara --player cyrus", "Rolling up the party"),
        ("uv run dnd-cli character level-up menzoberranzan minthara", "Levelling the party"),
        ("uv run dnd-cli character show halsin", "Reading the character sheets"),
        ("uv run dnd-cli quest add x", "Weaving the plot threads"),
        ("uv run dnd-cli attack goblin", "Checking the rules"),
        ("uv run dnd-cli get races/elf --fields subraces", "Looking up the rules"),
        ("uv run dnd-cli search subraces --name drow", "Looking up the rules"),
        ("uv run dnd-cli session end --appeared x <<'EOF'", "Writing the session record"),
        ("dnd-cli state set location=x", None),
        ("uv run dnd-cli show beat <<'EOF'\n@scene x", None),
        ("uv run roll 1d20 -v", None),
        ("ls -la campaigns", None),
    ]:
        check(f"label: {cmd[:40]!r}", label("Bash", {"command": cmd}) == want)
    check("a label is short", all(len(v) <= 40 for v in list(hook.SKILLS.values()) + [x[1] for x in hook.CLI_LABELS]))

    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "events.ndjson"
        os.environ["DUNGEON_STAGE_LOG"] = str(log)
        try:
            for payload in [{"hook_event_name": "PreToolUse", "tool_name": "Skill", "tool_input": {"skill": "stage"}},
                            {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}}]:
                _sys.stdin = io.StringIO(json.dumps(payload))
                hook.main()
        finally:
            _sys.stdin = _sys.__stdin__
            del os.environ["DUNGEON_STAGE_LOG"]
        check("hook writes dm_activity, skips the trivial call",
              [json.loads(l) for l in log.read_text().splitlines()] == [{"type": "dm_activity", "text": "Rehearsing the stagecraft"}])

    s = state.empty()
    check("activity starts empty", s["activity"] == [])
    for t in ["a", "a", "b"]:
        s = state.apply(s, {"type": "dm_activity", "text": t})
    check("fold drops a consecutive duplicate", s["activity"] == ["a", "b"])
    for i in range(20):
        s = state.apply(s, {"type": "dm_activity", "text": str(i)})
    check("fold keeps the last 12", len(s["activity"]) == 12 and s["activity"][-1] == "19")
    check("busy keeps it", state.apply(s, {"type": "dm_status", "status": "busy"})["activity"] == s["activity"])
    check("idle clears it", state.apply(s, {"type": "dm_status", "status": "idle"})["activity"] == [])
    check("exited clears it", state.apply(s, {"type": "dm_status", "status": "exited"})["activity"] == [])


def test_party() -> None:
    print("the party comes with @scene")
    import io, sys as _sys
    from dnd_cli.commands import show_cmd

    def show(c: Path, text: str) -> list[dict]:
        time.sleep(0.01)  # a beat id is the millisecond: two beats in one tick would merge
        _sys.stdin = io.StringIO(text)
        try:
            show_cmd.execute_beat(str(c), None)
        finally:
            _sys.stdin = _sys.__stdin__
        return [json.loads(l) for l in beat.log_path(c).read_text().splitlines()]

    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp)
        (c / "characters").mkdir()
        for n in ("zed", "amy", "bob", "cat", "dan", "eve"):
            (c / "characters" / f"{n}.json").write_text("{}")
        lines = show(c, "@scene inn\n@narrate Hi.")
        check("no party_members: the sheets, sorted, max 4", lines[0]["party"] == ["amy", "bob", "cat", "dan"])
        (c / "state.json").write_text('{"party_members": ["zed", "amy"]}')
        lines = show(c, "@scene road")
        check("party_members wins", lines[-1]["party"] == ["zed", "amy"])
        n = len(show(c, "@scene road"))
        check("a resent beat is still caught", n == len(lines))
    with tempfile.TemporaryDirectory() as tmp:
        check("no party, no key", "party" not in show(Path(tmp), "@scene inn")[0])

    from stage import scenes as _scenes
    check("the loading room renders with every desk icon", _scenes.filler_png()[:4] == b"\x89PNG"
          and all((Path(__import__("stage.assets", fromlist=["x"]).ensure_dcss()) / "item" / p).exists()
                  for p, _, _ in _scenes.FILLER_STUFF))
    s = state.apply(state.empty(), {"type": "scene", "location": "inn", "party": ["zed", "amy"]})
    check("the state seeds the actors", s["actors"]["zed"]["position"] == "left" and s["actors"]["amy"]["position"] == "right")
    s2 = state.apply(s, {"type": "enter", "actor": "gareth"})
    check("an NPC takes the next free slot", s2["actors"]["gareth"]["position"] == "center")
    check("same room keeps who is there", state.apply(s2, {"type": "scene", "location": "inn", "party": ["zed", "amy"]})["actors"] == s2["actors"])
    check("@exit removes a PC", "zed" not in state.apply(s, {"type": "exit", "actor": "zed"})["actors"])
    check("@enter center moves a PC", state.apply(s, {"type": "enter", "actor": "zed", "position": "center"})["actors"]["zed"]["position"] == "center")
    check("an old event has no party", state.apply(state.empty(), {"type": "scene", "location": "inn"})["actors"] == {})


def test_player_actions() -> None:
    print("roll requests, party view, and the player's own actions")
    import asyncio
    import shutil
    import subprocess
    import sys

    from dnd_cli import character, combat, effects
    from stage import party
    from stage.server import create_app

    check("@roll parses", beat.parse("@roll sireth stealth dc 14") == [{"type": "roll_request", "who": "sireth", "what": "stealth", "dc": 14}])
    check("@roll can hide the DC", beat.parse("@roll sireth dex-save 13 hide")[0] == {
        "type": "roll_request", "who": "sireth", "what": "dex-save", "dc": 13, "hide": True})
    check("@roll needs a check", raises(lambda: beat.parse("@roll sireth")))
    check("@roll refuses an unknown word", raises(lambda: beat.parse("@roll sireth stealth easy")))
    s = state.apply(state.empty(), {"type": "roll_request", "who": "sireth", "what": "stealth", "dc": 14, "beat": "1"})
    check("the state holds the request, without the beat id", s["roll_request"] == {"who": "sireth", "what": "stealth", "dc": 14, "seq": 1})
    check("a roll, a narration or a new scene ends the request", all(
        state.apply(s, e)["roll_request"] is None for e in (
            {"type": "roll", "expr": "x", "total": 1, "dice": []}, {"type": "narrate", "text": "x"}, {"type": "scene", "location": "x"},
            {"type": "roll_done"})))
    check("a roll keeps the detail", state.apply(s, {"type": "roll", "expr": "x", "total": 1, "dice": [], "detail": {"kind": "check"}})["rolls"][-1]["detail"] == {"kind": "check"})

    with tempfile.TemporaryDirectory() as tmp:
        c = fixture_campaign(tmp)

        view = party.view(c)
        legolas = next(x for x in view["characters"] if x["id"] == "legolas")
        check("no combat: nothing used, no order", view["combat"] is None and not legolas["in_combat"]
              and legolas["turn"] == {"action": False, "bonus": False, "reaction": False})
        check("the card lists the common actions, with the reason one is off",
              {a["id"] for a in legolas["actions"]} >= {"attack", "dash", "disengage", "dodge", "help", "hide", "shove"}
              and next(a for a in legolas["actions"] if a["id"] == "attack")["why"] == "Only in a combat"
              and next(a for a in legolas["actions"] if a["id"] == "hide")["why"] is None)
        check("every character can punch, and the weapons come with their damage",
              [a["name"] for a in legolas["attacks"]][-1] == "Unarmed Strike")
        check("nobody in the party can give a bonus, so none is on offer", legolas["offers"] == [])
        check("the sheet's abilities, skills and slots reach the view",
              legolas["abilities"]["dexterity"]["mod"] == 3 and legolas["spell"]["slots"]["1"]["max"] == 3
              and next(k for k in legolas["skills"] if k["name"] == "Survival")["prof"] == 1)
        check("a ranger has no class resource at level 3; a fighter has", legolas["resources"] == [] and
              [r["name"] for r in next(x for x in view["characters"] if x["id"] == "aragorn")["resources"]] == ["Second Wind", "Action Surge"])
        check("the effect presets come with the view", {e["id"] for e in view["effects"]} >= {"guidance", "bless", "advantage"})

        st = combat.load_state(c)
        st["active_encounter"] = {"type": "combat", "round": 2, "participants": ["aragorn", "goblin#1", "legolas"], "current_turn": "aragorn",
                                  "initiative_order": [{"name": "aragorn", "initiative": 15, "bonus": 1}, {"name": "goblin#1", "initiative": 9, "bonus": 2},
                                                       {"name": "legolas", "initiative": 5, "bonus": 3}],
                                  "conditions": {"aragorn": [{"condition": "poisoned"}]}, "monsters": {"goblin#1": {"id": "goblin#1", "kind": "monster", "name": "Goblin", "hp": {"current": 7, "max": 7}, "ac": 15,
                                                                                         "mods": {}, "attacks": []}}}
        combat.spend_turn(st, "aragorn", "bonus")
        combat.save_state(c, st)
        view = party.view(c)
        aragorn = next(x for x in view["characters"] if x["id"] == "aragorn")
        check("combat: the order, the turn and what is used", view["combat"]["current"] == "aragorn"
              and view["combat"]["order"][1] == {"id": "goblin#1", "name": "Goblin 1", "initiative": 9, "pc": False,
                                                   "health": "unhurt", "conditions": []}
              and aragorn["turn"] == {"action": False, "bonus": True, "reaction": False} and aragorn["in_combat"]
              and aragorn["conditions"] == [{"name": "poisoned", "stance": False}])
        check("a monster's HP and AC never reach the view", "7" not in json.dumps(view["combat"]) and "\"ac\"" not in json.dumps(view["combat"])
              and "monsters" not in json.dumps(view))
        st["active_encounter"]["monsters"]["goblin#1"]["hp"]["current"] = 3
        combat.save_state(c, st)
        check("how hurt a creature is shows as a band: bloodied at half, near death at a quarter, down at 0",
              [party.view(c)["combat"]["order"][1]["health"]] == ["bloodied"] and all(
                  combat.health_band({"hp": {"current": cur, "max": 8}}) == band
                  for cur, band in ((8, "unhurt"), (7, "injured"), (4, "bloodied"), (2, "near death"), (0, "down"))))
        st["active_encounter"]["monsters"]["goblin#1"]["hp"]["current"] = 7
        combat.save_state(c, st)
        check("a new turn gives the actions back", combat.next_turn(c, st) and st["active_encounter"]["resources"]["goblin#1"] == {})

        async def routes():
            app = create_app(None)
            stage = await app.state.table.start(c, ["cat"])
            for who in ("aragorn", "legolas"):
                stage.seats.claim(HOST_DEVICE, who, "Alex")  # the test device plays both
            post = lambda path, b: api(app, "POST", path, b)
            stage.state["dm"] = {"status": "busy"}
            status, r = await post("/api/effects", {"who": "aragorn", "op": "add", "effect": "bless"})
            check("a busy DM refuses a change", status == 409)
            stage.state["dm"] = {"status": "idle"}
            status, r = await post("/api/effects", {"who": "aragorn", "effect": "bless"})
            check("a bonus nobody can give is refused", status == 400 and effects.active(c, "aragorn") == [])
            status, r = await post("/api/effects", {"who": "../x", "effect": "bless"})
            check("an unknown character is refused", status == 404)
            ranger = character.load(c, "legolas")
            ranger["spellcasting"]["spells_known"].append("Guidance")
            character.save(c, "legolas", ranger)
            status, r = await post("/api/effects", {"who": "aragorn", "from": "legolas", "effect": "guidance"})
            check("a caster cannot cast out of turn", status == 400 and effects.active(c, "aragorn") == [])
            sent = []

            async def fake(text):
                sent.append(text)
            stage.submit = fake
            status, r = await post("/api/turn", {"who": "aragorn", "kind": "action"})
            check("the used-or-free toggle is gone", status == 404)
            status, r = await post("/api/action", {"who": "aragorn", "action": "dash"})
            check("Dash is a condition for a round, spends the action, and the DM is told",
                  status == 200 and combat.load_state(c)["active_encounter"]["resources"]["aragorn"]["action"] is True
                  and any(x["condition"] == "dashing" for x in combat.load_state(c)["active_encounter"]["conditions"]["aragorn"])
                  and sent and "aragorn takes the Dash action" in sent[-1])
            status, r = await post("/api/action", {"who": "aragorn", "action": "dodge"})
            check("a spent action is refused", status == 400 and "used" in r["error"])
            status, r = await post("/api/action", {"who": "legolas", "action": "dash"})
            check("out of turn is refused", status == 400 and "not your turn" in r["error"])
            status, r = await post("/api/action", {"who": "aragorn", "action": "fly"})
            check("an unknown action is refused", status == 400)
            n = len(sent)
            st = combat.load_state(c)
            combat.spend_turn(st, "aragorn", "bonus", False)
            combat.save_state(c, st)
            stage.state["dm"] = {"status": "busy"}
            status, r = await post("/api/action", {"who": "aragorn", "action": "shove", "target": "goblin#1"})
            check("a busy DM refuses an action", status == 409)
            stage.state["dm"] = {"status": "idle"}
            status, r = await post("/api/action", {"who": "aragorn", "action": "shove", "target": "goblin#1"})
            req = stage.state["roll_request"] or {}
            check("Shove asks the player for an Athletics roll, and nothing goes to the DM yet",
                  status == 200 and req["what"] == "athletics" and req["title"] == "Shove" and req["hide"] and "goblin#1" in req["note"]
                  and "dc" not in stage.snapshot()["state"]["roll_request"] and len(sent) == n)
            status, r = await post("/api/roll", {})
            check("the roll tells the DM what it was for", status == 200 and "goblin#1" in sent[-1] and "Athletics" in sent[-1])
            status, r = await post("/api/end-turn", {"who": "legolas"})
            check("only the creature whose turn it is can end it", status == 400)
            status, r = await post("/api/end-turn", {"who": "aragorn"})
            check("End Turn moves the tracker and tells the DM to run the creature",
                  status == 200 and combat.load_state(c)["active_encounter"]["current_turn"] == "goblin#1"
                  and "ends their turn" in sent[-1] and "goblin#1's turn: run it" in sent[-1])
            check("a new turn has all three free", combat.load_state(c)["active_encounter"]["resources"]["goblin#1"] == {})
            st = combat.load_state(c)
            st["active_encounter"]["current_turn"] = "legolas"
            combat.save_state(c, st)
            status, r = await post("/api/effects", {"who": "aragorn", "from": "legolas", "effect": "guidance"})
            check("a caster on their turn gives a bonus and spends the action", status == 200 and effects.active(c, "aragorn") == ["guidance"]
                  and combat.load_state(c)["active_encounter"]["resources"]["legolas"]["action"] is True)
            effects.remove(c, "aragorn", "guidance")
            st["active_encounter"]["current_turn"] = "aragorn"
            combat.save_state(c, st)
            from test_rules import GOBLIN
            st = combat.load_state(c)
            st["active_encounter"]["monsters"]["goblin#1"] = combat.monster_record(GOBLIN, "goblin#1")
            combat.spend_turn(st, "aragorn", "action", False)
            combat.save_state(c, st)
            status, r = await post("/api/action", {"who": "aragorn", "action": "attack", "target": "goblin#1", "weapon": "Longsword"})
            check("an attack from the card tells the DM to describe the wound, with no numbers",
                  status == 200 and "goblin#1 now looks" in sent[-1] and "no numbers" in sent[-1]
                  and combat.load_state(c)["active_encounter"]["resources"]["aragorn"]["action"] is True)
            effects.add(c, "aragorn", "bless")  # the DM's own `effect add`
            status, r = await post("/api/resource", {"who": "aragorn", "name": "Second Wind"})
            check("a class resource is spent", status == 200 and json.loads((c / "characters" / "aragorn.json").read_text())["resources_used"] == {"Second Wind": 1})
            status, r = await post("/api/resource", {"who": "aragorn", "name": "Rage"})
            check("an unknown resource is refused", status == 400)

            status, r = await post("/api/roll", {})
            check("no request: no roll", status == 409)
            events = [{"type": "roll_request", "who": "aragorn", "what": "athletics", "dc": 14, "name": "Aragorn"}]
            beat.append(c, events)
            stage.fold(stage.read_new_events())
            status, r = await post("/api/roll", {"skip": ["bless"]})
            hidden = {"type": "roll_request", "who": "aragorn", "what": "athletics", "dc": 17, "hide": True, "name": "Aragorn"}
            stage.fold([hidden])
            check("a hidden DC is not in the snapshot, but the server still has it",
                  "dc" not in stage.snapshot()["state"]["roll_request"] and stage.state["roll_request"]["dc"] == 17)
            stage.fold([events[0]])
            check("the roll is made and the DM is told", status == 200 and sent and "Aragorn rolled" in sent[-1] and "Athletics" in sent[-1] and "vs DC 14" in sent[-1])
            stage.fold(stage.read_new_events())
            check("the stage shows the roll with its breakdown", stage.state["roll_request"] is None
                  and stage.state["rolls"][-1]["detail"]["rolls"][0]["who"] == "aragorn")
            check("an effect left off the roll is still there", effects.active(c, "aragorn") == ["bless"])
            status, r = await post("/api/roll", {})
            check("a second click rolls nothing", status == 409)
            status, r = await api(app, "GET", "/api/spell/..%2Fx")
            check("a bad spell index is refused", status == 404)
            await app.state.table.stop()
        asyncio.run(routes())


if __name__ == "__main__":
    test_parse()
    test_parse_errors()
    test_append()
    test_state()
    test_initial_prompt()
    test_actors()
    test_scenes()
    test_rolls()
    test_activity()
    test_party()
    test_player_actions()
    test_seats()
    test_table_talk()
    test_local_only()
    test_crawl()
    test_maps()
    test_explore_beat()
    test_session_brief()
    test_cli_defaults_and_races()
    test_creator()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
