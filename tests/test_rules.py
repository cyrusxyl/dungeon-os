"""Checks for the rules commands: dice, encounters, attacks, saves, checks, sheets, session end.

Run from the repo root:  .venv/bin/python tests/test_rules.py

Plain asserts, a seeded RNG, and stub monster data: no network.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from dnd_cli import actions, canon, character, combat, dice, effects, loot, resources, sheet
from dnd_cli import item as inv
from dnd_cli.commands import session_cmd

REPO = Path(__file__).resolve().parents[1]
PASS = FAIL = 0

GOBLIN = {
    "index": "goblin", "name": "Goblin", "hit_points": 7, "armor_class": [{"value": 15}], "xp": 50,
    "strength": 8, "dexterity": 14, "constitution": 10, "intelligence": 10, "wisdom": 8, "charisma": 8,
    "proficiencies": [{"value": 6, "proficiency": {"index": "skill-stealth"}}],
    "damage_resistances": ["fire"], "damage_immunities": [], "damage_vulnerabilities": [],
    "actions": [
        {"name": "Multiattack", "damage": []},
        {"name": "Scimitar", "attack_bonus": 4, "damage": [{"damage_dice": "1d6+2", "damage_type": {"name": "Slashing"}}]},
        {"name": "Spit", "dc": {"dc_type": {"index": "dex"}, "dc_value": 12, "success_type": "half"},
         "damage": [{"damage_dice": "2d6", "damage_type": {"name": "Acid"}}]},
    ],
}


def wear(d: dict, name: str, on: bool) -> None:
    it = inv.get(d, name)
    (it.equip if on else it.unequip)(d)


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + cond, FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


def raises(fn) -> bool:
    try:
        fn()
    except (combat.RulesError, canon.CanonError, dice.DiceError):
        return True
    return False


class Fixed(random.Random):
    """randint returns queued values (then 10)."""

    def __init__(self, *values):
        super().__init__(0)
        self.values = list(values)

    def randint(self, a, b):
        return self.values.pop(0) if self.values else 10


def campaign(tmp: Path) -> Path:
    """The example campaign as committed (a live run may have changed the working copy)."""
    src = REPO / "tests" / "fixtures" / "example-campaign"
    c = tmp / "camp"
    shutil.copytree(src, c, ignore=shutil.ignore_patterns("stage", ".cache"))
    tracked = subprocess.run(["git", "ls-files", "."], cwd=src, capture_output=True, text=True).stdout.split()
    for rel in tracked:
        committed = subprocess.run(["git", "show", f"HEAD:./{rel}"], cwd=src, capture_output=True)
        if committed.returncode == 0:
            (c / rel).write_bytes(committed.stdout)
    return c


def fight(c: Path) -> dict:
    """A running combat: the party and two goblins, built without the API."""
    state = combat.load_state(c)
    state["active_encounter"] = {"type": "combat", "round": 1, "participants": [], "initiative_order": [],
                                 "current_turn": None, "conditions": {}, "monsters": {}}
    enc = state["active_encounter"]
    for i, cid in enumerate(["aragorn", "legolas", "goblin#1", "goblin#2"]):
        if cid.startswith("goblin"):
            enc["monsters"][cid] = combat.monster_record(GOBLIN, cid)
        enc["participants"].append(cid)
        enc["initiative_order"].append({"name": cid, "initiative": 20 - i, "bonus": 0})
    enc["current_turn"] = "aragorn"
    return state


def test_dice() -> None:
    print("dice")
    check("parse terms", dice.parse("2d6+1d4-1") == ([(1, 2, 6), (1, 1, 4)], -1))
    check("a bad expression is refused", raises(lambda: dice.parse("2x6")))
    total, groups = dice.roll("1d6+2", Fixed(4))
    check("roll adds the bonus", total == 6 and groups == [{"die": "1d6", "faces": [4]}])
    total, groups = dice.roll("1d6+2", Fixed(4, 5), crit=True)
    check("a crit rolls the dice twice", total == 11 and groups[0]["die"] == "2d6")
    check("advantage keeps the higher d20", dice.d20(Fixed(3, 17), adv=True) == (17, [3, 17]))


def test_combat(c: Path) -> None:
    print("encounter, attack, save, check")
    state = fight(c)
    lines = combat.attack(c, state, "aragorn", "longsword", "goblin#1", rng=Fixed(15, 6))
    check("a hit applies damage to the goblin", "hit" in lines[0] and state["active_encounter"]["monsters"]["goblin#1"]["hp"]["current"] == 0)
    check("a downed creature is marked", "DOWN" in lines[1])
    hp = state["active_encounter"]["monsters"]["goblin#2"]["hp"]["current"]
    lines = combat.attack(c, state, "aragorn", "improvised", "goblin#2", rng=Fixed(15, 3), damage_expr="1d4", damage_type="bludgeoning", bonus=2, cost=None)
    check("an improvised attack needs no entry on the record: the to-hit is --bonus", "hit" in lines[0] and "17" in lines[0]
          and state["active_encounter"]["monsters"]["goblin#2"]["hp"]["current"] == hp - 3)
    state["active_encounter"]["monsters"]["goblin#2"]["hp"]["current"] = hp
    check("it needs damage dice", raises(lambda: combat.attack(c, state, "aragorn", "improvised", "goblin#2", rng=Fixed(15))))
    before = character.load(c, "aragorn")["hp"]["current"]
    lines = combat.attack(c, state, "goblin#2", "scimitar", "aragorn", rng=Fixed(20, 3, 4))
    hp = character.load(c, "aragorn")["hp"]["current"]
    check("a natural 20 crits and doubles dice; the PC sheet is saved",
          any("CRITICAL" in ln for ln in lines) and hp == before - 9)
    from dnd_cli.commands import rules_cmd
    import argparse

    disk = (c / "state.json").read_bytes()  # the later checks need the state as it was
    combat.save_state(c, state)
    ev = staged(c, lambda: rules_cmd.execute_encounter(str(c), "damage", argparse.Namespace(target="aragorn", amount="3", type=None)))
    check("damage with no roll still leaves a line in the log for a hero", [e["type"] for e in ev] == ["feed"] and "HP" in ev[0]["text"])
    ev = staged(c, lambda: rules_cmd.execute_encounter(str(c), "damage", argparse.Namespace(target="goblin#2", amount="1", type=None)))
    check("and hides the HP of a creature", len(ev) == 1 and "HP" not in ev[0]["text"] and "takes damage" in ev[0]["text"])
    (c / "state.json").write_bytes(disk)
    ev = staged(c, lambda: combat.attack(c, state, "goblin#2", "scimitar", "aragorn", rng=Fixed(20, 3, 4), secret=True, cost=None, catch_up=False))
    check("a secret hit on a hero hides the dice but shows a line", [e["type"] for e in ev] == ["feed"] and "takes" in ev[0]["text"] and "AC" not in ev[0]["text"])
    ev = staged(c, lambda: combat.attack(c, state, "goblin#2", "scimitar", "aragorn", rng=Fixed(2), secret=True, cost=None, catch_up=False))
    check("a secret miss on a hero shows a line", [e["type"] for e in ev] == ["feed"] and "misses" in ev[0]["text"])
    ev = staged(c, lambda: combat.attack(c, state, "aragorn", "longsword", "goblin#2", rng=Fixed(2), secret=True, cost=None, catch_up=False))
    check("a secret attack on a creature stays hidden", ev == [])
    from dnd_cli.commands import character_cmd

    ev = staged(c, lambda: character_cmd.execute_apply_damage(str(c), "aragorn", 2))
    check("hand damage on a sheet leaves a line", [e["type"] for e in ev] == ["feed"] and "aragorn takes 2" in ev[0]["text"])
    check("an attack moves the turn to the attacker", state["active_encounter"]["current_turn"] == "goblin#2")
    check("a natural 1 misses", "miss" in combat.attack(c, state, "goblin#2", "scimitar", "aragorn", rng=Fixed(1))[-1])
    state["active_encounter"]["current_turn"] = "aragorn"
    state["active_encounter"]["round"] = 1
    check("a DC action points to save", raises(lambda: combat.attack(c, state, "goblin#2", "spit", "aragorn")))
    check("Multiattack is not an attack", all(a["name"] != "Multiattack" for a in state["active_encounter"]["monsters"]["goblin#2"]["attacks"]))
    out = combat.damage(c, state, "goblin#2", 6, "fire")
    check("resistance halves damage", "resists fire" in out and state["active_encounter"]["monsters"]["goblin#2"]["hp"]["current"] == 4)
    # The damage is rolled once, before the saves: 2d6 = 1 + 2, then a d20 of 15.
    lines = combat.save(c, state, ["legolas"], None, None, source="goblin#2:spit", rng=Fixed(1, 2, 15))
    before = character.load(c, "legolas")["hp"]["current"]
    check("a bad target id rolls and damages no one",
          raises(lambda: combat.save(c, state, ["legolas", "goblin#9"], "dex", 12, damage_expr="2d6"))
          and character.load(c, "legolas")["hp"]["current"] == before)
    check("--from takes DC, damage and half from the action", "DEX save" in lines[0] and "success" in lines[0]
          and "legolas takes 1" in lines[1])
    lines = combat.check(c, state, ["aragorn", "legolas"], "perception", dc=15, rng=Fixed(12, 2))
    check("a group check passes when half succeed", lines[-1].endswith("SUCCESS"))
    check("passive scores need no roll", combat.check(c, state, ["legolas"], "perception", passive=True)[0].endswith("16"))
    combat.condition(state, "goblin#2", "add", "poisoned", rounds=1, save="con:11")
    lines = combat.next_turn(c, state)
    check("next skips to the next living combatant", lines[0].startswith("Round 1: legolas"))
    lines = combat.next_turn(c, state)
    check("goblin#1 is down and skipped; goblin#2's condition ends", "goblin#2's turn" in lines[0] and "poisoned ends" in lines[1])
    check("status lists everyone", len(combat.status(c, state)) == 5)
    combat.damage(c, state, "goblin#2", 10)
    lines = combat.end(c, state)
    check("end splits XP of defeated foes", lines[0].startswith("Defeated foes give 100 XP: 50 each")
          and character.load(c, "aragorn")["experience_points"] == 900 + 50)
    check("end clears the encounter", state["active_encounter"] is None)

    state = fight(c)
    state["active_encounter"]["monsters"]["goblin#1"]["xp"] = 30
    combat.damage(c, state, "goblin#2", 10)
    check("--resolved on an unknown id is refused and the fight stays", raises(lambda: combat.end(c, state, resolved=["orc#1"])) and state["active_encounter"] is not None)
    lines = combat.end(c, state, resolved=["goblin#1"])
    check("a creature resolved without a kill gives its XP", lines[0].startswith("Defeated foes give 80 XP: 40 each"))


def staged(c: Path, fn) -> list[dict]:
    """The roll events a rules call sends to the stage."""
    log = c / "stage" / "events.ndjson"
    log.parent.mkdir(exist_ok=True)
    log.unlink(missing_ok=True)
    os.environ["DUNGEON_STAGE_LOG"] = str(log)
    try:
        fn()
    finally:
        del os.environ["DUNGEON_STAGE_LOG"]
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_effects(c: Path) -> None:
    print("effects and the roll window")
    state = fight(c)
    skill = combat.skill_bonus(combat.combatant(c, state, "aragorn"), "athletics")
    effects.add(c, "aragorn", "guidance")
    # The bonus die is rolled first (3), then the d20 (10).
    check_line: list = []
    ev = staged(c, lambda: check_line.append(combat.check(c, state, ["aragorn"], "athletics", dc=12, rng=Fixed(3, 10))))
    d = ev[0]["detail"]
    r = d["rolls"][0]
    check("guidance adds its die to the total", r["total"] == 10 + skill + 3 and r["bonus"] == [
        {"label": "Guidance", "die": "1d4", "faces": [3], "value": 3}])
    check("the output line names the effect", "guidance +3" in check_line[-1][0])
    check("a check shows its DC and title", d["target"] == {"label": "Difficulty Class", "value": 12}
          and d["title"] == "Athletics" and d["subtitle"] == "Strength Check" and ev[0]["total"] == r["total"])
    check("the tiles add up to the skill bonus", sum(t["value"] for t in r["mods"]) == skill)
    check("guidance is spent by the check", effects.active(c, "aragorn") == [])
    ev = staged(c, lambda: combat._initiative_feed(c, state, state["active_encounter"]))
    check("the initiative goes to the stage log by name", ev and ev[0]["type"] == "feed" and ev[0]["text"].startswith("Initiative: Aragorn 20")
          and "Goblin 1 18" in ev[0]["text"] and "#" not in ev[0]["text"])
    ev = staged(c, lambda: combat.check(c, state, ["aragorn"], "athletics", dc=12, hide_dc=True, rng=Fixed(10)))
    check("--hide-dc keeps the DC off the stage", "target" not in ev[0]["detail"] and ev[0]["detail"]["rolls"][0]["bonus"] == [])
    check("a check with no DC has no outcome", staged(c, lambda: combat.check(
        c, state, ["aragorn"], "athletics", rng=Fixed(10)))[0]["detail"]["rolls"][0]["outcome"] is None)

    effects.add(c, "aragorn", "advantage")
    r = staged(c, lambda: combat.check(c, state, ["aragorn"], "athletics", dc=30, rng=Fixed(4, 18)))[0]["detail"]["rolls"][0]
    check("advantage rolls two d20 and keeps the higher", r["mode"] == "advantage" and r["d20"] == [4, 18] and r["kept"] == 1)
    effects.add(c, "aragorn", "advantage")
    effects.add(c, "aragorn", "disadvantage")
    r = staged(c, lambda: combat.check(c, state, ["aragorn"], "athletics", rng=Fixed(4)))[0]["detail"]["rolls"][0]
    check("advantage and disadvantage cancel to one die", r["mode"] == "normal" and len(r["d20"]) == 1)

    effects.add(c, "aragorn", "bless")
    effects.add(c, "aragorn", "guidance")
    check("Bless and Guidance can both be on one character", effects.active(c, "aragorn") == ["bless", "guidance"])
    r = staged(c, lambda: combat.check(c, state, ["aragorn"], "dex-save", dc=12, rng=Fixed(2, 9)))[0]["detail"]
    check("a save through check uses the save effects (Bless), not the check effects (Guidance)",
          r["kind"] == "save" and [b["label"] for b in r["rolls"][0]["bonus"]] == ["Bless"] and effects.active(c, "aragorn") == ["bless", "guidance"])
    effects.remove(c, "aragorn", "guidance")
    r = staged(c, lambda: combat.save(c, state, ["aragorn", "legolas"], "dex", 12, rng=Fixed(2, 9, 14)))
    rolls = r[0]["detail"]["rolls"]
    check("a save for two targets is one event with two rolls; bless stays", len(r) == 1 and len(rolls) == 2
          and rolls[0]["bonus"][0]["label"] == "Bless" and effects.active(c, "aragorn") == ["bless"])
    check("an outcome is judged on the total, not the natural d20", rolls[0]["outcome"] == ("success" if rolls[0]["total"] >= 12 else "fail"))
    r = staged(c, lambda: combat.save(c, state, ["aragorn"], "dex", 12, skip=("bless",), rng=Fixed(9)))[0]["detail"]["rolls"][0]
    check("the player can leave an effect off a roll", r["bonus"] == [] and effects.active(c, "aragorn") == ["bless"])
    try:
        effects.add(c, "aragorn", "haste")
        refused = False
    except ValueError:
        refused = True
    check("a bad effect name is refused", refused)

    ev = staged(c, lambda: combat.attack(c, state, "aragorn", "longsword", "goblin#2", rng=Fixed(2, 15, 6)))
    check("a monster's AC stays off the stage", "target" not in ev[0]["detail"] and ev[0]["detail"]["rolls"][0]["outcome"] == "hit")
    ev = staged(c, lambda: combat.attack(c, state, "goblin#2", "scimitar", "aragorn", rng=Fixed(5)))
    check("a player character's AC is shown", ev[0]["detail"]["target"]["label"] == "Armor Class")
    effects.remove(c, "aragorn", "bless")

    rec = {"mods": {"charisma": 2}, "prof": 2}
    check("expertise splits into two tiles", [t["value"] for t in combat._tiles(rec, "charisma", 6, "Deception")] == [2, 2, 2])
    check("proficiency is one tile", len(combat._tiles(rec, "charisma", 4, "Deception")) == 2)
    check("an unknown bonus is Other", combat._tiles(rec, "charisma", 3, "Deception")[1]["label"] == "Other")
    check("a death save has a window", staged(c, lambda: (combat.damage(c, state, "legolas", 100),
          combat.death_save(c, state, "legolas", Fixed(12))))[0]["detail"]["kind"] == "death")
    combat.heal(c, state, "legolas", 100)


def raises_value(fn) -> bool:
    try:
        fn()
    except ValueError:
        return True
    return False


def test_resources(c: Path) -> None:
    print("class resources and turn actions")
    fighter = {"class": "Fighter", "level": 3, "ability_scores": {"charisma": 10}}
    check("a fighter has Second Wind and Action Surge", [(r["name"], r["max"]) for r in resources.for_sheet(fighter)] == [("Second Wind", 1), ("Action Surge", 1)])
    check("rage grows with level", resources.for_sheet({"class": "Barbarian", "level": 9, "ability_scores": {}})[0]["max"] == 4)
    check("a rogue has none", resources.for_sheet({"class": "Rogue", "level": 5, "ability_scores": {}}) == [])
    check("bardic inspiration follows CHA (at least 1)", resources.for_sheet({"class": "Bard", "level": 1, "ability_scores": {"charisma": 16}})[0]["max"] == 3)
    pal = {"class": "Paladin", "level": 3, "ability_scores": {"charisma": 16}}
    check("Lay on Hands holds 5 HP per level", next(r for r in resources.for_sheet(pal) if r["name"] == "Lay on Hands")["max"] == 15)
    check("a spend is counted", resources.spend(fighter, "Second Wind")["used"] == 1)
    check("a spend above what is left is refused and changes nothing", raises_value(lambda: resources.spend(fighter, "Second Wind")) and fighter["resources_used"]["Second Wind"] == 1)
    check("a big spend of a pool is refused", raises_value(lambda: resources.spend(pal, "Lay on Hands", 16)) and not pal.get("resources_used"))
    check("the whole pool can be spent", resources.spend(pal, "Lay on Hands", 15)["used"] == 15)
    check("a use can be given back", resources.spend(fighter, "Second Wind", -1)["used"] == 0)
    monk = {"class": "Monk", "level": 5, "ability_scores": {}}
    resources.spend(monk, "Ki", 3)
    resources.rest(monk, "short")
    check("a short rest restores ki", resources.for_sheet(monk)[0]["used"] == 0)
    sorc = {"class": "Sorcerer", "level": 5, "ability_scores": {}}
    resources.spend(sorc, "Sorcery Points", 2)
    resources.rest(sorc, "short")
    check("a short rest keeps what comes back on a long rest", resources.for_sheet(sorc)[0]["used"] == 2)
    resources.rest(sorc, "long")
    check("a long rest restores all", resources.for_sheet(sorc)[0]["used"] == 0)
    state = fight(c)
    combat.spend_turn(state, "aragorn", "reaction")
    check("a reaction is marked used", state["active_encounter"]["resources"]["aragorn"] == {"reaction": True})
    check("only an action, bonus action or reaction counts", raises(lambda: combat.spend_turn(state, "aragorn", "dance")))
    from dnd_cli.commands import character_cmd as cc

    def run(fn, *args, **kw):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return fn(str(c), *args, **kw)
    before = character.load(c, "aragorn")
    check("character use above what is left fails and saves nothing", run(cc.execute_use, "aragorn", "Second Wind", 5) == 1 and character.load(c, "aragorn") == before)
    check("character set records a fighting style", run(cc.execute_set, "aragorn", "fighting_style", "Defense") == 0 and character.load(c, "aragorn")["fighting_style"] == "Defense")
    check("character set records a subclass", run(cc.execute_set, "aragorn", "subclass", "Champion") == 0 and character.load(c, "aragorn")["subclass"] == "Champion")
    check("character add puts a spell in spells_known", run(cc.execute_add, "legolas", "spell", "Fog Cloud") == 0 and "Fog Cloud" in character.load(c, "legolas")["spellcasting"]["spells_known"])
    check("character add --prepared uses spells_prepared", run(cc.execute_add, "legolas", "spell", "Fog Cloud", prepared=True) == 0 and character.load(c, "legolas")["spellcasting"]["spells_prepared"] == ["Fog Cloud"])
    check("the same spell twice is refused", run(cc.execute_add, "legolas", "spell", "fog cloud") == 1)
    check("a spell for a non-caster is refused", run(cc.execute_add, "aragorn", "spell", "Fog Cloud") == 1)
    check("character add puts a feat in features_and_traits", run(cc.execute_add, "aragorn", "feat", "Alert", desc="+5 initiative.") == 0
          and {"name": "Alert", "description": "+5 initiative."} in character.load(c, "aragorn")["features_and_traits"])
    check("only a combatant counts", raises(lambda: combat.spend_turn(state, "bilbo", "action")))
    combat.next_turn(c, state)
    check("the next combatant starts with all three free", state["active_encounter"]["resources"][state["active_encounter"]["current_turn"]] == {})


def test_actions(c: Path) -> None:
    print("turn economy, common actions, bonuses from the party")
    sheet_ = character.load(c, "aragorn")
    unarmed = next(a for a in combat.pc_record({**sheet_, "weapons": []}, "aragorn")["attacks"] if a["name"] == "Unarmed Strike")
    check("a character with no weapon still has Unarmed Strike: 1 + Strength, bludgeoning",
          unarmed["damage"] == [["1+3", "bludgeoning"]] and unarmed["bonus"] == 3 + sheet_["proficiency_bonus"])

    state = fight(c)
    combat.attack(c, state, "aragorn", "longsword", "goblin#1", rng=Fixed(15, 6))
    check("an attack spends the action", combat.turn_used(state, "aragorn") == {"action": True, "bonus": False, "reaction": False})
    state = fight(c)
    combat.attack(c, state, "aragorn", "longsword", "goblin#1", rng=Fixed(15, 6), cost=None)
    check("a free attack (a second one of the same action) spends nothing", combat.turn_used(state, "aragorn")["action"] is False)
    combat.attack(c, state, "aragorn", "longsword", "goblin#2", rng=Fixed(15, 6), cost="reaction")
    check("an opportunity attack spends the reaction", combat.turn_used(state, "aragorn") == {"action": False, "bonus": False, "reaction": True})

    # Dodging gives disadvantage: two d20 are rolled and the lower one counts.
    state = fight(c)
    combat.condition(state, "goblin#1", "add", "dodging", rounds=1)
    line = combat.attack(c, state, "aragorn", "longsword", "goblin#1", rng=Fixed(18, 4))[0]
    check("attacking a dodging creature has disadvantage", "disadvantage 18,4" in line and "4+5 = 9" in line)
    combat.condition(state, "aragorn", "add", "hidden")
    line = combat.attack(c, state, "aragorn", "longsword", "goblin#2", rng=Fixed(4, 17))[0]
    check("a hidden attacker has advantage and is seen afterwards", "advantage 4,17" in line and not combat.has_condition(state, "aragorn", "hidden"))

    # The actions on the card.
    state = fight(c)
    rng = Fixed(15, 6)
    done = actions.perform(c, state, "aragorn", "attack", "goblin#1", "Longsword", rng)
    check("Attack from the card rolls, applies damage and spends the action",
          "hit" in done["lines"][0] and combat.turn_used(state, "aragorn")["action"])
    check("a spent action cannot be spent again", raises(lambda: actions.perform(c, state, "aragorn", "dash")))
    check("a bonus action is still free for Shove", actions.perform(c, state, "aragorn", "shove", "goblin#2")["roll"]["what"] == "athletics"
          and combat.turn_used(state, "aragorn")["bonus"])
    check("Shove needs a standing enemy", raises(lambda: actions.perform(c, fight(c), "aragorn", "shove", "legolas")))
    check("only the character whose turn it is can act", raises(lambda: actions.perform(c, fight(c), "legolas", "dash")))
    state = fight(c)
    actions.perform(c, state, "aragorn", "dodge")
    check("Dodge is a condition for one round, and spends the action",
          combat.has_condition(state, "aragorn", "dodging") and combat.turn_used(state, "aragorn")["action"])
    state = fight(c)
    check("Hide asks for a Stealth roll", actions.perform(c, state, "aragorn", "hide")["roll"]["what"] == "stealth")
    check("a creature that is not in a combat cannot Dash", raises(lambda: actions.perform(c, combat.load_state(c), "aragorn", "dash")))
    check("Hide works outside a combat and spends nothing", bool(actions.perform(c, combat.load_state(c), "aragorn", "hide")["roll"]))
    why = {a["id"]: a["why"] for a in actions.listing(c, fight(c), "legolas", character.load(c, "legolas"))}
    check("the card says why an action is greyed out", why["dash"] == "Not your turn" and why["attack"] == "Not your turn")
    why = {a["id"]: a["why"] for a in actions.listing(c, combat.load_state(c), "aragorn", character.load(c, "aragorn"))}
    check("outside a combat Attack is on when someone is here",
          next(a for a in actions.listing(c, combat.load_state(c), "aragorn", character.load(c, "aragorn"), [{"id": "x", "name": "X"}])
               if a["id"] == "attack")["why"] is None)
    check("outside a combat only the combat-free ones are on",
          why["attack"] == "No one here to attack" and why["hide"] is None and why["feature:Second Wind"] is None)

    # Second Wind and Action Surge.
    state = fight(c)
    character.apply_damage(sheet_ := character.load(c, "aragorn"), 8)
    character.save(c, "aragorn", sheet_)
    hp = character.load(c, "aragorn")["hp"]["current"]
    actions.perform(c, state, "aragorn", "feature:Second Wind", rng=Fixed(6))
    after = character.load(c, "aragorn")
    check("Second Wind heals 1d10 + level, spends a use and the bonus action",
          after["hp"]["current"] == min(after["hp"]["max"], hp + 6 + after["level"])
          and after["resources_used"] == {"Second Wind": 1} and combat.turn_used(state, "aragorn")["bonus"])
    check("a spent feature is refused", raises(lambda: actions.perform(c, state, "aragorn", "feature:Second Wind")))
    combat.spend_turn(state, "aragorn", "action")
    actions.perform(c, state, "aragorn", "feature:Action Surge")
    check("Action Surge gives the action back", combat.turn_used(state, "aragorn")["action"] is False)

    # End turn.
    state = fight(c)
    check("only the creature whose turn it is can end it", raises(lambda: combat.end_turn(c, state, "legolas")))
    lines = combat.end_turn(c, state, "aragorn")
    check("ending the turn moves to the next creature", state["active_encounter"]["current_turn"] == "legolas" and "legolas" in lines[0])

    # Bonuses: only what a party member can give.
    state = combat.load_state(c)
    check("a party with no caster of them has nothing to offer",
          [o["effect"] for o in actions.offers(c, state, "aragorn")] == [])
    ranger = character.load(c, "legolas")
    ranger["spellcasting"]["spells_known"].append("Guidance")
    character.save(c, "legolas", ranger)
    offered = actions.offers(c, state, "aragorn")
    check("a known spell (any spelling) is on offer from its caster", [(o["effect"], o["from"]) for o in offered] == [("guidance", "legolas")])
    check("an unknown effect is refused", raises(lambda: actions.grant(c, state, "legolas", "aragorn", "advantage")))
    check("a character who cannot cast it is refused", raises(lambda: actions.grant(c, state, "aragorn", "legolas", "guidance")))
    actions.grant(c, state, "legolas", "aragorn", "guidance")
    check("a cantrip is given for free outside a combat", effects.active(c, "aragorn") == ["guidance"])
    check("an effect already held is not offered again", actions.offers(c, state, "aragorn") == [])
    effects.remove(c, "aragorn", "guidance")
    state = fight(c)
    state["active_encounter"]["current_turn"] = "legolas"
    actions.grant(c, state, "legolas", "aragorn", "guidance")
    check("in a combat the caster spends the action", combat.turn_used(state, "legolas")["action"] and effects.active(c, "aragorn") == ["guidance"])
    effects.remove(c, "aragorn", "guidance")
    check("a spent action blocks the next spell", raises(lambda: actions.grant(c, state, "legolas", "aragorn", "guidance")))
    ranger = character.load(c, "legolas")
    ranger["class"], ranger["resources_used"] = "Bard", {}
    character.save(c, "legolas", ranger)
    check("a bard offers Bardic Inspiration to others, not to themselves",
          ("bardic-inspiration", "legolas") in [(o["effect"], o["from"]) for o in actions.offers(c, combat.load_state(c), "aragorn")]
          and "bardic-inspiration" not in [o["effect"] for o in actions.offers(c, combat.load_state(c), "legolas")])
    ranger["spellcasting"]["spells_known"].remove("Guidance")
    ranger["class"] = "Ranger"
    character.save(c, "legolas", ranger)


def test_paladin(c: Path) -> None:
    print("Divine Smite and Lay on Hands")
    pal = character.load(c, "aragorn")
    pal["name"] = "Pally"
    pal["class"], pal["level"] = "Paladin", 3
    pal["features_and_traits"] = [{"name": "Lay on Hands", "description": "x"}, {"name": "Divine Smite", "description": "x"}]
    pal["spellcasting"] = {"ability": "charisma", "spell_save_dc": 11, "spell_attack_bonus": 3,
                           "spell_slots": {"1": {"max": 3, "remaining": 3}, "2": {"max": 1, "remaining": 1}}}
    pal["resources_used"] = {}
    pal["hp"] = {"current": 10, "max": 28, "temp": 0}
    character.save(c, "pally", pal)

    def duel(hp: int = 100, ctype: str = "") -> dict:
        st = fight(c)
        enc = st["active_encounter"]
        enc["participants"].append("pally")
        enc["initiative_order"].append({"name": "pally", "initiative": 30, "bonus": 0})
        enc["current_turn"] = "pally"
        for g in enc["monsters"].values():
            g["hp"] = {"current": hp, "max": hp}
            g["ctype"] = ctype
        return st

    def slots() -> dict:
        return {k: v["remaining"] for k, v in character.load(c, "pally")["spellcasting"]["spell_slots"].items()}

    def dealt(st: dict) -> int:
        return 100 - st["active_encounter"]["monsters"]["goblin#1"]["hp"]["current"]

    def refill() -> None:
        sh = character.load(c, "pally")
        for v in sh["spellcasting"]["spell_slots"].values():
            v["remaining"] = v["max"]
        character.save(c, "pally", sh)

    check("smite dice: 2d8 at level 1, +1d8 per level, 5d8 at most, +1d8 against undead or a fiend",
          [combat.smite_dice(n) for n in (1, 2, 4, 5, 9)] == ["2d8", "3d8", "5d8", "5d8", "5d8"]
          and combat.smite_dice(1, "Undead") == "3d8" and combat.smite_dice(4, "fiend (devil)") == "6d8")
    state = duel()
    lines = combat.attack(c, state, "pally", "longsword", "goblin#1", rng=Fixed(15, 6, 3, 4), smite=1)
    check("--smite adds 2d8 radiant after the weapon (9 + 7) and spends a level 1 slot",
          dealt(state) == 16 and slots() == {"1": 2, "2": 1} and any("Divine Smite" in ln and "2d8" in ln for ln in lines))
    refill()
    state = duel()
    combat.attack(c, state, "pally", "longsword", "goblin#1", rng=Fixed(20, 6, 6, 1, 2, 3, 4, 5, 6), smite=2)
    check("a critical hit doubles the smite dice: 3d8 becomes 6d8 (15 + 1+2+3+4+5+6)", dealt(state) == 15 + 21 and slots() == {"1": 3, "2": 0})
    refill()
    state = duel(ctype="undead")
    combat.attack(c, state, "pally", "longsword", "goblin#1", rng=Fixed(15, 6, 1, 1, 1), smite=1)
    check("an undead takes one more die (3d8)", dealt(state) == 9 + 3)
    refill()
    state = duel()
    check("a level 5 slot or more still gives 5d8 at most", combat.smite_dice(9) == "5d8")
    check("no smite on a miss, and no slot spent",
          len(combat.attack(c, duel(), "pally", "longsword", "goblin#1", rng=Fixed(2), smite=1)) == 1 and slots() == {"1": 3, "2": 1})
    check("no smite without a slot of that level", raises(lambda: combat.attack(c, duel(), "pally", "longsword", "goblin#1", rng=Fixed(15), smite=3)))
    check("no smite on a ranged attack", raises(lambda: combat.attack(c, duel(), "pally", "longbow", "goblin#1", rng=Fixed(15), smite=1)))
    check("no smite on a melee weapon used at range", raises(lambda: combat.attack(c, duel(), "pally", "longsword", "goblin#1", rng=Fixed(15), smite=1, melee=False)))
    check("no smite for a character without the feature", raises(lambda: combat.attack(c, duel(), "aragorn", "longsword", "goblin#1", rng=Fixed(15), smite=1)))
    sh = character.load(c, "pally")
    sh["weapons"].append({"name": "Javelin", "attack_bonus": 5, "damage": "1d6+3", "damage_type": "piercing",
                          "properties": ["thrown"], "equipped": False})
    character.save(c, "pally", sh)
    check("no smite for a thrown javelin without the board's say", raises(lambda: combat.attack(c, duel(), "pally", "javelin", "goblin#1", rng=Fixed(15, 4), smite=1)))
    st_j = duel()
    combat.attack(c, st_j, "pally", "javelin", "goblin#1", rng=Fixed(15, 4))
    check("a thrown javelin leaves no smite offer", "pending_smite" not in st_j["active_encounter"])
    combat.attack(c, duel(), "pally", "javelin", "goblin#1", rng=Fixed(15, 4, 3, 3), smite=1, melee=True)
    check("the board can still say a thrown weapon is a melee attack", slots()["1"] == 2)
    refill()
    st_d = duel()
    st_d["active_encounter"]["monsters"]["goblin#1"]["hp"] = {"current": 5, "max": 5}
    out_d = combat.attack(c, st_d, "pally", "longsword", "goblin#1", rng=Fixed(15, 6), smite=1)
    check("--smite on a target the hit killed spends no slot", slots() == {"1": 3, "2": 1} and "does not smite" in out_d[-1])
    sh_s = character.load(c, "pally")
    check("smite:12 and smite:0 are a clean RulesError, not IndexError",
          raises(lambda: actions.spec_for(sh_s, "smite:12")) and raises(lambda: actions.spec_for(sh_s, "smite:0"))
          and raises(lambda: actions.spec_for(sh_s, "smite:99")))
    check("smite:3 with no level 3 slot is a RulesError", raises(lambda: actions.spec_for(sh_s, "smite:3")))
    check("smite:1 is a spec", actions.spec_for(sh_s, "smite:1")["smite"] == 1)
    check("the refused tries spent nothing", slots() == {"1": 3, "2": 1})

    # The card: a melee hit leaves an offer, and the choice comes after the hit.
    state = duel()
    ids = [a["id"] for a in actions.listing(c, state, "pally", character.load(c, "pally"))]
    check("a paladin has the Lay on Hands card and no smite card before a hit",
          "feature:Lay on Hands" in ids and not any(i.startswith("smite:") for i in ids))
    actions.perform(c, state, "pally", "attack", "goblin#1", "Longsword", Fixed(15, 6))
    listed = {a["id"]: a for a in actions.listing(c, state, "pally", character.load(c, "pally"))}
    check("after a melee hit the card offers a smite per slot level, with the slots left, and No smite",
          [i for i in listed if i.startswith("smite:")] == ["smite:1", "smite:2", "smite:none"]
          and listed["smite:1"]["stat"] == "3 left" and listed["smite:2"]["why"] is None)
    done = actions.perform(c, state, "pally", "smite:1", rng=Fixed(4, 4))
    check("choosing a smite deals 8 radiant to the target and spends the slot",
          dealt(state) == 9 + 8 and slots()["1"] == 2 and "Divine Smite" in done["lines"][0])
    check("the offer is gone after use", "pending_smite" not in state["active_encounter"] and raises(lambda: actions.perform(c, state, "pally", "smite:1")))
    refill()
    state = duel()
    actions.perform(c, state, "pally", "attack", "goblin#1", "Longsword", Fixed(15, 6))
    actions.perform(c, state, "pally", "smite:none")
    check("No smite drops the offer and spends no slot", "pending_smite" not in state["active_encounter"] and slots()["1"] == 3)
    state = duel()
    actions.perform(c, state, "pally", "attack", "goblin#1", "Longsword", Fixed(15, 6))
    combat.next_turn(c, state)
    check("the offer ends with the turn", "pending_smite" not in state["active_encounter"])
    state = duel()
    actions.perform(c, state, "pally", "attack", "goblin#1", "Longsword", Fixed(2))
    check("no offer after a miss", "pending_smite" not in state["active_encounter"])
    state = duel()
    state["active_encounter"]["monsters"]["goblin#1"]["hp"] = {"current": 5, "max": 5}
    actions.perform(c, state, "pally", "attack", "goblin#1", "Longsword", Fixed(15, 6))
    check("no offer when the target is down", "pending_smite" not in state["active_encounter"])
    state = duel()
    actions.perform(c, state, "pally", "attack", "goblin#1", "Longsword", Fixed(15, 1))
    sheet_ = character.load(c, "pally")
    sheet_["spellcasting"]["spell_slots"]["1"]["remaining"] = 0
    why = {a["id"]: a["why"] for a in actions.listing(c, state, "pally", sheet_)}
    check("a level with no slot left is not offered", "smite:1" not in why and why["smite:2"] is None)

    # Lay on Hands (the pool is 5 x level 3 = 15).
    state = duel()
    pool = lambda: character.load(c, "pally")["resources_used"].get("Lay on Hands", 0)  # noqa: E731
    actions.perform(c, state, "pally", "feature:Lay on Hands", "pally", amount=6)
    check("Lay on Hands heals the amount, spends it from the pool and the action",
          character.load(c, "pally")["hp"]["current"] == 16 and pool() == 6 and combat.turn_used(state, "pally")["action"])
    state = duel()
    legolas = character.load(c, "legolas")
    legolas["hp"]["current"] = legolas["hp"]["max"] - 3
    character.save(c, "legolas", legolas)
    actions.perform(c, state, "pally", "feature:Lay on Hands", "legolas", amount=9)
    check("it heals an ally, never above their max HP, and spends only the points that healed",
          character.load(c, "legolas")["hp"]["current"] == legolas["hp"]["max"] and pool() == 9)
    check("a full-HP target is refused", raises(lambda: actions.perform(c, duel(), "pally", "feature:Lay on Hands", "legolas", amount=1)))
    check("zero points is refused", raises(lambda: actions.perform(c, duel(), "pally", "feature:Lay on Hands", "pally", amount=0)))
    check("more than the pool is refused (15 - 9 = 6 left)", raises(lambda: actions.perform(c, duel(), "pally", "feature:Lay on Hands", "pally", amount=7)))
    check("a creature that is not in the party is refused", raises(lambda: actions.perform(c, duel(), "pally", "feature:Lay on Hands", "goblin#1", amount=1)))
    entry = next(a for a in actions.listing(c, duel(), "pally", character.load(c, "pally")) if a["id"] == "feature:Lay on Hands")
    check("the card shows the points left and takes an ally", entry["left"] == 6 and entry["target"] == "ally")

    # Minthara of the-underdark has both.
    underdark = REPO / "game" / "campaigns" / "the-underdark"
    if (underdark / "characters" / "minthara.json").exists():
        sheet_ = character.load(underdark, "minthara")
        names = [a["id"] for a in actions.listing(underdark, combat.load_state(underdark), "minthara", sheet_)]
        check("Minthara has the Lay on Hands card", "feature:Lay on Hands" in names)
        check("Minthara can smite (the offer appears after a melee hit)", combat.smite_levels(sheet_) != {})


def test_cli_guards(c: Path) -> None:
    print("validate --fix offline, use --amount, cache-only brief")
    import contextlib
    import io
    import sys

    from dnd_cli.__main__ import main
    from dnd_cli.commands import character_cmd, rules_cmd

    def offline(endpoint: str) -> dict:
        raise combat.RulesError("offline")

    orig_api, orig_argv = rules_cmd._api, sys.argv
    path = character.character_path(c, "aragorn")
    try:
        rules_cmd._api = offline
        before, mtime = path.read_bytes(), path.stat().st_mtime_ns
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = character_cmd.execute_validate(str(c), "aragorn", fix=True)
        check("validate --fix offline: warning, no fixed claim, exit 1, sheet untouched",
              rc == 1 and "warning: cannot check" in err.getvalue() and "fixed:" not in out.getvalue()
              and path.read_bytes() == before and path.stat().st_mtime_ns == mtime)
        sys.argv = ["dnd-cli", "character", "use", str(c), "aragorn", "Second Wind", "--amount", "-2"]
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = main()
        check("use --amount -2 is refused, no uses given back", rc == 1 and "--amount" in err.getvalue() and path.read_bytes() == before)

        def run(*argv: str) -> tuple[int, str, str]:
            sys.argv = ["dnd-cli", "character", "item", str(c), "aragorn", *argv]
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                return main(), out.getvalue(), err.getvalue()
        rc, out, _ = run("add", "+1 Rapier of Frost", "--perk", "keen", "--rarity", "rare", "--effects", "magic-weapon-1,frost-edge")
        row = next(i for i in character.load(c, "aragorn")["inventory"] if i["name"] == "+1 Rapier of Frost")
        check("item add takes a perk, a rarity and gear effects, and finds the base",
              rc == 0 and row["description"] == "keen" and row["rarity"] == "rare" and row["effects"] == ["magic-weapon-1", "frost-edge"]
              and row["type"] == "weapon" and row["base"] == "Rapier")
        rc, _, err = run("add", "Ring", "--effects", "bless")
        check("item add refuses an effect that is not gear", rc == 1 and "no gear effect bless" in err)
        rc, _, err = run("add", "Ring", "--rarity", "shiny")
        check("item add refuses an unknown rarity", rc == 1 and "rarity is one of" in err)
        path.write_bytes(before)
    finally:
        rules_cmd._api, sys.argv = orig_api, orig_argv

    calls = []
    import dnd_cli.api as api_mod
    orig_call = api_mod.safe_api_call
    api_mod.safe_api_call = lambda e: calls.append(e) or (None, "no network")
    try:
        text = session_cmd.brief(c, session_cmd.cached_api)
    finally:
        api_mod.safe_api_call = orig_call
    check("the brief audit never calls the network", calls == [] and "Session brief" in text)
    check("an uncached endpoint is a RulesError the audit reads as cannot check",
          raises(lambda: session_cmd.cached_api("classes/zzz-not-cached")))


def test_death(c: Path) -> None:
    print("death saves")
    state = combat.load_state(c)
    check("a PC dropped to 0 is down", "DOWN" in combat.damage(c, state, "legolas", 100))
    combat.death_save(c, state, "legolas", Fixed(5))
    out = combat.death_save(c, state, "legolas", Fixed(1))
    check("a natural 1 counts two failures", "3 failures" in out and "DEAD" in out)
    combat.heal(c, state, "legolas", 5)
    check("healing resets death saves", character.load(c, "legolas")["death_saves"] == {"successes": 0, "failures": 0})


def test_sheet(c: Path) -> None:
    print("character sheet")
    data = character.load(c, "aragorn")
    inv.add(data, "Healing Potion", 2)
    check("removing the last unit removes the entry", "no Healing Potion left" in inv.remove(data, "Healing Potion", 2)
          and not any(i["name"] == "Healing Potion" for i in data["inventory"]))
    inv.add(data, "Smoke bomb", 1)
    inv.set_profile(data, "Smoke bomb", {"kind": "throw", "range_ft": 20, "damage": ["1d6", "fire"]})
    check("a DM ruling is saved on the row as its profile", next(i for i in data["inventory"] if i["name"] == "Smoke bomb")["profile"]["kind"] == "throw")
    check("a bad profile is refused", all(raises(lambda p=p: inv.set_profile(data, "Smoke bomb", p)) for p in
          ({"kind": "bless"}, {"kind": "heal"}, {"kind": "throw", "range_ft": 20, "damage": ["1d6"]}, {"kind": "heal", "heal": "lots"}, {"kind": "heal", "heal": "1d4", "cost": "reaction"})))
    check("a profile for an item that is not carried is refused", raises(lambda: inv.set_profile(data, "Ghost", {"kind": "heal", "heal": "1d4"})))
    check("gold cannot go below zero", raises(lambda: sheet.gold(data, -5)))
    check("gold is an item", sheet.gold(data, 30) == "Aragorn: 30 gp")
    mail = {"name": "Chain Mail", "equipment_category": {"index": "armor"}, "armor_category": "Heavy",
            "armor_class": {"base": 16, "dex_bonus": False}, "stealth_disadvantage": True}
    inv.equip_base(data, mail)
    check("heavy armor sets AC without DEX", data["armor_class"] == 16)
    shield = {"name": "Shield", "equipment_category": {"index": "armor"}, "armor_category": "Shield"}
    inv.equip_base(data, shield)
    check("a shield adds 2 once", data["armor_class"] == 18 and "already" in inv.equip_base(data, shield)[0])
    rapier = {"name": "Rapier", "equipment_category": {"index": "weapon"}, "weapon_range": "Melee",
              "properties": [{"index": "finesse"}], "damage": {"damage_dice": "1d8", "damage_type": {"index": "piercing"}}}
    inv.equip_base(data, rapier)
    w = next(w for w in data["weapons"] if w["name"] == "Rapier")
    check("a finesse weapon uses the better of STR and DEX", w["attack_bonus"] == 3 + 2 and w["damage"] == "1d8+3")
    character.save(c, "aragorn", data)

    data["hp"]["current"] = 5
    out = sheet.short_rest(data, 1, Fixed(6))
    check("a short rest spends hit dice and heals", data["hp"]["current"] == 5 + 6 + 2 and "hit dice 2/3" in out)
    sheet.long_rest(data)
    check("a long rest restores HP and half the hit dice", data["hp"]["current"] == data["hp"]["max"] and data["hit_dice"]["remaining"] == 3)
    check("XP reports a level up", "LEVEL UP READY" in sheet.add_xp(data, 2000))

    level = {"level": 4, "prof_bonus": 2, "features": []}
    longbow = next(w for w in data["weapons"] if w["name"] == "Longbow")
    sheet.level_up(data, level, 10, "avg", {"dexterity": 2})
    check("level-up adds HP (avg + CON)", data["hp"]["max"] == 28 + 8 and data["level"] == 4)
    check("a bow keeps DEX and follows the new modifier", longbow["damage"] == "1d8+3" and longbow["attack_bonus"] == 5)
    check("a skill keeps its proficiency", data["skills"]["athletics"] == 3 + 2)
    check("the wrong level is refused", raises(lambda: sheet.level_up(data, level, 10)))
    data["features_and_traits"] = [{"name": "Dwarven Toughness", "description": ""}]
    before = data["hp"]["max"]
    sheet.level_up(data, {"level": 5, "prof_bonus": 3, "features": []}, 10, "avg")
    check("Dwarven Toughness adds 1 HP per level", data["hp"]["max"] - before == 6 + 2 + 1)


def test_session_end(c: Path) -> None:
    print("session end")
    data = canon.load(c)
    canon.add_villain(data, "Glasstaff", "Rule the town", "Vain")
    canon.add_clock(data, "Glasstaff", "Seize the town", 4)
    canon.add_thread(data, "redbrands", "Bullies")
    canon.save(c, data)
    check("an untouched clock blocks the close, and nothing is written",
          raises(lambda: session_cmd.end(c, "recap", [], [])) and canon.load(c)["threads"][0]["staleness_count"] == 0)
    data = canon.load(c)
    canon.touch_clock(data, "Glasstaff", "Seize the town")
    canon.save(c, data)
    check("a bad thread id writes nothing", raises(lambda: session_cmd.end(c, "recap", ["nope"], []))
          and canon.load(c)["last_session_written"] == 0)
    check("a session with no canon fact needs --no-facts", raises(lambda: session_cmd.end(c, "recap", [], [])))
    data = canon.load(c)
    canon.add_clock(data, "Glasstaff", "Hire the Redbrands", 6, waiting=True)
    canon.add_fact(data, 1, "DM", "Toblen runs the Stonehill Inn.")
    canon.save(c, data)
    lines = session_cmd.end(c, "We met Toblen.", [], ["Glasstaff/Seize the town=warning"], "Day 2")
    check("a waiting clock does not advance", canon.load(c)["villains"][0]["clocks"][1]["segments_filled"] == 0)
    data = canon.load(c)
    check("clocks advance by their mode", data["villains"][0]["clocks"][0]["segments_filled"] == 2)
    check("threads are swept", data["threads"][0]["staleness_count"] == 1)
    check("the session is closed and logged", data["last_session_written"] == 1
          and "## Session 1" in (c / "session_log.md").read_text() and lines[-1].startswith("Session 1 closed"))
    check("a second run is refused (the next session must touch a clock)", raises(lambda: session_cmd.end(c, "again", [], [])))
    check("game time is set", json.loads((c / "state.json").read_text())["game_time"] == "Day 2")


def _bow_match(c: Path) -> bool:
    d = character.load(c, "aragorn")
    inv.add(d, "+1 Hand Crossbow of Frost", 1, effects=["magic-weapon-1"])
    wear(d, "+1 Hand Crossbow of Frost", True)
    character.save(c, "aragorn", d)
    ok = effects.weapon(c, "aragorn", "", "Crossbow, hand")["dmg"] == 1
    d["inventory"] = [i for i in d["inventory"] if "Crossbow" not in i["name"]]
    character.save(c, "aragorn", d)
    return ok


def test_gear(c: Path) -> None:
    """The effect types that item perks use: weapon bonuses, crit range, extra dice, AC, saves, resistance."""
    print("gear effects")
    state = fight(c)
    gob = state["active_encounter"]["monsters"]["goblin#1"]
    gob["hp"], gob["ac"], gob["resist"] = {"current": 500, "max": 500}, 10, []

    def swing(vals, weapon="longsword", ac=10):
        gob["ac"] = ac
        hp = gob["hp"]["current"]
        line = []
        ev = staged(c, lambda: line.append(combat.attack(c, state, "aragorn", weapon, "goblin#1", rng=Fixed(*vals), cost=None)))
        return ev[0]["detail"]["rolls"][0], hp - gob["hp"]["current"], line[0]

    base, base_dmg, _ = swing([12, 4])
    effects.add(c, "aragorn", "magic-weapon-1")
    r, dmg, line = swing([12, 4])
    check("a +1 weapon adds 1 to the to-hit, as its own tile, and 1 to the damage",
          r["total"] == base["total"] + 1 and dmg == base_dmg + 1 and {"label": "+1 Weapon", "value": 1} in r["mods"]
          and "+1 weapon +1" in " ".join(line))
    plain, plain_dmg, _ = swing([12], "unarmed strike")
    effects.remove(c, "aragorn", "magic-weapon-1")
    off, off_dmg, _ = swing([12], "unarmed strike")
    check("a +1 weapon does not touch Unarmed Strike", plain["total"] == off["total"] and plain_dmg == off_dmg)
    effects.add(c, "aragorn", "magic-weapon-1")
    ev = staged(c, lambda: combat.attack(c, state, "aragorn", "improvised", "goblin#1", rng=Fixed(12, 3), damage_expr="1d4", cost=None))
    check("a thrown improvised item gets no weapon bonus", [t["label"] for t in ev[0]["detail"]["rolls"][0]["mods"]] == ["Attack Bonus"])
    effects.remove(c, "aragorn", "magic-weapon-1")

    effects.add(c, "aragorn", "keen-edge")
    r, dmg, _ = swing([19, 4, 4])
    check("Keen: a natural 19 that hits is a critical hit and doubles the dice", r["outcome"] == "crit" and dmg == 8 + 3)
    r, _, _ = swing([19, 4, 4], ac=40)
    check("Keen: a natural 19 that misses is only a miss", r["outcome"] == "miss")
    r, _, _ = swing([18, 4, 4])
    check("Keen: an 18 is not a critical hit", r["outcome"] == "hit")
    effects.remove(c, "aragorn", "keen-edge")
    r, _, _ = swing([19, 4, 4])
    check("without Keen a 19 is a plain hit", r["outcome"] == "hit")

    effects.add(c, "aragorn", "flame-edge")
    r, dmg, line = swing([12, 4, 3])
    check("of Flame: +1d4 fire damage on a hit, named in the output", dmg == 4 + 3 + 3 and "3 fire" in " ".join(line))
    r, dmg, _ = swing([20, 4, 4, 2, 2])
    check("extra dice are doubled on a critical hit", r["outcome"] == "crit" and dmg == 8 + 3 + 4)
    r, dmg, _ = swing([2, 4, 4], ac=40)
    check("extra dice need a hit", dmg == 0)
    gob["resist"] = ["fire"]
    r, dmg, _ = swing([12, 4, 4])
    check("the extra damage keeps its own type: a fire resistant target halves it", dmg == 4 + 3 + 2)
    effects.remove(c, "aragorn", "flame-edge")
    effects.add(c, "aragorn", "purging-edge")
    r, dmg, _ = swing([12, 4, 4])
    check("Purging does nothing against a goblin", dmg == 4 + 3)
    gob["ctype"] = "undead"
    r, dmg, _ = swing([12, 4, 5])
    check("Purging adds 1d6 radiant against an undead", dmg == 4 + 3 + 5)
    gob["ctype"] = "humanoid"
    effects.remove(c, "aragorn", "purging-edge")

    sheet_ac = character.load(c, "aragorn")["armor_class"]
    effects.add(c, "aragorn", "magic-armor-2")
    check("+2 armor adds to the combat record, not to the sheet", combat.combatant(c, state, "aragorn")["ac"] == sheet_ac + 2
          and character.load(c, "aragorn")["armor_class"] == sheet_ac)
    lines = combat.attack(c, state, "goblin#1", "scimitar", "aragorn", rng=Fixed(sheet_ac + 1 - 4), cost=None)  # the goblin's +4 just reaches the bare AC + 1
    check("a hit on the bare AC misses the armor", "miss" in lines[-1] and f"vs AC {sheet_ac + 2}" in lines[-1])
    effects.remove(c, "aragorn", "magic-armor-2")
    check("the bonus ends with the effect", combat.combatant(c, state, "aragorn")["ac"] == sheet_ac)

    r = staged(c, lambda: combat.save(c, state, ["aragorn"], "dex", 12, rng=Fixed(9)))[0]["detail"]["rolls"][0]
    effects.add(c, "aragorn", "warding")
    w = staged(c, lambda: combat.save(c, state, ["aragorn"], "dex", 12, rng=Fixed(9)))[0]["detail"]["rolls"][0]
    check("Warding adds 1 to a save as a tile, and the effect stays", w["total"] == r["total"] + 1
          and {"label": "Warding", "value": 1} in w["mods"] and effects.active(c, "aragorn") == ["warding"])
    a = staged(c, lambda: combat.attack(c, state, "aragorn", "unarmed strike", "goblin#1", rng=Fixed(9), cost=None))[0]["detail"]["rolls"][0]
    check("Warding does not touch an attack", all(t["label"] != "Warding" for t in a["mods"]))
    effects.remove(c, "aragorn", "warding")

    effects.add(c, "aragorn", "might")
    s_str = staged(c, lambda: combat.save(c, state, ["aragorn"], "str", 12, rng=Fixed(9)))[0]["detail"]["rolls"][0]
    s_dex = staged(c, lambda: combat.save(c, state, ["aragorn"], "dex", 12, rng=Fixed(9)))[0]["detail"]["rolls"][0]
    c_ath = staged(c, lambda: combat.check(c, state, ["aragorn"], "athletics", rng=Fixed(9)))[0]["detail"]["rolls"][0]
    c_acr = staged(c, lambda: combat.check(c, state, ["aragorn"], "acrobatics", rng=Fixed(9)))[0]["detail"]["rolls"][0]
    has = lambda roll: any(t["label"] == "Might" for t in roll["mods"])  # noqa: E731
    check("Might counts for Strength saves and Strength skills, not for Dexterity", has(s_str) and has(c_ath) and not has(s_dex) and not has(c_acr))
    effects.remove(c, "aragorn", "might")

    combat.heal(c, state, "aragorn", 100)
    effects.add(c, "aragorn", "fire-ward")
    check("Fire Resistance halves fire damage", "takes 5 (resists fire)" in combat.damage(c, state, "aragorn", 10, "fire"))
    check("it does not touch cold damage", "takes 10:" in combat.damage(c, state, "aragorn", 10, "cold"))
    effects.remove(c, "aragorn", "fire-ward")
    effects.add(c, "aragorn", "cushioning")
    check("Cushioning takes 1 off a slashing hit", "takes 4 (gear absorbs 1)" in combat.damage(c, state, "aragorn", 5, "slashing"))
    check("it does not touch fire damage", "takes 5:" in combat.damage(c, state, "aragorn", 5, "fire"))
    effects.add(c, "aragorn", "unyielding")
    check("Cushioning and Unyielding add up, and damage stops at 0", "takes 0" in combat.damage(c, state, "aragorn", 3, "slashing"))
    effects.remove(c, "aragorn", "cushioning")
    effects.remove(c, "aragorn", "unyielding")

    effects.add(c, "aragorn", "blessed")
    b = staged(c, lambda: combat.save(c, state, ["aragorn"], "dex", 12, rng=Fixed(3, 9)))[0]["detail"]["rolls"][0]
    check("Blessed is Bless without concentration: +1d4 on saves, kept", b["bonus"][0]["label"] == "Blessed" and effects.active(c, "aragorn") == ["blessed"]
          and effects.PRESETS["bless"]["concentration"] and not effects.PRESETS["blessed"]["concentration"])
    effects.remove(c, "aragorn", "blessed")
    check("the stage lists every preset with a tone", all(e["tone"] for e in effects.catalogue()))

    print("worn gear")

    def give(name, ids, on=True):
        d = character.load(c, "aragorn")
        inv.add(d, name, 1, effects=ids)
        wear(d, name, on)
        character.save(c, "aragorn", d)

    sheet_ac = character.load(c, "aragorn")["armor_class"]
    give("+1 Chain Mail", ["magic-armor-1"], on=False)
    check("an item in the pack that is not worn gives nothing", effects.active(c, "aragorn") == [] and combat.combatant(c, state, "aragorn")["ac"] == sheet_ac)
    d = character.load(c, "aragorn")
    wear(d, "+1 Chain Mail", True)
    character.save(c, "aragorn", d)
    check("a worn +1 armor adds 1 AC in the combat record", combat.combatant(c, state, "aragorn")["ac"] == sheet_ac + 1
          and effects.defense(c, "aragorn")["ac"] == 1 and effects.stored(c, "aragorn") == [])
    effects.add(c, "aragorn", "guidance")
    effects.apply(c, "aragorn", "check", Fixed(2))
    check("spending a next-roll effect does not write worn gear into effects.json", effects.stored(c, "aragorn") == []
          and effects.active(c, "aragorn") == ["magic-armor-1"])
    give("Ring of Warding", ["warding"])
    give("Cloak of Warding", ["warding"])
    check("the same perk on two worn items counts twice", effects.apply(c, "aragorn", "save")["flat"] == [{"label": "Warding", "value": 1}] * 2)
    d = character.load(c, "aragorn")
    wear(d, "Cloak of Warding", False)
    wear(d, "Ring of Warding", False)
    wear(d, "+1 Chain Mail", False)
    character.save(c, "aragorn", d)
    check("the bonus ends when the item is put away", effects.active(c, "aragorn") == [] and combat.combatant(c, state, "aragorn")["ac"] == sheet_ac)

    give("+1 Longsword of Flame", ["magic-weapon-1", "flame-edge"])
    sword = effects.weapon(c, "aragorn", "", "Longsword")
    bow = effects.weapon(c, "aragorn", "", "Longbow")
    check("a worn sword's perks apply to the sword and not to the bow", sword["dmg"] == 1 and sword["extra"] == [["1d4", "fire"]]
          and bow["dmg"] == 0 and not bow["extra"] and not bow["hit"])
    effects.add(c, "aragorn", "magic-weapon-2")
    check("a stored weapon effect still applies to every weapon", effects.weapon(c, "aragorn", "", "Longbow")["dmg"] == 2)
    effects.remove(c, "aragorn", "magic-weapon-2")
    check("an API-style weapon name matches the loot item name", effects.weapon(c, "aragorn", "", "Crossbow, hand")["dmg"] == 0
          and _bow_match(c))

    old = {"name": "Leather", "quantity": 1, "equipped": True, "effects": ["magic-armor-1"]}
    d = {"name": "T", "level": 1, "ability_scores": {a: 10 for a in combat.ABILITIES}, "armor_class": 11, "inventory": [old],
         "armor": {"name": "Leather", "type": "light", "ac_bonus": 11, "equipped": True}}
    inv.equip_base(d, {"name": "Plate", "equipment_category": {"index": "armor"}, "armor_class": {"base": 18, "dex_bonus": False}})
    check("new armor takes the old armor off, and its perks end", old["equipped"] is False)
    d = character.load(c, "aragorn")
    wear(d, "+1 Longsword of Flame", False)
    character.save(c, "aragorn", d)

    # A loot weapon is made from a base: equipping it makes the attack, under the item's name.
    from dnd_cli.commands import rules_cmd
    rapier = {"name": "Rapier", "equipment_category": {"index": "weapon"}, "weapon_range": "Melee", "properties": [{"index": "finesse"}],
              "damage": {"damage_dice": "1d8", "damage_type": {"index": "piercing"}}}
    plate = {"name": "Plate", "equipment_category": {"index": "armor"}, "armor_category": "Heavy", "armor_class": {"base": 18, "dex_bonus": False}}
    asked = []
    before = character.load(c, "aragorn")
    orig = rules_cmd._api
    rules_cmd._api = lambda ep: (asked.append(ep), plate if "plate" in ep else rapier)[1]
    try:
        d = character.load(c, "aragorn")
        inv.add(d, "+1 Rapier of Frost", 1, type="weapon", base="Rapier", effects=["magic-weapon-1", "frost-edge"])
        inv.add(d, "+1 Plate Armor", 1, type="armor", base="Plate Armor", effects=["magic-armor-1"])
        _wear = rules_cmd._equip
        _wear(d, "+1 Rapier of Frost", True)
        w = next(w for w in d["weapons"] if w["name"] == "+1 Rapier of Frost")
        check("equipping a loot weapon makes an attack under its name, from the stats of its base", asked == ["equipment/rapier"] and w["equipped"]
              and w["damage"].startswith("1d8") and w["damage_type"] == "piercing")
        old = next(i for i in d["inventory"] if i["name"] == "Chain Mail") if any(i["name"] == "Chain Mail" for i in d["inventory"]) else None
        _wear(d, "+1 Plate Armor", True)
        check("equipping loot armor sets the AC from its base and names the armor", d["armor"]["name"] == "+1 Plate Armor" and d["armor_class"] >= 18
              and asked[-1] == "equipment/plate-armor" and (old is None or not old.get("equipped")))
        character.save(c, "aragorn", d)
        r = effects.weapon(c, "aragorn", "", "+1 Rapier of Frost")
        check("the perks of the item reach the attack of the same name", r["dmg"] == 1 and r["extra"] == [["1d4", "cold"]])
        inv.get(d, "+1 Rapier of Frost").unequip(d)
        check("putting the weapon away keeps the attack, not wielded", next(w for w in d["weapons"] if w["name"] == "+1 Rapier of Frost")["equipped"] is False)
        inv.add(d, "Flame Tongue", 1, type="weapon", effects=["flame-edge"])
        check("a weapon with effects and no base warns the DM", any("Warning" in line for line in _wear(d, "Flame Tongue", True)))
        asked.clear()
        _wear(d, "rapier", True)
        check("an item not in the inventory is made from the 5e item of that name", asked == ["equipment/rapier"]
              and any(i["name"] == "Rapier" and i["equipped"] for i in d["inventory"]))
    finally:
        rules_cmd._api = orig
        character.save(c, "aragorn", before)


def test_loot() -> None:
    print("loot")
    a, b = loot.roll(1, "hoard", 7), loot.roll(1, "hoard", 7)
    check("the same seed gives the same list", a == b and a["seed"] == 7)
    check("another seed gives another list", any(loot.roll(1, "hoard", n) != a for n in range(8, 20)))
    check("an individual has coins and no items", bool((r := loot.roll(2, "individual", 3))["coins"]) and not r["items"])
    check("a hoard has coins and items, each with a rarity of its tier", all(i["rarity"] in ("common", "uncommon") for i in loot.roll(2, "hoard", 4)["items"]) and bool(loot.roll(2, "hoard", 4)["items"]))
    check("a higher CR pays more", loot.roll(14, "individual", 1)["coins"]["gp"] > loot.roll(1, "individual", 1)["coins"]["gp"])
    check("the tier follows the CR", loot.tier(0.25)["max_cr"] == 4 and loot.tier(4)["max_cr"] == 4 and loot.tier(5)["max_cr"] == 10 and loot.tier(30)["max_cr"] == 99)
    check("a beast carries nothing", not (r := loot.roll(1, "hoard", 1, "Beast"))["coins"] and not r["items"] and "no treasure" in r["note"])
    check("a legendary item is never named: the DM writes it", any(i["rarity"] == "legendary" and i["name"] is None for n in range(40) for i in loot.roll(20, "hoard", n)["items"]))
    check("a bad kind or CR is refused", raises(lambda: loot.roll(1, "pile")) and raises(lambda: loot.roll(-1)))
    data = {"name": "Aragorn", "inventory": []}
    inv.add(data, "Longsword", 1, "keen: it hums near orcs", "uncommon")
    check("a forced item keeps its perk text and rarity", data["inventory"][0] == {"name": "Longsword", "quantity": 1, "description": "keen: it hums near orcs", "rarity": "uncommon"})
    hints = loot.hints("Keen, of Flame, hums")
    check("item add names the effect of a catalog perk and says when the DM must rule", any("--effects keen-edge" in h for h in hints)
          and any("--effects flame-edge" in h for h in hints) and len(hints) == 2
          and any("you rule it" in h for h in loot.hints("vicious")))
    inv.add(data, "Ring", 1, effects=["warding"])
    check("a forced item keeps the effects it gives when worn", data["inventory"][1]["effects"] == ["warding"])
    inv.add(data, "Ring", 1, effects=["vigor"])
    check("giving an item again adds its effects", data["inventory"][1]["effects"] == ["vigor"] and data["inventory"][1]["quantity"] == 2)
    check("a hint is skipped for an effect that was given", loot.hints("Keen", ["keen-edge"]) == [])
    check("the base and type of gear are found in its name", loot.base_of("+1 Keen Hand Crossbow of Frost") == ("weapon", "Hand Crossbow")
          and loot.base_of("Plate Armor of Warding") == ("armor", "Plate Armor") and loot.base_of("Flame Tongue") is None
          and loot.base_of("Flame Tongue", "longsword") == ("weapon", "Longsword") and raises(lambda: loot.base_of("x", "Lightsaber")))
    check("a base maps to its 5e API index", loot.api_index("Longsword") == "longsword" and loot.api_index("Hand Crossbow") == "crossbow-hand"
          and loot.api_index("Half Plate") == "half-plate-armor")
    check("every base of the loot table has an API index in the cache or a plain slug",
          all(loot.api_index(b) for names in loot.table()["gear"]["bases"].values() for b in names))
    check("a rolled gear item names its base", all(i["base"] in loot.table()["gear"]["bases"][i["type"]] for n in range(30)
                                                   for i in loot.roll(14, "hoard", n)["items"] if i.get("type")))

    print("perk catalog")
    book = loot.perks()["perks"]
    kinds = set(loot.table()["gear"]["bases"])
    check("the catalog has 20 to 30 perks", 20 <= len(book) <= 30)
    check("a perk fits known types, a rarity and a slot", all(set(p["types"]) <= kinds and p["rarity"] in loot.RARITIES[1:4]
                                                              and p.get("until", "very rare") in loot.RARITIES[1:4] and p["slot"] in ("prefix", "suffix")
                                                              and p["weight"] > 0 for p in book))
    check("a perk is a known effect, or the DM rules it and says what is missing",
          all((p["effect"] in effects.PRESETS) if p["effect"] else bool(p["ruling"] and p["needs"]) for p in book))
    check("a perk effect needs no concentration", all(not effects.PRESETS[p["effect"]]["concentration"] for p in book if p["effect"]))
    check("a perk has one name per type", len({(p["name"], t) for p in book for t in p["types"]}) == sum(len(p["types"]) for p in book))
    check("more perks are compiled than left to the DM, and some are left to the DM", sum(1 for p in book if p["effect"]) > sum(1 for p in book if not p["effect"]) > 0)
    check("every item type has a roll weight", set(loot.table()["gear"]["types"]) == kinds)
    gear = [i for n in range(150) for i in loot.roll(20, "hoard", n)["items"] if i.get("type")]
    by_name = {(p["name"], t): p for p in book for t in p["types"]}
    fine = all(all((n, i["type"]) in by_name and by_name[(n, i["type"])]["rarity"] in loot.RARITIES[:loot.RARITIES.index(i["rarity"]) + 1]
                   for n in i["perks"]) for i in gear)
    check("a rolled perk fits the item type and its rarity", bool(gear) and fine)
    counts = {r: {len(i["perks"]) for i in gear if i["rarity"] == r} for r in ("rare", "very rare")}
    check("rare and very rare gear has two perks", counts == {"rare": {2}, "very rare": {2}})
    low = [i for n in range(300) for i in loot.roll(3, "hoard", n)["items"] if i.get("type")]
    check("uncommon gear has one perk and common gear none", {len(i["perks"]) for i in low if i["rarity"] == "uncommon"} == {1}
          and {len(i["perks"]) for i in low if i["rarity"] == "common"} == {0})
    check("an uncommon weapon is only an enchant", all(i["perks"] == ["+1"] for i in low if i["rarity"] == "uncommon" and i["type"] == "weapon"))
    check("a weapon starts with its enchant, and no second enchant joins it",
          all(i["perks"][0] in ("+1", "+2", "+3") and not set(i["perks"][1:]) & {"+1", "+2", "+3"} for i in gear if i["type"] == "weapon"))
    check("accessories roll perks", {i["type"] for i in gear if i["perks"]} >= {"ring", "amulet", "cloak", "boots", "gloves", "helmet"})
    check("a fixed item (potion, scroll) never has perks", all(not i.get("perks") for n in range(60) for i in loot.roll(20, "hoard", n)["items"] if not i.get("type")))
    check("the same seed gives the same items and the same perks", all(loot.roll(14, "hoard", n) == loot.roll(14, "hoard", n) for n in range(30))
          and any(i["perks"] for n in range(30) for i in loot.roll(14, "hoard", n)["items"] if i.get("type")))
    text = "\n".join(line for n in range(40) for line in loot.lines(loot.roll(14, "hoard", n)))
    check("the list names the effects to give and the perks to rule", "give it with --effects" in text and "you rule:" in text)


if __name__ == "__main__":
    test_dice()
    test_loot()
    with tempfile.TemporaryDirectory() as tmp:
        c = campaign(Path(tmp))
        test_combat(c)
        test_effects(c)
        test_gear(c)
        test_resources(c)
        test_actions(c)
        test_paladin(c)
        test_cli_guards(c)
        test_death(c)
        test_sheet(c)
        test_session_end(c)
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
