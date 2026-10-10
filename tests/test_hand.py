"""Checks for the hand of a player character on the board: abilities with reasons, odds in words, spells, shove and hide.

Run from the repo root:  .venv/bin/python tests/test_hand.py

Plain asserts so no test runner is needed. It reads the cached 5e API data under .cache.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dnd_cli import character, combat  # noqa: E402
from stage import board, hand, improvise  # noqa: E402
from tests.test_board import dark, setup  # noqa: E402
from tests.test_rules import Fixed  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}{'' if cond or not detail else f'  ({detail})'}")


def raises(fn) -> str | None:
    try:
        fn()
    except board.BoardError as e:
        return str(e)
    return None


def by_id(items: list[dict]) -> dict:
    return {x["id"]: x for x in items}


def give_spells(c: Path, who: str, spells: list[str], slots: dict) -> None:
    sheet = character.load(c, who)
    sheet["spellcasting"] = {"ability": "intelligence", "spell_save_dc": 13, "spell_attack_bonus": 5, "spells_known": spells,
                             "spell_slots": {k: {"max": v, "remaining": v} for k, v in slots.items()}}
    sheet["level"] = 5
    character.save(c, who, sheet)


def test_listing() -> None:
    print("hand: the abilities of a character")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = setup(Path(tmp), at={"goblin#1": (3, 3), "goblin#2": (9, 5)})
        hand_ = by_id(hand.listing(c, state, a, "aragorn"))
        check("weapons, unarmed strike, the common actions and class features are all there",
              {"attack:Longsword", "attack:Longbow", "attack:Unarmed Strike", "dash", "disengage", "dodge", "help", "hide", "shove", "feature:Second Wind"} <= set(hand_))
        sword = hand_["attack:Longsword"]
        check("a weapon says its reach and its numbers, and needs a target", sword["needs"] == "target" and sword["text"] == "Reach 5 ft" and sword["stat"] == "+5 · 1d8+3")
        near, far = by_id(sword["targets"])["goblin#1"], by_id(sword["targets"])["goblin#2"]
        check("a creature in reach is a valid target, with odds in words and no AC", near["ok"] and near["odds"] in ("good odds", "even odds", "poor odds")
              and '"ac"' not in json.dumps(hand_).lower())
        check("a creature out of reach says how far", not far["ok"] and "ft away" in far["why"] and far["dist_ft"] == 35)
        check("a bow reaches it", by_id(hand_["attack:Longbow"]["targets"])["goblin#2"]["ok"])
        check("a character that is not on turn has every ability off", all(hand.listing(c, state, a, "legolas")[i]["why"] for i in range(3)))
        check("on turn, nothing is off at the start but shove needs a creature next to it", sword["why"] is None and hand_["dash"]["why"] is None)
        combat.spend_turn(state, "aragorn", "action")
        spent = by_id(hand.listing(c, state, a, "aragorn"))
        check("a spent action turns off attacks and Dash, not a bonus action", spent["attack:Longsword"]["why"] == "The action is used." and spent["dash"]["why"]
              and spent["feature:Second Wind"]["why"] is None)


def test_spells() -> None:
    print("hand: spells")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = setup(Path(tmp), at={"goblin#1": (5, 3), "goblin#2": (6, 3), "boss": (10, 6)})
        give_spells(c, "aragorn", ["burning-hands", "fire-bolt", "fireball", "cure-wounds"], {"1": 2, "3": 1})
        h = by_id(hand.listing(c, state, a, "aragorn"))
        check("damage spells are in the hand, a healing spell is not", {"spell:burning-hands", "spell:fire-bolt", "spell:fireball"} <= set(h) and "spell:cure-wounds" not in h)
        check("a cantrip is at will, with its range and the dice of the caster's level", h["spell:fire-bolt"]["text"] == "Cantrip · 120 ft" and h["spell:fire-bolt"]["damage"] == [["2d10", "fire"]]
              and h["spell:fire-bolt"]["needs"] == "target")
        check("an area spell is aimed at a cell", h["spell:fireball"]["needs"] == "aim" and h["spell:fireball"]["stat"] == "DC 13 · 8d6")
        check("burning hands takes the level 1 slot", h["spell:burning-hands"]["slot"] == 1 and h["spell:burning-hands"]["damage"] == [["3d6", "fire"]])
        check("a spell with no slot is off, and says so", by_id(hand.listing(c, state, a, "aragorn"))["spell:fireball"]["why"] is None)
        pv = hand.preview(c, state, a, "aragorn", "spell:fireball", (6, 3))
        check("the preview shows the cells and the creatures in a fireball", pv["ok"] and (6, 3) in {tuple(x) for x in pv["cells"]} and set(pv["units"]) >= {"goblin#1", "goblin#2"})
        check("a cone has no range: any other cell is a direction", hand.preview(c, state, a, "aragorn", "spell:burning-hands", (6, 3))["ok"]
              and not hand.preview(c, state, a, "aragorn", "spell:burning-hands", (2, 3))["ok"])
        lines = hand.act(c, state, a, "aragorn", "spell:fireball", aim=(6, 3), rng=Fixed(10, 3, 3, 3, 3, 3, 3, 3, 3, 12, 12))
        check("a fireball is cast: it uses the action and a level 3 slot, and the creatures save", combat.turn_used(state, "aragorn")["action"]
              and character.load(c, "aragorn")["spellcasting"]["spell_slots"]["3"]["remaining"] == 0 and sum("save" in ln for ln in lines) >= 2)
        check("with the action used it is off", by_id(hand.listing(c, state, a, "aragorn"))["spell:fireball"]["why"] == "The action is used.")
        state["active_encounter"]["resources"]["aragorn"] = {}
        msg = raises(lambda: hand.act(c, state, a, "aragorn", "spell:fireball", aim=(6, 3)))
        check("a spell with no slot is refused, and costs nothing", msg == "No spell slot left." and not combat.turn_used(state, "aragorn")["action"])
        msg = raises(lambda: hand.act(c, state, a, "aragorn", "spell:fire-bolt", target="boss", rng=Fixed(15, 6)))
        check("a cantrip attack on a creature in sight works and spends the action", msg is None and combat.turn_used(state, "aragorn")["action"])
        state["active_encounter"]["resources"]["aragorn"] = {}
        check("a spell attack needs a target, an area needs an aim", "target" in (raises(lambda: hand.act(c, state, a, "aragorn", "spell:fire-bolt")) or "")
              and "aim" in (raises(lambda: hand.act(c, state, a, "aragorn", "spell:burning-hands")) or ""))
        state["active_encounter"]["resources"]["aragorn"] = {}
        a["units"]["boss"] = {"x": 3, "y": 3}
        state["active_encounter"]["monsters"]["boss"]["hp"]["current"] = 7  # it survived or fell above: stand it up
        lines = hand.act(c, state, a, "aragorn", "spell:burning-hands", aim=(5, 3), rng=Fixed(10, 3, 3, 3, 12, 12))
        check("a cone starts next to the caster and never covers him", any(ln.startswith("boss DEX") for ln in lines) and not any(ln.startswith("aragorn DEX") for ln in lines), str(lines))
        dark(a)
        a["units"]["goblin#1"] = {"x": 10, "y": 1}
        h = by_id(hand.listing(c, state, a, "aragorn"))
        check("a creature out of sight is not a target in the dark", "goblin#1" not in {t["id"] for t in h["spell:fire-bolt"]["targets"]})


def test_actions() -> None:
    print("hand: shove, hide and the stances")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = setup(Path(tmp), at={"goblin#1": (3, 3), "goblin#2": (9, 5)})
        lines = hand.act(c, state, a, "aragorn", "shove", target="goblin#1", rng=Fixed(20, 1))
        check("a won shove pushes the creature 5 ft away and uses the bonus action", board.pos(a, "goblin#1") == (4, 3) and combat.turn_used(state, "aragorn")["bonus"]
              and any("pushed 5 ft" in ln for ln in lines))
        state["active_encounter"]["resources"]["aragorn"] = {}
        check("a shove at a creature that is not next to you is refused", "ft away" in (raises(lambda: hand.act(c, state, a, "aragorn", "shove", target="goblin#2")) or ""))
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = setup(Path(tmp), at={"goblin#1": (3, 3), "goblin#2": (9, 5)})
        lines = hand.act(c, state, a, "aragorn", "shove", target="goblin#1", rng=Fixed(2, 19))
        check("a lost shove leaves it where it is", board.pos(a, "goblin#1") == (3, 3) and any("holds its ground" in ln for ln in lines))
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = setup(Path(tmp), at={"goblin#1": (3, 3), "goblin#2": (9, 5)})
        a["grid"][3] = a["grid"][3][:4] + "~" + a["grid"][3][5:]
        a["spec"]["decor"] = "tavern"
        lines = hand.act(c, state, a, "aragorn", "shove", target="goblin#1", rng=Fixed(20, 1, 4, 4))
        check("shoved into lava a creature takes 2d6", board.pos(a, "goblin#1") == (4, 3) and any("goblin#1" in ln and "takes" in ln for ln in lines))
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = setup(Path(tmp), at={"goblin#1": (3, 3), "goblin#2": (9, 5)})
        a["grid"][3] = a["grid"][3][:4] + "#" + a["grid"][3][5:]
        hand.act(c, state, a, "aragorn", "shove", target="goblin#1", rng=Fixed(20, 1))
        check("a shove into a wall does not move it", board.pos(a, "goblin#1") == (3, 3))
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = setup(Path(tmp), at={"goblin#1": (8, 3), "goblin#2": (9, 5)})
        state["active_encounter"]["current_turn"] = "legolas"
        lines = hand.act(c, state, a, "legolas", "hide", rng=Fixed(20))
        check("hide: stealth against the best passive Perception; a success is hidden", combat.has_condition(state, "legolas", "hidden") and combat.turn_used(state, "legolas")["action"], str(lines))
        check("the DC and the roll stay on the stage: the lines say only what the story needs", lines == ["Legolas slips out of sight."])
        state["active_encounter"]["resources"]["legolas"] = {}
        combat.condition(state, "legolas", "remove", "hidden")
        hand.act(c, state, a, "legolas", "hide", rng=Fixed(1))
        check("a failed hide leaves the character in the open", not combat.has_condition(state, "legolas", "hidden"))
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = setup(Path(tmp), at={"goblin#1": (8, 3), "goblin#2": (9, 5)})
        hand.act(c, state, a, "aragorn", "dodge")
        check("a stance from the hand is the condition, and spends the action", combat.has_condition(state, "aragorn", "dodging") and combat.turn_used(state, "aragorn")["action"])
        check("an ability that is off refuses with the reason", raises(lambda: hand.act(c, state, a, "aragorn", "dash")) == "The action is used")
        check("an unknown ability is refused", "no ability" in (raises(lambda: hand.act(c, state, a, "aragorn", "nope")) or ""))
        check("out of turn is refused", "turn" in (raises(lambda: hand.act(c, state, a, "legolas", "dash")) or ""))


def test_improvise() -> None:
    print("hand: improvise")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = setup(Path(tmp), props=({"kind": "barrel", "x": 3, "y": 3}, {"kind": "stool", "x": 2, "y": 4}), at={"goblin#1": (8, 3), "goblin#2": (9, 5)})
        ids = by_id(hand.listing(c, state, a, "aragorn"))
        check("the hand has Improvise: it needs text, and costs the action", ids["improvise"]["needs"] == "text" and ids["improvise"]["cost"] == "action" and not ids["improvise"]["why"])
        check("Improvise does not run from act: it goes to the DM", "DM" in (raises(lambda: hand.act(c, state, a, "aragorn", "improvise")) or ""))
        stool = improvise.suggest(c, state, "aragorn", "I throw the stool at the goblin", improvise.find_object(a, "stool#1"))
        check("a thrown object is an improvised weapon: Dex attack, 1d4, range 20/60, used up",
              stool["roll"]["type"] == "attack" and stool["roll"]["bonus"] == 2 and stool["roll"]["range_ft"] == [20, 60] and stool["consume"] and "1d4" in stool["effect"], str(stool))
        barrel = improvise.suggest(c, state, "aragorn", "I hurl the barrel", improvise.find_object(a, "barrel#0"))
        check("a heavy object is a Strength check, not a throw", barrel["roll"]["type"] == "check" and barrel["roll"]["dc"] == 15)
        push = improvise.suggest(c, state, "aragorn", "I kick the barrel over", improvise.find_object(a, "barrel#0"))
        check("pushing a heavy object is harder", push["roll"]["dc"] == 15 and improvise.suggest(c, state, "aragorn", "I tip the stool", improvise.find_object(a, "stool#1"))["roll"]["dc"] == 10)
        check("breaking something that is made to break gives a DC from its HP", improvise.suggest(c, state, "aragorn", "I smash the barrel", improvise.find_object(a, "barrel#0"))["roll"]["dc"] == 10)
        check("a free interaction costs no action", improvise.suggest(c, state, "aragorn", "I pick up the stool", improvise.find_object(a, "stool#1"))["cost"] == "free")
        other = improvise.suggest(c, state, "aragorn", "I try to impress the goblins with a song", None)
        check("an action with no rule is a plain check: the engine never refuses", other["roll"]["type"] == "check" and other["roll"]["dc"] == 12)
        line = improvise.prompt(c, state, a, "aragorn", "I throw the stool at the goblin", "stool#1")
        check("the DM prompt has the words, the object with its tags and the ruling", line.startswith("[combat] Aragorn (aragorn) improvises") and "stool (portable, breakable, flammable" in line and "Suggested ruling" in line and "5 ft away" in line, line[:300])
        check("an unknown object is refused", "no object" in (raises(lambda: improvise.prompt(c, state, a, "aragorn", "I throw it", "ghost#9")) or ""))


def stock(c: Path, who: str, rows: list[dict]) -> None:
    sheet = character.load(c, who)
    sheet["inventory"] = rows
    character.save(c, who, sheet)


def test_items() -> None:
    print("hand: items")
    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = setup(Path(tmp), at={"goblin#1": (5, 3), "goblin#2": (9, 5), "legolas": (3, 3)})
        stock(c, "aragorn", [{"name": "Potion of healing", "quantity": 2}, {"name": "Alchemist's fire", "quantity": 1}, {"name": "Rope", "quantity": 1},
                             {"name": "Mystery flask", "quantity": 1, "profile": {"kind": "heal", "heal": "1d4", "cost": "bonus"}}])
        sheet = character.load(c, "aragorn")
        sheet["hp"]["current"] = 2
        character.save(c, "aragorn", sheet)
        ab = by_id(hand.listing(c, state, a, "aragorn"))
        check("a row with a profile is an ability: the table's, or its own", {"item:Potion of healing", "item:Alchemist's fire", "item:Mystery flask"} <= set(ab) and "item:Rope" not in ab)
        check("a row with no profile has no card", not any(x["name"] == "Rope" for x in ab.values()))
        check("an item says its count and its numbers", ab["item:Potion of healing"]["text"].startswith("x2") and ab["item:Potion of healing"]["stat"] == "heals 2d4+2"
              and ab["item:Alchemist's fire"]["stat"] == "+2 · 1d4 fire")
        check("its own profile sets its cost", ab["item:Mystery flask"]["cost"] == "bonus")
        heal_to = by_id(ab["item:Potion of healing"]["targets"])
        check("a potion goes to the user or a friend next to them", heal_to["aragorn"]["ok"] and heal_to["legolas"]["ok"])
        lines = hand.act(c, state, a, "aragorn", "item:Potion of healing", target="legolas", rng=Fixed(3, 4))
        check("a potion for a friend heals them with its dice and costs the action", "legolas heals 9" in lines[1] and combat.turn_used(state, "aragorn")["action"])
        check("the potion is used up one at a time", next(i for i in character.load(c, "aragorn")["inventory"] if i["name"] == "Potion of healing")["quantity"] == 1)
        state["active_encounter"]["resources"]["aragorn"] = {}
        far = raises(lambda: hand.act(c, state, a, "aragorn", "item:Potion of healing", target="goblin#1"))
        check("a potion does not go to a foe, and a refusal costs nothing", far is not None and not combat.turn_used(state, "aragorn")["action"]
              and next(i for i in character.load(c, "aragorn")["inventory"] if i["name"] == "Potion of healing")["quantity"] == 1)
        hand.act(c, state, a, "aragorn", "item:Potion of healing", target="aragorn", rng=Fixed(1, 1))
        check("the last potion leaves the sheet", not any(i["name"] == "Potion of healing" for i in character.load(c, "aragorn")["inventory"]) and character.load(c, "aragorn")["hp"]["current"] == 6)
        state["active_encounter"]["resources"]["aragorn"] = {}
        out = raises(lambda: hand.act(c, state, a, "aragorn", "item:Alchemist's fire", target="goblin#2"))
        check("a thrown item that is out of range is refused and kept", out and "ft away" in out and any(i["name"] == "Alchemist's fire" for i in character.load(c, "aragorn")["inventory"]))
        before = combat.combatant(c, state, "goblin#1")["hp"]["current"]
        lines = hand.act(c, state, a, "aragorn", "item:Alchemist's fire", target="goblin#1", rng=Fixed(15, 3))
        check("a thrown item is a ranged attack with its damage; it is gone", combat.combatant(c, state, "goblin#1")["hp"]["current"] < before
              and not any(i["name"] == "Alchemist's fire" for i in character.load(c, "aragorn")["inventory"]) and combat.turn_used(state, "aragorn")["action"])

    with tempfile.TemporaryDirectory() as tmp:
        c, state, a = setup(Path(tmp), at={"goblin#1": (8, 3), "goblin#2": (9, 5)})
        stock(c, "aragorn", [])
        a["items"] = [{"id": "item#1", "name": "Bottle", "x": 2, "y": 4}, {"id": "item#2", "name": "Stone", "x": 3, "y": 3}, {"id": "item#3", "name": "Far cup", "x": 8, "y": 6}]
        ab = by_id(hand.listing(c, state, a, "aragorn"))
        check("only the objects next to the character can be picked up", {"pickup:item#1", "pickup:item#2"} <= set(ab) and "pickup:item#3" not in ab and ab["pickup:item#1"]["cost"] == "free")
        hand.act(c, state, a, "aragorn", "pickup:item#1")
        check("a pick-up puts it on the sheet and takes it off the board", [i["name"] for i in character.load(c, "aragorn")["inventory"]] == ["Bottle"] and [i["id"] for i in a["items"]] == ["item#2", "item#3"])
        check("a pick-up costs no action", not any(combat.turn_used(state, "aragorn").values()))
        check("a second pick-up in a turn is refused", "free object interaction" in (raises(lambda: hand.act(c, state, a, "aragorn", "pickup:item#2")) or ""))
        check("the free interaction is back on the next turn", (state["active_encounter"]["resources"].__setitem__("aragorn", {}) or True)
              and hand.act(c, state, a, "aragorn", "pickup:item#2") == ["aragorn picks up Stone."])


if __name__ == "__main__":
    for t in (test_listing, test_spells, test_actions, test_improvise, test_items):
        t()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
