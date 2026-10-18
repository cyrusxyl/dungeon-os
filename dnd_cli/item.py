"""Items: one typed layer over the rows of `inventory` in a character sheet.

The sheet stays the save file. An `Item` wraps one row (it does not copy it), so a change made through the item
is a change to the sheet, and a field this module does not know stays in the row. `to_row()` gives the row back.
Nothing here loads or saves a file: the caller does, through dnd_cli.character.

A row is an *instance*: name, quantity, equipped, rarity, and a reference to what it is (`type`, `base`).
The *definition* comes from the 5e API data (`equip_base`), from stage/data/items.json (a profile), or from the row
itself (a field of the row wins: a `profile` is a DM ruling). See combat-board.md, section 6.

New item kinds are added here and nowhere else. This module imports no other rules module, so any of them may import it.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

from dnd_cli import dice
from dnd_cli.errors import RulesError

ITEMS_PATH = Path(__file__).resolve().parents[1] / "stage" / "data" / "items.json"
PROFILE_KINDS = ("heal", "throw")
GOLD = "Gold Pieces"


@cache
def table() -> dict:
    """The profiles of common items, keyed by the lower-case name."""
    return {k: v for k, v in json.loads(ITEMS_PATH.read_text()).items() if not k.startswith("_")}


class Item:
    """One inventory row. `Item(row)` wraps it; `.row` is the same dict."""

    def __init__(self, row: dict):
        self.row = row

    # -- what the row says ---------------------------------------------------

    @property
    def name(self) -> str:
        return self.row.get("name", "")

    @property
    def quantity(self) -> int:
        return self.row.get("quantity", 1)

    @property
    def equipped(self) -> bool:
        return bool(self.row.get("equipped"))

    @property
    def perks(self) -> list[str]:
        """The effect presets the item has, worn or not."""
        return self.row.get("effects", [])

    @property
    def base(self) -> str | None:
        """The base item it is made from (Longsword, Plate Armor), if any."""
        return self.row.get("base")

    @property
    def needs_base(self) -> bool:
        """True when equipping takes the stats of a base item from the 5e API (a weapon or armor with a `base`)."""
        return bool(self.base) and self.row.get("type") in ("weapon", "armor")

    def profile(self) -> dict | None:
        """What it does on the board: the row's own profile, else the table's, else none."""
        p = self.row.get("profile") or table().get(self.name.lower())
        return p if p and p.get("kind") in PROFILE_KINDS else None

    # -- what it gives -------------------------------------------------------

    def effects(self) -> list[str]:
        """The effect presets it gives now: its own while it is equipped, none otherwise."""
        return list(self.perks) if self.equipped else []

    def ability(self, rec: dict) -> dict | None:
        """The hand card of the item (heal or throw), or None when it has no profile. `rec` is the combat record of the user."""
        p = self.profile()
        if p is None:
            return None
        base = {"id": f"item:{self.name}", "name": self.name, "cost": p.get("cost", "action"), "source": "item", "qty": self.quantity}
        if p["kind"] == "heal":
            return {**base, "kind": "heal", "heal": p["heal"], "text": f"x{base['qty']} · yourself or a creature next to you", "stat": f"heals {p['heal']}"}
        bonus = rec["mods"]["dexterity"]  # an improvised weapon: no proficiency
        expr, dtype = p["damage"]
        return {**base, "kind": "spell_attack", "spell_level": 0, "weapon": "improvised", "to_hit": bonus,
                "attack": {"bonus": bonus, "range_ft": p["range_ft"]}, "damage": [[expr, dtype]],
                "text": f"x{base['qty']} · Range {p['range_ft']} ft", "stat": f"{bonus:+d} · {expr} {dtype}"}

    def view(self) -> dict:
        """What the UI shows of the row."""
        r = self.row
        return {"name": r.get("name"), "quantity": self.quantity, "weight": r.get("weight", 0), "equipped": self.equipped,
                "description": r.get("description", ""), "rarity": r.get("rarity"), "effects": self.perks}

    # -- changes -------------------------------------------------------------

    def equip(self, sheet: dict, base: dict | None = None, proficient: bool = True) -> list[str]:
        """Wear or wield it. With the 5e data of its base (`needs_base`), a weapon becomes an attack under the item's name
        and armor sets the AC and takes off the armor it replaces. Without, it only gets the flag."""
        if base is not None and self.needs_base:
            return equip_base(sheet, base, proficient, self.name)
        return [self._flag(sheet, True)]

    def unequip(self, sheet: dict) -> list[str]:
        """Put it away. Its effects end. A weapon stays an attack that the character can use, like any weapon that is not wielded."""
        return [self._flag(sheet, False)]

    def _flag(self, sheet: dict, on: bool) -> str:
        self.row["equipped"] = on
        for w in sheet.get("weapons", []):
            if w.get("name") == self.name:
                w["equipped"] = on
        return f"{sheet['name']}: {self.name} {'equipped' if on else 'put away'}"

    def set_profile(self, profile: dict) -> str:
        """Keep a profile on the row (a ruling the DM approved) and return its kind. The shape is in stage/data/items.json."""
        kind = profile.get("kind")
        if kind == "heal":
            need = {"heal": str}
        elif kind == "throw":
            need = {"range_ft": int, "damage": list}
        else:
            raise RulesError("a profile has kind heal or throw.")
        for key, typ in need.items():
            if not isinstance(profile.get(key), typ):
                raise RulesError(f"a {kind} profile needs {key}.")
        if kind == "throw" and len(profile["damage"]) != 2:
            raise RulesError('damage is ["1d6", "fire"]: dice and type.')
        if profile.get("cost", "action") not in ("action", "bonus"):
            raise RulesError("cost is action or bonus.")
        try:
            dice.parse(profile["heal"] if kind == "heal" else profile["damage"][0])
        except dice.DiceError as e:
            raise RulesError(str(e)) from None
        self.row["profile"] = profile
        return kind


# -- the inventory of a sheet ------------------------------------------------


def find(sheet: dict, name: str) -> Item | None:
    rows = sheet.setdefault("inventory", [])
    row = next((r for r in rows if r.get("name", "").lower() == name.lower()), None)
    return None if row is None else Item(row)


def get(sheet: dict, name: str) -> Item:
    found = find(sheet, name)
    if not found:
        have = ", ".join(r["name"] for r in sheet.get("inventory", [])) or "nothing"
        raise RulesError(f"{sheet['name']} has no {name!r}. Inventory: {have}.")
    return found


def items(sheet: dict) -> list[Item]:
    return [Item(r) for r in sheet.get("inventory", [])]


def add(sheet: dict, name: str, qty: int = 1, description: str = "", rarity: str | None = None, **gear) -> str:
    """Add an item, or add to its quantity. Giving it again with more detail updates it. `gear`: type, base, effects."""
    if qty < 1:
        raise RulesError("quantity must be 1 or more.")
    found = find(sheet, name)
    if found:
        row = found.row
        row["quantity"] = found.quantity + qty
    else:
        row = {"name": name, "quantity": qty}
        sheet["inventory"].append(row)
    for key, value in {"description": description, "rarity": rarity, **gear}.items():
        if value:
            row[key] = value  # giving an item again with more detail updates it
    return f"{sheet['name']}: {row['name']} x{row['quantity']}"


def remove(sheet: dict, name: str, qty: int = 1) -> str:
    item = get(sheet, name)
    if item.quantity < qty:
        raise RulesError(f"{sheet['name']} has only {item.quantity} {item.name}.")
    item.row["quantity"] = item.quantity - qty
    if item.row["quantity"] == 0:  # the schema has no zero quantities
        sheet["inventory"].remove(item.row)
        return f"{sheet['name']}: no {item.name} left"
    return f"{sheet['name']}: {item.name} x{item.quantity}"


def set_profile(sheet: dict, name: str, profile: dict) -> str:
    item = get(sheet, name)
    kind = item.set_profile(profile)
    return f"{sheet['name']}: {item.name} now does something in a fight ({kind})"


def shield_equipped(sheet: dict) -> bool:
    return any(i.equipped and i.name.lower() == "shield" for i in items(sheet))


# -- gear from the 5e data ---------------------------------------------------


def _mod(sheet: dict, ability: str) -> int:
    return dice.mod(sheet["ability_scores"].get(ability, 10))


def _weapon_ability(sheet: dict, props: list[str], ranged: bool) -> str:
    if "finesse" in props or "martial arts" in props:
        return "dexterity" if _mod(sheet, "dexterity") >= _mod(sheet, "strength") else "strength"
    return "dexterity" if ranged else "strength"


def with_bonus(expr: str, bonus: int) -> str:
    base = re.sub(r"[+-]\d+$", "", expr.replace(" ", ""))
    return base + (dice.signed(bonus) if bonus else "")


def equip_base(sheet: dict, base: dict, proficient: bool = True, as_name: str | None = None) -> list[str]:
    """Equip a weapon, armor, or shield from the 5e API data `base`. Only armor and shields change AC.
    `as_name`: the inventory row it is (a magic item made from this base): the attack or armor takes that name.

    Unarmored AC (a monk's 10 + DEX + WIS) is never recomputed: a shield adds 2 to it.
    """
    name = as_name or base["name"]
    category = base.get("equipment_category", {}).get("index", "")
    armor_cat = base.get("armor_category", "").lower()
    if armor_cat == "shield" and shield_equipped(sheet):
        return [f"{sheet['name']} already carries a shield: AC {sheet['armor_class']}"]
    shield = shield_equipped(sheet)
    if not find(sheet, name):
        add(sheet, name, 1)
    if category == "armor" and armor_cat != "shield" and sheet.get("armor"):  # new armor replaces the old: its perks end
        old = find(sheet, sheet["armor"].get("name", ""))
        if old:
            old.row["equipped"] = False
    find(sheet, name).row["equipped"] = True
    prof = sheet.get("proficiency_bonus", dice.prof_for_level(sheet["level"]))
    if category == "weapon":
        props = [p["index"] for p in base.get("properties", [])]
        abil = _weapon_ability(sheet, props, base.get("weapon_range") == "Ranged")
        dmg = base.get("damage") or {}
        bonus = _mod(sheet, abil) + (prof if proficient else 0)
        entry = {
            "name": name, "attack_bonus": bonus,
            "damage": with_bonus(dmg.get("damage_dice", "1"), _mod(sheet, abil)),
            "damage_type": dmg.get("damage_type", {}).get("index", ""),
            "properties": props, "equipped": True,
        }
        sheet["weapons"] = [w for w in sheet.get("weapons", []) if w.get("name") != name] + [entry]
        return [f"{sheet['name']} wields {name}: {dice.signed(bonus)} to hit, {entry['damage']} {entry['damage_type']}"]
    if armor_cat == "shield":
        sheet["armor_class"] += 2
        return [f"{sheet['name']} takes up a shield: AC {sheet['armor_class']}"]
    if category == "armor":
        ac = base.get("armor_class", {})
        cap = ac.get("max_bonus") if ac.get("dex_bonus") else 0  # None: no cap
        dex = _mod(sheet, "dexterity") if cap is None else min(_mod(sheet, "dexterity"), cap)
        sheet["armor"] = {"name": name, "type": armor_cat, "ac_bonus": ac.get("base", 10), "equipped": True}
        sheet["armor_class"] = ac.get("base", 10) + dex + (2 if shield else 0)
        line = f"{sheet['name']} wears {name}: AC {sheet['armor_class']}"
        if base.get("str_minimum") and sheet["ability_scores"]["strength"] < base["str_minimum"]:
            line += f" (STR under {base['str_minimum']}: speed -10 ft)"
        if base.get("stealth_disadvantage"):
            line += " (disadvantage on Stealth)"
        return [line]
    return [f"{sheet['name']} carries {name} (no attack or AC change)."]
