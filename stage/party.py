"""What the party panel and the character sheet show, from the character files and the combat tracker.

An allowlist, like the rest of the stage server: a player character's own sheet, the names and
initiative of everyone in a combat, and the PC's own conditions. Never a monster's HP, AC or stats.
"""

from __future__ import annotations

from pathlib import Path

from dnd_cli import combat, dice, effects, resources
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


def _character(campaign_dir: Path, cid: str, sheet: dict, enc: dict) -> dict:
    scores = sheet.get("ability_scores", {})
    mods = {a: dice.mod(scores.get(a, 10)) for a in combat.ABILITIES}
    prof = sheet.get("proficiency_bonus", 2)
    saves = sheet.get("saving_throws", {})
    inventory = [{"name": i.get("name"), "quantity": i.get("quantity", 1), "weight": i.get("weight", 0),
                  "equipped": bool(i.get("equipped")), "description": i.get("description", ""), "rarity": i.get("rarity")}
                 for i in sheet.get("inventory", [])]
    spell = sheet.get("spellcasting") or {}
    spent = (enc.get("resources") or {}).get(cid, {})
    in_combat = cid in (enc.get("participants") or [])
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
        "conditions": [c["condition"] for c in (enc.get("conditions") or {}).get(cid, [])],
        # Only in a combat: what the character has used this turn.
        "turn": {k: bool(spent.get(k)) for k in combat.TURN_KINDS} if in_combat else None,
    }


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
        out["characters"].append(_character(campaign_dir, path.stem, sheet, fight))
    if fight:
        out["combat"] = {
            "round": fight.get("round", 1),
            "current": fight.get("current_turn"),
            "order": [{"id": o["name"], "name": pcs.get(o["name"]) or beat.title(o["name"]), "initiative": o["initiative"], "pc": o["name"] in pcs}
                      for o in fight.get("initiative_order", [])],
        }
    return out
