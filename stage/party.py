"""What the party panel and the character sheet show, from the character files and the combat tracker.

An allowlist, like the rest of the stage server: a player character's own sheet, the names, initiative,
conditions and how hurt (a band, never a number) everyone in a combat is. Never a monster's HP, AC or stats.
"""

from __future__ import annotations

from pathlib import Path

from dnd_cli import actions, combat, dice, effects, resources
from stage import beat
from stage.files import read_json


def _skills(sheet: dict, mods: dict, prof: int) -> list[dict]:
    """Every skill with its bonus and how proficient the sheet is in it (0, 1, or 2 for expertise)."""
    out = []
    for name, abil in combat.SKILLS.items():
        bonus = sheet.get("skills", {}).get(name, mods[abil])
        rank = round((bonus - mods[abil]) / prof) if prof else 0
        out.append({"name": name.replace("_", " ").title(), "ability": abil[:3].upper(), "bonus": bonus,
                    "prof": max(0, min(2, rank))})
    return out


def _character(campaign_dir: Path, cid: str, sheet: dict, st: dict) -> dict:
    scores = sheet.get("ability_scores", {})
    mods = {a: dice.mod(scores.get(a, 10)) for a in combat.ABILITIES}
    prof = sheet.get("proficiency_bonus", 2)
    saves = sheet.get("saving_throws", {})
    inventory = [{"name": i.get("name"), "quantity": i.get("quantity", 1), "weight": i.get("weight", 0),
                  "equipped": bool(i.get("equipped")), "description": i.get("description", ""), "rarity": i.get("rarity")}
                 for i in sheet.get("inventory", [])]
    spell = sheet.get("spellcasting") or {}
    return {
        "id": cid,
        "name": sheet.get("name"),
        "race": sheet.get("race"),
        "class": sheet.get("class"),
        "level": sheet.get("level"),
        "background": sheet.get("background"),
        "hp": sheet.get("hp", {}),
        "armor_class": sheet.get("armor_class"),
        "speed": sheet.get("speed", 30),
        "initiative": sheet.get("initiative", mods["dexterity"]),
        "prof": prof,
        "abilities": {a: {"score": scores.get(a, 10), "mod": mods[a], "save": saves.get(a, mods[a]),
                          "save_prof": saves.get(a, mods[a]) != mods[a]} for a in combat.ABILITIES},
        "skills": _skills(sheet, mods, prof),
        "weapons": sheet.get("weapons", []),
        "armor": sheet.get("armor"),
        "inventory": inventory,
        "capacity": scores.get("strength", 10) * 15,
        "spell": {"ability": spell.get("ability"), "dc": spell.get("spell_save_dc"), "attack": spell.get("spell_attack_bonus"),
                  "slots": spell.get("spell_slots") or {}, "known": spell.get("spells_known") or []} if spell else None,
        "resources": resources.for_sheet(sheet),
        "features": sheet.get("features_and_traits", []),
        "death_saves": sheet.get("death_saves"),
        "effects": effects.active(campaign_dir, cid),
        "conditions": _conditions(st, cid),
        # What the character has used this turn (all false, and not counted, outside a combat).
        "in_combat": combat.in_combat(st, cid),
        "turn": combat.turn_used(st, cid),
        "actions": actions.listing(campaign_dir, st, cid, sheet),
        "attacks": actions.attacks(sheet),
        # Bonuses the party can really give this character: a spell someone knows, Bardic Inspiration.
        "offers": actions.offers(campaign_dir, st, cid),
    }


def _conditions(st: dict, cid: str) -> list[dict]:
    """A creature's conditions; a `stance` is something it chose to do (Dodge, Hide), not something done to it."""
    names = [c["condition"] for c in ((st.get("active_encounter") or {}).get("conditions") or {}).get(cid, [])]
    return [{"name": n, "stance": n in combat.STANCES} for n in names]


def view(campaign_dir: Path) -> dict:
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
    }
    pcs: dict[str, str] = {}
    for path in sorted((campaign_dir / "characters").glob("*.json")):
        if (sheet := read_json(path)) is None:
            continue
        pcs[path.stem] = sheet.get("name") or beat.title(path.stem)
        out["characters"].append(_character(campaign_dir, path.stem, sheet, st))
    if fight:
        out["combat"] = {
            "round": fight.get("round", 1),
            "current": fight.get("current_turn"),
            "order": [_entrant(campaign_dir, st, o, pcs) for o in fight.get("initiative_order", [])],
        }
    return out


def _entrant(campaign_dir: Path, st: dict, entry: dict, pcs: dict[str, str]) -> dict:
    """One place in the turn order. How hurt it is comes as a band; a creature's numbers stay behind the screen."""
    cid = entry["name"]
    rec = combat.combatant(campaign_dir, st, cid)
    name = pcs.get(cid) or rec["name"] + (f" {cid.split('#')[1]}" if "#" in cid else "")
    return {"id": cid, "name": name, "initiative": entry["initiative"], "pc": cid in pcs,
            "health": combat.health_band(rec), "conditions": _conditions(st, cid)}
