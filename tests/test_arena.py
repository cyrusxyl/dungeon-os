"""Checks for the combat arena: the generator, the board geometry, and the props catalog.

Run from the repo root:  .venv/bin/python tests/test_arena.py

Plain asserts so no test runner is needed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dnd_cli import combat  # noqa: E402
from stage import arena, board, crawl, scenes, state as stage_state  # noqa: E402
from tests.test_rules import GOBLIN  # noqa: E402

PASS = FAIL = 0
BOARD_PROPS = ["barrel", "barrel_pile", "bush", "chair", "chests", "column_broken", "dresser", "hearth", "mushroom",
               "oak", "pine", "stones", "stool", "stump", "tree"]


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


def raises(fn) -> bool:
    try:
        fn()
    except arena.ArenaError:
        return True
    return False


def source(kind: str, **extra) -> dict:
    cfg = arena.arena_data()
    base = {"scene": {"kind": "scene", "id": "x", "look": arena.look_of("tavern"), "shell": "room", "layout": "open", "decor": "tavern",
                      "props": [("barrel_pile", "back_left"), ("stool", "mid_left"), ("hearth", "wall_center")]},
            "site": {"kind": "site", "id": "x", "look": arena.look_of("crypt"), "shell": "room", "layout": "pillars", "decor": "crypt"},
            "none": {"kind": "none", "id": None, "look": arena.look_of("forest"), "shell": "open", "layout": "open", "props": [],
                     "decor": "forest"}}[kind]
    assert cfg
    return {**base, **extra}


def test_geometry() -> None:
    print("arena: lines, cover, walking")
    wall = {(2, 0)}
    check("a wall between two cells blocks the line", not arena.clear_line((0, 0), (4, 0), wall))
    check("a wall off the line does not", arena.clear_line((0, 1), (4, 1), wall))
    check("the end cells never block their own line", arena.clear_line((0, 0), (2, 0), wall))
    cover = {(2, 0): "half", (3, 0): "three-quarters"}
    check("the best cover on the line counts", arena.cover_between((0, 0), (5, 0), cover) == "three-quarters")
    check("no cover off the line", arena.cover_between((0, 1), (5, 1), cover) == "none")
    dist, prev = arena.reach((0, 0), 3, {(1, 0), (0, 1)}, (4, 4))
    check("a diagonal step past two blocked side cells is not allowed", (1, 1) not in dist)
    dist, prev = arena.reach((0, 0), 2, set(), (5, 5))
    check("8 directions: two diagonal steps reach (2, 2)", dist.get((2, 2)) == 2 and arena.path_from(prev, (0, 0), (2, 2)) == [(1, 1), (2, 2)])
    dist, _ = arena.reach((0, 0), 5, set(), (5, 5), occupied={(1, 0), (0, 1), (1, 1)})
    check("occupied cells cannot be entered or passed", all(c not in dist for c in [(1, 0), (0, 1), (1, 1)]) and len(dist) == 1)
    check("cheb is the larger axis", arena.cheb((0, 0), (3, 2)) == 3)


def test_props() -> None:
    print("arena: prop catalog")
    check("each of the 15 board props has an entry", all("board" in scenes.catalog()["props"][p] for p in BOARD_PROPS))
    check("a tall prop blocks sight", arena.board_of("tree")["blocks_sight"] and arena.board_of("oak")["blocks_sight"])
    check("a barrel blocks movement, gives half cover, does not block sight",
          arena.board_of("barrel")["blocks_move"] and arena.board_of("barrel")["cover"] == "half" and not arena.board_of("barrel")["blocks_sight"])
    check("a bush does not block movement", not arena.board_of("bush")["blocks_move"])
    other = next(p for p in scenes.catalog()["props"] if p not in BOARD_PROPS)
    check("a prop without an entry blocks movement and gives no cover", arena.board_of(other) == arena.DEFAULT_BOARD)
    cfg = arena.arena_data()
    check("every scene template has a look, and each look is a theme",
          all(t in cfg["scene_looks"] for t in scenes.catalog()["templates"]) and all(v in arena.themes() for v in cfg["scene_looks"].values()))
    check("every decor prop has a board entry",
          all(p in BOARD_PROPS for d in cfg["decor"].values() for p in d["obstacles"] + d["cover"] + d["small"] + [d["pillar"]]))
    check("the forest theme has tiles", arena.atlas_png("forest") and arena.icon_png("lava") and arena.icon_png("water"))


def test_parse() -> None:
    print("arena: the DM's words")
    spec = arena.parse(["layout=chokepoint", "size=small", "light=dark", "ambush=yes", "seed=7", "feature=cover@foes", "hazard=lava@center"])
    check("tokens become a spec", spec["layout"] == "chokepoint" and spec["size"] == "small" and spec["light"] == "dark"
          and spec["ambush"] is True and spec["seed"] == 7 and spec["features"] == [["cover", "foes"]] and spec["hazards"] == [["lava", "center"]])
    check("a prop of the catalog is a feature", arena.parse(["feature=barrel@party"])["features"] == [["barrel", "party"]])
    for bad in ("layout=maze", "size=huge", "light=blind", "ambush=maybe", "seed=x", "theme=nope", "feature=cover", "feature=cover@moon",
                "feature=dragon@foes", "hazard=acid@foes", "colour=red", "layout"):
        check(f"{bad!r} is refused", raises(lambda b=bad: arena.parse([b])))


def test_generator() -> None:
    print("arena: generator")
    made, bad = 0, []
    for kind in ("scene", "site", "none"):
        for layout in arena.LAYOUTS:
            for size in arena.SIZES:
                for ambush in (False, True):
                    for edits in ([], ["feature=cover@foes", "feature=barrels@party", "feature=pillar@center", "hazard=lava@center"]):
                        for seed in range(1, 9):
                            spec = {**arena.parse(edits), "layout": layout, "size": size, "ambush": ambush, "seed": seed}
                            a = arena.generate(spec, source(kind), 3, 4)
                            made += 1
                            blocked = arena.blocked_cells(a)
                            starts = [tuple(p) for p in a["starts"]["party"] + a["starts"]["foes"]]
                            dist, _ = arena.reach(starts[0], 999, blocked, (a["w"], a["h"]))
                            ok = (len(a["starts"]["party"]) == 3 and len(a["starts"]["foes"]) == 4 and len(set(starts)) == 7
                                  and all(p in dist for p in starts) and not any(p in blocked for p in starts)
                                  and len(a["items"]) == 1 and (a["items"][0]["x"], a["items"][0]["y"]) not in blocked
                                  and len({(p["x"], p["y"]) for p in a["props"]}) == len(a["props"]))
                            if not ok:
                                bad.append((kind, layout, size, ambush, seed))
    check(f"{made} arenas: starts are free and connected, one item, no stacked props", not bad)
    spec = {**arena.parse(["feature=cover@foes"]), "seed": 5}
    check("the same seed makes the same arena", arena.generate(spec, source("scene")) == arena.generate(spec, source("scene")))
    check("another seed makes another arena", arena.generate({**spec, "seed": 6}, source("scene"))["grid"] != arena.generate(spec, source("scene"))["grid"]
          or arena.generate({**spec, "seed": 6}, source("scene"))["props"] != arena.generate(spec, source("scene"))["props"])
    a = arena.generate({**arena.parse(["hazard=lava@center"]), "seed": 3, "layout": "open"}, source("scene"))
    check("a hazard feature puts hazard tiles in the grid", any(arena.HAZARD in row for row in a["grid"]))
    a = arena.generate({"features": [], "hazards": [], "layout": "chasm", "seed": 4}, source("scene"))
    check("a chasm has hazard tiles and a bridge across", any(arena.HAZARD in row for row in a["grid"]))
    a = arena.generate({"features": [], "hazards": [], "seed": 4}, source("scene"))
    check("a scene prop lands in the arena by its zone, a wall prop does not", any(p["kind"] == "barrel_pile" for p in a["props"]) and not any(p["kind"] == "hearth" for p in a["props"]))
    a = arena.generate({"features": [], "hazards": [], "seed": 4}, source("none"))
    check("an open shell has no door gaps", arena.DOOR not in "".join(a["grid"]))
    a = arena.generate({"features": [], "hazards": [], "seed": 4}, source("scene"))
    check("a room shell has a door on each short side", a["grid"][a["h"] // 2][0] == arena.DOOR and a["grid"][a["h"] // 2][-1] == arena.DOOR)


def test_source_and_files() -> None:
    print("arena: source and files")
    with tempfile.TemporaryDirectory() as tmp:
        campaign = Path(tmp)
        none = arena.source_of(campaign, {}, {})
        check("no scene and no site: an open forest", none["kind"] == "none" and none["shell"] == "open" and none["decor"] == "forest")
        scenes.save(campaign, "wine-cellar", {"template": "tavern", "slots": {}, "add": [["barrel", "front_right"]]})
        scene = arena.source_of(campaign, {"scene": "wine-cellar"}, {})
        check("a scene gives its floor, walls, props and a room shell",
              scene["kind"] == "scene" and scene["look"]["floor"] == "lpc:planks" and scene["shell"] == "room"
              and ("barrel", "front_right") in scene["props"] and scene["decor"] == "tavern")
        scenes.save(campaign, "road-bend", {"template": "road", "slots": {}, "add": []})
        check("a road scene is open", arena.source_of(campaign, {"scene": "road-bend"}, {})["shell"] == "open")
        check("a scene with no file falls back to nothing", arena.source_of(campaign, {"scene": "ghost"}, {})["kind"] == "none")
        site = crawl.generate({"theme": "crypt", "size": "small", "seed": 3, "danger": "low", "name": "Vault"}, [])
        crawl.save(campaign, "vault", site)
        got = arena.source_of(campaign, {"explore": "vault", "scene": "wine-cellar"}, {})
        check("exploring a site wins over the scene and uses its theme", got["kind"] == "site" and got["look"] == arena.look_of("crypt") and got["decor"] == "crypt")
        check("theme= overrides the walls of a scene", arena.source_of(campaign, {"scene": "wine-cellar"}, {"theme": "crypt"})["look"]["wall"] == arena.look_of("crypt")["wall"])
        a = arena.generate({"features": [], "hazards": [], "seed": 1}, scene)
        check("the arena file keeps the look and the spec", a["look"] == scene["look"] and a["spec"]["source"] == "scene" and a["spec"]["source_id"] == "wine-cellar")
        check("the first arena id is arena-1", arena.new_id(campaign) == "arena-1")
        arena.save(campaign, "arena-1", a)
        check("an arena file loads back as saved", arena.load(campaign, "arena-1") == a)
        check("the next id is arena-2", arena.new_id(campaign) == "arena-2")
        check("a bad id loads nothing", arena.load(campaign, "../x") is None and arena.load(campaign, "nope") is None)


def fight(tmp: Path) -> tuple[Path, dict]:
    """A running combat on a copy of the example campaign: the party, two goblins and a named bugbear."""
    c = tmp / "camp"
    shutil.copytree(REPO / "tests" / "fixtures" / "example-campaign", c, ignore=shutil.ignore_patterns("stage", ".cache"))
    state = combat.load_state(c)
    enc = state["active_encounter"] = {"type": "combat", "round": 1, "participants": [], "initiative_order": [], "current_turn": None,
                                       "conditions": {}, "monsters": {}}
    for i, cid in enumerate(["aragorn", "legolas", "goblin#1", "goblin#2", "boss"]):
        if cid != "aragorn" and cid != "legolas":
            enc["monsters"][cid] = combat.monster_record(GOBLIN, cid)
        enc["participants"].append(cid)
        enc["initiative_order"].append({"name": cid, "initiative": 20 - i, "bonus": 0})
    enc["current_turn"] = "aragorn"
    return c, state


def test_start() -> None:
    print("arena: encounter start --arena")
    with tempfile.TemporaryDirectory() as tmp:
        c, state = fight(Path(tmp))
        lines = board.start(c, state, ["layout=chokepoint", "size=small", "light=dark", "seed=5", "feature=cover@foes"], {})
        enc = state["active_encounter"]
        a = arena.load(c, enc["arena"])
        check("the encounter keeps the arena id", enc["arena"] == "arena-1" and a is not None)
        starts = a["starts"]
        check("every combatant stands on a start tile of its side",
              [list(a["units"][u].values()) for u in ("aragorn", "legolas")] == starts["party"]
              and [list(a["units"][u].values()) for u in ("goblin#1", "goblin#2", "boss")] == starts["foes"])
        check("the spec keeps light and size", a["spec"]["light"] == "dark" and (a["w"], a["h"]) == (12, 8))
        check("a creature the DM named is DM-played, the others are not",
              a["control"] == {"goblin#1": "engine", "goblin#2": "engine", "boss": "dm"} and "You play: boss" in lines[-1])
        check("a bare monster index is engine-played, a renamed one is DM-played",
              board.controlled_by({"id": "goblin#2", "index": "goblin"}) == "engine" and board.controlled_by({"id": "boss", "index": "bugbear"}) == "dm"
              and board.controlled_by({"id": "cassara", "index": "cassara", "kind": "npc"}) == "dm")
    with tempfile.TemporaryDirectory() as tmp:
        c, state = fight(Path(tmp))
        check("a bad token is refused and nothing is written",
              raises(lambda: board.start(c, state, ["layout=maze"], {})) and "arena" not in state["active_encounter"]
              and not arena.arenas_dir(c).exists())


def test_state() -> None:
    print("arena: stage state")
    s = stage_state.empty()
    check("a new stage has no arena", s["arena"] is None)
    s = stage_state.apply(s, {"type": "arena", "arena": "arena-1"})
    check("an arena event shows the arena and bumps its version", s["arena"] == "arena-1" and s["versions"]["arena:arena-1"] == s["seq"])
    s2 = stage_state.apply(s, {"type": "arena_updated", "arena": "arena-1"})
    check("arena_updated makes the browser fetch it again", s2["versions"]["arena:arena-1"] == s2["seq"] > s["versions"]["arena:arena-1"])
    s3 = stage_state.apply(stage_state.apply(s, {"type": "explore", "site": "vault"}), {"type": "arena", "arena": "arena-2"})
    check("a fight inside a site keeps the site", s3["arena"] == "arena-2" and s3["explore"] == "vault")
    s4 = stage_state.apply(s3, {"type": "arena_end"})
    check("the end of the fight shows the site again", s4["arena"] is None and s4["explore"] == "vault")
    check("a scene clears the arena", stage_state.apply(s, {"type": "scene", "location": "inn", "party": []})["arena"] is None)
    check("an explore clears the arena", stage_state.apply(s, {"type": "explore", "site": "vault"})["arena"] is None)
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "events.ndjson"
        log.write_text('{"type": "scene", "location": "inn", "party": []}\nnot json\n{"type": "arena", "arena": "arena-1"}\n')
        got = stage_state.replay(log)
        check("replay folds a log, skipping bad lines", got["scene"] == "inn" and got["arena"] == "arena-1")
        check("replay of a missing log is the empty stage", stage_state.replay(Path(tmp) / "none.ndjson") == stage_state.empty())


if __name__ == "__main__":
    for t in (test_geometry, test_props, test_parse, test_generator, test_source_and_files, test_start, test_state):
        t()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
