"""How a roll reaches the stage: the dice box, the feed, and the data of the roll window."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dnd_cli import dice, effects
from dnd_cli.combat.records import SKILLS, ability, combatant, save_bonus, skill_bonus


def stage_roll(expr: str, total: int, groups: list[dict], secret: bool = False, detail: dict | None = None) -> None:
    """Show a roll in the stage's dice box (no-op without a running stage, or when secret).

    `detail` is the roll window's breakdown (see `roll_detail`). Without it the stage shows `expr` and the dice.
    """
    log = os.environ.get("DUNGEON_STAGE_LOG")
    if log and not secret:
        event = {"type": "roll", "expr": expr, "total": total, "dice": groups}
        if detail:
            event["detail"] = detail
        with open(log, "a") as f:
            f.write(json.dumps(event) + "\n")


def stage_feed(text: str) -> None:
    """A line for the stage's log (no-op without a running stage). Rolls reach the log by themselves."""
    log = os.environ.get("DUNGEON_STAGE_LOG")
    if log:
        with open(log, "a") as f:
            f.write(json.dumps({"type": "feed", "text": text}) + "\n")


def secret_feed(secret: bool, recs: list[dict], text: str) -> None:
    """A secret roll hides the dice, but a hero who loses HP to it still gets a line in the log."""
    if secret and any(r["kind"] == "pc" for r in recs):
        stage_feed(text)


def shown_damage(dtype: str, expr: str, groups: list[dict], total: int) -> dict:
    """One damage entry for the roll window. `faces` is every die in one list (old clients); `groups` keeps them by die type."""
    return {"type": dtype, "expr": expr, "faces": [f for g in groups for f in g["faces"]], "groups": groups, "total": total}


def d20_groups(faces: list[int], kept: int) -> list[dict]:
    """The kept d20 first (the legacy dice box colours a natural 20 or 1 from it)."""
    rest = list(faces)
    rest.remove(kept)
    return [{"die": "1d20", "faces": [kept]}] + ([{"die": "1d20 dropped", "faces": rest}] if rest else [])


def roll_d20(campaign_dir: Path, cid: str, kind: str, adv: bool, dis: bool, rng, skip=(), tags=()) -> dict:
    """One d20 roll for a creature, with its active effects: advantage, disadvantage, bonus dice and flat bonuses.

    `tags` say what the roll is about (its ability, its skill) for effects that need one."""
    fx = effects.apply(campaign_dir, cid, kind, rng, skip, tags)
    adv, dis = adv or fx["adv"], dis or fx["dis"]
    kept, faces = dice.d20(rng, adv, dis)
    mode = "normal" if len(faces) == 1 else "advantage" if adv else "disadvantage"
    return {"kept": kept, "faces": faces, "mode": mode, "bonus": fx["bonus"], "flat": fx["flat"], "used": fx["used"]}


def fx_note(roll: dict) -> str:
    """The effects a roll used, for the DM's output line: ` (advantage 17,5; guidance +3)`."""
    notes = []
    if roll["mode"] != "normal":
        notes.append(f"{roll['mode']} {','.join(map(str, roll['faces']))}")
    notes += [f"{b['label'].lower()} {dice.signed(b['value'])}" for b in roll["bonus"] + roll.get("flat", [])]
    return f" ({'; '.join(notes)})" if notes else ""


def check_tiles(rec: dict, abil: str, bonus: int, what: str) -> list[dict]:
    """A skill or save bonus split into the roll window's tiles: ability, proficiency, expertise."""
    base = rec["mods"][abil]
    tiles = [{"label": abil.capitalize(), "value": base}]
    rest = bonus - base
    prof = rec.get("prof") or rest
    if rest and rest == prof:
        tiles.append({"label": f"{what} Proficiency", "value": rest})
    elif rest and rest == 2 * prof:
        tiles += [{"label": f"{what} Proficiency", "value": prof}, {"label": f"{what} Expertise", "value": prof}]
    elif rest:
        tiles.append({"label": "Other", "value": rest})
    return tiles


def check_spec(rec: dict, what: str) -> dict:
    """What a check or a save is: its ability, bonus, window title and the tiles that make the bonus.

    `what` is a skill (`athletics`), an ability (`str`), or a save (`dex-save`).
    """
    what = what.lower().replace(" ", "_")
    if what.endswith(("-save", "_save")):
        abil = ability(what[:-5])
        bonus = save_bonus(rec, abil)
        return {"kind": "save", "abil": abil, "bonus": bonus, "title": f"{abil.capitalize()} Saving Throw", "subtitle": "",
                "label": abil[:3].upper(), "tiles": check_tiles(rec, abil, bonus, f"{abil.capitalize()} Save")}
    what = what.replace("-", "_")
    if what in SKILLS:
        abil = SKILLS[what]
        bonus, label = skill_bonus(rec, what), what.replace("_", " ").title()
        return {"kind": "check", "abil": abil, "bonus": bonus, "title": label, "subtitle": f"{abil.capitalize()} Check",
                "label": label, "tiles": check_tiles(rec, abil, bonus, label)}
    abil = ability(what)
    bonus = rec["mods"][abil]
    return {"kind": "check", "abil": abil, "bonus": bonus, "title": abil.capitalize(), "subtitle": "Ability Check",
            "label": abil[:3].upper(), "tiles": check_tiles(rec, abil, bonus, abil.capitalize())}


def roll_preview(campaign_dir: Path, state: dict, cid: str, what: str) -> dict:
    """The roll window before the roll: who rolls what, and the tiles that will add to the d20."""
    rec = combatant(campaign_dir, state, cid)
    spec = check_spec(rec, what)
    return {"name": rec["name"], "kind": spec["kind"], "title": spec["title"], "subtitle": spec["subtitle"], "mods": spec["tiles"]}


def roll_entry(rec: dict, roll: dict, tiles: list[dict], outcome: str | None = None, total: int | None = None) -> dict:
    """One creature's roll for the roll window. The total is the d20 plus every tile and bonus die.
    Flat bonuses from effects join the tiles."""
    tiles = tiles + roll.get("flat", [])
    total = roll["kept"] + sum(t["value"] for t in tiles) + sum(b["value"] for b in roll["bonus"]) if total is None else total
    return {"who": rec["id"], "name": rec["name"], "d20": roll["faces"], "kept": roll["faces"].index(roll["kept"]),
            "mode": roll["mode"], "mods": tiles, "bonus": roll["bonus"], "total": total, "outcome": outcome}


def roll_detail(kind: str, title: str, subtitle: str, rolls: list[dict], target: dict | None = None,
                damage: list[dict] | None = None) -> dict:
    """The roll window's data: what is rolled, the target number (only when the players may see it), each roll."""
    detail: dict = {"kind": kind, "title": title, "subtitle": subtitle, "rolls": rolls}
    if target:
        detail["target"] = target
    if damage:
        detail["damage"] = damage
    return detail
