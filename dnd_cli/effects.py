"""Active effects: bonuses and advantage that the rules commands add to a roll.

A player (in the stage) or the DM (`dnd-cli effect add`) puts an effect on a
character. The next `check`, `save` or `attack` for that character applies it:
the bonus die is rolled here, so the DM never adds it in its head, and the
stage shows it in the roll window. An effect with `use: next` is spent by the
roll that applies it; `use: kept` stays until it is removed.

A preset has one or more of these parts:
- `bonus` (a die) or `mode` (advantage, disadvantage): added to the d20 of the rolls in `on`.
- `flat`: a number added to the d20 of the rolls in `on`. `only` limits it to rolls with one of
  these tags: the ability of the save or check, or the skill of the check.
- `weapon`: for weapon attacks only (not Unarmed Strike, spell or improvised attacks). `hit` and `dmg` are flat
  numbers, `crit` is the lowest d20 that is a critical hit, `extra` is [dice, damage type] added on a hit, and
  `vs` limits the preset to targets whose creature type contains one of these words.
- `ac`, `resist` and `reduce`: Armor Class, damage resistances, and flat damage reduction ({damage type or "all": n})
  of a player character.
Loot perks (stage/data/perks.json) name presets with these parts.

Effects live in `{campaign}/stage/effects.json` as `{character id: [preset id]}`.
They are not in `state.json`: the rules commands load and save the whole state
file, and the stage writes effects while the DM is idle.

Worn gear adds effects too. An inventory item with `equipped: true` and an `effects` list
gives those presets while it is equipped. Nothing is stored for them, so unequip removes them.
Two equipped items with the same perk both count. A `weapon` part of an item applies only to
the attack whose name words are all in the item name ("Longsword" in "+1 Longsword of Flame").
"""

from __future__ import annotations

import random
import re
from pathlib import Path

from dnd_cli import character, dice
from stage.files import read_json, write_json

ROLLS = ("check", "save", "attack")

def _gear(label: str, info: str, **parts) -> dict:
    """A preset from an item perk: it stays until removed and needs no concentration."""
    return {"label": label, "info": info, "on": parts.pop("on", ()), "use": "kept", "concentration": False, **parts}


