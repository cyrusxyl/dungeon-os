"""Checks for teams in a fight: who is at war with whom, who joins a fight from the stage, a bystander that is drawn in, who the stage
plays, XP, and what the scene keeps when the fight ends.

Run from the repo root:  .venv/bin/python tests/test_teams.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dnd_cli import actions  # noqa: E402
from dnd_cli.combat import encounters, records, tracker  # noqa: E402
from stage import arena, board, foes, scenes, state as stage_state  # noqa: E402
from tests.test_rules import GOBLIN, Fixed, campaign  # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}{'' if cond or not detail else f'  ({detail})'}")


def fighter(name: str, hp: int = 12) -> dict:
    return {"name": name, "hp": {"current": hp, "max": hp}, "armor_class": 12, "xp": 100,
            "ability_scores": {"strength": 14, "dexterity": 12, "constitution": 12, "intelligence": 10, "wisdom": 10, "charisma": 10},
            "actions": [{"name": "Club", "attack_bonus": 4, "damage": "1d6+2", "desc": "Melee Weapon Attack: reach 5 ft., one target."}]}


def scene_fight(tmp: str):
    """A scene with the party, a green companion, a yellow faction fighter, a red goblin, a bystander and a fallen guard."""
    c = campaign(Path(tmp))
    npcs = c / "world" / "npcs"
    for name in ("ilvuur", "qorlia", "mara-shop"):
        (npcs / f"{name}.json").write_text(json.dumps(fighter(name) if name != "mara-shop" else {"name": "Mara", "role": "shopkeeper", "personality": "Sells rope"}))
    scenes.save(c, "hall", {"template": "tavern", "slots": {}, "add": [], "mood": "day", "shape": "fixed"})
    room = scenes.room(scenes.load(c, "hall"))
    free = [(x, y) for y, row in enumerate(room["grid"]) for x, ch in enumerate(row) if ch == "." and not any((p["x"], p["y"]) == (x, y) for p in room["props"])]
    cell = lambda i: list(free[i * 3])  # noqa: E731
    actors = {"aragorn": {"side": "party", "cell": cell(0)}, "legolas": {"side": "party", "cell": cell(1)},
              "ilvuur": {"side": "ally", "cell": cell(2)}, "qorlia": {"side": "neutral", "cell": cell(3)},
              "goblin#1": {"side": "hostile", "cell": cell(4)}, "mara-shop": {"side": "bystander", "cell": cell(5)},
              "dead-guard": {"side": "hostile", "down": True, "cell": cell(6)}}
    return c, {"scene": "hall", "actors": actors}


def main() -> int:
    encounters.api_get = lambda path: (dict(GOBLIN, index=path.split("/")[1]), None, None)

    # The relations.
    enc = {"type": "combat", "participants": ["aragorn", "ilvuur", "qorlia", "goblin#1"], "teams": {"ilvuur": "party", "qorlia": "neutral"},
           "monsters": {"goblin#1": {}, "ilvuur": {}, "qorlia": {}}}
    st = {"active_encounter": enc}
    check("a player character is on the party's team, a monster on the hostile one, a companion where it was put",
          [tracker.team_of(st, i) for i in ("aragorn", "goblin#1", "ilvuur", "qorlia")] == ["party", "hostile", "party", "neutral"])
    check("party and hostile fight, and so do neutral and hostile", tracker.enemies(st, "aragorn", "goblin#1") and tracker.enemies(st, "qorlia", "goblin#1")
          and tracker.enemies(st, "goblin#1", "ilvuur"))
    check("party and neutral are at peace, and a team is not its own enemy", not tracker.enemies(st, "aragorn", "qorlia") and not tracker.enemies(st, "aragorn", "ilvuur"))
    check("only the hostile are enemies of the party", [tracker.hostile_to_party(st, i) for i in ("qorlia", "ilvuur", "goblin#1")] == [False, False, True])
    check("a strike on someone at peace makes a feud, one way for one target", tracker.feud(st, "aragorn", "qorlia") and tracker.enemies(st, "aragorn", "qorlia")
          and tracker.enemies(st, "qorlia", "ilvuur") and not tracker.feud(st, "aragorn", "qorlia") and not tracker.feud(st, "aragorn", "ilvuur"))
    check("the feud is with that one, not its whole team", tracker.hostile_to_party(st, "qorlia") and not tracker.hostile_to_party({"active_encounter": {**enc, "feuds": []}}, "qorlia"))

    with tempfile.TemporaryDirectory() as tmp:
        c, stage = scene_fight(tmp)
        state = tracker.load_state(c)
        started = encounters.start(c, state, ["goblin"], None, rng=Fixed(10), stage=stage["actors"])
        enc = state["active_encounter"]
        check("the fighters of the stage join: the party, the companion, the faction, the goblin under its stage id",
              set(enc["participants"]) == {"aragorn", "legolas", "ilvuur", "qorlia", "goblin#1"}, str(enc["participants"]))
        check("a bystander and a fallen creature do not", "mara-shop" not in enc["participants"] and "dead-guard" not in enc["participants"])
        teams = next(x for x in started if x.startswith("Teams:"))
        check("the start output lists each team and who is out of the fight",
              "party aragorn, legolas, ilvuur" in teams and "neutral qorlia" in teams and "hostile goblin#1" in teams
              and teams.endswith("Out of the fight: mara-shop."), teams)
        check("teams: green companion, yellow faction", enc["teams"] == {"ilvuur": "party", "qorlia": "neutral"})
        check("everyone who joined has an initiative", {o["name"] for o in enc["initiative_order"]} == set(enc["participants"]))

        # A spec that names creatures on the stage keeps their side: allies stay allies, new ones are hostile.
        state2 = tracker.load_state(c)
        stage2 = {**stage["actors"], "guard#1": {"side": "ally", "cell": [0, 0]}, "guard#2": {"side": "ally", "cell": [0, 1]},
                  "guard#3": {"side": "hostile", "cell": [0, 2]}}
        encounters.start(c, state2, ["guard:4"], None, rng=Fixed(10), stage=stage2)
        t2 = {i: tracker.team_of(state2, i) for i in state2["active_encounter"]["participants"] if i.startswith("guard")}
        check("encounter start: stage allies named in a spec fight for the party, the rest are hostile",
              t2 == {"guard#1": "party", "guard#2": "party", "guard#3": "hostile", "guard#4": "hostile"}, str(t2))

        encounters.add(c, state2, ["guard"], stage={**stage2, "guard#5": {"side": "ally", "cell": [1, 0]}, "guard#6": {"side": "ally", "cell": [1, 1]}})
        check("encounter add: a stage ally takes its side, and a stage fighter that is not named stays out",
              tracker.team_of(state2, "guard#5") == "party" and "guard#6" not in state2["active_encounter"]["participants"])

        # The arena.
        arena_id, a, _ = board.build(c, state, [], stage)
        check("the arena is the room of the scene, every fighter on the cell it had on the stage",
              all(a["units"][i] == {"x": v["cell"][0], "y": v["cell"][1]} for i, v in stage["actors"].items() if i in enc["participants"]))
        check("the bystander stands where it stood, and is not a unit", a["bystanders"] == {"mara-shop": {"x": stage["actors"]["mara-shop"]["cell"][0], "y": stage["actors"]["mara-shop"]["cell"][1]}}
              and "mara-shop" not in a["units"])
        check("the stage plays every creature: the companion and the faction too", all(a["control"][i] == "engine" for i in ("ilvuur", "qorlia", "goblin#1")))
        check("a bystander blocks its cell", (a["bystanders"]["mara-shop"]["x"], a["bystanders"]["mara-shop"]["y"]) in board.occupied(c, state, a))
        view = board.view(c, state, arena_id, a, {"reaction_seconds": 0})
        check("the view tells each unit's team and lists the bystanders", {u["id"]: u["team"] for u in view["units"]} == {
            "aragorn": "party", "legolas": "party", "ilvuur": "party", "qorlia": "neutral", "goblin#1": "hostile"} and [b["id"] for b in view["bystanders"]] == ["mara-shop"])

        # Who the stage attacks.
        for who, hits in (("ilvuur", {"goblin#1"}), ("qorlia", {"goblin#1"}), ("goblin#1", {"aragorn", "legolas", "ilvuur", "qorlia"})):
            enc["current_turn"] = who
            targets = set(foes.Ctx(c, state, a, who).targets)
            check(f"{who} may attack {sorted(hits)} and no one else", targets == hits, str(targets))
        pl = foes.plan(c, state, a, "qorlia")
        check("the yellow faction fights the red goblin, not the party", pl is not None and pl.get("target") == "goblin#1", str(pl))

        # Peace: an attack on the faction, or on the bystander, asks first.
        enc["current_turn"] = "aragorn"
        why = board.needs_confirm(state, a, "aragorn", "qorlia")
        check("an attack on someone at peace needs a confirmation", bool(why) and "peace" in why)
        check("so does one on a bystander, which says so", "bystander" in (board.needs_confirm(state, a, "aragorn", "mara-shop") or ""))
        check("an enemy needs none, and neither does a friend", board.needs_confirm(state, a, "aragorn", "goblin#1") is None and board.needs_confirm(state, a, "aragorn", "ilvuur") is None)
        refused = False
        try:
            board.player_attack(c, state, a, "aragorn", "mara-shop")
        except board.NeedsConfirm:
            refused = True
        check("player_attack refuses a bystander without `confirm`, and changes nothing", refused and "mara-shop" in a["bystanders"] and "mara-shop" not in enc["participants"])

        # Provocation: the bystander joins.
        before = len(enc["initiative_order"])
        board.player_attack(c, state, a, "aragorn", "mara-shop", confirm=True)
        check("the bystander is drawn in: a unit, in the order, on a team of its own, an enemy of the attacker",
              "mara-shop" in a["units"] and "mara-shop" not in a["bystanders"] and len(enc["initiative_order"]) == before + 1
              and enc["teams"]["mara-shop"] == "neutral" and tracker.enemies(state, "aragorn", "mara-shop"))
        check("it fights on the stage's side of control, as the engine", a["control"]["mara-shop"] == "engine")
        check("a drawn-in bystander is not an enemy of the whole party's team", tracker.team_of(state, "mara-shop") == "neutral")
        check("the party's allies are its enemy's enemies: the green companion fights the one that attacks the party", tracker.enemies(state, "mara-shop", "ilvuur"))
        board.player_attack(c, state, a, "aragorn", "qorlia", confirm=True)
        check("an attack on the faction at peace makes a feud", tracker.enemies(state, "aragorn", "qorlia") and tracker.enemies(state, "qorlia", "legolas"))

        # XP: only the party's enemies give it.
        enc["monsters"]["mara-shop"]["hp"]["current"] = enc["monsters"]["mara-shop"]["hp"]["max"]  # the attack above was a real roll: it may have killed her
        for cid in ("ilvuur", "goblin#1", "qorlia"):
            enc["monsters"][cid]["hp"]["current"] = 0
        lines = encounters.end(c, state, award_xp=True)
        check("a dead companion gives no XP; the goblin and the faction at war with the party do",
              any("Defeated foes give" in ln for ln in lines) and f"give {GOBLIN.get('xp', 0) + 100} XP" in " ".join(lines), " ".join(lines))

    # The end of a fight: what the scene keeps.
    with tempfile.TemporaryDirectory() as tmp:
        c, stage = scene_fight(tmp)
        state = tracker.load_state(c)
        encounters.start(c, state, ["goblin"], None, rng=Fixed(10), stage=stage["actors"])
        arena_id, a, _ = board.build(c, state, [], stage)
        enc = state["active_encounter"]
        enc["current_turn"] = "aragorn"
        board.player_attack(c, state, a, "aragorn", "mara-shop", confirm=True)
        a["units"]["aragorn"] = {"x": 3, "y": 3}
        enc["monsters"]["goblin#1"]["hp"]["current"] = 0
        done = board.outcome(c, state, a)
        check("the outcome has every unit's last cell, the fallen, and the faction sides",
              done["cells"]["aragorn"]["cell"] == [3, 3] and "goblin#1" in done["down"] and done["sides"] == {"qorlia": "neutral", "mara-shop": "hostile"})
        scene = {**stage_state.empty(), "scene": "hall", "actors": {i: {k: v for k, v in x.items() if k != "down"} for i, x in stage["actors"].items()}}
        after = stage_state.apply(scene, {"type": "arena_end", **done})
        check("the scene puts everyone where the fight left them", after["actors"]["aragorn"]["cell"] == [3, 3] and after["arena"] is None)
        check("the fallen lie where they fell", after["actors"]["goblin#1"].get("down") is True and not after["actors"]["aragorn"].get("down"))
        check("a faction at peace stays yellow; one still at war with the party is red", after["actors"]["qorlia"]["side"] == "neutral" and after["actors"]["mara-shop"]["side"] == "hostile")
        check("an actor that did not fight keeps its side", after["actors"]["dead-guard"]["side"] == "hostile" and after["actors"]["ilvuur"]["side"] == "ally")

    # The stage plays the party's friends against its enemies: out of reach, a companion walks toward the goblin, not toward the party.
    with tempfile.TemporaryDirectory() as tmp:
        c, stage = scene_fight(tmp)
        state = tracker.load_state(c)
        encounters.start(c, state, ["goblin"], None, rng=Fixed(10), stage=stage["actors"])
        arena_id, a, _ = board.build(c, state, [], stage)
        props = {(p["x"], p["y"]) for p in a["props"]}
        open_cells = sorted(((x, y) for y, row in enumerate(a["grid"]) for x, ch in enumerate(row) if ch == arena.FLOOR and (x, y) not in props), key=lambda c: (c[0] + c[1], c))
        near_party = [c for c in open_cells if all(arena.cheb(c, p) > 1 for p in props)][:12:3]  # four cells with room round them, in a corner
        far = open_cells[-1]
        a["units"].update({k: {"x": x, "y": y} for k, (x, y) in zip(("ilvuur", "aragorn", "legolas", "qorlia"), near_party)})
        a["units"]["goblin#1"] = {"x": far[0], "y": far[1]}
        a["bystanders"] = {}
        state["active_encounter"]["current_turn"] = "ilvuur"
        pl = foes.approach_plan(c, state, a, "ilvuur")
        check("a companion out of reach walks toward the goblin", pl is not None and pl["target"] == "goblin#1" and arena.cheb(pl["p"], far) < arena.cheb(near_party[0], far), str(pl))
        pl = foes.approach_plan(c, state, a, "qorlia")
        check("so does the yellow faction", pl is not None and pl["target"] == "goblin#1", str(pl))
        check("the goblin goes for the party, a friend of the party, or the faction at war with it",
              foes.approach_plan(c, state, a, "goblin#1")["target"] in ("aragorn", "legolas", "ilvuur", "qorlia"))
        check("the card's enemies are the party's enemies: a companion and a faction at peace are not on it",
              actions._enemies(state) == ["goblin#1"])
        state["active_encounter"]["current_turn"] = "aragorn"
        board.player_attack(c, state, a, "aragorn", "qorlia", confirm=True)
        state["active_encounter"]["monsters"]["qorlia"]["hp"]["current"] = 12  # the attack uses real dice; a kill (2 in 100) would take qorlia off the card
        check("once the faction is at war with the party it is on the card", set(actions._enemies(state)) == {"goblin#1", "qorlia"})

    # The fight ends: a player character who went down is not a corpse, and stands again in the next outcome. Units are never left on a chair.
    with tempfile.TemporaryDirectory() as tmp:
        c, stage = scene_fight(tmp)
        state = tracker.load_state(c)
        encounters.start(c, state, ["goblin"], None, rng=Fixed(10), stage=stage["actors"])
        arena_id, a, _ = board.build(c, state, [], stage)
        sheet = records.combatant(c, state, "legolas")
        sheet["hp"]["current"] = 0
        state["active_encounter"]["monsters"]["ilvuur"]["hp"]["current"] = 0
        done = board.outcome(c, state, a)
        check("a creature that is down is a corpse; a player character at 0 HP is not", done["down"] == ["ilvuur"], str(done["down"]))
        scene = {**stage_state.empty(), "scene": "hall", "actors": {i: dict(x) for i, x in stage["actors"].items()}}
        scene["actors"]["ilvuur"]["down"] = True
        after = stage_state.apply(scene, {"type": "arena_end", **done})
        state["active_encounter"]["monsters"]["ilvuur"]["hp"]["current"] = 5
        after2 = stage_state.apply(after, {"type": "arena_end", **board.outcome(c, state, a)})
        check("the next fight's end stands it up", "down" not in after2["actors"]["ilvuur"] and "down" in after["actors"]["ilvuur"])
        solid = next(p for p in a["room"]["props"] if not p.get("flat"))
        a["units"]["aragorn"] = {"x": solid["x"], "y": solid["y"]}
        done = board.outcome(c, state, a)
        landed = tuple(done["cells"]["aragorn"]["cell"])
        check("a unit that ended on a chair or a table stands on free floor beside it", landed != (solid["x"], solid["y"])
              and a["grid"][landed[1]][landed[0]] == arena.FLOOR and landed not in {(p["x"], p["y"]) for p in a["room"]["props"] if not p.get("flat")}, str(landed))

    # A fighter with no stat block the stage can find is named, not dropped silently.
    with tempfile.TemporaryDirectory() as tmp:
        c, stage = scene_fight(tmp)
        stage["actors"]["ghost-knight"] = {"side": "hostile", "cell": [1, 1]}
        real = encounters.api_get
        encounters.api_get = lambda path: (None, "not found", None)
        try:
            state = tracker.load_state(c)
            lines = encounters.start(c, state, [], None, rng=Fixed(10), stage=stage["actors"])
        finally:
            encounters.api_get = real
        check("an actor with no stat block is left out of the fight, and the DM is told which", "ghost-knight" not in state["active_encounter"]["participants"]
              and any("ghost-knight" in ln and "not in the fight" in ln for ln in lines), str(lines))

    # The end of a fight through the DM's command writes the event that the scene folds.
    import argparse
    import os

    from dnd_cli.commands import rules_cmd
    from stage import beat

    with tempfile.TemporaryDirectory() as tmp:
        c, stage = scene_fight(tmp)
        beat.append(c, [{"type": "scene", "location": "hall", "party": ["aragorn", "legolas"]}, {"type": "join", "actor": "ilvuur", "side": "ally"}])
        events = [{"type": "enter", "actor": "goblin#1", "side": "hostile"}]
        beat.append(c, events)
        live = stage_state.replay(beat.log_path(c))
        state = tracker.load_state(c)
        encounters.start(c, state, ["goblin"], None, rng=Fixed(10), stage=live["actors"])
        _, a, _ = board.build(c, state, [], {**live, "actors": {i: {**v, "cell": v.get("cell") or [2 + n, 3]} for n, (i, v) in enumerate(live["actors"].items())}})
        enc = state["active_encounter"]
        arena_id = arena.new_id(c)
        enc["arena"] = arena_id
        a["units"]["aragorn"] = {"x": 4, "y": 4}
        enc["monsters"]["goblin#1"]["hp"]["current"] = 0
        arena.save(c, arena_id, a)
        tracker.save_state(c, state)
        os.environ["DUNGEON_STAGE_LOG"] = str(beat.log_path(c))
        try:
            rules_cmd.execute_encounter(str(c), "end", argparse.Namespace(no_xp=True, resolved=None))
        finally:
            os.environ.pop("DUNGEON_STAGE_LOG", None)
        after = stage_state.replay(beat.log_path(c))
        check("`encounter end` writes where everyone stands and who fell, and a replay of the log shows it",
              after["arena"] is None and after["actors"]["aragorn"]["cell"] == [4, 4] and after["actors"]["goblin#1"].get("down") is True)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
