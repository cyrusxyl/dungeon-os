"""What the party panel and the character sheet show, from the character files and the combat tracker.

An allowlist, like the rest of the stage server: a player character's own sheet, the names, initiative,
conditions and how hurt (a band, never a number) everyone in a combat is. Never a monster's HP, AC or stats.
"""

from __future__ import annotations

from pathlib import Path

from dnd_cli import actions, dice, effects, item as items, resources
from dnd_cli.combat import records, tracker
from stage import beat
from core.files import read_json


def _skills(sheet: dict, mods: dict, prof: int) -> list[dict]:
    """Every skill with its bonus and how proficient the sheet is in it (0, 1, or 2 for expertise)."""
    out = []
    for name, abil in records.SKILLS.items():
        bonus = sheet.get("skills", {}).get(name, mods[abil])
        rank = round((bonus - mods[abil]) / prof) if prof else 0
        out.append({"name": name.replace("_", " ").title(), "ability": abil[:3].upper(), "bonus": bonus,
                    "prof": max(0, min(2, rank))})
    return out


def _character(campaign_dir: Path, cid: str, sheet: dict, st: dict, present: list[dict], sheets: dict[str, dict]) -> dict:
    scores = sheet.get("ability_scores", {})
    mods = dice.mods(scores)
    prof = sheet.get("proficiency_bonus", 2)
    saves = sheet.get("saving_throws", {})
    inventory = [i.view() for i in items.items(sheet)]
    weapons, armor = items.gear_view(sheet)
    spell = sheet.get("spellcasting") or {}
    held = effects.active(campaign_dir, cid, sheet)
    return {
        "id": cid,
        "name": sheet.get("name"),
        "race": sheet.get("race"),
        "class": sheet.get("class"),
        "level": sheet.get("level"),
        "background": sheet.get("background"),
        "hp": sheet.get("hp", {}),
        "inspiration": sheet.get("inspiration", 0),
        "armor_class": None if sheet.get("armor_class") is None else sheet["armor_class"] + effects.defense_of(held)["ac"],
        "speed": sheet.get("speed", 30),
        "initiative": sheet.get("initiative", mods["dexterity"]),
        "prof": prof,
        "abilities": {a: {"score": scores.get(a, 10), "mod": mods[a], "save": saves.get(a, mods[a]),
                          "save_prof": saves.get(a, mods[a]) != mods[a]} for a in records.ABILITIES},
        "skills": _skills(sheet, mods, prof),
        "weapons": weapons,
        "armor": armor,
        "inventory": inventory,
        "capacity": scores.get("strength", 10) * 15,
        "spell": {"ability": spell.get("ability"), "dc": spell.get("spell_save_dc"), "attack": spell.get("spell_attack_bonus"),
                  "slots": spell.get("spell_slots") or {}, "known": spell.get("spells_known") or []} if spell else None,
        "resources": resources.for_sheet(sheet),
        "features": sheet.get("features_and_traits", []),
        "death_saves": sheet.get("death_saves"),
        "effects": held,
        "conditions": _conditions(st, cid),
        # What the character has used this turn (all false, and not counted, outside a combat).
        "in_combat": tracker.in_combat(st, cid),
        "turn": tracker.turn_used(st, cid),
        "actions": actions.listing(campaign_dir, st, cid, sheet, present),
        "attacks": actions.attacks(sheet),
        # Bonuses the party can really give this character: a spell someone knows, Bardic Inspiration.
        "offers": actions.offers(campaign_dir, st, cid, sheets),
    }


def _conditions(st: dict, cid: str) -> list[dict]:
    """A creature's conditions; a `stance` is something it chose to do (Dodge, Hide), not something done to it."""
    names = [c["condition"] for c in ((st.get("active_encounter") or {}).get("conditions") or {}).get(cid, [])]
    return [{"name": n, "stance": n in tracker.STANCES} for n in names]


def view(campaign_dir: Path, hidden: frozenset[str] = frozenset(), present: list[dict] | None = None) -> dict:
    """`present`: the creatures on the stage that are not in the party, as {id, name}: the targets of an Attack out of a fight.
    `hidden`: creatures the party cannot see (a fight in the dark). They are in the turn bar as "Unseen", with no name or picture."""
    st = read_json(campaign_dir / "state.json") or {}
    enc = st.get("active_encounter") or {}
    fight = enc if enc.get("type") == "combat" else {}
    out: dict = {
        "characters": [],
        "location": st.get("location"),
        "game_time": st.get("game_time"),
        "quests": [{"title": q.get("title"), "status": q.get("status")} for q in st.get("quest_log", [])],
        "effects": effects.catalogue(),
        "combat": None,
        "present": present or [],
    }
    sheets = {p.stem: s for p in sorted((campaign_dir / "characters").glob("*.json")) if (s := read_json(p)) is not None}
    pcs = {cid: s.get("name") or beat.title(cid) for cid, s in sheets.items()}
    out["characters"] = [_character(campaign_dir, cid, s, st, present or [], sheets) for cid, s in sheets.items()]
    if fight:
        out["combat"] = {
            "round": fight.get("round", 1),
            "current": fight.get("current_turn"),
            "order": [_entrant(campaign_dir, st, o, pcs, n) if o["name"] not in hidden else _unseen(o, n)
                      for n, o in enumerate(fight.get("initiative_order", []))],
        }
        if fight.get("current_turn") in hidden:
            out["combat"]["current"] = f"unseen-{next(n for n, o in enumerate(fight['initiative_order']) if o['name'] == fight['current_turn'])}"
    return out


def _unseen(entry: dict, n: int) -> dict:
    return {"id": f"unseen-{n}", "name": "Unseen", "initiative": entry["initiative"], "pc": False, "team": "hostile", "health": "unhurt", "conditions": []}


def _entrant(campaign_dir: Path, st: dict, entry: dict, pcs: dict[str, str], n: int = 0) -> dict:
    """One place in the turn order. How hurt it is comes as a band; a creature's numbers stay behind the screen."""
    cid = entry["name"]
    rec = records.combatant(campaign_dir, st, cid)
    name = pcs.get(cid) or rec["name"] + (f" {cid.split('#')[1]}" if "#" in cid else "")
    return {"id": cid, "name": name, "initiative": entry["initiative"], "pc": cid in pcs, "team": tracker.team_of(st, cid),
            "health": records.health_band(rec), "conditions": _conditions(st, cid)}