# label, what it adds, which rolls it touches, how long it lasts, and whether the caster concentrates on it.
PRESETS: dict[str, dict] = {
    "guidance": {"label": "Guidance", "bonus": "1d4", "on": ("check",), "use": "next", "concentration": True,
                 "info": "+1d4 to the next ability check"},
    "bless": {"label": "Bless", "bonus": "1d4", "on": ("attack", "save"), "use": "kept", "concentration": True,
              "info": "+1d4 to attack rolls and saving throws"},
    "bane": {"label": "Bane", "bonus": "-1d4", "on": ("attack", "save"), "use": "kept", "concentration": True,
             "info": "-1d4 to attack rolls and saving throws"},
    "bardic-inspiration": {"label": "Bardic Inspiration", "bonus": "1d6", "on": ROLLS, "use": "next",
                           "concentration": False, "info": "+1d6 to one check, save or attack"},
    "resistance": {"label": "Resistance", "bonus": "1d4", "on": ("save",), "use": "next", "concentration": True,
                   "info": "+1d4 to the next saving throw"},
    "advantage": {"label": "Advantage", "mode": "advantage", "on": ROLLS, "use": "next", "concentration": False,
                  "info": "Roll two d20 and keep the higher one"},
    "disadvantage": {"label": "Disadvantage", "mode": "disadvantage", "on": ROLLS, "use": "next",
                     "concentration": False, "info": "Roll two d20 and keep the lower one"},
    # Item perks. The caster of Bless concentrates; a worn item does not, so Blessed is its own preset.
    "blessed": _gear("Blessed", "+1d4 to attack rolls and saving throws, from an item", bonus="1d4", on=("attack", "save")),
    "magic-weapon-1": _gear("+1 Weapon", "+1 to attack and damage rolls with a weapon", weapon={"hit": 1, "dmg": 1}),
    "magic-weapon-2": _gear("+2 Weapon", "+2 to attack and damage rolls with a weapon", weapon={"hit": 2, "dmg": 2}),
    "magic-weapon-3": _gear("+3 Weapon", "+3 to attack and damage rolls with a weapon", weapon={"hit": 3, "dmg": 3}),
    "keen-edge": _gear("Keen", "Weapon attacks are critical hits on a natural 19 or 20", weapon={"crit": 19}),
    "flame-edge": _gear("Flame", "+1d4 fire damage on a weapon hit", weapon={"extra": ("1d4", "fire")}),
    "frost-edge": _gear("Frost", "+1d4 cold damage on a weapon hit", weapon={"extra": ("1d4", "cold")}),
    "storm-edge": _gear("Storm", "+1d4 lightning damage on a weapon hit", weapon={"extra": ("1d4", "lightning")}),
    "purging-edge": _gear("Purging", "+1d6 radiant damage on a weapon hit against undead and fiends",
                          weapon={"extra": ("1d6", "radiant"), "vs": ("undead", "fiend")}),
    "magic-armor-1": _gear("+1 Armor", "+1 Armor Class", ac=1),
    "magic-armor-2": _gear("+2 Armor", "+2 Armor Class", ac=2),
    "warding": _gear("Warding", "+1 to saving throws", flat=1, on=("save",)),
    "protection": _gear("Protection", "+1 Armor Class and +1 to saving throws", flat=1, ac=1, on=("save",)),
    "might": _gear("Might", "+1 to Strength saves and Strength checks", flat=1, only=("strength",), on=("save", "check")),
    "agility": _gear("Agility", "+1 to Dexterity saves and Dexterity checks", flat=1, only=("dexterity",), on=("save", "check")),
    "vigor": _gear("Vigor", "+1 to Constitution saves and Constitution checks", flat=1, only=("constitution",), on=("save", "check")),
    "cushioning": _gear("Cushioning", "1 less damage from each piercing, slashing and bludgeoning hit",
                        reduce={"piercing": 1, "slashing": 1, "bludgeoning": 1}),
    "unyielding": _gear("Unyielding", "2 less damage from every hit", reduce={"all": 2}),
    "fire-ward": _gear("Fire Ward", "Resistance to fire damage", resist=("fire",)),
    "cold-ward": _gear("Cold Ward", "Resistance to cold damage", resist=("cold",)),
    "poison-ward": _gear("Poison Ward", "Resistance to poison damage", resist=("poison",)),
}
NO_WEAPON = {"hit": [], "dmg": 0, "crit": 20, "extra": []}


def path(campaign_dir: Path) -> Path:
    return campaign_dir / "stage" / "effects.json"


def load(campaign_dir: Path) -> dict[str, list[str]]:
    data = read_json(path(campaign_dir)) or {}
    return {cid: [e for e in ids if e in PRESETS] for cid, ids in data.items() if isinstance(ids, list)}


def stored(campaign_dir: Path, cid: str) -> list[str]:
    return load(campaign_dir).get(cid, [])


