"""What a player character can do from the stage: common actions, class features, and bonuses for allies.

Modelled on Baldur's Gate 3: Attack, Dash, Disengage, Help and Hide cost an action; Shove costs a bonus
action. Dodge is not a BG3 action but a 5e one, so it is here too. In a combat only the character whose
turn it is can act, and each action spends the action, bonus action or reaction it costs. The turn
tracker (`active_encounter.resources`) is the one record: the stage shows it, and the DM's `attack` spends
the same pips.

`listing` says what is on offer and why something is greyed out. `perform` does it and returns the lines
for the DM, or a roll the player still has to make (Hide, Shove). `offers` and `grant` are the bonuses a
party member can really give (a spell they know, Bardic Inspiration): nothing is on the menu that no one
at the table can provide.
"""

from __future__ import annotations

import random
from pathlib import Path

from dnd_cli import character, combat, dice, effects, resources

# id, label, cost, what it needs (a target, a roll, a stance that lasts a round), and the tooltip.
BASIC: list[dict] = [
    {"id": "attack", "label": "Attack", "cost": "action", "target": "enemy", "combat": True,
     "info": "Strike with a weapon, or with bare fists"},
    {"id": "shove", "label": "Shove", "cost": "bonus", "target": "enemy", "combat": True, "roll": "athletics",
     "info": "Athletics check against the target's Athletics or Acrobatics: push it away or knock it prone"},
    {"id": "dash", "label": "Dash", "cost": "action", "combat": True, "stance": "dashing",
     "info": "Double your movement this turn"},
    {"id": "disengage", "label": "Disengage", "cost": "action", "combat": True, "stance": "disengaged",
     "info": "Moving away does not provoke opportunity attacks this turn"},
    {"id": "dodge", "label": "Dodge", "cost": "action", "combat": True, "stance": "dodging",
     "info": "Attacks against you have disadvantage until your next turn"},
    {"id": "help", "label": "Help", "cost": "action", "combat": True, "stance": "helping",
     "info": "Get a downed or prone ally back up, or give an ally advantage on their next check or attack"},
    {"id": "hide", "label": "Hide", "cost": "action", "roll": "stealth",
     "info": "Stealth check against what the enemies notice. Hidden, your next attack has advantage"},
]
# Class features the character card can use: (cost, only in a combat, tooltip). The use count comes from `resources`.
FEATURES: dict[str, tuple[str | None, bool, str]] = {
    "Second Wind": ("bonus", False, "Heal 1d10 + your fighter level"),
    "Action Surge": (None, True, "Take one more action this turn"),
    "Rage": ("bonus", True, "Bonus damage and resistance to weapon damage while it lasts"),
    "Channel Divinity": ("action", False, "Call on your god's power"),
    "Wild Shape": ("bonus", False, "Turn into a beast"),
    "Divine Sense": ("action", False, "Sense celestials, fiends and undead nearby"),
}
# Spells a character can cast on an ally for a bonus: effect id -> spell level (0 is a cantrip).
SPELL_BONUSES = {"guidance": 0, "resistance": 0, "bless": 1}


def _slug(name: str) -> str:
    return name.lower().replace("'", "").replace(" ", "-")


def _blocked(campaign_dir: Path, state: dict, cid: str, cost: str | None, only_combat: bool = False) -> str | None:
    """Why `cid` cannot spend `cost` now, or None."""
    if not combat.in_combat(state, cid):
        return "Only in a combat" if only_combat else None
    enc = state["active_encounter"]
    if enc.get("current_turn") != cid:
        return "Not your turn"
    if cost and combat.turn_used(state, cid)[cost]:
        return f"The {'bonus action' if cost == 'bonus' else cost} is used"
    return None


def _enemies(state: dict) -> list[str]:
    enc = state.get("active_encounter") or {}
    return [c for c in enc.get("participants", []) if c in (enc.get("monsters") or {})
            and enc["monsters"][c]["hp"]["current"] > 0]


