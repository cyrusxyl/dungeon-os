"""Checks for the combat board engine: walking, reaction attacks, reach, sight and cover.

Run from the repo root:  .venv/bin/python tests/test_board.py

Plain asserts so no test runner is needed.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dnd_cli import combat  # noqa: E402
from stage import arena, board  # noqa: E402
from tests.test_arena import fight  # noqa: E402
from tests.test_rules import Fixed  # noqa: E402

PASS = FAIL = 0
ROOM = ["#" * 12] + ["#" + "." * 10 + "#"] * 6 + ["#" * 12]  # 12 x 8, floor inside


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


def raises(fn) -> bool:
    try:
        fn()
    except board.BoardError:
        return True
    return False


def setup(tmp: Path, props=(), grid=ROOM, at=None):
    """The fixture fight (aragorn, legolas, goblin#1, goblin#2, boss) on a plain room; `at` places units."""
    c, state = fight(tmp)
    where = {"aragorn": (2, 3), "legolas": (2, 5), "goblin#1": (8, 3), "goblin#2": (8, 5), "boss": (9, 4)} | (at or {})
    a = {"w": 12, "h": 8, "grid": list(grid), "props": [dict(p, id=f"{p['kind']}#{i}") for i, p in enumerate(props)], "items": [],
         "starts": {"party": [[2, 3], [2, 5]], "foes": [[8, 3], [8, 5], [9, 4]]}, "units": {k: {"x": x, "y": y} for k, (x, y) in where.items()},
         "look": arena.look_of("tavern"), "spec": {"decor": "tavern"}}
    state["active_encounter"]["arena"] = "arena-1"
    return c, state, a


def test_walking() -> None:
    print("board: walking")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = setup(Path(tmp))
        rec = combat.combatant(c, state, "aragorn")
        check("a speed of 30 ft is 6 tiles", board.tiles_left(state, rec) == 6 and rec["speed_ft"] == 30)
        check("a speed of 35 ft is 7 tiles", board.tiles_left(state, combat.combatant(c, state, "legolas")) == 7)
        dist, _ = board.reachable(c, state, a, "aragorn")
        check("the walkable cells are within 6 steps", max(dist.values()) == 6 and (8, 3) not in dist and (7, 3) in dist)
        r = board.move(c, state, a, "aragorn", (5, 3))
        check("a walk moves the unit and spends tiles", a["units"]["aragorn"] == {"x": 5, "y": 3} and len(r["steps"]) == 3
              and board.tiles_left(state, rec) == 3)
        check("the walk cannot go past what is left", raises(lambda: board.move(c, state, a, "aragorn", (9, 3))))
        check("a unit cannot walk onto another", raises(lambda: board.move(c, state, a, "aragorn", (8, 3))))
        check("a wall cell is not reachable", raises(lambda: board.move(c, state, a, "aragorn", (0, 3))))
        combat.condition(state, "aragorn", "add", "dashing", rounds=1)
        check("Dash doubles the speed", board.tiles_left(state, rec) == 9)
        state["active_encounter"]["resources"]["aragorn"] = {}
        check("a new turn gives the walking back", board.tiles_left(state, rec) == 12)


def test_blocking() -> None:
    print("board: blocking")
    with tempfile.TemporaryDirectory() as tmp:
        wall = [dict(kind="barrel", x=3, y=y) for y in range(1, 7)]  # a barrel wall across the room
        c, state, a = setup(Path(tmp), props=wall)
        dist, _ = board.reachable(c, state, a, "aragorn")
        check("props that block movement cut the room", (4, 3) not in dist and (3, 3) not in dist)
        c, state, a = setup(Path(tmp) / "b", props=[dict(kind="bush", x=3, y=3)])
        dist, _ = board.reachable(c, state, a, "aragorn")
        check("a bush does not block movement", (3, 3) in dist)
        c, state, a = setup(Path(tmp) / "c", at={"legolas": (3, 3)})
        dist, _ = board.reachable(c, state, a, "aragorn")
        check("another unit blocks its cell", (3, 3) not in dist)
        c, state, a = setup(Path(tmp) / "d")
        state["active_encounter"]["monsters"]["goblin#1"]["hp"]["current"] = 0
        dist, _ = board.reachable(c, state, a, "aragorn")
        check("a dead creature frees its cell", (8, 3) in dist or (7, 3) in dist)
        state["active_encounter"]["monsters"]["goblin#1"]["hp"]["current"] = 7
        a["units"]["legolas"] = {"x": 3, "y": 3}
        from dnd_cli import character
        sheet = character.load(c, "legolas")
        sheet["hp"]["current"] = 0
        character.save(c, "legolas", sheet)
        dist, _ = board.reachable(c, state, a, "aragorn")
        check("a player character at 0 HP lies where it fell and blocks its cell", (3, 3) not in dist)


def test_reactions() -> None:
    print("board: reaction attacks")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = setup(Path(tmp), at={"goblin#1": (3, 3)})
        before = combat.combatant(c, state, "aragorn")["hp"]["current"]
        r = board.move(c, state, a, "aragorn", (1, 3), rng=Fixed(15, 3))
        check("walking out of a goblin's reach gives it a reaction attack", any("reaction attack" in ln for ln in r["lines"]) and r["pending"] is None)
        check("the goblin used its reaction", combat.turn_used(state, "goblin#1")["reaction"])
        check("the attack hit", combat.combatant(c, state, "aragorn")["hp"]["current"] < before)
        check("the tracker did not move to the goblin's turn", state["active_encounter"]["current_turn"] == "aragorn")
        c, state, a = setup(Path(tmp) / "b", at={"goblin#1": (3, 3)})
        combat.condition(state, "aragorn", "add", "disengaged", rounds=1)
        r = board.move(c, state, a, "aragorn", (1, 3), rng=Fixed(15, 3))
        check("Disengage: no reaction attack", not r["lines"] and not combat.turn_used(state, "goblin#1")["reaction"])
        c, state, a = setup(Path(tmp) / "c", at={"goblin#1": (3, 3)})
        r = board.move(c, state, a, "aragorn", (3, 4))
        check("moving but staying in reach gives no reaction attack", not r["lines"])
        c, state, a = setup(Path(tmp) / "d", at={"goblin#1": (3, 3)})
        r = board.move(c, state, a, "aragorn", (4, 4), rng=Fixed(15, 3))
        check("a step to a cell still next to the goblin gives none", not r["lines"])
        # a player character reacts when a goblin walks away
        c, state, a = setup(Path(tmp) / "e", at={"goblin#1": (3, 3)})
        r = board.walk(c, state, a, "goblin#1", [(4, 3), (5, 3)], rng=Fixed(15, 3))
        check("a player character is asked, and the walk waits", r["pending"] and r["pending"]["who"] == "aragorn" and r["steps"] == []
              and a["units"]["goblin#1"] == {"x": 3, "y": 3})
        check("a second move is refused while a question waits", raises(lambda: board.move(c, state, a, "goblin#1", (4, 3))))
        r = board.answer(c, state, a, True, rng=Fixed(15, 3))
        check("answer yes: the attack is made and the walk goes on", any("reaction attack" in ln for ln in r["lines"])
              and a["units"]["goblin#1"] == {"x": 5, "y": 3} and a["pending"] is None)
        check("the reaction is spent", combat.turn_used(state, "aragorn")["reaction"])
        c, state, a = setup(Path(tmp) / "f", at={"goblin#1": (3, 3)})
        board.walk(c, state, a, "goblin#1", [(4, 3)], rng=Fixed(15, 3))
        r = board.answer(c, state, a, False)
        check("answer no: no attack, the walk goes on, the reaction is spent", not r["lines"] and a["units"]["goblin#1"] == {"x": 4, "y": 3}
              and combat.turn_used(state, "aragorn")["reaction"])
        check("an answer with no question is refused", raises(lambda: board.answer(c, state, a, True)))
        c, state, a = setup(Path(tmp) / "g", at={"goblin#1": (3, 3)})
        state["active_encounter"]["monsters"]["goblin#1"]["hp"]["current"] = 1
        board.walk(c, state, a, "goblin#1", [(4, 3), (5, 3)], rng=Fixed(15, 3))
        r = board.answer(c, state, a, True, rng=Fixed(15, 3))
        check("a walker that falls to a reaction attack stops", a["units"]["goblin#1"] == {"x": 3, "y": 3} and r["steps"] == [])


def test_attacks() -> None:
    print("board: reach, sight and cover")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = setup(Path(tmp))
        check("a melee attack needs the target within reach", raises(lambda: board.attack(c, state, a, "aragorn", "longsword", "goblin#1")))
        a["units"]["goblin#1"] = {"x": 3, "y": 4}
        lines = board.attack(c, state, a, "aragorn", "longsword", "goblin#1", rng=Fixed(15, 4))
        check("next to the target, the attack is made", any("Longsword" in ln for ln in lines))
        c, state, a = setup(Path(tmp) / "a2", at={"goblin#1": (3, 4)})
        check("a diagonal neighbor is in reach", board.attack_check(c, state, a, "aragorn", {"name": "x", "reach_ft": 5}, "goblin#1")["mode"] == "melee")
        c, state, a = setup(Path(tmp) / "b")
        lines = board.attack(c, state, a, "legolas", "longbow", "goblin#1", rng=Fixed(15, 4))
        check("a longbow shoots 6 tiles away", any("Longbow" in ln for ln in lines))
        check("past the range the attack is refused", raises(lambda: board.attack(c, state, a, "aragorn", "longsword", "boss")))
        c, state, a = setup(Path(tmp) / "c", at={"goblin#1": (10, 3)})
        a["grid"][3] = "#" + "." * 4 + "#" + "." * 5 + "#"  # a wall at x=5 on row 3
        check("a wall on the line hides the target", raises(lambda: board.attack(c, state, a, "aragorn", "longbow", "goblin#1")))
        c, state, a = setup(Path(tmp) / "d", at={"goblin#1": (10, 3)}, props=[dict(kind="barrel", x=5, y=3)])
        info = board.attack_check(c, state, a, "aragorn", combat.combatant(c, state, "aragorn")["attacks"][1], "goblin#1")
        check("a barrel on the line gives half cover, and does not hide", info["cover"] == "half" and info["mode"] == "ranged")
        lines = board.attack(c, state, a, "aragorn", "longbow", "goblin#1", rng=Fixed(10, 4))
        check("half cover lowers the roll by 2 (+4 becomes +2)", any("half cover: -2" in ln for ln in lines) and any("10+2 = 12" in ln for ln in lines))
        c, state, a = setup(Path(tmp) / "e", at={"goblin#1": (10, 3)}, props=[dict(kind="column_broken", x=5, y=3)])
        check("three-quarters cover from a column", board.attack_check(c, state, a, "aragorn", combat.combatant(c, state, "aragorn")["attacks"][1], "goblin#1")["cover"] == "three-quarters")
        c, state, a = setup(Path(tmp) / "f", at={"goblin#1": (10, 3)}, props=[dict(kind="tree", x=5, y=3)])
        check("a tree hides the target", raises(lambda: board.attack(c, state, a, "aragorn", "longbow", "goblin#1")))
        c, state, a = setup(Path(tmp) / "g", at={"goblin#1": (3, 3), "goblin#2": (9, 3)})
        info = board.attack_check(c, state, a, "aragorn", combat.combatant(c, state, "aragorn")["attacks"][1], "goblin#2")
        check("an enemy next to an archer gives disadvantage", info["dis"] is True)
        state["active_encounter"]["monsters"]["goblin#2"]["hp"]["current"] = 0
        check("an attack on a creature that is down is refused", raises(lambda: board.attack(c, state, a, "aragorn", "longbow", "goblin#2")))


def test_sync_and_start() -> None:
    print("board: new creatures")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = setup(Path(tmp))
        enc = state["active_encounter"]
        enc["monsters"]["goblin#3"] = combat.monster_record(__import__("tests.test_rules", fromlist=["GOBLIN"]).GOBLIN, "goblin#3")
        enc["participants"].append("goblin#3")
        added = board.sync_units(c, state, a)
        x, y = board.pos(a, "goblin#3")
        check("a creature added in the fight gets a free cell near the foes", added == ["goblin#3"] and x >= 6 and (x, y) not in
              [board.pos(a, u) for u in a["units"] if u != "goblin#3"] and (x, y) not in arena.blocked_cells(a))
        c2, state2, a2 = setup(Path(tmp) / "ap")
        near = board.approach(c2, state2, a2, "goblin#1", "aragorn")
        check("approach: the reachable cell nearest the target", near is not None and arena.cheb(near, (2, 3)) == 1)
        a2["units"]["goblin#1"] = {"x": 3, "y": 3}
        check("approach: none when it is already next to the target", board.approach(c2, state2, a2, "goblin#1", "aragorn") is None)
        check("units that are placed stay where they are", a["units"]["aragorn"] == {"x": 2, "y": 3})
        check("an unknown unit has no place", raises(lambda: board.pos(a, "nobody")))
        state["active_encounter"].pop("arena")
        check("no arena, no board", raises(lambda: board.running(c, state)))


if __name__ == "__main__":
    for t in (test_walking, test_blocking, test_reactions, test_attacks, test_sync_and_start):
        t()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
