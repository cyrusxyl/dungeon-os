"""Checks for `character new` (dnd_cli/creation.py).

Run from the repo root:  .venv/bin/python tests/test_creation.py

Plain asserts and stub 5e API data: no network.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from dnd_cli import character, combat, creation
from test_rules import campaign  # the committed example campaign, copied to a temp dir

PASS = FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + cond, FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


def ref(index: str) -> dict:
    return {"index": index, "name": index.title()}


def skill_choice(n: int, names: list[str]) -> dict:
    return {"choose": n, "from": {"options": [{"option_type": "reference", "item": ref(f"skill-{s}")} for s in names]}}


def cls(index, die, saves, skills, n, caster=None):
    d = {"index": index, "name": index.title(), "hit_die": die, "saving_throws": [ref(s) for s in saves],
         "proficiency_choices": [skill_choice(n, skills)]}
    if caster:
        d["spellcasting"] = {"spellcasting_ability": ref(caster)}
    return d


DATA = {
    "races/elf": {"index": "elf", "name": "Elf", "speed": 30, "languages": [{"name": "Common"}, {"name": "Elvish"}],
                  "ability_bonuses": [{"ability_score": ref("dex"), "bonus": 2}],
                  "traits": [ref("keen-senses"), ref("trance")]},
    "races/half-elf": {"index": "half-elf", "name": "Half-Elf", "speed": 30, "languages": [],
                       "ability_bonuses": [{"ability_score": ref("cha"), "bonus": 2}], "traits": [],
                       "ability_bonus_options": {"choose": 2, "from": {"options": [
                           {"ability_score": ref(a), "bonus": 1} for a in ("str", "dex", "con", "int", "wis")]}}},
    "races/dwarf": {"index": "dwarf", "name": "Dwarf", "speed": 25, "languages": [], "traits": [],
                    "ability_bonuses": [{"ability_score": ref("con"), "bonus": 2}]},
    "subraces/high-elf": {"index": "high-elf", "name": "High Elf", "ability_bonuses": [{"ability_score": ref("int"), "bonus": 1}],
                          "racial_traits": [ref("elf-weapon-training")]},
    "classes/fighter": cls("fighter", 10, ["str", "con"], ["athletics", "perception", "survival", "acrobatics"], 2),
    "classes/wizard": cls("wizard", 6, ["int", "wis"], ["arcana", "history", "insight"], 2, "int"),
    "classes/monk": cls("monk", 8, ["str", "dex"], ["acrobatics", "athletics", "insight"], 2),
    "classes/barbarian": cls("barbarian", 12, ["str", "con"], ["athletics", "perception"], 2),
    "classes/fighter/levels/1": {"level": 1, "features": [ref("fighting-style")]},
    "classes/monk/levels/1": {"level": 1, "features": []},
    "classes/barbarian/levels/1": {"level": 1, "features": []},
    "classes/wizard/levels/1": {"level": 1, "features": [ref("arcane-recovery")], "spellcasting": {
        "cantrips_known": 3, "spell_slots_level_1": 2, "spell_slots_level_2": 0}},
    "backgrounds/acolyte": {"index": "acolyte", "starting_proficiencies": [ref("skill-insight"), ref("skill-religion")]},
    "traits/keen-senses": {"desc": ["You have proficiency in Perception. More text."]},
    "features/arcane-recovery": {"desc": ["You regain some slots. Once per day."]},
    "equipment/longsword": {"index": "longsword", "name": "Longsword", "equipment_category": {"index": "weapon"},
                            "weapon_range": "Melee", "properties": [ref("versatile")],
                            "damage": {"damage_dice": "1d8", "damage_type": ref("slashing")}},
    "equipment/chain-mail": {"index": "chain-mail", "name": "Chain Mail", "equipment_category": {"index": "armor"},
                             "armor_category": "Heavy", "armor_class": {"base": 16, "dex_bonus": False}},
    "equipment/shield": {"index": "shield", "name": "Shield", "equipment_category": {"index": "armor"},
                         "armor_category": "Shield", "armor_class": {"base": 2, "dex_bonus": False}},
}


def opt(items: list[tuple[str, int]], choose: int = 1) -> dict:
    return {"desc": "(a) x or (b) y", "choose": choose, "type": "equipment", "from": {"option_set_type": "options_array", "options": [
        {"option_type": "counted_reference", "count": n, "of": {**ref(i), "url": ""}} for i, n in items]}}


DATA.update({
    "races": {"results": [ref("elf"), ref("half-elf"), ref("dwarf")]},
    "classes": {"results": [ref("fighter"), ref("wizard")]},
    "backgrounds": {"results": [ref("acolyte")]},
    "races/elf": {**DATA["races/elf"], "subraces": [ref("high-elf")]},
    "backgrounds/acolyte": {**DATA["backgrounds/acolyte"], "name": "Acolyte"},
    "classes/fighter": {**DATA["classes/fighter"], "starting_equipment": [{"equipment": ref("shield"), "quantity": 1}],
                        "starting_equipment_options": [opt([("longsword", 1), ("chain-mail", 1)]),
                                                       opt([("shield", 1), ("longsword", 2)]),
                                                       {"desc": "a martial weapon", "choose": 1, "from": {"option_set_type": "equipment_category"}}]},
    "classes/wizard/spells": {"results": [{**ref("fire-bolt"), "level": 0}, {**ref("magic-missile"), "level": 1}, {**ref("fireball"), "level": 3}]},
    "equipment/explorers-pack": {"index": "explorers-pack", "name": "Explorer's Pack", "equipment_category": {"index": "adventuring-gear"}},
})


def fetch(endpoint: str) -> dict:
    if endpoint not in DATA:
        raise combat.RulesError(f"no {endpoint}")
    return DATA[endpoint]


STD = dict(player="p1", name="Test", race="elf", cls="fighter", background="acolyte",
           scores="15,14,13,12,10,8", assign="str,dex,con,int,wis,cha", skills="athletics,survival")


def build(**kw) -> dict:
    return creation.build(fetch, **{**STD, **kw})


def fails(**kw) -> str:
    try:
        build(**kw)
    except combat.RulesError as e:
        return str(e)
    return ""


def test_build() -> None:
    d = build(subrace="high-elf", equipment="longsword,chain-mail,shield")
    s = d["ability_scores"]
    check("racial and subracial bonuses are added", s["dexterity"] == 16 and s["intelligence"] == 13 and s["strength"] == 15)
    check("modifiers", d["ability_modifiers"]["dexterity"] == 3 and d["ability_modifiers"]["charisma"] == -1)
    check("HP is the hit die plus CON", d["hp"] == {"current": 11, "max": 11, "temp": 0})
    check("hit dice", d["hit_dice"] == {"total": 1, "remaining": 1, "type": "d10"})
    check("skills: class, background, and the elf's Perception, as totals",
          d["skills"] == {"athletics": 4, "survival": 2, "insight": 2, "religion": 3, "perception": 2})
    check("saves are the class saves", d["saving_throws"] == {"strength": 4, "constitution": 3})
    check("armor and shield set the AC", d["armor_class"] == 16 + 2)
    w = d["weapons"][0]
    check("weapon attack is STR + proficiency", w["name"] == "Longsword" and w["attack_bonus"] == 4 and w["damage"] == "1d8+2")
    check("gear is in the inventory", {i["name"] for i in d["inventory"]} == {"Longsword", "Chain Mail", "Shield"})
    check("race name and languages", d["race"] == "Elf (High Elf)" and d["languages"] == ["Common", "Elvish"])
    feats = {f["name"]: f["description"] for f in d["features_and_traits"]}
    check("traits and features hold the first sentence", feats["Keen-Senses"] == "You have proficiency in Perception.")
    check("initiative and speed", d["initiative"] == 3 and d["speed"] == 30 and "spellcasting" not in d)
    check("score cap at 20", build(scores="18,18,18,18,18,18", assign="dex,str,con,int,wis,cha")["ability_scores"]["dexterity"] == 20)
    check("half-elf picks two bonus abilities",
          build(race="half-elf", bonus_abilities="str,con")["ability_scores"]["charisma"] == 8 + 2
          and fails(race="half-elf").startswith("Half-Elf adds +1"))
    d = build(race="dwarf")
    check("dwarf speed", d["speed"] == 25 and d["ability_scores"]["constitution"] == 15)


def test_errors() -> None:
    check("one skill short", "picks 2 different skills" in fails(skills="athletics"))
    check("a skill outside the class list", "picks 2" in fails(skills="athletics,arcana"))
    check("the same skill twice", "picks 2" in fails(skills="athletics,athletics"))
    check("a skill from two sources", "two sources" in fails(skills="athletics,perception"))
    check("an unknown skill", "no skill" in fails(skills="athletics,flying"))
    check("five scores", "six numbers" in fails(scores="15,14,13,12,10"))
    check("a score over 18", "six numbers" in fails(scores="19,14,13,12,10,8"))
    check("assign repeats an ability", "once" in fails(assign="str,str,con,int,wis,cha"))
    check("an unknown race", "no race" in fails(race="gnoll"))
    check("an unknown background needs skills", "--background-skills" in fails(background="Folk Hero"))
    d = build(background="Folk Hero", background_skills="animal-handling,survival", skills="athletics,perception", race="dwarf")
    check("a free-text background works with its skills", d["background"] == "Folk Hero" and "animal_handling" in d["skills"])
    check("spells for a non-caster are refused", "no spells" in fails(cantrips="light"))


def test_classes() -> None:
    d = build(cls="wizard", skills="arcana,history", cantrips="fire-bolt,light,mage-hand", spells="magic-missile",
              scores="8,14,13,15,10,12")
    sp = d["spellcasting"]
    check("caster: ability, DC, attack", sp["ability"] == "intelligence" and sp["spell_save_dc"] == 8 + 2 + 2 and sp["spell_attack_bonus"] == 4)
    check("caster: slots and spells", sp["spell_slots"] == {"1": {"max": 2, "remaining": 2}}
          and sp["spells_known"] == ["Fire Bolt", "Light", "Mage Hand", "Magic Missile"])
    check("wizard HP d6", d["hp"]["max"] == 6 + 1)
    m = build(cls="monk", skills="acrobatics,athletics", assign="str,dex,con,int,wis,cha", scores="12,15,13,10,14,8")
    check("monk AC is 10 + DEX + WIS", m["armor_class"] == 10 + 3 + 2 and m["hp"]["max"] == 8 + 1)
    b = build(cls="barbarian", skills="athletics,perception", race="dwarf")
    check("barbarian AC is 10 + DEX + CON", b["armor_class"] == 10 + 2 + 2 and b["hp"]["max"] == 12 + 2)


def test_equipment_quantity() -> None:
    d = build(equipment="longsword,longsword,shield,explorers-pack")
    inv = {i["name"]: i["quantity"] for i in d["inventory"]}
    check("a repeated index is a quantity", inv == {"Longsword": 2, "Shield": 1, "Explorer's Pack": 1})
    check("a pack does not change weapons or AC", len(d["weapons"]) == 1 and d["armor_class"] == 10 + 3 + 2)


def test_options() -> None:
    o = creation.options(fetch)
    check("lists come from the index endpoints", [r["index"] for r in o["races"]] == ["elf", "half-elf", "dwarf"]
          and [c["index"] for c in o["classes"]] == ["fighter", "wizard"])
    elf, half = o["races"][0], o["races"][1]
    check("race: bonuses, subraces, look race", elf["ability_bonuses"] == {"dexterity": 2} and elf["look_race"] == "elf"
          and elf["subraces"] == [{"index": "high-elf", "name": "High Elf", "ability_bonuses": {"intelligence": 1}}]
          and elf["bonus_choice"] is None and elf["speed"] == 30)
    check("half-elf bonus choice uses full names", half["bonus_choice"]["count"] == 2
          and half["bonus_choice"]["options"][0] == "strength" and half["look_race"] == "half-elf")
    f, w = o["classes"]
    check("class: die, saves, skills", f["hit_die"] == 10 and f["saves"] == ["strength", "constitution"]
          and f["skill_count"] == 2 and "athletics" in f["skill_options"])
    check("no spellcasting at level 1 is null", f["spellcasting"] is None)
    check("only plain single-item choices; fixed gear",
          [c["options"][0]["index"] for c in f["equipment"]["choices"]] == ["longsword"]
          and f["equipment"]["fixed"] == [{"index": "shield", "name": "Shield", "quantity": 1}])
    sp = w["spellcasting"]
    check("wizard spells: ability, counts, level 0 and 1 options", sp["ability"] == "intelligence" and sp["cantrips"] == 3
          and sp["spells"] == 6 and [x["index"] for x in sp["cantrip_options"]] == ["fire-bolt"]
          and [x["index"] for x in sp["spell_options"]] == ["magic-missile"])
    check("background skills are SKILLS keys", o["backgrounds"] == [{"index": "acolyte", "name": "Acolyte", "skills": ["insight", "religion"]}])
    look = o["look"]
    check("look block", look["bodies"] == ["male", "female", "muscular"] and "green" in look["eyes"]
          and look["races"]["drow"] == {"skins": ["blue", "black", "lavender"], "default_skin": "blue"}
          and len(look["hair"]) == 10 and look["hair"][1] == {"id": "hair_long", "name": "Long"}
          and 5 <= len(look["hair_colors"]) <= 10 and list(o["skills"]) == list(combat.SKILLS) and len(o["abilities"]) == 6)


def test_campaign_config() -> None:
    from dnd_cli import campaign

    original = campaign.CAMPAIGNS_DIR
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        shutil.copytree(original / "template", root / "template")
        campaign.CAMPAIGNS_DIR = root
        try:
            slug = campaign.create_campaign("Plain")
            cfg = json.loads((root / slug / "config.json").read_text())
            check("defaults: no pitch, the player makes the party", cfg["pitch"] == "" and cfg["party"] == "create")
            slug = campaign.create_campaign("Epilogue", " Karlach lives. ", "premade")
            cfg = json.loads((root / slug / "config.json").read_text())
            check("pitch and party are saved", cfg["pitch"] == "Karlach lives." and cfg["party"] == "premade")
            for args in (("Empty", "", "premade"), ("Bad", "x", "other")):
                try:
                    campaign.create_campaign(*args)
                    refused = False
                except campaign.CampaignError:
                    refused = True
                check(f"refused: {args}", refused and not (root / campaign.slugify(args[0])).exists())
        finally:
            campaign.CAMPAIGNS_DIR = original


def test_create() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        c = campaign(Path(tmp))
        lines = creation.create(c, fetch, "thorin", player_name="Dana", **STD)
        loaded = character.load(c, "thorin")
        check("the sheet is saved and valid", loaded["name"] == "Test" and loaded["controlled_by"] == "p1")
        state = json.loads((c / "state.json").read_text())
        check("party_members keeps the old sheets and adds the new one",
              "thorin" in state["party_members"] and "aragorn" in state["party_members"])
        player = json.loads((c / "players" / "p1.json").read_text())
        check("a new player file is made", player["characters_controlled"] == ["thorin"] and player["player_name"] == "Dana")
        creation.create(c, fetch, "second", **STD)
        player = json.loads((c / "players" / "p1.json").read_text())
        check("an existing player file gets the new character", player["characters_controlled"] == ["thorin", "second"])
        try:
            creation.create(c, fetch, "thorin", **STD)
            refused = False
        except combat.RulesError as e:
            refused = "already exists" in str(e)
        check("an existing id is refused", refused)
        check("the output is short", len(lines) <= 3 and "HP 11" in lines[0] and "bonds" in lines[-1])


if __name__ == "__main__":
    test_build()
    test_errors()
    test_classes()
    test_equipment_quantity()
    test_options()
    test_campaign_config()
    test_create()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
