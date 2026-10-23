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

from dnd_cli import dice, sheet as sheets  # noqa: E402
from dnd_cli.combat import records  # noqa: E402
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
    ok = all(json.dumps(Item(copy.deepcopy(r)).row) == json.dumps(r) for r in rows)
    check(f"{len(rows)} rows come back byte for byte, unknown fields and key order kept", ok)
    row = {"name": "Rope"}
    Item(row).view()
    Item(row).effects()
    check("reading an item adds no key to the row", row == {"name": "Rope"})
    check("view of a bare row has the old defaults", Item({}).view() == {
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


def test_ability_and_effects() -> None:
    print("ability and effects")
    rec = {"mods": {"dexterity": 3}}
    heal = Item({"name": "Potion of Healing", "quantity": 2}).ability(rec)
    check("heal card", heal and heal["kind"] == "heal" and heal["heal"] == "2d4+2" and heal["qty"] == 2 and heal["id"] == "item:Potion of Healing")
    bomb = Item({"name": "Acid"}).ability(rec)
    check("throw card uses DEX", bomb and bomb["to_hit"] == 3 and bomb["damage"] == [["2d6", "acid"]] and bomb["attack"]["range_ft"] == 20)
    own = Item({"name": "Acid", "profile": {"kind": "heal", "heal": "1d4"}}).ability(rec)
    check("the row's profile wins over the table", own and own["kind"] == "heal")
    check("no profile, no card", Item({"name": "Rope"}).ability(rec) is None)
    ring = Item({"name": "Ring", "effects": ["warding"], "equipped": True})
    check("effects count while equipped only", ring.effects() == ["warding"] and Item({"name": "Ring", "effects": ["warding"]}).effects() == [])


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
    check("needs_base", sword.needs_base and not Item({"name": "x", "type": "ring", "base": "y"}).needs_base)
    sh["weapons"].append({"name": "+1 Sword", "item": "+1 Sword", "attack_bonus": 4, "damage": "1d8", "equipped": False})
    sh["weapons"].append({"name": "Longsword", "attack_bonus": 5, "damage": "1d8", "equipped": False})
    check("equip gives one line", sword.equip(sh) == "Tester: +1 Sword equipped")
    check("equip without base data sets the flag and the linked attack", sword.equipped and sh["weapons"][0]["equipped"] and not sh["weapons"][1]["equipped"])
    check("unequip gives one line", sword.unequip(sh) == "Tester: +1 Sword put away")
    check("unequip puts both away", not sword.equipped and not sh["weapons"][0]["equipped"])
    sh["weapons"].pop()
    longsword = {"name": "Longsword", "equipment_category": {"index": "weapon"}, "damage": {"damage_dice": "1d8", "damage_type": {"index": "slashing"}}, "properties": []}
    sword.equip(sh, longsword)
    check("equip with base data makes the attack under the item's name",
          sh["weapons"][-1]["name"] == "+1 Sword" and sh["weapons"][-1]["attack_bonus"] == 4 and len([w for w in sh["weapons"] if w["name"] == "+1 Sword"]) == 1)
    check("profile is checked", raises(lambda: sword.set_profile({"kind": "heal"})) and raises(lambda: sword.set_profile({"kind": "x"})))


def test_link() -> None:
    print("gear is joined to its row by the item field")
    sh = sheet()
    sh.update(proficiency_bonus=2, ability_scores={"strength": 14, "dexterity": 14, "constitution": 10})
    rapier = {"name": "Rapier", "equipment_category": {"index": "weapon"}, "weapon_range": "Melee", "properties": [{"index": "finesse"}],
              "damage": {"damage_dice": "1d8", "damage_type": {"index": "piercing"}}}
    items.add(sh, "Flame Rapier", 1, type="weapon", base="Rapier", effects=["flame-edge"])
    line = items.get(sh, "Flame Rapier").equip(sh, rapier)
    check("equip_base gives one line and links the attack to its row", isinstance(line, str) and sh["weapons"][0]["item"] == "Flame Rapier")
    sh["weapons"][0]["name"] = "Ember"
    atk = items.attacks(sh)
    check("a renamed attack is still the attack of its row", [a["name"] for a in atk] == ["Ember", "Unarmed Strike"] and atk[0]["equipped"])
    items.get(sh, "Flame Rapier").unequip(sh)
    check("unequip finds the attack by the link, not the name", not sh["weapons"][0]["equipped"] and not items.attacks(sh)[0]["equipped"])
    check("wielded: the equipped one, else the first, else none", records.wielded([{"name": "a"}, {"name": "b", "equipped": True}])["name"] == "b"
          and records.wielded([{"name": "a"}, {"name": "b"}])["name"] == "a" and records.wielded([]) is None)

    sh["inventory"][0]["equipped"] = True
    sh["weapons"][0]["equipped"] = True
    sh.update(hp={"current": 9, "max": 9, "temp": 0}, ability_scores={"strength": 14, "dexterity": 14, "constitution": 10})
    sheets.level_up(sh, {"level": 2, "prof_bonus": 2, "features": []}, 8, "avg", {"dexterity": 2})
    w = sh["weapons"][0]
    check("level_up keeps the link and sets the bonuses", w["item"] == "Flame Rapier" and w["name"] == "Ember" and w["damage"] == "1d8+3" and w["attack_bonus"] == 5)
    view, _ = items.gear_view(sh)
    check("the UI view takes equipped from the row", view[0]["equipped"] is True)
    sh["inventory"][0]["equipped"] = False
    check("...and the row wins when they differ", items.gear_view(sh)[0][0]["equipped"] is False and sh["weapons"][0]["equipped"] is True)

    old = {"weapons": [{"name": "Flame Rapier", "damage": "1d8"}, {"name": "Stick"}], "armor": {"name": "Flame Rapier"},
           "inventory": [{"name": "Flame Rapier"}]}
    items.link_gear(old)
    check("an old sheet gets links where the names are the same row", old["weapons"][0]["item"] == "Flame Rapier" and "item" not in old["weapons"][1]
          and old["armor"]["item"] == "Flame Rapier")


def test_armor() -> None:
    print("armor")
    sh = sheet()
    sh["ability_scores"]["constitution"] = 10
    leather = {"name": "Leather Armor", "equipment_category": {"index": "armor"}, "armor_category": "Light", "armor_class": {"base": 11, "dex_bonus": True}}
    plate = {"name": "Plate Armor", "equipment_category": {"index": "armor"}, "armor_category": "Heavy", "armor_class": {"base": 18, "dex_bonus": False}}
    shield = {"name": "Shield", "equipment_category": {"index": "armor"}, "armor_category": "Shield"}
    items.add(sh, "Dragon Plate", 1, type="armor", base="Plate Armor", effects=["magic-armor-2"])
    items.equip_base(sh, leather)
    items.equip_base(sh, shield)
    items.get(sh, "Dragon Plate").equip(sh, plate)
    leather_row, plate_row = items.get(sh, "Leather Armor"), items.get(sh, "Dragon Plate")
    check("new armor un-equips the old row and links itself", not leather_row.equipped and plate_row.equipped
          and sh["armor"]["item"] == "Dragon Plate" and sh["armor_class"] == 20)
    plate_row.unequip(sh)
    check("putting the armor away clears its flag on the armor entry too", sh["armor"]["equipped"] is False and not plate_row.equipped)
    check("the shield stays", items.shield_equipped(sh))
    items.add(sh, "Mithral Vest", 1, type="armor")  # no base: only the flag
    items.get(sh, "Dragon Plate").equip(sh, plate)
    items.get(sh, "Mithral Vest").equip(sh)
    check("armor with no base still replaces the worn armor", items.get(sh, "Mithral Vest").equipped
          and not items.get(sh, "Dragon Plate").equipped and sh["armor"]["equipped"] is False)


def test_dice() -> None:
    print("dice helpers")
    check("mods: six abilities, 10 by default", dice.mods({"strength": 16}) == {"strength": 3, "dexterity": 0, "constitution": 0, "intelligence": 0, "wisdom": 0, "charisma": 0})
    check("with_bonus", dice.with_bonus("1d8 + 2", 3) == "1d8+3" and dice.with_bonus("1d8-1", 0) == "1d8" and dice.with_bonus("2d6", -1) == "2d6-1")


if __name__ == "__main__":
    for t in (test_round_trip, test_hand_edit_survives, test_ability_and_effects, test_inventory, test_link, test_armor, test_dice):
        t()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
