"""Items on the board: the abilities a character gets from its inventory, and the objects that lie on a tile.

An inventory row has a profile when it is in stage/data/items.json or carries a `profile` of its own (a DM ruling that was
saved). A profile gives the row an ability in the format of dnd_cli/abilities.py. Using it removes one from the sheet.
Other rows have no card: the player uses them with Improvise. See combat-board.md, section 6.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from dnd_cli import abilities, character, combat, dice, sheet as sheets
from stage import arena, board

ITEMS_PATH = Path(__file__).resolve().parent / "data" / "items.json"
PROFILE_KINDS = ("heal", "throw")


@cache
def table() -> dict:
    return {k: v for k, v in json.loads(ITEMS_PATH.read_text()).items() if not k.startswith("_")}


def profile_of(row: dict) -> dict | None:
    """The profile of an inventory row: its own, else the table's, else none."""
    p = row.get("profile") or table().get(row.get("name", "").lower())
    return p if p and p.get("kind") in PROFILE_KINDS else None


def object_free(state: dict, cid: str) -> bool:
    """Each turn has one free object interaction (pick up, hand over, draw). A new turn clears it."""
    return not state["active_encounter"].get("resources", {}).get(cid, {}).get("object")


def listing(sheet: dict, rec: dict) -> list[dict]:
    """One ability for each inventory row that has a profile."""
    out = []
    for row in sheet.get("inventory", []):
        p = profile_of(row)
        if p is None:
            continue
        base = {"id": f"item:{row['name']}", "name": row["name"], "cost": p.get("cost", "action"), "source": "item", "qty": row.get("quantity", 1)}
        if p["kind"] == "heal":
            out.append({**base, "kind": "heal", "heal": p["heal"], "text": f"x{base['qty']} · yourself or a creature next to you", "stat": f"heals {p['heal']}"})
        else:
            bonus = rec["mods"]["dexterity"]  # an improvised weapon: no proficiency
            expr, dtype = p["damage"]
            out.append({**base, "kind": "spell_attack", "spell_level": 0, "weapon": "improvised", "to_hit": bonus, "attack": {"bonus": bonus, "range_ft": p["range_ft"]}, "damage": [[expr, dtype]],
                        "text": f"x{base['qty']} · Range {p['range_ft']} ft", "stat": f"{bonus:+d} · {expr} {dtype}"})
    return out


def ally_targets(campaign_dir: Path, state: dict, a: dict, cid: str) -> list[dict]:
    """Who a healing item can go to: the user and each friend next to them."""
    here, out = board.pos(a, cid), []
    for other in a["units"]:
        if board.is_foe(state, other) != board.is_foe(state, cid):
            continue
        dist = arena.cheb(here, board.pos(a, other)) * board.TILE_FT
        out.append({"id": other, "name": combat.combatant(campaign_dir, state, other)["name"], "dist_ft": dist, "ok": dist <= board.TILE_FT,
                    "why": None if dist <= board.TILE_FT else "Not next to you."})
    return out


def pickups(state: dict, a: dict, cid: str) -> list[dict]:
    """The objects on the tiles next to the character: a free object interaction each turn."""
    here, free = board.pos(a, cid), object_free(state, cid)
    return [{"id": f"pickup:{i['id']}", "name": f"Pick up {i['name']}", "cost": "free", "kind": "pickup", "source": "board", "text": "Free object interaction",
             "stat": "", "why": None if free else "The free object interaction of this turn is used."}
            for i in a["items"] if arena.cheb(here, (i["x"], i["y"])) <= 1]


def consume(campaign_dir: Path, cid: str, name: str) -> None:
    sh = character.load(campaign_dir, cid)
    sheets.remove_item(sh, name, 1)
    character.save(campaign_dir, cid, sh)


def heal(campaign_dir: Path, state: dict, a: dict, cid: str, ab: dict, target: str | None, rng=None) -> list[str]:
    """Drink or pour a healing item: the user or a creature next to them gets the dice. The checks come first, then the action is spent."""
    if target not in {t["id"] for t in ally_targets(campaign_dir, state, a, cid)}:
        raise board.BoardError("give it to yourself or a friend.")
    if arena.cheb(board.pos(a, cid), board.pos(a, target)) > 1:
        raise board.BoardError("Not next to you.")
    board.spend_ability(campaign_dir, state, cid, ab)
    amount, _ = dice.roll(ab["heal"], rng)
    name = combat.combatant(campaign_dir, state, cid)["name"]
    who = combat.combatant(campaign_dir, state, target)["name"]
    board.note(a, f"{name} used {ab['name']} on {'themselves' if target == cid else who}")
    return [f"{cid} uses {ab['name']} on {target}.", combat.heal(campaign_dir, state, target, amount)]


def pick_up(campaign_dir: Path, state: dict, a: dict, cid: str, pick_id: str) -> list[str]:
    item = next((i for i in a["items"] if f"pickup:{i['id']}" == pick_id), None)
    if item is None or arena.cheb(board.pos(a, cid), (item["x"], item["y"])) > 1:
        raise board.BoardError("there is nothing like that next to you.")
    if not object_free(state, cid):
        raise board.BoardError("The free object interaction of this turn is used.")
    sh = character.load(campaign_dir, cid)
    sheets.add_item(sh, item["name"], 1)
    character.save(campaign_dir, cid, sh)
    a["items"].remove(item)
    state["active_encounter"].setdefault("resources", {}).setdefault(cid, {})["object"] = True
    board.note(a, f"{combat.combatant(campaign_dir, state, cid)['name']} picked up {item['name']}")
    return [f"{cid} picks up {item['name']}."]
