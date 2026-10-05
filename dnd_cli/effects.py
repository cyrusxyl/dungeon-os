"""Active effects: bonuses and advantage that the rules commands add to a roll.

A player (in the stage) or the DM (`dnd-cli effect add`) puts an effect on a
character. The next `check`, `save` or `attack` for that character applies it:
the bonus die is rolled here, so the DM never adds it in its head, and the
stage shows it in the roll window. An effect with `use: next` is spent by the
roll that applies it; `use: kept` stays until it is removed.

Effects live in `{campaign}/stage/effects.json` as `{character id: [preset id]}`.
They are not in `state.json`: the rules commands load and save the whole state
file, and the stage writes effects while the DM is idle.
"""

from __future__ import annotations

import random
from pathlib import Path

from dnd_cli import dice
from stage.files import read_json, write_json

ROLLS = ("check", "save", "attack")

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
}


def path(campaign_dir: Path) -> Path:
    return campaign_dir / "stage" / "effects.json"


def load(campaign_dir: Path) -> dict[str, list[str]]:
    data = read_json(path(campaign_dir)) or {}
    return {cid: [e for e in ids if e in PRESETS] for cid, ids in data.items() if isinstance(ids, list)}


def active(campaign_dir: Path, cid: str) -> list[str]:
    return load(campaign_dir).get(cid, [])


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
          skip: tuple[str, ...] | list[str] = ()) -> dict:
    """What the character's effects add to one roll of `kind`: advantage, disadvantage, bonus dice.

    Spends the `next` effects it used. `skip` names effects the player left off this roll.
    """
    rng = rng or random
    out: dict = {"adv": False, "dis": False, "bonus": [], "used": []}
    ids = active(campaign_dir, cid)
    for eid in ids:
        spec = PRESETS[eid]
        if kind not in spec["on"] or eid in skip:
            continue
        out["used"].append(eid)
        if spec.get("mode") == "advantage":
            out["adv"] = True
        elif spec.get("mode") == "disadvantage":
            out["dis"] = True
        else:
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


def tone(spec: dict) -> str:
    """How the stage colours an effect: good (advantage), bad (a penalty), or gold (a bonus die)."""
    if spec.get("mode"):
        return "good" if spec["mode"] == "advantage" else "bad"
    return "bad" if spec["bonus"].startswith("-") else "gold"


def catalogue() -> list[dict]:
    """The presets for the stage's Add Bonus menu."""
    return [{"id": k, "label": v["label"], "info": v["info"], "concentration": v["concentration"],
             "on": list(v["on"]), "tone": tone(v)} for k, v in PRESETS.items()]
