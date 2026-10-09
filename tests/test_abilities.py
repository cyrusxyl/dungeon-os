"""Checks for abilities: the 5e API data as structured abilities, and the area shapes of the arena.

Run from the repo root:  .venv/bin/python tests/test_abilities.py

Plain asserts so no test runner is needed. It reads the cached 5e API data under .cache.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dnd_cli import abilities, combat  # noqa: E402
from dnd_cli.api import api_get  # noqa: E402
from stage import arena  # noqa: E402
from tests.test_rules import Fixed  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


def monster(index: str) -> dict:
    data, err, _ = api_get(f"monsters/{index}")
    assert not err, err
    return combat.monster_record(data, index)


def test_shapes_from_text() -> None:
    print("abilities: the area in the text")
    st = abilities.shape_from_text
    check("a cone", st("The dragon exhales fire in a 60-foot cone.") == {"type": "cone", "size_ft": 60})
    check("a sphere by radius", st("in a 20-foot-radius sphere") == {"type": "sphere", "size_ft": 20})
    check("a line", st("in a line that is 90 feet long and 5 feet wide") == {"type": "line", "size_ft": 90})
    check("a cube", st("a 15-foot cube") == {"type": "cube", "size_ft": 15})
    check("nothing means one target", st("one creature within 5 feet") == {"type": "single", "size_ft": 0})


def test_monsters() -> None:
    print("abilities: monsters")
    dragon = monster("young-red-dragon")
    names = {a["name"]: a for a in dragon["abilities"]}
    breath = names["Fire Breath"]
    check("a breath weapon is a zone with a save, a cone, damage and a recharge",
          breath["kind"] == "zone" and breath["save"] == {"ability": "dex", "dc": 17, "success": "half"} and breath["shape"]["type"] == "cone"
          and breath["shape"]["size_ft"] == 30 and breath["damage"] == [["16d6", "fire"]] and breath["uses"] == {"per": "recharge", "min": 5, "left": 1})
    check("Multiattack lists its attacks", names["Multiattack"]["kind"] == "multiattack" and names["Multiattack"]["parts"] == [["Bite", 1], ["Claw", 2]])
    check("an attack roll stays in `attacks`, not in the abilities", all(a["name"] not in ("Bite", "Claw") for a in dragon["abilities"]))
    adult = monster("adult-red-dragon")
    ids = {a["name"]: a for a in adult["abilities"]}
    check("an action the stage cannot read is for the DM", ids["Frightful Presence"]["kind"] == "dm" and ids["Tail Attack"]["kind"] == "dm"
          and ids["Tail Attack"]["cost"] == "legendary")
    check("a breath that does nothing on a save: success none", ids["Fire Breath"]["save"]["success"] == "none")
    mage = monster("mage")
    spells = {a["name"]: a for a in mage["abilities"]}
    check("a monster's damage spells come with their slots", mage["slots"] == {"1": 4, "2": 3, "3": 3, "4": 3, "5": 1}
          and spells["Fireball"]["uses"] == {"per": "slot", "level": 3} and spells["Fireball"]["damage"] == [["8d6", "fire"]])
    check("Fireball: DC from the monster, a sphere of 20 ft, range 150 ft",
          spells["Fireball"]["save"] == {"ability": "dex", "dc": 14, "success": "half"} and spells["Fireball"]["shape"] == {"type": "sphere", "size_ft": 20, "range_ft": 150})
    check("a cantrip is at will and a spell attack uses the monster's bonus",
          spells["Fire Bolt"]["kind"] == "spell_attack" and "uses" not in spells["Fire Bolt"] and spells["Fire Bolt"]["attack"]["bonus"] == 6
          and spells["Fire Bolt"]["attack"]["range_ft"] == 120)
    check("a buff or a utility spell is not an ability", "Detect Magic" not in spells and "Mage Hand" not in spells)
    goblin = monster("goblin")
    check("a trait with a rule is kept, and Nimble Escape is a bonus action", goblin["traits"] == ["Nimble Escape"]
          and goblin["abilities"][0]["cost"] == "bonus" and goblin["abilities"][0]["effect"] == "disengage")
    check("Pack Tactics and Martial Advantage are known traits", monster("wolf")["traits"] == ["Pack Tactics"] and monster("hobgoblin")["traits"] == ["Martial Advantage"])
    check("a plain monster has no abilities beyond its attacks", monster("ogre")["abilities"] == [])


def test_spells() -> None:
    print("abilities: spells")
    spell = lambda i: api_get(f"spells/{i}")[0]  # noqa: E731
    fireball = abilities.from_spell(spell("fireball"), slot=5, dc=15)
    check("a leveled spell takes its damage from the slot", fireball["damage"] == [["10d6", "fire"]] and fireball["slot"] == 5)
    check("without a slot it uses the spell's own level", abilities.from_spell(spell("fireball"), dc=15)["damage"] == [["8d6", "fire"]])
    check("a cantrip grows with the caster's level", abilities.from_spell(spell("fire-bolt"), caster_level=5, attack=7)["damage"] == [["2d10", "fire"]]
          and abilities.from_spell(spell("fire-bolt"), caster_level=4, attack=7)["damage"] == [["1d10", "fire"]])
    bh = abilities.from_spell(spell("burning-hands"), dc=13)
    check("burning hands: a 15-foot cone from the caster, DEX save for half", bh["shape"]["type"] == "cone" and bh["shape"]["size_ft"] == 15
          and bh["save"]["success"] == "half")
    check("a spell with no dice (cure wounds) is not a damage ability", abilities.from_spell(spell("cure-wounds"), dc=13, attack=5) is None)
    check("a spell with neither a save nor an attack needs the right number to be one", abilities.from_spell(spell("fire-bolt")) is None)
    check("a damage table gives the highest entry at or under the level", abilities.at_level({"1": "1d4", "5": "2d4"}, 7) == "2d4" and abilities.at_level({"3": "8d6"}, 1) == "8d6")


def test_uses() -> None:
    print("abilities: uses, slots and recharge")
    dragon = monster("young-red-dragon")
    breath = next(a for a in dragon["abilities"] if a["name"] == "Fire Breath")
    check("a ready breath is available", abilities.available(dragon, breath))
    abilities.spend(dragon, breath)
    check("a spent breath is not", not abilities.available(dragon, breath) and breath["uses"]["left"] == 0)
    check("a recharge roll under the minimum does nothing", abilities.recharge(dragon, Fixed(3))[0].endswith("not yet.") and breath["uses"]["left"] == 0)
    check("a roll of 5 or 6 brings it back", abilities.recharge(dragon, Fixed(5))[0].endswith("ready.") and breath["uses"]["left"] == 1)
    check("a breath that is ready is not rolled for", abilities.recharge(dragon, Fixed(1)) == [])
    mage = monster("mage")
    fireball = next(a for a in mage["abilities"] if a["name"] == "Fireball")
    for _ in range(3):
        abilities.spend(mage, fireball)
    check("slots count down, and no slot means no spell", mage["slots"]["3"] == 0 and not abilities.available(mage, fireball))
    check("a DM-only ability is never available", not abilities.available(dragon, {"kind": "dm"}))


def test_area() -> None:
    print("arena: area shapes")
    size = (30, 30)
    sphere = arena.shape_cells({"type": "sphere", "size_ft": 20}, (0, 0), (15, 15), size)
    check("a 20-foot-radius sphere covers about 50 cells and is round", 45 <= len(sphere) <= 85 and (15, 11) in sphere and (11, 11) not in sphere and (19, 15) in sphere)
    check("a sphere is cut at the edge of the map", all(0 <= x < 30 and 0 <= y < 30 for x, y in arena.shape_cells({"type": "sphere", "size_ft": 20}, (0, 0), (1, 1), size)))
    check("one target is one cell", arena.shape_cells({"type": "single", "size_ft": 0}, (0, 0), (4, 4), size) == {(4, 4)})
    cone = arena.shape_cells({"type": "cone", "size_ft": 30}, (5, 10), (20, 10), size)
    check("a 30-foot cone points at the aim, is 6 long, and widens", (6, 10) in cone and (11, 10) in cone and (12, 10) not in cone and (10, 12) in cone
          and (10, 14) not in cone and (5, 10) not in cone and (4, 10) not in cone)
    diagonal = arena.shape_cells({"type": "cone", "size_ft": 30}, (5, 5), (15, 15), size)
    check("a cone works on the diagonal", (8, 8) in diagonal and (8, 4) not in diagonal and (4, 8) not in diagonal)
    line = arena.shape_cells({"type": "line", "size_ft": 30}, (2, 2), (20, 2), size)
    check("a line is one cell wide and as long as the shape", line == {(x, 2) for x in range(3, 9)})
    cube = arena.shape_cells({"type": "cube", "size_ft": 15}, (0, 0), (10, 10), size)
    check("a 15-foot cube is about 3 by 3", len(cube) in (9, 25) and (10, 10) in cube)
    check("a cylinder is a sphere", arena.shape_cells({"type": "cylinder", "size_ft": 20}, (0, 0), (15, 15), size) == sphere)


if __name__ == "__main__":
    for t in (test_shapes_from_text, test_monsters, test_spells, test_uses, test_area):
        t()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
