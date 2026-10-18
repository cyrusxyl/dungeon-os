"""Checks for dnd_cli/item.py: the typed layer over the inventory rows of a sheet.

Run from the repo root:  .venv/bin/python tests/test_item.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dnd_cli import item as items  # noqa: E402
from dnd_cli.errors import RulesError  # noqa: E402
from dnd_cli.item import Item  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}{'' if cond or not detail else f'  ({detail})'}")


def raises(fn) -> bool:
    try:
        fn()
    except RulesError:
        return True
    return False


def sheet() -> dict:
    return {"name": "Tester", "level": 1, "armor_class": 12, "ability_scores": {"strength": 14, "dexterity": 14},
            "inventory": [], "weapons": []}


def test_round_trip() -> None:
    print("row round trip")
    rows = [{"name": "Rope"}, {"name": "Gold Pieces", "quantity": 5}, {"zeta": 1, "name": "X", "alpha": [1], "equipped": False},
            {"name": "+1 Sword", "quantity": 1, "type": "weapon", "base": "Longsword", "effects": ["magic-weapon-1"], "dm_note": "hand edit"}]
    for pattern in (REPO / "tests" / "fixtures", REPO / "game" / "campaigns"):
        for f in pattern.glob("**/characters/*.json"):
            rows += json.loads(f.read_text()).get("inventory", [])
    ok = all(json.dumps(Item.from_row(copy.deepcopy(r)).to_row()) == json.dumps(r) for r in rows)
    check(f"{len(rows)} rows come back byte for byte, unknown fields and key order kept", ok)
    row = {"name": "Rope"}
    Item.from_row(row).view()
    Item.from_row(row).effects()
    check("reading an item adds no key to the row", row == {"name": "Rope"})
    check("view of a bare row has the old defaults", Item.from_row({}).view() == {
        "name": None, "quantity": 1, "weight": 0, "equipped": False, "description": "", "rarity": None, "effects": []})


def test_hand_edit_survives() -> None:
    print("a hand edit survives the changes")
    sh = sheet()
    row = {"zeta": 1, "name": "+1 Sword", "dm_note": "x", "type": "weapon", "base": "Longsword"}
    sh["inventory"].append(copy.deepcopy(row))
    longsword = {"name": "Longsword", "equipment_category": {"index": "weapon"}, "damage": {"damage_dice": "1d8", "damage_type": {"index": "slashing"}}, "properties": []}
    items.add(sh, "+1 Sword", 1, "hums")
    it = items.get(sh, "+1 Sword")
    it.equip(sh, longsword)
    it.unequip(sh)
    it.set_profile({"kind": "heal", "heal": "1d4"})
    after = sh["inventory"][0]
    check("unknown keys are still there", after["zeta"] == 1 and after["dm_note"] == "x")
    check("old keys keep their order, new keys come last", list(after)[:5] == list(row) and list(after)[5:] == ["quantity", "description", "equipped", "profile"],
          str(list(after)))


def test_kinds() -> None:
    print("kinds")
    kind = lambda **r: Item.from_row({"name": r.pop("name", "Thing"), **r}).kind  # noqa: E731
    check("weapon and armor by type", kind(type="weapon") == "weapon" and kind(type="armor") == "armor")
    check("a table potion is a consumable", kind(name="Potion of Healing") == "consumable")
    check("a table bomb is a throwable", kind(name="Acid") == "throwable")
    check("a profile on the row gives the kind", kind(profile={"kind": "heal", "heal": "1d4"}) == "consumable"
          and kind(profile={"kind": "throw", "range_ft": 20, "damage": ["1d4", "fire"]}) == "throwable")
    check("a ring or an item with effects is a wearable", kind(type="ring") == "wearable" and kind(effects=["warding"]) == "wearable")
    check("anything else is an item", kind() == "item")


def test_ability_and_effects() -> None:
    print("ability and effects")
    rec = {"mods": {"dexterity": 3}}
    heal = Item.from_row({"name": "Potion of Healing", "quantity": 2}).ability(rec)
    check("heal card", heal and heal["kind"] == "heal" and heal["heal"] == "2d4+2" and heal["qty"] == 2 and heal["id"] == "item:Potion of Healing")
    bomb = Item.from_row({"name": "Acid"}).ability(rec)
    check("throw card uses DEX", bomb and bomb["to_hit"] == 3 and bomb["damage"] == [["2d6", "acid"]] and bomb["attack"]["range_ft"] == 20)
    own = Item.from_row({"name": "Acid", "profile": {"kind": "heal", "heal": "1d4"}}).ability(rec)
    check("the row's profile wins over the table", own and own["kind"] == "heal")
    check("no profile, no card", Item.from_row({"name": "Rope"}).ability(rec) is None)
    ring = Item.from_row({"name": "Ring", "effects": ["warding"], "equipped": True})
    check("effects count while equipped only", ring.effects() == ["warding"] and Item.from_row({"name": "Ring", "effects": ["warding"]}).effects() == [])


def test_inventory() -> None:
    print("inventory and equip")
    sh = sheet()
    items.add(sh, "Rope", 2)
    items.add(sh, "Rope", 1, "50 ft")
    check("add stacks and updates", sh["inventory"] == [{"name": "Rope", "quantity": 3, "description": "50 ft"}])
    check("add refuses 0", raises(lambda: items.add(sh, "Rope", 0)))
    check("remove refuses too many", raises(lambda: items.remove(sh, "Rope", 4)))
    check("remove the last one drops the row", "no Rope left" in items.remove(sh, "Rope", 3) and sh["inventory"] == [])
    check("get names the inventory", raises(lambda: items.get(sh, "Ghost")))
    items.add(sh, "+1 Sword", 1, type="weapon", base="Longsword", effects=["magic-weapon-1"])
    sword = items.get(sh, "+1 sword")
    check("needs_base", sword.needs_base and not Item.from_row({"name": "x", "type": "ring", "base": "y"}).needs_base)
    sh["weapons"].append({"name": "+1 Sword", "attack_bonus": 4, "damage": "1d8", "equipped": False})
    sword.equip(sh)
    check("equip without base data sets the flag and the attack", sword.equipped and sh["weapons"][0]["equipped"])
    sword.unequip(sh)
    check("unequip puts both away", not sword.equipped and not sh["weapons"][0]["equipped"])
    longsword = {"name": "Longsword", "equipment_category": {"index": "weapon"}, "damage": {"damage_dice": "1d8", "damage_type": {"index": "slashing"}}, "properties": []}
    sword.equip(sh, longsword)
    check("equip with base data makes the attack under the item's name",
          sh["weapons"][-1]["name"] == "+1 Sword" and sh["weapons"][-1]["attack_bonus"] == 4 and len([w for w in sh["weapons"] if w["name"] == "+1 Sword"]) == 1)
    check("profile is checked", raises(lambda: sword.set_profile({"kind": "heal"})) and raises(lambda: sword.set_profile({"kind": "x"})))


if __name__ == "__main__":
    for t in (test_round_trip, test_hand_edit_survives, test_kinds, test_ability_and_effects, test_inventory):
        t()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
