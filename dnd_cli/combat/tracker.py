"""Fight state: the state file, teams (who fights whom), turn tokens and conditions. Imports no other combat module."""

from __future__ import annotations

from pathlib import Path

from core.files import read_json, write_json
from dnd_cli import character
from dnd_cli.errors import RulesError


def state_path(campaign_dir: Path) -> Path:
    return campaign_dir / "state.json"


def load_state(campaign_dir: Path) -> dict:
    return read_json(state_path(campaign_dir)) or {}


def save_state(campaign_dir: Path, state: dict) -> None:
    write_json(state_path(campaign_dir), state, indent=2)


def encounter(state: dict) -> dict:
    enc = state.get("active_encounter")
    if not enc or enc.get("type") != "combat":
        raise RulesError("no combat is running. Start one with: uv run dnd-cli encounter start goblin:3")
    return enc


PARTY, HOSTILE, NEUTRAL = "party", "hostile", "neutral"


WAR = {frozenset((PARTY, HOSTILE)), frozenset((NEUTRAL, HOSTILE))}


def team_of(state: dict, cid: str) -> str:
    enc = state.get("active_encounter") or {}
    return (enc.get("teams") or {}).get(cid) or (HOSTILE if cid in (enc.get("monsters") or {}) else PARTY)


def _war(state: dict, a: str, b: str, labels_a: set[str], labels_b: set[str]) -> bool:
    """Are two teams (`a`, `b`) at war, or is there a feud between a label of one side (its id or its team) and a label of the other?"""
    if a == b:
        return False
    if frozenset((a, b)) in WAR:
        return True
    feuds = (state.get("active_encounter") or {}).get("feuds") or []
    return any((x in labels_a and y in labels_b) or (x in labels_b and y in labels_a) for x, y in feuds)


def enemies(state: dict, a: str, b: str) -> bool:
    """Are combatants `a` and `b` enemies?"""
    ta, tb = team_of(state, a), team_of(state, b)
    return _war(state, ta, tb, {a, ta}, {b, tb})


def feud(state: dict, attacker: str, target: str) -> bool:
    """`attacker` strikes `target`. When they are on different teams that are at peace, `target` is an enemy of the attacker's whole
    team from now on (one pair in `enc["feuds"]`; other members of the target's team are not drawn in). True when a feud was made."""
    enc = state.get("active_encounter") or {}
    if enc.get("type") != "combat" or team_of(state, attacker) == team_of(state, target) or enemies(state, attacker, target):
        return False
    enc.setdefault("feuds", []).append([target, team_of(state, attacker)])
    return True


def hostile_to_party(state: dict, cid: str) -> bool:
    """Is `cid` an enemy of the player characters' team?"""
    t = team_of(state, cid)
    return _war(state, t, PARTY, {cid, t}, {PARTY})


def party(campaign_dir: Path, state: dict) -> list[str]:
    members = state.get("party_members") or [p.stem for p in sorted((campaign_dir / "characters").glob("*.json"))]
    return [m for m in members if character.character_path(campaign_dir, m).exists()]


def active_conditions(state: dict, cid: str) -> list[dict]:
    return ((state.get("active_encounter") or {}).get("conditions") or {}).get(cid, [])


TURN_KINDS = ("action", "bonus", "reaction")


# What a creature does on its turn and what it leaves behind. `rounds=1` ends when its next turn starts.
STANCES = {"dodging": "Dodge", "dashing": "Dash", "disengaged": "Disengage", "helping": "Help", "hidden": "Hide"}


def spend_turn(state: dict, cid: str, kind: str, used: bool = True, quiet: bool = False) -> None:
    """Mark an action, bonus action or reaction as used (or free) for a combatant of the running combat.

    `quiet` ignores a creature outside the combat (a DM attack with no tracker running).
    """
    if quiet and not in_combat(state, cid):
        return
    enc = encounter(state)
    if kind not in TURN_KINDS or cid not in enc["participants"]:
        raise RulesError(f"use one of {', '.join(TURN_KINDS)} for a creature in this combat.")
    enc.setdefault("resources", {}).setdefault(cid, {})[kind] = bool(used)


def in_combat(state: dict, cid: str) -> bool:
    enc = state.get("active_encounter") or {}
    return enc.get("type") == "combat" and cid in enc.get("participants", [])


def turn_used(state: dict, cid: str) -> dict:
    spent = ((state.get("active_encounter") or {}).get("resources") or {}).get(cid, {}) if in_combat(state, cid) else {}
    return {k: bool(spent.get(k)) for k in TURN_KINDS}


def has_condition(state: dict, cid: str, name: str) -> bool:
    return any(c["condition"] == name for c in active_conditions(state, cid))
