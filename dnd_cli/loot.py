"""Treasure for `dnd-cli loot roll`: coins and items from the challenge rating, the kind of treasure and a seed.

The table is core/data/loot.json and the perks are in core/data/perks.json. The same seed gives the same list. The engine rolls; the DM decides: it gives
coins with `character gold`, items with `character item add`, and rerolls with another seed.
"""

from __future__ import annotations

import json
import random
import re
from functools import cache
from pathlib import Path

from dnd_cli import dice
from dnd_cli.errors import RulesError

LOOT_PATH = Path(__file__).resolve().parents[1] / "core" / "data" / "loot.json"
PERKS_PATH = LOOT_PATH.with_name("perks.json")
KINDS = ("individual", "hoard")
RARITIES = ("common", "uncommon", "rare", "very rare", "legendary")
IN_GP = {"cp": 0.01, "sp": 0.1, "gp": 1, "pp": 10}


@cache
def table() -> dict:
    return json.loads(LOOT_PATH.read_text())


@cache
def perks() -> dict:
    return json.loads(PERKS_PATH.read_text())


def _fits(perk: dict, gear_type: str, rarity: str) -> bool:
    top = perk.get("until", "very rare")
    return gear_type in perk["types"] and RARITIES.index(perk["rarity"]) <= RARITIES.index(rarity) <= RARITIES.index(top)


def roll_perks(gear_type: str, rarity: str, rng: random.Random) -> list[dict]:
    """The perks of one gear item. A weapon of uncommon rarity or more starts with an enchant (+1, +2, +3).
    No two perks of one `group` meet on one item."""
    want = perks()["per_rarity"].get(rarity, 0)
    fit = [p for p in perks()["perks"] if _fits(p, gear_type, rarity)]
    chosen: list[dict] = []

    def pick(pool: list[dict]) -> None:
        pool = [p for p in pool if p not in chosen and not (p.get("group") and any(c.get("group") == p["group"] for c in chosen))]
        if pool and len(chosen) < want:
            chosen.append(rng.choices(pool, weights=[p["weight"] for p in pool])[0])

    if gear_type == "weapon":
        pick([p for p in fit if p.get("group") == "enchant"])
    while len(chosen) < want:
        before = len(chosen)
        pick(fit)
        if len(chosen) == before:  # nothing else fits
            break
    return chosen


def gear_name(base: str, chosen: list[dict]) -> str:
    """`+1 Keen Longsword of Flame and Warding`: prefixes, the base name, then the suffixes."""
    prefix = [p["name"] for p in chosen if p["slot"] == "prefix"]
    suffix = [p["name"] for p in chosen if p["slot"] == "suffix"]
    tail = (" " + suffix[0] + "".join(" and " + s.removeprefix("of ") for s in suffix[1:])) if suffix else ""
    return " ".join(prefix + [base]) + tail


def gear(rarity: str, rng: random.Random) -> dict:
    """One armor, weapon or accessory with its rolled perks. `effects` are presets to add when it is worn;
    `rulings` are perks that the DM must rule."""
    g = table()["gear"]
    kind = rng.choices(list(g["types"]), weights=list(g["types"].values()))[0]
    chosen = roll_perks(kind, rarity, rng)
    base = rng.choice(g["bases"][kind])
    return {"name": gear_name(base, chosen), "base": base, "rarity": rarity, "type": kind, "perks": [p["name"] for p in chosen],
            "effects": [p["effect"] for p in chosen if p["effect"]],
            "rulings": [f"{p['name']}: {p['ruling']}" for p in chosen if not p["effect"]]}


def base_of(name: str, base: str | None = None) -> tuple[str, str] | None:
    """(type, base) of a gear item from its name ("+1 Hand Crossbow of Frost" is a weapon on the base Hand Crossbow).
    `base` names it by hand. Gives the longest base name found in the item name, or None."""
    bases = table()["gear"]["bases"]
    want = (base or name).lower()
    found = [(kind, b) for kind, names in bases.items() for b in names if b.lower() == want or (not base and b.lower() in want)]
    if base and not found:
        raise RulesError(f"no base {base!r}. Bases: {', '.join(b for names in bases.values() for b in names)}.")
    return max(found, key=lambda f: len(f[1])) if found else None


def api_index(base: str) -> str:
    """The 5e API equipment index of a base: the slug of its name, unless the table says otherwise."""
    return table()["gear"].get("api", {}).get(base) or re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")


def hints(perk_text: str, given: list[str] | tuple = ()) -> list[str]:
    """For `character item add`: the catalog perks named in the free text (split at commas), and what to do with each.
    A perk whose effect is in `given` needs no hint."""
    out = []
    for word in (w.strip().lower() for w in perk_text.split(",")):
        for p in perks()["perks"]:
            if p["name"].lower() == word and p["effect"] not in given:
                out.append(f"{p['name']} ({'/'.join(p['types'])}): " + (f"give it again with `--effects {p['effect']}`, and the stage counts it while it is equipped." if p["effect"]
                                                                       else f"you rule it: {p['ruling']}"))
    return out


def tier(cr: float) -> dict:
    return next(t for t in table()["tiers"] if cr <= t["max_cr"])


def roll(cr: float, kind: str = "individual", seed: int | None = None, creature_type: str = "") -> dict:
    """{"seed", "coins": {"gp": 12}, "items": [{"name", "rarity"}], "note"}. A legendary item has no name: the DM writes it.
    A gear item also has "type", "perks", "effects" (presets) and "rulings" (perks the DM must rule)."""
    if kind not in KINDS:
        raise RulesError(f"kind is one of {', '.join(KINDS)}.")
    if cr < 0:
        raise RulesError("cr cannot be negative.")
    seed = random.SystemRandom().randrange(10**6) if seed is None else seed
    rng = random.Random(seed)
    out = {"seed": seed, "coins": {}, "items": [], "note": ""}
    if creature_type.lower() in table()["no_treasure"]:
        out["note"] = f"A creature of type {creature_type.lower()} carries no treasure."
        return out
    t = tier(cr)
    for coin, (expr, times) in t[kind].items():
        out["coins"][coin] = dice.roll(expr, rng)[0] * times
    if kind == "hoard":
        for _ in range(dice.roll(t["items"], rng)[0]):
            rarity = rng.choices(list(t["rarity"]), weights=list(t["rarity"].values()))[0]
            if rarity != "legendary" and rng.random() < table()["gear"]["chance"].get(rarity, 0):
                out["items"].append(gear(rarity, rng))
                continue
            pool = table()["items"].get(rarity)
            out["items"].append({"name": rng.choice(pool) if pool else None, "rarity": rarity})
    return out


def lines(result: dict) -> list[str]:
    out = [f"Loot (seed {result['seed']}; another seed rerolls):"]
    if result["note"]:
        return out + [f"  {result['note']}"]
    coins = ", ".join(f"{n} {c}" for c, n in result["coins"].items())
    total = int(sum(n * IN_GP[c] for c, n in result["coins"].items()))
    out.append(f"  Coins: {coins} ({total} gp in all)" if coins else "  Coins: none")
    for item in result["items"]:
        out.append(f"  {item['name'] or 'A legendary item: write it yourself'} ({item['rarity']})")
        if item.get("effects"):
            out.append(f"      give it with --effects {','.join(item['effects'])}")
        out += [f"      you rule: {r}" for r in item.get("rulings", [])]
    out.append("  Give coins with `character gold <who> +N` (in gp), items with `character item <who> add \"<item>\" [--perk \"...\"] [--effects <preset>]`.")
    return out
