"""Items: one typed layer over the rows of `inventory` in a character sheet.

The sheet stays the save file. An `Item` wraps one row (it does not copy it), so a change made through the item
is a change to the sheet, and a field this module does not know stays in the row. `to_row()` gives the row back.
Nothing here loads or saves a file: the caller does, through dnd_cli.character.

A row is an *instance*: name, quantity, equipped, rarity, and a reference to what it is (`type`, `base`).
The *definition* comes from the 5e API data (`equip_base`), from core/data/items.json (a profile), or from the row
itself (a field of the row wins: a `profile` is a DM ruling). See combat-board.md, section 6.

A weapon or armor that comes from a row has an `item` field in `weapons[]` or `armor`: the name of its row. That
link, and not the name of the attack, tells which gear a perk or a flag belongs to. See `link_gear`.

New item kinds are added here and nowhere else. This module imports no other rules module, so any of them may import it.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

from dnd_cli import dice
from dnd_cli.errors import RulesError

ITEMS_PATH = Path(__file__).resolve().parents[1] / "core" / "data" / "items.json"
PROFILE_KINDS = ("heal", "throw")
GOLD = "Gold Pieces"


@cache
def profiles() -> dict:
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

    def has_weapon_effects(self, presets: dict) -> bool:
        """True when one of its effects is a weapon effect. `presets` is the effects.PRESETS mapping (this module does not import it)."""
        return any("weapon" in presets.get(e, {}) for e in self.perks)

    def profile(self) -> dict | None:
        """What it does on the board: the row's own profile, else the common-item profiles', else none."""
        p = self.row.get("profile") or profiles().get(self.name.lower())
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

    def equip(self, sheet: dict, base: dict | None = None, proficient: bool = True) -> str:
        """Wear or wield it. With the 5e data of its base (`needs_base`), a weapon becomes an attack under the item's name
        and armor sets the AC and takes off the armor it replaces. Without, it only gets the flag."""
        if base is not None and self.needs_base:
            return equip_base(sheet, base, proficient, self.name)
        if self.row.get("type") == "armor" and (old := find(sheet, (sheet.get("armor") or {}).get("item", ""))) and old.row is not self.row:
            old.unequip(sheet)  # one armor at a time, also when this one has no base: its perks end
        return self._flag(sheet, True)

    def weapon_warning(self, presets: dict) -> str | None:
        """A line for the DM when the item has weapon effects but no base, so no attack matches it."""
        if not self.base and self.has_weapon_effects(presets):
            return ("Warning: no attack matches it, so its weapon effects do nothing. Give it a base: "
                    "`character item <who> add \"<item>\" --base <Longsword>`.")
        return None

    def unequip(self, sheet: dict) -> str:
        """Put it away. Its effects end. A weapon stays an attack that the character can use, like any weapon that is not wielded."""
        return self._flag(sheet, False)

    def _flag(self, sheet: dict, on: bool) -> str:
        self.row["equipped"] = on
        for gear in [*sheet.get("weapons", []), sheet.get("armor") or {}]:
            if gear.get("item") == self.name:
                gear["equipped"] = on
        return f"{sheet['name']}: {self.name} {'equipped' if on else 'put away'}"

    def set_profile(self, profile: dict) -> str:
        """Keep a profile on the row (a ruling the DM approved) and return its kind. The shape is in core/data/items.json."""
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
    row = _put(sheet, name, qty, description, rarity, **gear).row
    return f"{sheet['name']}: {row['name']} x{row['quantity']}"


def _put(sheet: dict, name: str, qty: int, description: str = "", rarity: str | None = None, **gear) -> Item:
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
    return Item(row)


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


def _weapon_ability(m: dict, props: list[str], ranged: bool) -> str:
    if "finesse" in props or "martial arts" in props:
        return "dexterity" if m["dexterity"] >= m["strength"] else "strength"
    return "dexterity" if ranged else "strength"


def equip_base(sheet: dict, base: dict, proficient: bool = True, as_name: str | None = None) -> str:
    """Equip a weapon, armor, or shield from the 5e API data `base`. Only armor and shields change AC.
    `as_name`: the inventory row it is (a magic item made from this base): the attack or armor takes that name.
    The attack or armor keeps that name in its `item` field.

    Unarmored AC (a monk's 10 + DEX + WIS) is never recomputed: a shield adds 2 to it.
    """
    name = as_name or base["name"]
    category = base.get("equipment_category", {}).get("index", "")
    armor_cat = base.get("armor_category", "").lower()
    shield = shield_equipped(sheet)
    if armor_cat == "shield" and shield:
        return f"{sheet['name']} already carries a shield: AC {sheet['armor_class']}"
    it = find(sheet, name) or _put(sheet, name, 1)
    if category == "armor" and armor_cat != "shield" and (old := find(sheet, (sheet.get("armor") or {}).get("item", ""))):
        old.unequip(sheet)  # new armor replaces the old: its perks end
    it._flag(sheet, True)
    m = dice.mods(sheet["ability_scores"])
    prof = sheet.get("proficiency_bonus", dice.prof_for_level(sheet["level"]))
    if category == "weapon":
        props = [p["index"] for p in base.get("properties", [])]
        abil = _weapon_ability(m, props, base.get("weapon_range") == "Ranged")
        dmg = base.get("damage") or {}
        bonus = m[abil] + (prof if proficient else 0)
        entry = {
            "name": name, "item": name, "attack_bonus": bonus,
            "damage": dice.with_bonus(dmg.get("damage_dice", "1"), m[abil]),
            "damage_type": dmg.get("damage_type", {}).get("index", ""),
            "properties": props, "equipped": True,
        }
        sheet["weapons"] = [w for w in sheet.get("weapons", []) if w.get("name") != name] + [entry]
        return f"{sheet['name']} wields {name}: {dice.signed(bonus)} to hit, {entry['damage']} {entry['damage_type']}"
    if armor_cat == "shield":
        sheet["armor_class"] += 2
        return f"{sheet['name']} takes up a shield: AC {sheet['armor_class']}"
    if category == "armor":
        ac = base.get("armor_class", {})
        cap = ac.get("max_bonus") if ac.get("dex_bonus") else 0  # None: no cap
        dex = m["dexterity"] if cap is None else min(m["dexterity"], cap)
        sheet["armor"] = {"name": name, "item": name, "type": armor_cat, "ac_bonus": ac.get("base", 10), "equipped": True}
        sheet["armor_class"] = ac.get("base", 10) + dex + (2 if shield else 0)
        line = f"{sheet['name']} wears {name}: AC {sheet['armor_class']}"
        if base.get("str_minimum") and sheet["ability_scores"]["strength"] < base["str_minimum"]:
            line += f" (STR under {base['str_minimum']}: speed -10 ft)"
        if base.get("stealth_disadvantage"):
            line += " (disadvantage on Stealth)"
        return line
    return f"{sheet['name']} carries {name} (no attack or AC change)."


def link_gear(sheet: dict) -> None:
    """Give each weapon and armor that has no `item` link, and is named like an inventory row, the link to that row.
    For sheets from before the link existed. A weapon with no row has no link, and so no gear perks."""
    names = {i.name for i in items(sheet)}
    for gear in [*sheet.get("weapons", []), sheet.get("armor") or {}]:
        if "item" not in gear and gear.get("name") in names:
            gear["item"] = gear["name"]


# -- the attacks of a character ----------------------------------------------


def geometry(text: str, ranged_only: bool = False) -> dict:
    """How far an attack reaches, from its text: `reach 5 ft.` (melee) and `range 80/320 ft.` or `(range 150/600)` (ranged), in feet.

    A weapon with neither word is a melee weapon with reach 5. `ranged_only` is for ammunition weapons.
    """
    out = {}
    if m := re.search(r"reach (\d+) ft", text):
        out["reach_ft"] = int(m.group(1))
    if m := re.search(r"range (\d+)(?:/\d+)?", text):
        out["range_ft"] = int(m.group(1))
    if not out and not ranged_only:
        out["reach_ft"] = 5
    return out


def attacks(sheet: dict) -> list[dict]:
    """The attacks of a character as the combat record has them: each weapon, then Unarmed Strike, then the spell attack."""
    out = []
    for w in sheet.get("weapons", []):
        props = " ".join(w.get("properties", []))
        reach = geometry(props, ranged_only="ammunition" in props)
        if "ammunition" not in props:
            reach["reach_ft"] = 10 if "reach" in props.split() else 5  # a thrown weapon is also a melee weapon
        out.append({"name": w["name"], "bonus": w.get("attack_bonus", 0), "equipped": bool(w.get("equipped")), **reach,
                    **({"thrown": True} if "thrown" in props.split() else {}),
                    "damage": [[w["damage"], w.get("damage_type", "")]] if w.get("damage") else []})
    # Bare fists, as in Baldur's Gate 3: 1 + Strength modifier, bludgeoning.
    strength = dice.mods(sheet.get("ability_scores", {}))["strength"]
    out.append({"name": "Unarmed Strike", "bonus": strength + sheet.get("proficiency_bonus", 2), "reach_ft": 5,
                "damage": [[f"1{dice.signed(strength)}", "bludgeoning"]], "plain": True})
    spell = sheet.get("spellcasting") or {}
    if "spell_attack_bonus" in spell:
        out.append({"name": "spell", "bonus": spell["spell_attack_bonus"], "damage": [], "plain": True})
    return out


def gear_view(sheet: dict) -> tuple[list[dict], dict | None]:
    """The weapons and the armor for the UI. A piece of gear with an `item` link is worn as its row says."""
    rows = {i.name: i for i in items(sheet)}

    def one(gear: dict) -> dict:
        row = rows.get(gear.get("item"))
        return {**gear, "equipped": row.equipped} if row else gear

    return [one(w) for w in sheet.get("weapons", [])], one(sheet["armor"]) if sheet.get("armor") else None


def retotal_weapons(sheet: dict, old_mods: dict, old_prof: int, new_mods: dict, prof: int) -> None:
    """Level-up: set the attack bonus and damage bonus of each weapon for new modifiers and a new proficiency bonus.
    A weapon keeps its ability and its proficiency (none, proficient, expertise), as its old totals show them.
    The weapon changes in place, so its `item` link stays."""
    for w in sheet.get("weapons", []):
        abil = _stored_ability(w, old_mods)
        mult = dice.multiple(w.get("attack_bonus", 0), old_mods[abil], old_prof)
        w["attack_bonus"] = new_mods[abil] + mult * prof
        if w.get("damage"):
            w["damage"] = dice.with_bonus(w["damage"], new_mods[abil])


def _stored_ability(weapon: dict, old_mods: dict) -> str:
    """The ability a stored weapon uses: the one whose modifier is its damage bonus (DEX on a tie)."""
    flat = dice.flat_bonus(weapon.get("damage", ""))
    for abil in ("dexterity", "strength"):
        if old_mods[abil] == flat:
            return abil
    props = [p.lower() for p in weapon.get("properties", [])]
    ranged = "ammunition" in props or any(k in weapon.get("name", "").lower() for k in ("bow", "sling", "dart"))
    return "dexterity" if ranged or "finesse" in props else "strength"
