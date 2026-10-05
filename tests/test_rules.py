"""Checks for the rules commands: dice, encounters, attacks, saves, checks, sheets, session end.

Run from the repo root:  .venv/bin/python tests/test_rules.py

Plain asserts, a seeded RNG, and stub monster data: no network.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from dnd_cli import canon, character, combat, dice, effects, resources, sheet
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
    before = character.load(c, "aragorn")["hp"]["current"]
    lines = combat.attack(c, state, "goblin#2", "scimitar", "aragorn", rng=Fixed(20, 3, 4))
    hp = character.load(c, "aragorn")["hp"]["current"]
    check("a natural 20 crits and doubles dice; the PC sheet is saved",
          any("CRITICAL" in ln for ln in lines) and hp == before - 9)
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


def test_resources(c: Path) -> None:
    print("class resources and turn actions")
    fighter = {"class": "Fighter", "level": 3, "ability_scores": {"charisma": 10}}
    check("a fighter has Second Wind and Action Surge", [(r["name"], r["max"]) for r in resources.for_sheet(fighter)] == [("Second Wind", 1), ("Action Surge", 1)])
    check("rage grows with level", resources.for_sheet({"class": "Barbarian", "level": 9, "ability_scores": {}})[0]["max"] == 4)
    check("a rogue has none", resources.for_sheet({"class": "Rogue", "level": 5, "ability_scores": {}}) == [])
    check("bardic inspiration follows CHA (at least 1)", resources.for_sheet({"class": "Bard", "level": 1, "ability_scores": {"charisma": 16}})[0]["max"] == 3)
    resources.spend(fighter, "second wind")
    check("a spend is counted, and cannot pass the max", resources.spend(fighter, "Second Wind")["used"] == 1)
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
    check("only a combatant counts", raises(lambda: combat.spend_turn(state, "bilbo", "action")))
    combat.next_turn(c, state)
    check("the next combatant starts with all three free", state["active_encounter"]["resources"][state["active_encounter"]["current_turn"]] == {})


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
    sheet.add_item(data, "Healing Potion", 2)
    check("removing the last unit removes the entry", "no Healing Potion left" in sheet.remove_item(data, "Healing Potion", 2)
          and not any(i["name"] == "Healing Potion" for i in data["inventory"]))
    check("gold cannot go below zero", raises(lambda: sheet.gold(data, -5)))
    check("gold is an item", sheet.gold(data, 30) == "Aragorn: 30 gp")
    mail = {"name": "Chain Mail", "equipment_category": {"index": "armor"}, "armor_category": "Heavy",
            "armor_class": {"base": 16, "dex_bonus": False}, "stealth_disadvantage": True}
    sheet.equip(data, mail)
    check("heavy armor sets AC without DEX", data["armor_class"] == 16)
    shield = {"name": "Shield", "equipment_category": {"index": "armor"}, "armor_category": "Shield"}
    sheet.equip(data, shield)
    check("a shield adds 2 once", data["armor_class"] == 18 and "already" in sheet.equip(data, shield)[0])
    rapier = {"name": "Rapier", "equipment_category": {"index": "weapon"}, "weapon_range": "Melee",
              "properties": [{"index": "finesse"}], "damage": {"damage_dice": "1d8", "damage_type": {"index": "piercing"}}}
    sheet.equip(data, rapier)
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


if __name__ == "__main__":
    test_dice()
    with tempfile.TemporaryDirectory() as tmp:
        c = campaign(Path(tmp))
        test_combat(c)
        test_effects(c)
        test_resources(c)
        test_death(c)
        test_sheet(c)
        test_session_end(c)
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
