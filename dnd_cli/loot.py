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
KINDS = ("individual", "hoard")
RARITIES = ("common", "uncommon", "rare", "very rare", "legendary")
IN_GP = {"cp": 0.01, "sp": 0.1, "gp": 1, "pp": 10}


@cache
def table() -> dict:
    return json.loads(LOOT_PATH.read_text())


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
    out.append("  Give coins with `character gold <who> +N` (in gp), items with `character item <who> add \"<item>\"`, or `loot force \"<item>\" --to <who> --perk \"...\"`.")
    return out
