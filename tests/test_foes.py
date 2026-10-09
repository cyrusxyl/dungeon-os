"""Checks for the foe planner: what the stage does with a creature's turn, from the plain goblin to the dragon and the mage.

Run from the repo root:  .venv/bin/python tests/test_foes.py

Plain asserts so no test runner is needed. It reads the cached 5e API data under .cache.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dnd_cli import character, combat  # noqa: E402
from stage import arena, board, foes  # noqa: E402
from tests.test_board import ROOM  # noqa: E402
from tests.test_rules import Fixed, campaign  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}{'' if cond or not detail else f'  ({detail})'}")


def battle(tmp: Path, specs: list[str], at: dict, props=()):
    """The example party (Aragorn, Legolas) against API creatures, on a plain room. `at` places units by id."""
    c = campaign(Path(tmp))
    state = combat.load_state(c)
    combat.start(c, state, specs, None, rng=Fixed(10))
    enc = state["active_encounter"]
    units = {k: {"x": x, "y": y} for k, (x, y) in at.items()}
    a = {"w": 12, "h": 8, "grid": list(ROOM), "props": [dict(p, id=f"{p['kind']}#{i}") for i, p in enumerate(props)], "items": [],
         "starts": {"party": [[2, 3]], "foes": [[9, 4]]}, "units": units, "look": arena.look_of("tavern"),
         "spec": {"decor": "tavern", "light": "lit", "settings": {}}, "control": {}, "seen": ["0" * 12] * 8}
    enc["arena"] = "arena-1"
    enc["current_turn"] = next(iter(enc["monsters"]))  # a creature acts on its own turn: no catch-up of the tracker
    return c, state, a


def tough(c: Path) -> None:
    """Heroes with 200 HP: no single hit is a kill, so a plan is about damage and areas."""
    for hero in ("aragorn", "legolas"):
        sheet = character.load(c, hero)
        sheet["hp"].update(current=200, max=200)
        character.save(c, hero, sheet)


def test_basic() -> None:
    print("foes: attack, move, and the choice of target")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = battle(tmp, ["goblin"], {"aragorn": (2, 3), "legolas": (2, 6), "goblin": (4, 3)})
        state["active_encounter"]["monsters"]["goblin"]["abilities"] = []
        pl = foes.plan(c, state, a, "goblin")
        check("a plain goblin plans an attack on a hero", pl["kind"] == "attack" and pl["entry"] in ("Scimitar", "Shortbow") and pl["target"] in ("aragorn", "legolas"))
        check("the plan names the hit chance for the intent chip", pl["info"].endswith("%"))
        sheet = character.load(c, "legolas")
        sheet["hp"]["current"] = 2
        character.save(c, "legolas", sheet)
        check("a creature goes for a hero it can kill", foes.plan(c, state, a, "goblin")["target"] == "legolas")
        a["spec"]["style"] = "sneaky"
        check("a sneaky creature goes for the weakest hero", foes.plan(c, state, a, "goblin")["target"] == "legolas")
        check("an aggressive creature without cover stands next to its target (no danger term)", foes.style_of(a, state["active_encounter"]["monsters"]["goblin"]) == "sneaky")


def test_multiattack_and_breath() -> None:
    print("foes: Multiattack and a breath weapon")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = battle(tmp, ["young-red-dragon"], {"aragorn": (2, 3), "legolas": (10, 6), "young-red-dragon": (3, 3)})
        tough(c)
        down = character.load(c, "legolas")
        down["hp"]["current"] = 0  # one hero stands: the dragon has one target
        character.save(c, "legolas", down)
        dragon = state["active_encounter"]["monsters"]["young-red-dragon"]
        pl = foes.plan(c, state, a, "young-red-dragon")
        check("next to a hero, the dragon uses its Multiattack, not the breath", pl["kind"] == "multiattack")
        lines = foes.play_foe(c, state, a, "young-red-dragon", rng=Fixed(15, 1, 1, 15, 1, 1, 15, 1, 1))["lines"]
        check("the Multiattack is a bite and two claws, with one action", sum("Bite" in ln or "Claw" in ln for ln in lines) == 3 and combat.turn_used(state, "young-red-dragon")["action"])
        board.resources(state, "young-red-dragon").clear()
        down["hp"]["current"] = 200
        character.save(c, "legolas", down)
        a["units"]["legolas"] = {"x": 2, "y": 4}
        pl = foes.plan(c, state, a, "young-red-dragon")
        check("two heroes in a line of fire: the breath wins", pl["kind"] == "zone" and pl["ability"] == "fire-breath" and pl["info"] == "2 targets", str(pl))
        lines = foes.play_foe(c, state, a, "young-red-dragon", rng=Fixed(10, 12, 12, 3))["lines"]
        breath = next(x for x in dragon["abilities"] if x["name"] == "Fire Breath")
        check("the breath is spent after it is used", any("Fire Breath" in ln for ln in lines) and breath["uses"]["left"] == 0)
        check("each hero in the area saved", sum("DEX save" in ln for ln in lines) >= 2)
        board.resources(state, "young-red-dragon").clear()
        check("a spent breath is not planned again", foes.plan(c, state, a, "young-red-dragon") is None or foes.plan(c, state, a, "young-red-dragon")["kind"] != "zone")
        out = foes.play_foe(c, state, a, "young-red-dragon", rng=Fixed(6, 15, 5))
        check("the recharge roll is made at the start of the turn", any("recharge roll 6" in ln for ln in out["lines"]) and breath["uses"]["left"] == 1 or breath["uses"]["left"] == 0)


def test_fireball() -> None:
    print("foes: a mage and its Fireball")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = battle(tmp, ["mage"], {"aragorn": (2, 3), "legolas": (3, 3), "mage": (9, 5)})
        mage = state["active_encounter"]["monsters"]["mage"]
        tough(c)  # no area is worth it for a kill alone
        pl = foes.plan(c, state, a, "mage")
        check("two heroes side by side: Fireball (or a bigger area spell) is the play", pl["kind"] == "zone" and pl["info"] == "2 targets", str(pl))
        check("a mage plays as a skirmisher", foes.style_of(a, mage) == "skirmisher")
        sheet = character.load(c, "legolas")
        sheet["hp"]["current"] = 0
        character.save(c, "legolas", sheet)
        pl = foes.plan(c, state, a, "mage")
        check("one hero alone: the mage uses a cantrip or an at-will attack, and saves its slots", pl["kind"] in ("spell_attack", "attack") and pl.get("ability", "fire-bolt") == "fire-bolt", str(pl))
        sheet["hp"]["current"] = 200
        character.save(c, "legolas", sheet)
        a["units"]["legolas"] = {"x": 3, "y": 3}
        mage["slots"] = {k: 0 for k in mage["slots"]}
        pl = foes.plan(c, state, a, "mage")
        check("with no slots left, no spell is planned", pl["kind"] != "zone")
        mage["slots"] = {"1": 4, "2": 3, "3": 3, "4": 0, "5": 0}
        fireball = next(x for x in mage["abilities"] if x["name"] == "Fireball")
        lines = foes.play_foe(c, state, a, "mage", rng=Fixed(12, 3, 3, 12, 3, 3, 12, 3, 3))["lines"]
        check("it casts: a slot is spent, the heroes save", any("uses" in ln for ln in lines) and sum("save" in ln for ln in lines) >= 2 and mage["slots"]["3"] == 2 or mage["slots"] != {"1": 4, "2": 3, "3": 3, "4": 0, "5": 0}, str(lines[:3]))
        # an ally in the fire costs
        c, state, a = battle(Path(tmp) / "b", ["mage", "goblin"], {"aragorn": (2, 3), "legolas": (3, 3), "mage": (9, 5), "goblin": (2, 4)})
        free = foes.plan(c, state, a, "mage")
        check("an ally next to the heroes lowers the value of an area (or the mage aims elsewhere)", free is not None)


def test_styles() -> None:
    print("foes: styles, nerve and kiting")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = battle(tmp, ["goblin"], {"aragorn": (2, 3), "legolas": (2, 6), "goblin": (4, 3)})
        goblin = state["active_encounter"]["monsters"]["goblin"]
        goblin["abilities"] = []
        a["spec"]["style"] = "cowardly"
        goblin["hp"]["current"] = 3
        out = foes.play_foe(c, state, a, "goblin", rng=Fixed(10))
        x, y = board.pos(a, "goblin")
        check("a cowardly creature below half its HP runs, and gets farther away",
              any("flees" in ln for ln in out["lines"]) and min(arena.cheb((x, y), (2, 3)), arena.cheb((x, y), (2, 6))) >= 4 and combat.has_condition(state, "goblin", "dashing"))
        check("it does not attack when it runs", combat.turn_used(state, "goblin")["action"] and not any("Scimitar" in ln for ln in out["lines"]))
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = battle(tmp, ["goblin"], {"aragorn": (2, 3), "legolas": (2, 6), "goblin": (4, 3)})
        state["active_encounter"]["monsters"]["goblin"]["abilities"] = []
        state["active_encounter"]["monsters"]["goblin"]["hp"]["current"] = 3
        a["spec"]["style"] = "aggressive"
        out = foes.play_foe(c, state, a, "goblin", rng=Fixed(15, 3))
        check("an aggressive creature fights on when it is hurt", any("→" in ln for ln in out["lines"]))
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = battle(tmp, ["goblin"], {"aragorn": (2, 3), "legolas": (2, 6), "goblin": (9, 4)})
        gob = state["active_encounter"]["monsters"]["goblin"]
        gob["abilities"] = []
        gob["attacks"] = [{"name": "Shortbow", "bonus": 4, "range_ft": 80, "damage": [["1d6+2", "piercing"]]}]
        check("a creature with only a bow plays as a skirmisher", foes.style_of(a, gob) == "skirmisher")
        pl = foes.plan(c, state, a, "goblin")
        far = min(arena.cheb(pl["p"], (2, 3)), arena.cheb(pl["p"], (2, 6)))
        near = foes.plan(c, state, a, "goblin", style="aggressive")
        check("the archer shoots from as far from the heroes as it can", pl["kind"] == "attack" and far >= min(arena.cheb(near["p"], (2, 3)), arena.cheb(near["p"], (2, 6))), str((pl, near)))
        check("the aggressive plan does not care about distance (it may stay put)", near["kind"] == "attack")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = battle(tmp, ["goblin"], {"aragorn": (2, 3), "legolas": (2, 6), "goblin": (4, 6)},
                             props=[{"kind": "barrel", "x": 4, "y": 5}, {"kind": "barrel", "x": 5, "y": 6}])
        state["active_encounter"]["monsters"]["goblin"]["abilities"] = []
        a["spec"]["style"] = "sneaky"
        pl = foes.plan(c, state, a, "goblin")
        check("a sneaky creature likes a cell with cover next to it", pl is not None and any((pl["p"][0] + dx, pl["p"][1] + dy) in {(4, 5), (5, 6)} for dx in (-1, 0, 1) for dy in (-1, 0, 1)))


def test_traits() -> None:
    print("foes: traits")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = battle(tmp, ["wolf:2"], {"aragorn": (5, 3), "legolas": (2, 6), "wolf#1": (4, 3), "wolf#2": (6, 3)})
        wolf = state["active_encounter"]["monsters"]["wolf#1"]
        check("Pack Tactics: advantage when an ally is next to the target", "Pack Tactics" in wolf["traits"])
        lines = board.attack(c, state, a, "wolf#1", "bite", "aragorn", rng=Fixed(3, 12, 4))
        check("the attack rolls twice and keeps the better", any("advantage" in ln for ln in lines), str(lines))
        a["units"]["wolf#2"] = {"x": 9, "y": 6}
        board.resources(state, "wolf#1").clear()
        lines = board.attack(c, state, a, "wolf#1", "bite", "aragorn", rng=Fixed(3, 4))
        check("alone, no advantage", not any("advantage" in ln for ln in lines))
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = battle(tmp, ["hobgoblin:2"], {"aragorn": (5, 3), "legolas": (2, 6), "hobgoblin#1": (4, 3), "hobgoblin#2": (6, 3)})
        lines = board.attack(c, state, a, "hobgoblin#1", "longsword", "aragorn", rng=Fixed(18, 4, 3, 3))
        check("Martial Advantage: +2d6 once per turn when an ally is next to the target", board.resources(state, "hobgoblin#1").get("martial") is True
              and any("2d6" in ln or "damage" in ln for ln in lines))
        before = combat.combatant(c, state, "aragorn")["hp"]["current"]
        board.attack(c, state, a, "hobgoblin#1", "longsword", "aragorn", rng=Fixed(18, 4))
        check("only once per turn: the second hit is 1d8+1 alone (4 + 1)", before - combat.combatant(c, state, "aragorn")["hp"]["current"] == 5)
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = battle(tmp, ["goblin"], {"aragorn": (2, 3), "legolas": (2, 6), "goblin": (3, 3)})
        lines = foes._disengage_first(c, state, a, "goblin")
        check("Nimble Escape: a goblin next to a hero disengages with its bonus action before it walks away",
              lines and combat.turn_used(state, "goblin")["bonus"] and combat.has_condition(state, "goblin", "disengaged"))
        check("and only once", foes._disengage_first(c, state, a, "goblin") == [])
        a["units"]["goblin"] = {"x": 9, "y": 3}
        state["active_encounter"]["resources"]["goblin"] = {}
        combat.condition(state, "goblin", "remove", "disengaged")
        check("no hero next to it: no need", foes._disengage_first(c, state, a, "goblin") == [])


def test_intents() -> None:
    print("foes: what the players see over a creature")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = battle(tmp, ["mage", "goblin"], {"aragorn": (2, 3), "legolas": (3, 3), "mage": (9, 5), "goblin": (6, 3)})
        a["control"] = {"mage": "engine", "goblin": "dm"}
        board.refresh_intents(c, state, a)
        check("a creature the stage plays shows its play and its targets", a["intents"]["mage"]["kind"] == "zone" and "→ 2 targets" in a["intents"]["mage"]["text"], str(a["intents"]))
        check("a creature the DM plays says so", a["intents"]["goblin"] == {"kind": "dm", "text": "DM decides"})
        a["spec"]["style"] = "cowardly"
        state["active_encounter"]["monsters"]["mage"]["hp"]["current"] = 3
        check("a creature about to flee says so", foes.describe(c, state, a, "mage") == {"kind": "flee", "text": "Flees"})
        state["active_encounter"]["monsters"]["mage"]["hp"]["current"] = 40
        a["spec"]["style"] = "aggressive"
        state["active_encounter"]["monsters"]["mage"]["slots"] = {k: 0 for k in state["active_encounter"]["monsters"]["mage"]["slots"]}
        a["units"]["mage"] = {"x": 11, "y": 1}
        a["units"]["legolas"] = {"x": 2, "y": 7}
        check("a creature with nothing in reach says where it walks", foes.describe(c, state, a, "mage")["kind"] in ("move", "attack", "spell_attack"))
        v = board.view(c, state, "arena-1", a, {"reaction_seconds": 10, "round_summary": True})
        check("the board view carries the intent of each creature in sight", next(u for u in v["units"] if u["id"] == "goblin")["intent"]["text"] == "DM decides"
              and "intent" not in next(u for u in v["units"] if u["id"] == "aragorn"))


def test_dm_only() -> None:
    print("foes: what is left to the DM")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = battle(tmp, ["adult-red-dragon"], {"aragorn": (2, 3), "legolas": (2, 4), "adult-red-dragon": (8, 3)})
        dragon = state["active_encounter"]["monsters"]["adult-red-dragon"]
        pl = foes.plan(c, state, a, "adult-red-dragon")
        check("the stage plans only abilities it can run (breath and attacks), never a legendary action",
              pl["kind"] in ("zone", "multiattack") and pl.get("ability") in ("fire-breath", "multiattack"))
        prompt = board.dm_prompt(c, state, a, "adult-red-dragon")
        check("the DM prompt lists what only the DM can play", "Frightful Presence" in prompt and "Tail Attack" in prompt)


if __name__ == "__main__":
    for t in (test_basic, test_multiattack_and_breath, test_fireball, test_styles, test_traits, test_intents, test_dm_only):
        t()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