def spec_for(sheet: dict, action: str) -> dict:
    """The BASIC or FEATURES entry named `action` (a feature is `feature:Second Wind`) for this sheet."""
    if action.startswith("feature:"):
        name = action.split(":", 1)[1]
        res = next((r for r in resources.for_sheet(sheet) if r["name"] == name), None)
        if name not in FEATURES or res is None:
            raise combat.RulesError(f"no class feature {name!r}.")
        cost, only_combat, info = FEATURES[name]
        return {"id": action, "label": name, "cost": cost, "combat": only_combat, "info": info,
                "left": res["max"] - res["used"], "feature": name}
    spec = next((a for a in BASIC if a["id"] == action), None)
    if spec is None:
        raise combat.RulesError(f"no action {action!r}. Actions: {', '.join(a['id'] for a in BASIC)}.")
    return spec


def why_not(campaign_dir: Path, state: dict, cid: str, sheet: dict, spec: dict) -> str | None:
    reason = _blocked(campaign_dir, state, cid, spec["cost"], spec.get("combat", False))
    if reason:
        return reason
    if spec.get("target") == "enemy" and not _enemies(state):
        return "No enemy"
    if spec.get("feature") and spec["left"] <= 0:
        return "No uses left"
    return None


def listing(campaign_dir: Path, state: dict, cid: str, sheet: dict) -> list[dict]:
    """The card's actions: the common ones, then the class features, each with `why` when it is greyed out."""
    specs = list(BASIC)
    specs += [spec_for(sheet, f"feature:{r['name']}") for r in resources.for_sheet(sheet) if r["name"] in FEATURES]
    return [{"id": s["id"], "label": s["label"], "cost": s["cost"], "info": s["info"], "target": s.get("target"),
             "why": why_not(campaign_dir, state, cid, sheet, s)} for s in specs]


def attacks(sheet: dict) -> list[dict]:
    """The weapons the Attack action can use, for the card's weapon step."""
    out = []
    for a in combat.pc_record(sheet, "x")["attacks"]:
        if a["damage"]:
            out.append({"name": a["name"], "bonus": a["bonus"], "damage": " + ".join(f"{e} {t}".strip() for e, t in a["damage"])})
    return out


def perform(campaign_dir: Path, state: dict, cid: str, action: str, target: str | None = None,
            weapon: str | None = None, rng: random.Random | None = None) -> dict:
    """Do one action. Returns {"lines": [...]} for the DM, plus {"roll": {what, note}} when the player must roll."""
    rng = rng or random
    sheet = character.load(campaign_dir, cid)
    spec = spec_for(sheet, action)
    reason = why_not(campaign_dir, state, cid, sheet, spec)
    if reason:
        raise combat.RulesError(f"{spec['label']}: {reason.lower()}.")
    if spec.get("target") == "enemy" and target not in _enemies(state):
        raise combat.RulesError(f"{spec['label']} needs an enemy that is standing: {', '.join(_enemies(state))}.")
    cost = spec["cost"]
    if spec["id"] == "attack":
        name = weapon or next(a["name"] for a in attacks(sheet))
        # The attack spends the action itself (and a hidden or dodging creature changes the roll).
        return {"lines": combat.attack(campaign_dir, state, cid, name, target, rng=rng, cost=cost)}
    if cost and combat.in_combat(state, cid):
        combat.spend_turn(state, cid, cost)
    if "roll" in spec:
        note = (f"Shove {target}: the DM compares it with the target's Athletics or Acrobatics, and a hit pushes or knocks it prone."
                if spec["id"] == "shove" else
                "Hide: the DM compares it with the enemies' passive Perception. If it succeeds, add the condition hidden "
                f"(`encounter condition {cid} add hidden`).")
        return {"lines": [], "roll": {"what": spec["roll"], "note": note, "title": spec["label"]}}
    if "stance" in spec:
        if combat.in_combat(state, cid):
            combat.condition(state, cid, "add", spec["stance"], rounds=1)
        return {"lines": [f"{cid} takes the {spec['label']} action."]}
    return {"lines": _feature(campaign_dir, state, cid, sheet, spec, rng)}


