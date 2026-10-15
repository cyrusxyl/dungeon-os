"""Treasure for `dnd-cli loot roll`: coins and items from the challenge rating, the kind of treasure and a seed.

The table is stage/data/loot.json. The same seed gives the same list. The engine rolls; the DM decides: it gives
coins with `character gold`, items with `character item add` or `loot force`, and rerolls with another seed.
"""

from __future__ import annotations

import json
import random
from functools import cache
from pathlib import Path

from dnd_cli import dice
from dnd_cli.combat import RulesError

LOOT_PATH = Path(__file__).resolve().parents[1] / "stage" / "data" / "loot.json"
PERKS_PATH = LOOT_PATH.with_name("perks.json")
KINDS =("individual", "hoard")
RARITIES = ("common", "uncommon", "rare", "very rare", "legendary")
IN_GP = {"cp": 0.01, "sp": 0.1, "gp": 1, "pp": 10}


@cache
def table() -> dict:
    return json.loads(LOOT_PATH.read_text())


@cache
def perks() -> list[dict]:
    return json.loads(PERKS_PATH.read_text())["perks"]


def item_type(name: str | None) -> str:
    """weapon, armor or other, from the name in the table."""
    first = (name or "").lower()
    if first.startswith(("weapon", "ammunition")):
        return "weapon"
    return "armor" if first.startswith(("armor", "shield")) else "other"


def roll_perks(item: dict, rng: random.Random) -> list[str]:
    """Uncommon: one perk. Rare and very rare: two. Only a weapon or an armor gets one."""
    kind, rank = item_type(item["name"]), RARITIES.index(item["rarity"])
    count = {"uncommon": 1, "rare": 2, "very rare": 2}.get(item["rarity"], 0)
    pool = [p for p in perks() if kind in p["types"] and RARITIES.index(p["rarity"]) <= rank
            and p["name"].lower() not in item["name"].lower() and not (p["name"][0] == "+" and "+" in item["name"])]
    chosen: list[str] = []
    while pool and len(chosen) < count:
        p = rng.choices(pool, weights=[q["weight"] for q in pool])[0]
        pool.remove(p)
        chosen.append(p["name"])
    return chosen


def describe_perk(text: str) -> str:
    """A perk named in the catalog becomes its ruling. Any other text stays as the DM wrote it."""
    found = next((p for p in perks() if p["name"].lower() == text.strip().lower()), None)
    return f"{found['name']}: {found['ruling']}" if found else text


def tier(cr: float) -> dict:
    return next(t for t in table()["tiers"] if cr <= t["max_cr"])


def roll(cr: float, kind: str = "individual", seed: int | None = None, creature_type: str = "") -> dict:
    """{"seed", "coins": {"gp": 12}, "items": [{"name", "rarity"}], "note"}. A legendary item has no name: the DM writes it."""
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
            pool = table()["items"].get(rarity)
            out["items"].append({"name": rng.choice(pool) if pool else None, "rarity": rarity})
        perk_rng = random.Random(f"perks-{seed}")  # its own stream: the items stay the same with or without perks
        for item in out["items"]:
            item["perks"] = roll_perks(item, perk_rng)
    return out


def lines(result: dict) -> list[str]:
    out = [f"Loot (seed {result['seed']}; another seed rerolls):"]
    if result["note"]:
        return out + [f"  {result['note']}"]
    coins = ", ".join(f"{n} {c}" for c, n in result["coins"].items())
    total = int(sum(n * IN_GP[c] for c, n in result["coins"].items()))
    out.append(f"  Coins: {coins} ({total} gp in all)" if coins else "  Coins: none")
    for item in result["items"]:
        perk = f" - perk: {', '.join(item['perks'])}" if item.get("perks") else ""
        out.append(f"  {item['name'] or 'A legendary item: write it yourself'} ({item['rarity']}){perk}")
    out.append("  Give coins with `character gold <who> +N` (in gp), items with `character item <who> add \"<item>\"`, or `loot force \"<item>\" --to <who> --perk \"...\"`.")
    return out
