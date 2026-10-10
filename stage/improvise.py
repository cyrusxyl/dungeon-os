"""An improvised action: a player tries something the abilities do not list.

The engine suggests a ruling from the words and from the tags of the object (stage/data/scenery.json, `board`), and sends
the DM the text and the suggestion. The DM confirms or changes it, and runs it with the commands that exist (`attack ...
spell`, `encounter condition`, `encounter use`). There is no second rules path. See combat-board.md, section 6.
"""

from __future__ import annotations

import re
from pathlib import Path

from dnd_cli import combat
from stage import arena, board

# The first matching verb wins. Each rule: (words, ruling builder name).
VERBS = (
    ("throw", r"\b(throw|hurl|toss|fling|lob|chuck)\b"),
    ("push", r"\b(push|topple|tip|knock over|kick|shove|overturn)\b"),
    ("break", r"\b(break|smash|destroy|bash|shatter)\b"),
    ("climb", r"\bclimb\b"),
    ("light", r"\b(light|ignite|burn|set fire|set .* on fire)\b"),
    ("pickup", r"\b(pick up|grab|take|draw)\b"),
)


def find_object(a: dict, object_id: str | None) -> dict | None:
    """A prop or an item of the arena, with its board tags."""
    for p in a["props"]:
        if p["id"] == object_id:
            return {**p, "name": p["kind"].replace("_", " "), "board": arena.board_of(p["kind"])}
    for i in a["items"]:
        if i["id"] == object_id:
            return {**i, "kind": "item", "board": {**arena.DEFAULT_BOARD, "blocks_move": False, "tags": ["portable"]}}
    return None


def verb_of(text: str) -> str:
    low = text.lower()
    return next((name for name, pattern in VERBS if re.search(pattern, low)), "other")


def suggest(campaign_dir: Path, state: dict, cid: str, text: str, obj: dict | None) -> dict:
    """The default ruling: cost, roll, effect and whether the object is used up. Never a refusal: when the rules say
    nothing, the suggestion is a plain check and the DM sets the DC."""
    rec = combat.combatant(campaign_dir, state, cid)
    tags = set(obj["board"]["tags"]) if obj else set()
    verb = verb_of(text)
    if verb == "throw":
        if "heavy" in tags:
            return {"cost": "action", "roll": {"type": "check", "skill": "athletics", "dc": 15},
                    "effect": "The object is heavy: a Strength check to lift and throw it, then damage as the DM decides.", "consume": False}
        bonus = rec["mods"]["dexterity"]
        return {"cost": "action", "roll": {"type": "attack", "ability": "dex", "bonus": bonus, "range_ft": [20, 60]},
                "effect": "Improvised weapon: 1d4 bludgeoning, no proficiency. Picking it up is the free object interaction of the turn.",
                "consume": True}
    if verb == "push":
        dc = 10 + (5 if "heavy" in tags else 0)
        return {"cost": "action", "roll": {"type": "check", "skill": "athletics", "dc": dc},
                "effect": "On a success the object moves 5 ft or falls over; a creature it falls on makes a Dex save (DC 12) or takes 1d6 bludgeoning.",
                "consume": False}
    if verb == "break":
        if "breakable" not in tags:
            return {"cost": "action", "roll": {"type": "check", "skill": "athletics", "dc": 15},
                    "effect": "Not made to break: the DM sets the DC and what it gives.", "consume": False}
        hp = obj["board"]["hp"]
        return {"cost": "action", "roll": {"type": "check", "skill": "athletics", "dc": 10 if (hp or 10) <= 10 else 12},
                "effect": f"On a success the object breaks (it has {hp or 'few'} HP) and stops blocking.", "consume": False}
    if verb == "climb":
        ok = "climbable" in tags
        return {"cost": "free", "roll": {"type": "check", "skill": "athletics", "dc": 10 if ok else 15},
                "effect": "Climbing costs 1 extra foot of speed for each foot." if ok else "Nothing to hold on to: the DM sets the DC.", "consume": False}
    if verb == "light":
        ok = "flammable" in tags
        return {"cost": "action", "roll": {"type": "none"},
                "effect": "It burns: a creature in the fire takes 1d6 fire damage each turn." if ok else "It does not catch fire easily: the DM decides.",
                "consume": False}
    if verb == "pickup":
        return {"cost": "free", "roll": {"type": "none"}, "effect": "One free object interaction each turn. A second costs the action.", "consume": False}
    return {"cost": "action", "roll": {"type": "check", "skill": "(DM picks)", "dc": 12},
            "effect": "The rules list nothing for this. A plain check at a default DC: the DM can change it.", "consume": False}


def describe(ruling: dict) -> str:
    roll = ruling["roll"]
    how = (f"Dex attack {roll['bonus']:+d}, range {roll['range_ft'][0]}/{roll['range_ft'][1]} ft" if roll["type"] == "attack"
           else f"{roll['skill']} check, DC {roll['dc']}" if roll["type"] == "check" else "no roll")
    return f"costs {ruling['cost']}; {how}. {ruling['effect']}" + (" The object is used up." if ruling["consume"] else "")


def prompt(campaign_dir: Path, state: dict, a: dict, cid: str, text: str, object_id: str | None = None) -> str:
    """The line the DM hears. It carries the player's words, the object and the suggested ruling."""
    obj = find_object(a, object_id) if object_id else None
    if object_id and obj is None:
        raise board.BoardError(f"there is no object {object_id!r} on the board.")
    rec = combat.combatant(campaign_dir, state, cid)
    where = ""
    if obj:
        tags = ", ".join(obj["board"]["tags"]) or "no tags"
        where = f" Object: {obj['name']} ({tags}), {arena.cheb(board.pos(a, cid), (obj['x'], obj['y'])) * board.TILE_FT} ft away."
    ruling = suggest(campaign_dir, state, cid, text, obj)
    return (f"[combat] {rec['name']} ({cid}) improvises: \"{text}\".{where} Suggested ruling: {describe(ruling)} "
            f"Confirm it or change it, then run it with the usual commands (`uv run dnd-cli attack {cid} improvised <target> --damage 1d4 --type bludgeoning --bonus <to-hit>`, "
            f"`uv run dnd-cli encounter condition <target> add <name> --rounds N`, and `uv run dnd-cli encounter use {cid} action` "
            f"when no attack spends it). Narrate one beat. It is still {rec['name']}'s turn.")