def _words(name: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", name.lower()))


def worn(campaign_dir: Path, cid: str) -> list[tuple[str, str]]:
    """(preset id, item name) for each effect of an equipped item. A sheet that is missing gives none."""
    sheet = read_json(character.character_path(campaign_dir, cid)) or {}
    return [(e, i.get("name", "")) for i in sheet.get("inventory", []) if i.get("equipped")
            for e in i.get("effects", []) if e in PRESETS]


def active(campaign_dir: Path, cid: str) -> list[str]:
    """The stored effects, then the effects of worn gear."""
    return stored(campaign_dir, cid) + [e for e, _ in worn(campaign_dir, cid)]


def _save(campaign_dir: Path, data: dict[str, list[str]]) -> None:
    write_json(path(campaign_dir), {cid: ids for cid, ids in data.items() if ids})


def add(campaign_dir: Path, cid: str, preset: str) -> None:
    """Put an effect on a character. Concentration belongs to the caster, so the target may hold several."""
    if preset not in PRESETS:
        raise ValueError(f"no effect {preset!r}. Effects: {', '.join(PRESETS)}.")
    data = load(campaign_dir)
    data[cid] = [e for e in data.get(cid, []) if e != preset] + [preset]
    _save(campaign_dir, data)


def remove(campaign_dir: Path, cid: str, preset: str) -> None:
    data = load(campaign_dir)
    data[cid] = [e for e in data.get(cid, []) if e != preset]
    _save(campaign_dir, data)


def apply(campaign_dir: Path, cid: str, kind: str, rng: random.Random | None = None,
          skip: tuple[str, ...] | list[str] = (), tags: tuple[str, ...] = ()) -> dict:
    """What the character's effects add to one roll of `kind`: advantage, disadvantage, bonus dice, flat bonuses.

    Spends the `next` effects it used. `skip` names effects the player left off this roll.
    `tags` are what the roll is about (its ability and skill); an effect with `only` needs one of them.
    """
    rng = rng or random
    out: dict = {"adv": False, "dis": False, "bonus": [], "flat": [], "used": []}
    ids = stored(campaign_dir, cid)
    for eid in ids + [e for e, _ in worn(campaign_dir, cid)]:
        spec = PRESETS[eid]
        if kind not in spec["on"] or eid in skip or (spec.get("only") and not set(spec["only"]) & set(tags)):
            continue
        out["used"].append(eid)
        if spec.get("mode") == "advantage":
            out["adv"] = True
        elif spec.get("mode") == "disadvantage":
            out["dis"] = True
        elif "flat" in spec:
            out["flat"].append({"label": spec["label"], "value": spec["flat"]})
        elif "bonus" in spec:
            sign = -1 if spec["bonus"].startswith("-") else 1
            expr = spec["bonus"].lstrip("-")
            total, groups = dice.roll(expr, rng)
            out["bonus"].append({"label": spec["label"], "die": spec["bonus"], "faces": groups[0]["faces"],
                                 "value": sign * total})
    spent = [e for e in out["used"] if PRESETS[e]["use"] == "next"]
    if spent:
        data = load(campaign_dir)
        data[cid] = [e for e in ids if e not in spent]
        _save(campaign_dir, data)
    return out


def weapon(campaign_dir: Path, cid: str, target_type: str = "", attack: str = "") -> dict:
    """What the character's effects add to the weapon attack `attack` against a target of `target_type`:
    to-hit tiles, flat damage, the lowest d20 that is a critical hit, and extra [dice, type] damage."""
    out = {"hit": [], "dmg": 0, "crit": 20, "extra": []}
    # A stored effect is for every weapon. A worn item's effect is for the weapon it names.
    held = [(e, "") for e in stored(campaign_dir, cid)] + worn(campaign_dir, cid)
    for eid, item in held:
        spec = PRESETS[eid]
        part = spec.get("weapon")
        if not part or (part.get("vs") and not any(t in target_type.lower() for t in part["vs"])):
            continue
        if item and not _words(attack) <= _words(item):  # "Crossbow, hand" is in "+1 Hand Crossbow of Frost"
            continue
        if part.get("hit"):
            out["hit"].append({"label": spec["label"], "value": part["hit"]})
        out["dmg"] += part.get("dmg", 0)
        out["crit"] = min(out["crit"], part.get("crit", 20))
        if part.get("extra"):
            out["extra"].append(list(part["extra"]))
    return out


def defense(campaign_dir: Path, cid: str) -> dict:
    """What the character's effects add to its defense: Armor Class, resistances, flat damage reduction."""
    specs = [PRESETS[e] for e in active(campaign_dir, cid)]
    reduce: dict[str, int] = {}
    for s in specs:
        for dtype, n in s.get("reduce", {}).items():
            reduce[dtype] = reduce.get(dtype, 0) + n
    return {"ac": sum(s.get("ac", 0) for s in specs), "resist": [r for s in specs for r in s.get("resist", ())],
            "reduce": reduce}


def tone(spec: dict) -> str:
    """How the stage colours an effect: good (advantage), bad (a penalty), or gold (a bonus)."""
    if spec.get("mode"):
        return "good" if spec["mode"] == "advantage" else "bad"
    return "bad" if spec.get("bonus", "").startswith("-") else "gold"


def catalogue() -> list[dict]:
    """The presets for the stage's Add Bonus menu."""
    return [{"id": k, "label": v["label"], "info": v["info"], "concentration": v["concentration"],
             "on": list(v["on"]), "tone": tone(v)} for k, v in PRESETS.items()]