def _feature(campaign_dir: Path, state: dict, cid: str, sheet: dict, spec: dict, rng) -> list[str]:
    name = spec["feature"]
    lines = []
    if name == "Second Wind":
        total, groups = dice.roll(f"1d10+{sheet.get('level', 1)}", rng)
        combat.stage_roll(f"Second Wind 1d10+{sheet.get('level', 1)}", total, groups)
        lines.append(combat.heal(campaign_dir, state, cid, total))
    elif name == "Action Surge" and combat.in_combat(state, cid):
        combat.spend_turn(state, cid, "action", False)
        lines.append(f"{cid} Action Surge: the action is free again.")
    else:
        lines.append(f"{cid} uses {name}.")
    sheet = character.load(campaign_dir, cid)  # heal wrote the sheet
    resources.spend(sheet, name)
    character.save(campaign_dir, cid, sheet)
    if spec["cost"] and combat.in_combat(state, cid):
        combat.spend_turn(state, cid, spec["cost"])
    return lines


# -- bonuses a party member can give -------------------------------------------


def offers(campaign_dir: Path, state: dict, target: str) -> list[dict]:
    """The bonuses the party can put on `target` right now: a spell a member knows, Bardic Inspiration they have left."""
    out = []
    held = effects.active(campaign_dir, target)
    for src in combat.party(campaign_dir, state):
        if not character.character_path(campaign_dir, src).exists():
            continue
        sheet = character.load(campaign_dir, src)
        known = {_slug(s) for s in (sheet.get("spellcasting") or {}).get("spells_known", [])}
        slots = (sheet.get("spellcasting") or {}).get("spell_slots") or {}
        for eid, level in SPELL_BONUSES.items():
            if eid in known and eid not in held:
                free = level == 0 or (slots.get(str(level)) or {}).get("remaining", 0) > 0
                out.append(_offer(campaign_dir, state, src, sheet, eid, "action", level if level else None,
                                  None if free else "No spell slot"))
        inspiration = next((r for r in resources.for_sheet(sheet) if r["name"] == "Bardic Inspiration"), None)
        if inspiration and src != target and "bardic-inspiration" not in held:
            out.append(_offer(campaign_dir, state, src, sheet, "bardic-inspiration", "bonus", None,
                              None if inspiration["used"] < inspiration["max"] else "No uses left"))
    return out


def _offer(campaign_dir: Path, state: dict, src: str, sheet: dict, eid: str, cost: str, slot: int | None,
           why: str | None) -> dict:
    return {"effect": eid, "from": src, "from_name": sheet.get("name", src), "cost": cost, "slot": slot,
            "why": why or _blocked(campaign_dir, state, src, cost)}


def grant(campaign_dir: Path, state: dict, src: str, target: str, effect: str) -> str:
    """`src` puts `effect` on `target`: spends the slot or use and the action or bonus action, then adds it."""
    offer = next((o for o in offers(campaign_dir, state, target) if o["from"] == src and o["effect"] == effect), None)
    if offer is None:
        raise combat.RulesError(f"{src} cannot give {effect} to {target}.")
    if offer["why"]:
        raise combat.RulesError(f"{effect}: {offer['why'].lower()}.")
    sheet = character.load(campaign_dir, src)
    if offer["slot"]:
        character.cast_spell(sheet, offer["slot"])
    if effect == "bardic-inspiration":
        resources.spend(sheet, "Bardic Inspiration")
    character.save(campaign_dir, src, sheet)
    if combat.in_combat(state, src):
        combat.spend_turn(state, src, offer["cost"])
    effects.add(campaign_dir, target, effect)
    return f"{src} gives {effect} to {target}."
