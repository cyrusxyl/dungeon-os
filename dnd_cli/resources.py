"""Class resources that run out and come back on a rest: Rage, Ki, Second Wind, Bardic Inspiration.

The list comes from the class and level, so no sheet needs editing. The sheet keeps
only how many uses are spent (`resources_used`); a rest clears them.
"""

from __future__ import annotations

from dnd_cli import dice


def _steps(level: int, *steps: tuple[int, int]) -> int:
    """The value at the last (level, value) step that `level` has reached."""
    return max((v for lvl, v in steps if level >= lvl), default=0)


def for_sheet(sheet: dict) -> list[dict]:
    """[{name, max, recharge, used}] for the sheet's class: `recharge` is `short` or `long`."""
    cls = str(sheet.get("class", "")).split()[0].lower()
    level = int(sheet.get("level", 1))
    cha = dice.mod(sheet.get("ability_scores", {}).get("charisma", 10))
    found: list[tuple[str, int, str]] = {
        "barbarian": [("Rage", _steps(level, (1, 2), (3, 3), (6, 4), (12, 5), (17, 6)), "long")],
        "bard": [("Bardic Inspiration", max(1, cha), "short" if level >= 5 else "long")],
        "cleric": [("Channel Divinity", _steps(level, (2, 1), (6, 2), (18, 3)), "short")],
        "druid": [("Wild Shape", 2 if level >= 2 else 0, "short")],
        "fighter": [("Second Wind", 1, "short"), ("Action Surge", _steps(level, (2, 1), (17, 2)), "short")],
        "monk": [("Ki", level if level >= 2 else 0, "short")],
        "paladin": [("Divine Sense", 1 + max(0, cha), "long"), ("Channel Divinity", 1 if level >= 3 else 0, "short")],
        "sorcerer": [("Sorcery Points", level if level >= 2 else 0, "long")],
        "wizard": [("Arcane Recovery", 1, "long")],
    }.get(cls, [])
    used = sheet.get("resources_used") or {}
    return [{"name": n, "max": m, "recharge": r, "used": min(int(used.get(n, 0)), m)} for n, m, r in found if m > 0]


def spend(sheet: dict, name: str, delta: int = 1) -> dict:
    """Spend (`delta` > 0) or get back (`delta` < 0) uses of a resource. Raises KeyError for an unknown name."""
    res = next((r for r in for_sheet(sheet) if r["name"].lower() == name.lower()), None)
    if res is None:
        raise KeyError(name)
    used = max(0, min(res["max"], res["used"] + delta))
    sheet.setdefault("resources_used", {})[res["name"]] = used
    return {**res, "used": used}


def rest(sheet: dict, kind: str) -> None:
    """A long rest gives back every use; a short rest only the ones that recharge on a short rest."""
    used = sheet.get("resources_used") or {}
    keep = {r["name"]: r["used"] for r in for_sheet(sheet) if kind == "short" and r["recharge"] == "long"}
    sheet["resources_used"] = {n: u for n, u in used.items() if n in keep and keep[n]}
