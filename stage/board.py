"""The combat board engine: units on an arena, and the rules that need a position.

The turn tracker (`state.json` `active_encounter`, `dnd_cli/combat.py`) keeps the order, the HP, the
conditions and the action pips. This module adds where each unit stands, and the rules of the board:
walking, reach, sight and cover. It calls `combat.py` for rolls and damage. It never calls the DM.
See combat-board.md.
"""

from __future__ import annotations

from pathlib import Path

from dnd_cli import combat
from stage import arena


def controlled_by(rec: dict) -> str:
    """`dm` for a creature the DM plays (an NPC file, or a monster the DM named, as in boss=bugbear), else `engine`."""
    if rec.get("kind") == "npc":
        return "dm"
    return "dm" if rec["id"].split("#")[0] != rec.get("index") else "engine"


def start(campaign_dir: Path, state: dict, tokens: list[str], stage: dict) -> list[str]:
    """Build the arena for the running combat and put every combatant on its start tile."""
    enc = combat.encounter(state)
    spec = arena.parse(tokens)
    pcs = [c for c in enc["participants"] if c not in enc["monsters"]]
    foes = list(enc["monsters"])
    source = arena.source_of(campaign_dir, stage, spec)
    a = arena.generate(spec, source, len(pcs), len(foes))
    a["units"] = {cid: {"x": x, "y": y} for cid, (x, y) in zip(pcs, a["starts"]["party"])}
    a["units"] |= {cid: {"x": x, "y": y} for cid, (x, y) in zip(foes, a["starts"]["foes"])}
    a["control"] = {cid: controlled_by(enc["monsters"][cid]) for cid in foes}
    arena_id = arena.new_id(campaign_dir)
    arena.save(campaign_dir, arena_id, a)
    enc["arena"] = arena_id
    spec = a["spec"]
    dm = [cid for cid, who in a["control"].items() if who == "dm"]
    where = {"site": f"the site {spec['source_id']}", "scene": f"the scene {spec['source_id']}", "none": "an empty field"}[spec["source"]]
    return [f"Arena {arena_id}: {a['w']} x {a['h']}, layout {spec['layout']}, light {spec['light']}, built from {where} (seed {spec['seed']}).",
            "The party starts on the left, the foes on the right" + (" (an ambush: foes also on the flanks)." if spec["ambush"] else "."),
            "You play: " + (", ".join(dm) if dm else "no one") + ". The stage plays the other creatures."]
