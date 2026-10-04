"""Checks for the world commands: clock, state set, travel time, quests, NPCs, factions.

Run from the repo root:  uv run python tests/test_world.py

Plain asserts on a temp copy of the committed example campaign: no network.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from dnd_cli import world
from dnd_cli.commands import show_cmd
from stage import maps
from test_rules import campaign

PASS = FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + cond, FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}")


def raises(fn) -> bool:
    try:
        fn()
    except world.WorldError:
        return True
    return False


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def test_time() -> None:
    print("time")
    for text, minutes in [("2 days", 2880), ("3 hours", 180), ("15 min", 15), ("30 minutes", 30), ("half a day", 720),
                          ("1 day, 4 hours", 1680), ("2d", 2880), ("3h", 180), ("45m", 45), ("a day", 1440),
                          ("an hour", 60), ("+2h", 120)]:
        check(f"duration {text!r} = {minutes}", world.parse_duration(text) == minutes)
    check("a bad duration is refused", raises(lambda: world.parse_duration("soon")))
    check("trailing junk is refused", raises(lambda: world.parse_duration("2 days of rain")))
    check("periods", [world.period(m) for m in (0, 299, 300, 420, 660, 840, 1020, 1200, 1439)]
          == ["Night", "Night", "Dawn", "Morning", "Midday", "Afternoon", "Evening", "Night", "Night"])
    s = {"game_time": "Day 1, Morning"}
    check("derived from a period word", world.get_clock(s) == {"day": 1, "minute": 480})
    check("derived from HH:MM PM", world.get_clock({"game_time": "Day 5, 10:30 PM"}) == {"day": 5, "minute": 1350})
    check("no day, no time: day 1, 08:00", world.get_clock({"game_time": "later"}) == {"day": 1, "minute": 480})
    check("advance rolls the day", world.set_time(s, "+1d") == "Time: Day 2, Morning" and s["clock"]["day"] == 2)
    check("set by clock", world.set_time(s, "Day 3, 18:00") == "Time: Day 3, Evening" and s["game_time"] == "Day 3, Evening")
    world.set_time(s, "+7h")
    check("advance past midnight", s["clock"] == {"day": 4, "minute": 60} and s["game_time"] == "Day 4, Night")
    check("a time without a day is refused", raises(lambda: world.set_time(s, "evening")))


def test_state_set(c: Path) -> None:
    print("state set")
    s = load(c / "state.json")
    line = world.state_set(s, ["weather=Heavy_rain", "party_status=Resting"])
    check("values set, _ is a space", s["weather"] == "Heavy rain" and s["party_status"] == "Resting" and "weather" in line)
    world.state_set(s, ["active_player_turn=none"])
    check("turn cleared", s["active_player_turn"] is None)
    check("other keys are refused", raises(lambda: world.state_set(s, ["quest_log=x"])))
    check("a token without = is refused", raises(lambda: world.state_set(s, ["weather"])))


def test_travel(c: Path) -> None:
    print("travel")
    m = {"name": "Coast", "places": {k: {"name": k.title(), "known": True, "at": [i, 0]} for i, k in enumerate("abcd")},
         "routes": [{"a": "a", "b": "b", "travel": "2 days"}, {"a": "b", "b": "c", "travel": "6 hours"},
                    {"a": "c", "b": "d", "travel": "a long way"}]}
    s = {"game_time": "Day 1, Morning"}
    check("first place: no travel", world.travel(s, m, "a") is None and s["place"] == "a")
    check("same place: no travel", world.travel(s, m, "a") is None)
    line = world.travel(s, m, "c")
    check("route legs are summed", line == "Time: Day 3, Afternoon (+2 days 6 hours of travel)" and s["place"] == "c")
    check("an unparseable leg costs nothing", world.travel(s, m, "d") is None and s["place"] == "d")
    check("a place on another map: no travel", world.travel(s, {"places": {"x": {}}, "routes": []}, "x") is None)
    # through the real beat path
    state = load(c / "state.json")
    state["place"] = "a"
    (c / "state.json").write_text(json.dumps(state))
    maps.save(c, "coast", m)
    out = show_cmd._set_location(c, m, "b")
    st = load(c / "state.json")
    check("show_cmd stores place and clock", out and out.startswith("Time:") and st["place"] == "b" and st["clock"]["day"] == 3
          and st["location"] == "B, Coast")


def test_quests(c: Path) -> None:
    print("quests")
    s = load(c / "state.json")
    world.quest_add(c, s, "rescue", "Rescue Sildar", "Goblins", ["Find hideout", "Free him"], "50gp")
    qf = lambda: load(c / "world" / "quests" / "rescue.json")  # noqa: E731
    entry = lambda: next(e for e in s["quest_log"] if e["id"] == "rescue")  # noqa: E731
    check("add writes both files", qf()["objectives"][1] == {"task": "Free him", "completed": False}
          and entry()["status"] == "active" and qf()["reward"] == "50gp")
    check("a second add is refused", raises(lambda: world.quest_add(c, s, "rescue", "x")))
    world.quest_progress(c, s, "rescue", "Found a trail")
    check("progress in both", entry()["progress"] == "Found a trail" and "Found a trail" in qf()["notes"])
    line = world.quest_done(c, s, "rescue", 1)
    check("objective done", qf()["objectives"][0]["completed"] and "1/2" in line and qf()["status"] == "active")
    check("a bad objective is refused", raises(lambda: world.quest_done(c, s, "rescue", 3)))
    world.quest_done(c, s, "rescue")
    check("quest completed in both", qf()["status"] == "completed" and entry()["status"] == "completed")
    world.quest_add(c, s, "second", "Second")
    world.quest_fail(c, s, "second")
    check("quest failed", next(e for e in s["quest_log"] if e["id"] == "second")["status"] == "failed")
    check("show: a line per quest", len(world.quest_lines(c, s)) == 3 and "(1/2)" in world.quest_lines(c, s)[1])
    check("an unknown quest is refused", raises(lambda: world.quest_fail(c, s, "nope")))


def test_npcs(c: Path) -> None:
    print("npcs")
    npc = lambda i: load(c / "world" / "npcs" / f"{i}.json")  # noqa: E731
    check("a new npc needs name and type", raises(lambda: world.npc_set(c, "mira", ["personality=Shy"])))
    world.npc_set(c, "mira", ["name=Mira", "type=humanoid", "armor_class=12", "challenge_rating=0.5", "hp.max=9",
                              "personality=Shy_and_kind"])
    n = npc("mira")
    check("created, numbers parse, _ is a space, dotted keys nest",
          n["armor_class"] == 12 and n["challenge_rating"] == 0.5 and n["hp"] == {"max": 9}
          and n["personality"] == "Shy and kind")
    check("invalid values are refused and nothing is written",
          raises(lambda: world.npc_set(c, "mira", ["type=wizard"])) and npc("mira")["type"] == "humanoid")
    check("an update keeps other fields", "updated" in world.npc_set(c, "mira", ["motivation=Safety"])
          and npc("mira")["name"] == "Mira")
    # attitude
    toblen = "toblen-stonehill"
    world.npc_attitude(c, toblen, "up")
    check("friendly up is allied", npc(toblen)["relationship_to_party"] == "allied")
    world.npc_attitude(c, toblen, "up")
    check("up stops at allied", npc(toblen)["relationship_to_party"] == "allied")
    world.npc_attitude(c, toblen, "down")
    world.npc_attitude(c, toblen, "down")
    world.npc_attitude(c, toblen, "down")
    check("down steps", npc(toblen)["relationship_to_party"] == "unfriendly")
    world.npc_attitude(c, toblen, "hostile")
    world.npc_attitude(c, toblen, "down")
    check("hostile is the floor", npc(toblen)["relationship_to_party"] == "hostile")
    world.npc_attitude(c, "mira", "up")
    check("a missing attitude counts as neutral", npc("mira")["relationship_to_party"] == "friendly")
    check("a bad move is refused", raises(lambda: world.npc_attitude(c, "mira", "sideways")))
    # note
    world.npc_note(c, "mira", "Helped the party")
    check("note has the next session number", npc("mira")["notes"] == "Session 1: Helped the party")
    world.npc_note(c, "mira", "Left town")
    check("notes accumulate", npc("mira")["notes"].endswith("\nSession 1: Left town"))
    (c / "canon.json").unlink()
    world.npc_note(c, "mira", "No canon")
    check("without canon there is no prefix", npc("mira")["notes"].endswith("\nNo canon"))


def test_faction(c: Path) -> None:
    print("faction")
    s = load(c / "state.json")
    check("faction +2", world.faction(s, "Thieves Guild", "+2") == "Faction thieves-guild: 2")
    check("faction -5", world.faction(s, "thieves-guild", "-5") == "Faction thieves-guild: -3"
          and s["faction_reputation"] == {"thieves-guild": -3})
    check("no change shows", world.faction(s, "harpers", None) == "Faction harpers: 0")
    check("a bad change is refused", raises(lambda: world.faction(s, "harpers", "lots")))


if __name__ == "__main__":
    test_time()
    with tempfile.TemporaryDirectory() as tmp:
        c = campaign(Path(tmp))
        test_state_set(c)
        test_travel(c)
        test_quests(c)
        test_npcs(c)
        test_faction(c)
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
