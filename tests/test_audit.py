"""Checks for dnd_cli/audit.py and spellcasting start at level-up.

Run from the repo root:  .venv/bin/python tests/test_audit.py

Plain asserts and stub 5e API data: no network.
"""

from __future__ import annotations

import copy

from dnd_cli import audit, resources, sheet
from dnd_cli.combat import RulesError

PASS = FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + cond, FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


def ref(index: str) -> dict:
    return {"index": index, "name": index.title()}


def level(n: int, slots: int = 0, features=()) -> dict:
    d = {"level": n, "prof_bonus": 2, "features": [{"index": f.lower().replace(" ", "-"), "name": f} for f in features]}
    if slots:
        d["spellcasting"] = {"spell_slots_level_1": slots}
    return d


DATA = {
    "classes/paladin": {"name": "Paladin", "hit_die": 10, "spellcasting": {"spellcasting_ability": ref("cha")}},
    "classes/ranger": {"name": "Ranger", "hit_die": 10, "spellcasting": {"spellcasting_ability": ref("wis")}},
    "classes/fighter": {"name": "Fighter", "hit_die": 10},
    "classes/rogue": {"name": "Rogue", "hit_die": 8},
}
for cls in ("paladin", "ranger"):
    DATA[f"classes/{cls}/levels/1"] = level(1)
    DATA[f"classes/{cls}/levels/2"] = level(2, 2)
    DATA[f"classes/{cls}/levels/3"] = level(3, 3)
for cls in ("fighter", "rogue"):
    for n in (1, 2, 3):
        DATA[f"classes/{cls}/levels/{n}"] = level(n)
DATA["classes/paladin/levels/2"]["features"] = [{"index": "divine-smite", "name": "Divine Smite"}]


def fetch(endpoint: str) -> dict:
    if endpoint not in DATA:
        raise RulesError(endpoint)
    return DATA[endpoint]


def offline(endpoint: str) -> dict:
    raise RulesError("offline")


def make(cls: str, n: int = 1) -> dict:
    return {"name": "T", "race": "Human", "class": cls, "level": n, "proficiency_bonus": 2,
            "ability_scores": {"strength": 14, "dexterity": 12, "constitution": 12, "intelligence": 8,
                               "wisdom": 14, "charisma": 16},
            "hp": {"current": 10, "max": 10, "temp": 0}, "hit_dice": {"total": n, "remaining": n, "type": "d10"},
            "features_and_traits": []}


def up(s: dict, cls: str) -> list[str]:
    n = s["level"] + 1
    return sheet.level_up(s, DATA[f"classes/{cls}/levels/{n}"], 10, class_data=DATA[f"classes/{cls}"])


def test_level_up() -> None:
    print("spellcasting starts at level-up")
    pal = make("Paladin")
    up(pal, "paladin")
    sc = pal.get("spellcasting", {})
    check("paladin L1 -> L2 gets a CHA block with 2 slots",
          sc.get("ability") == "charisma" and sc["spell_slots"] == {"1": {"max": 2, "remaining": 2}}
          and sc["spell_save_dc"] == 8 + 2 + 3 and sc["spell_attack_bonus"] == 5 and sc["spells_known"] == [])
    up(pal, "paladin")
    check("paladin L3 has 3 slots, 3 remaining", pal["spellcasting"]["spell_slots"]["1"] == {"max": 3, "remaining": 3})
    ran = make("Ranger")
    up(ran, "ranger")
    check("ranger uses WIS", ran["spellcasting"]["ability"] == "wisdom" and ran["spellcasting"]["spell_save_dc"] == 12)
    fgt, rog = make("Fighter"), make("Rogue")
    up(fgt, "fighter"), up(rog, "rogue")
    check("fighter and rogue get none", "spellcasting" not in fgt and "spellcasting" not in rog)
    check("Lay on Hands max is 15 at level 3", resources.for_sheet({**pal, "level": 3})[0] == {"name": "Lay on Hands", "max": 15, "recharge": "long", "used": 0})


def test_audit() -> None:
    print("audit and repair")
    pal = make("Paladin", 3)
    pal["features_and_traits"] = [{"name": "Divine Smite"}, {"name": "Fighting Style"}, {"name": "Sacred Oath"}]
    found = audit.audit(pal, fetch)
    check("missing slots are reported", any("no spellcasting block" in p for p in found))
    check("Divine Smite without slots is reported", any("Divine Smite costs spell slots" in p for p in found))
    check("choices without a record are reported", any("Fighting Style" in p for p in found) and any("Sacred Oath" in p for p in found))
    pal["features_and_traits"].append({"name": "Lay on Hands"})
    check("Lay on Hands is tracked for a paladin", not any("Lay on Hands has no" in p for p in audit.audit(pal, fetch)))
    check("a fighter-style feature on a rogue is untracked", any("Second Wind has no tracked" in p for p in audit.audit(
        {**make("Rogue", 3), "features_and_traits": [{"name": "Second Wind"}]}, fetch)))
    fixed = audit.repair(pal, fetch)
    check("repair makes the block with 3 slots", pal["spellcasting"]["spell_slots"]["1"] == {"max": 3, "remaining": 3} and bool(fixed))
    after = audit.audit(pal, fetch)
    check("no slot problem is left", not any("spell" in p.lower() and "choose" not in p for p in after))
    check("the choices stay reported", any("Sacred Oath" in p for p in after))
    pal["spellcasting"]["spell_slots"]["1"] = {"max": 2, "remaining": 1}
    pal["spellcasting"]["spells_known"] = ["Bless"]
    audit.repair(pal, fetch)
    check("repair raises max, keeps spent slots and spells",
          pal["spellcasting"]["spell_slots"]["1"] == {"max": 3, "remaining": 2} and pal["spellcasting"]["spells_known"] == ["Bless"])
    pal["spellcasting"]["spell_slots"]["1"]["remaining"] = 0
    before = copy.deepcopy(pal)
    check("a right sheet is not changed", audit.repair(pal, fetch) == [] and pal == before)
    check("an offline API says cannot check", audit.audit(pal, offline)[0].startswith("cannot check")
          and audit.repair(pal, offline)[0].startswith("cannot check"))
    pal["subclass"], pal["fighting_style"] = "Devotion", "Dueling"
    check("a recorded choice is not reported", not any("choose" in p for p in audit.audit(pal, fetch)))
    check("every costed feature has an action card entry", audit.card_gaps(audit.COSTED) == [])
    audit.COSTED["Hex Blade"] = "Hex Blade"
    try:
        check("a costed feature with no entry is reported", audit.card_gaps(audit.COSTED) == ["feature Hex Blade has no action card"])
        pal["features_and_traits"].append({"name": "Hex Blade"})
        check("the sheet audit reports it when the sheet has the feature", "feature Hex Blade has no action card" in audit.audit(pal, fetch))
    finally:
        del audit.COSTED["Hex Blade"]


if __name__ == "__main__":
    test_level_up()
    test_audit()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
