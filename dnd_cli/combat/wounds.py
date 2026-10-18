"""Damage and healing."""

from __future__ import annotations

from pathlib import Path

from dnd_cli import character
from dnd_cli.combat.records import combatant
from dnd_cli.combat.tracker import active_conditions


def _scaled(rec: dict, amount: int, dtype: str) -> tuple[int, str]:
    """Damage after immunity, resistance, vulnerability (simple type matches only)."""
    if not dtype:
        return amount, ""
    plain = lambda lst: any(dtype in s.lower() and "nonmagical" not in s.lower() for s in lst)  # noqa: E731
    if plain(rec.get("immune", [])):
        return 0, f" (immune to {dtype})"
    if plain(rec.get("resist", [])):
        return amount // 2, f" (resists {dtype})"
    if plain(rec.get("vuln", [])):
        return amount * 2, f" (vulnerable to {dtype})"
    return amount, ""


def damage(campaign_dir: Path, state: dict, cid: str, amount: int, dtype: str = "", crit: bool = False) -> str:
    """Apply damage; returns the DM line. PCs are saved to their sheet; creatures stay in the encounter."""
    rec = combatant(campaign_dir, state, cid)
    amount, note = _scaled(rec, amount, dtype.lower())
    if amount and (cut := rec.get("reduce", {}).get(dtype.lower(), 0) + rec.get("reduce", {}).get("all", 0)):
        amount, note = max(0, amount - cut), note + f" (gear absorbs {min(cut, amount)})"
    concentrating = any(c["condition"] == "concentrating" for c in active_conditions(state, cid))
    conc = f"; concentration save DC {max(10, amount // 2)}" if concentrating and amount else ""
    if rec["kind"] == "pc":
        sheet = character.load(campaign_dir, cid)
        was_down = sheet["hp"]["current"] == 0
        report = character.apply_damage(sheet, amount)
        line = f"{cid} takes {amount}{note}: HP {report['hp_current']}/{report['hp_max']}"
        if was_down and amount:
            saves = sheet.setdefault("death_saves", {"successes": 0, "failures": 0})
            saves["failures"] = min(3, saves.get("failures", 0) + (2 if crit else 1))
            line += f"; death save failures {saves['failures']}/3" + (" DEAD" if saves["failures"] >= 3 else "")
        elif report["dropped_to_zero"]:
            line += " DOWN (unconscious; death saves start)"
        character.save(campaign_dir, cid, sheet)
        return line + conc
    hp = rec["hp"]
    hp["current"] = max(0, hp["current"] - amount)
    return f"{cid} takes {amount}{note}: HP {hp['current']}/{hp['max']}" + (" DOWN" if hp["current"] == 0 else "") + conc


def heal(campaign_dir: Path, state: dict, cid: str, amount: int) -> str:
    rec = combatant(campaign_dir, state, cid)
    if rec["kind"] == "pc":
        sheet = character.load(campaign_dir, cid)
        report = character.heal(sheet, amount)
        if amount > 0:
            sheet["death_saves"] = {"successes": 0, "failures": 0}
        character.save(campaign_dir, cid, sheet)
        return f"{cid} heals {amount}: HP {report['hp_current']}/{report['hp_max']}"
    hp = rec["hp"]
    hp["current"] = min(hp["max"], hp["current"] + amount)
    return f"{cid} heals {amount}: HP {hp['current']}/{hp['max']}"
