"""Checks for the visual stage: beat parsing and the event log.

Run from the repo root:  .venv/bin/python tests/test_stage.py

Plain asserts so no test runner is needed.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from stage import beat, state
from view.settings import build_dm_command

PASS = 0
FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}")


def raises(fn) -> bool:
    try:
        fn()
    except beat.BeatError:
        return True
    return False


def test_parse() -> None:
    print("beat.parse")
    events = beat.parse(
        "@scene chapel-of-ilmater\n"
        "@enter sister-gareth right\n"
        "@narrate Candle smoke hangs\n"
        "under the low beams.\n"
        "\n"
        "@say sister-gareth happy What brings you here?\n"
        "@say goblin#2 Give us the coin!\n"
        "@choices Talk | Fight | Leave\n"
        "@exit sister-gareth\n"
        "@clear\n"
    )
    types = [e["type"] for e in events]
    check("all lines become events", types == ["scene", "enter", "narrate", "say", "say", "choices", "exit", "clear"])
    check("continuation joins the previous text", events[2]["text"] == "Candle smoke hangs under the low beams.")
    check("emotion is read when given", events[3]["emotion"] == "happy" and events[3]["text"] == "What brings you here?")
    check("emotion defaults to neutral", events[4]["emotion"] == "neutral" and events[4]["actor"] == "goblin#2")
    check("choices split on |", events[5]["options"] == ["Talk", "Fight", "Leave"])
    check("enter keeps position", events[1]["position"] == "right")
    check("a bare first line is narration", beat.parse("Rain falls.")[0] == {"type": "narrate", "text": "Rain falls."})
    check("an emotion word alone is text, not emotion",
          beat.parse("@say toblen happy")[0]["text"] == "happy")


def test_parse_errors() -> None:
    print("beat.parse errors")
    check("empty beat", raises(lambda: beat.parse("  \n")))
    check("unknown command", raises(lambda: beat.parse("@dance toblen")))
    check("say without text", raises(lambda: beat.parse("@say toblen")))
    check("bad id", raises(lambda: beat.parse("@enter Sister Gareth")))
    check("bad position", raises(lambda: beat.parse("@enter toblen upstairs")))
    check("one choice only", raises(lambda: beat.parse("@choices Leave")))


def test_append() -> None:
    print("beat.append")
    with tempfile.TemporaryDirectory() as tmp:
        campaign_dir = Path(tmp)
        beat.append(campaign_dir, beat.parse("@narrate One."))
        beat.append(campaign_dir, beat.parse("@narrate Two.\n@narrate Three."))
        lines = [json.loads(line) for line in beat.log_path(campaign_dir).read_text().splitlines()]
        check("appends one line per event", [e["text"] for e in lines] == ["One.", "Two.", "Three."])
        check("events of one call share a beat id", lines[1]["beat"] == lines[2]["beat"])


def test_state() -> None:
    print("state.apply")
    s = state.empty()
    for e in beat.parse(
        "@scene chapel\n@enter gareth right\n@say sireth angry Who are you?\n@choices A | B"
    ):
        s = state.apply(s, e)
    check("scene is set", s["scene"] == "chapel")
    check("enter keeps the given position", s["actors"]["gareth"]["position"] == "right")
    check("a speaker not on stage is put on a free spot", s["actors"]["sireth"]["position"] == "left")
    check("the speaker's emotion is kept", s["actors"]["sireth"]["emotion"] == "angry")
    check("choices are open", s["choices"]["options"] == ["A", "B"])
    s = state.apply(s, {"type": "narrate", "text": "Later."})
    check("a new story line closes the choices", s["choices"] is None)
    s = state.apply(s, {"type": "scene", "location": "street"})
    check("a new scene clears the actors", s["actors"] == {})
    s = state.apply(s, {"type": "dm_status", "status": "idle", "dm_text": "Beat shown."})
    check("DM text goes to the DM log, not the story log",
          s["dm_log"] == ["Beat shown."] and all(l.get("text") != "Beat shown." for l in s["log"]))
    check("seq counts every event", s["seq"] == 7)


def test_initial_prompt() -> None:
    print("build_dm_command initial_prompt")
    cmd = build_dm_command({"agent_framework": "claude", "model": "haiku"}, Path("/g"), "sid", initial_prompt="Start it's on")
    check("claude takes the prompt as a quoted positional argument", cmd[2].endswith("'Start it'\"'\"'s on'"))
    cmd = build_dm_command({"agent_framework": "gemini", "model": ""}, Path("/g"), "sid", initial_prompt="Go")
    check("gemini takes the prompt with -i", "-i Go" in cmd[2])


def test_actors() -> None:
    print("lpc / actors")
    from stage import actors, lpc
    from stage.assets import LPC_DIR

    if not (LPC_DIR / "sheet_definitions").is_dir():
        print("  skip (LPC art not fetched; run uv run dungeon-os once)")
        return
    spec = actors.build("sireth", ["name=Sireth", "body=female", "skin=blue", "eyes=red", "elven", "robe:dark_gray"])
    check("build sets name and body", spec["name"] == "Sireth" and spec["body"] == "female")
    check("a known spec validates clean", lpc.validate(spec) == [])
    check("'_' in a color matches a space", dict((i.id, c) for i, c in lpc.resolve(spec)[1])["robe"] == "dark gray")
    frame = lpc.render(spec, "down")
    check("render gives one 64x64 frame with pixels", frame.size == (64, 64) and frame.getbbox() is not None)
    check("portrait is 36x36", lpc.portrait(spec, "angry").size == (36, 36))
    check("an item for another body only warns", lpc.validate({"body": "male", "items": ["robe"]}) != [])
    try:
        lpc.validate({"body": "female", "items": ["robe:neon"]})
        check("a bad color raises", False)
    except lpc.ActorError:
        check("a bad color raises", True)
    check("later item of a type wins", lpc.normalize_items(["robe:white", "hair_bob", "robe:black"]) == ["robe:black", "hair_bob"])
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        check("goblin#2 falls back to the goblin preset", actors.load(d, "goblin#2")["name"] == "Goblin")
        actors.save(d, "goblin", {"name": "Snik", "body": "teen", "items": []})
        check("a campaign actor file beats the preset", actors.load(d, "goblin#2")["name"] == "Snik")
        check("an unknown kind has no look", actors.load(d, "stranger") is None)
    bad = [k for k, p in actors.presets().items() if lpc.validate(p)]
    check(f"every preset validates without warnings {bad}", not bad)


if __name__ == "__main__":
    test_parse()
    test_parse_errors()
    test_append()
    test_state()
    test_initial_prompt()
    test_actors()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
