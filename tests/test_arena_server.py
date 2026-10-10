"""Checks for the stage routes of a fight on a board: the view, a move, an attack, a reaction answer.

Run from the repo root:  .venv/bin/python tests/test_arena_server.py

Plain asserts so no test runner is needed.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dnd_cli import combat  # noqa: E402
from stage import arena, board  # noqa: E402
from stage import server  # noqa: E402
from stage.server import create_app  # noqa: E402
from tests.test_arena import fight_with_boss  # noqa: E402
from tests.test_stage import HOST_DEVICE, api, call  # noqa: E402

PASS = FAIL = 0
OTHER = "other-device-00000000"


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}{'' if cond or not detail else f'  ({detail})'}")


def prepare(tmp: Path):
    """A fight on a board in a campaign copy: the arena on disk, the state saved."""
    c, state = fight_with_boss(tmp)
    board.start(c, state, ["layout=open", "size=small", "seed=3"], {})
    combat.save_state(c, state)
    return c, state


async def routes(c: Path, state: dict) -> None:
    import view.settings as saved_settings
    saved_settings.SETTINGS_PATH = Path(tempfile.mkdtemp()) / "settings.json"  # never the real settings of this machine
    server.BOARD_PACE = 0
    app = create_app(None)
    stage = await app.state.table.start(c, ["cat"])
    for who in ("aragorn", "legolas"):
        stage.seats.claim(HOST_DEVICE, who, "Alex")
    stage.state["dm"] = {"status": "idle"}
    arena_id = state["active_encounter"]["arena"]
    stage.state["arena"] = arena_id  # the arena event, as the stage log would have folded it
    stage.seats.ensure_host(HOST_DEVICE)

    status, view = await api(app, "GET", f"/api/arena/{arena_id}")
    check("the view has the grid, the units and the turn", status == 200 and view["w"] == 12 and len(view["units"]) == 5 and view["current"] == "aragorn")
    foe = next(u for u in view["units"] if u["id"] == "goblin#1")
    check("a creature shows a band, never numbers; a player character shows HP",
          "hp" not in foe and foe["health"] == "unhurt" and next(u for u in view["units"] if u["id"] == "aragorn")["hp"]["max"] > 0)
    check("the view lists where the current character can walk", view["walk"] and view["feet_left"] == 30)
    check("a bad arena id is a 404", (await api(app, "GET", "/api/arena/nope"))[0] == 404)

    me = view["units"][0]
    target = next(c for c in view["walk"] if abs(c[0] - me["x"]) <= 1 and abs(c[1] - me["y"]) <= 1 and tuple(c) != (me["x"], me["y"]))
    status, r = await api(app, "POST", "/api/arena/move", {"who": "aragorn", "to": target})
    check("a player moves their character on their turn", status == 200 and r["steps"] == [target] and r["pending"] is None)
    status, view2 = await api(app, "GET", f"/api/arena/{arena_id}")
    check("the view shows the new place and fewer feet", next(u for u in view2["units"] if u["id"] == "aragorn")["x"] == target[0] and view2["feet_left"] == 25)
    check("the stage tells browsers to fetch again", stage.state["versions"].get(f"arena:{arena_id}", 0) > 0)
    status, r = await api(app, "POST", "/api/arena/move", {"who": "legolas", "to": [1, 1]})
    check("a move out of turn is refused", status == 400 and "turn" in r["error"])
    status, r = await api(app, "POST", "/api/arena/move", {"who": "aragorn", "to": [0, 0]})
    check("a wall cell is refused", status == 400)
    status, r = await api(app, "POST", "/api/arena/move", {"who": "aragorn", "to": "x"})
    check("a bad target is refused", status == 400)
    status, r = await api(app, "POST", "/api/arena/move", {"who": "aragorn", "to": target}, device=OTHER)
    check("a device that does not play the character is refused", status == 403)
    stage.state["dm"] = {"status": "busy"}
    status, r = await api(app, "POST", "/api/arena/move", {"who": "aragorn", "to": [3, 3]})
    check("a busy DM refuses a move", status == 409)
    stage.state["dm"] = {"status": "idle"}

    # an attack: put a goblin next to aragorn on disk
    st = combat.load_state(c)
    a = arena.load(c, arena_id)
    ax, ay = board.pos(a, "aragorn")
    free = next(cell for cell in ((ax + 1, ay), (ax + 1, ay + 1), (ax, ay + 1), (ax - 1, ay)) if cell not in arena.blocked_cells(a))
    a["units"]["goblin#1"] = {"x": free[0], "y": free[1]}
    arena.save(c, arena_id, a)
    status, r = await api(app, "POST", "/api/arena/attack", {"who": "aragorn", "target": "goblin#2", "weapon": "longsword"})
    check("an attack on a target out of reach is refused with the distance", status == 400 and "ft away" in r["error"])
    status, r = await api(app, "POST", "/api/arena/attack", {"who": "aragorn", "target": "goblin#1"})
    check("a click on a creature picks the weapon that reaches it", board.default_weapon(c, st, a, "aragorn", "goblin#2") == "Longbow")
    check("an attack in reach is made", status == 200 and any("goblin#1" in ln for ln in r["lines"]))
    status, r = await api(app, "POST", "/api/arena/attack", {"who": "legolas", "target": "goblin#1"})
    check("an attack out of turn is refused", status == 400 and "turn" in r["error"])
    status, r = await api(app, "POST", "/api/arena/attack", {"who": "aragorn", "target": "nobody"})
    check("an unknown target is refused", status == 400)

    # a reaction question: legolas is asked
    a = arena.load(c, arena_id)
    a["pending"] = {"type": "react", "who": "legolas", "against": "goblin#1", "path": [[a["units"]["goblin#1"]["x"], a["units"]["goblin#1"]["y"]]],
                    "asked_at": time.time()}
    arena.save(c, arena_id, a)
    status, view3 = await api(app, "GET", f"/api/arena/{arena_id}")
    check("the view shows who is asked", view3["pending"]["who"] == "legolas" and view3["pending"]["against"] == "goblin#1" and view3["walk"] == [], str(view3["pending"]))
    status, r = await api(app, "POST", "/api/arena/move", {"who": "aragorn", "to": target})
    check("nobody walks while a question waits", status == 400)
    # the time is up: nobody answered, so there is no reaction attack
    a = arena.load(c, arena_id)
    a["pending"]["asked_at"] = time.time() - 30
    arena.save(c, arena_id, a)
    before = combat.load_state(c)["active_encounter"].get("resources", {}).get("legolas", {}).get("reaction")
    step = await asyncio.to_thread(stage.board_step)
    check("an unanswered question times out: no attack, the reaction is spent, the question is gone",
          arena.load(c, arena_id)["pending"] is None and step["kind"] == "turn" and combat.turn_used(combat.load_state(c), "legolas")["reaction"] and not before)
    a = arena.load(c, arena_id)
    a["pending"] = {"type": "react", "who": "legolas", "against": "goblin#1", "path": [], "asked_at": time.time()}
    arena.save(c, arena_id, a)
    status, r = await api(app, "POST", "/api/arena/react", {"take": False}, device=OTHER)
    check("only the player who is asked may answer", status == 403)
    status, r = await api(app, "POST", "/api/arena/react", {"take": False})
    check("the answer clears the question", status == 200 and arena.load(c, arena_id)["pending"] is None)
    status, r = await api(app, "POST", "/api/arena/react", {"take": True})
    check("an answer with no question is refused", status == 400)

    # the hand: abilities for the character, an action from it, a preview of an area
    state0 = combat.load_state(c)
    state0["active_encounter"]["resources"]["aragorn"] = {}
    state0["active_encounter"].setdefault("conditions", {}).pop("aragorn", None)
    combat.save_state(c, state0)
    status, h = await api(app, "GET", "/api/arena/hand?who=aragorn")
    names = {x["id"] for x in h["abilities"]} if status == 200 else set()
    check("the hand lists the weapons, the common actions and the features of a character",
          status == 200 and {"attack:Longsword", "dash", "shove", "feature:Second Wind"} <= names and h["turn"] == {"action": False, "bonus": False, "reaction": False} and h["current"] == "aragorn", str(h)[:200])
    check("a creature's AC is never in the hand", '"ac"' not in json.dumps(h).lower())
    status, r = await api(app, "GET", "/api/arena/hand?who=aragorn", device=OTHER)
    check("only the player of the character gets the hand", status == 403)
    check("an unknown character has no hand", (await api(app, "GET", "/api/arena/hand?who=nobody"))[0] == 404)
    status, r = await api(app, "POST", "/api/arena/act", {"who": "aragorn", "ability": "dash"})
    check("an ability of the hand is done from the stage", status == 200 and combat.has_condition(combat.load_state(c), "aragorn", "dashing") and r["lines"])
    status, r = await api(app, "POST", "/api/arena/act", {"who": "aragorn", "ability": "dash"})
    check("an ability that is off says why", status == 400 and "action is used" in r["error"])
    status, r = await api(app, "POST", "/api/arena/act", {"who": "legolas", "ability": "dash"})
    check("an ability out of turn is refused", status == 400 and "turn" in r["error"])
    status, r = await api(app, "POST", "/api/arena/preview", {"who": "aragorn", "ability": "dash", "aim": [3, 3]})
    check("a preview of an ability with no area is refused", status == 400)
    status, r = await api(app, "POST", "/api/arena/preview", {"who": "aragorn", "ability": "dash", "aim": "x"})
    check("a bad aim is refused", status == 400)

    # settings: only the host changes them; a fight's own values give way to the host's
    status, r = await api(app, "POST", "/api/combat/settings", {"reaction_seconds": 20}, device=OTHER)
    check("only the host changes the combat settings", status == 403)
    status, r = await api(app, "POST", "/api/combat/settings", {"reaction_seconds": 99})
    check("a bad value is refused", status == 400, str(r))
    status, r = await api(app, "POST", "/api/combat/settings", {"reaction_seconds": 20, "round_summary": False})
    check("the host's values apply at once", status == 200 and stage.combat == {"reaction_seconds": 20, "round_summary": False}
          and stage.snapshot(HOST_DEVICE)["state"]["combat_settings"]["reaction_seconds"] == 20, f"{status} {r}")
    status, view4 = await api(app, "GET", f"/api/arena/{arena_id}")
    check("the board view carries them", view4["settings"] == {"reaction_seconds": 20, "round_summary": False})
    await api(app, "POST", "/api/combat/settings", {"reaction_seconds": 10, "round_summary": True})

    # light: a creature out of sight is not in the board view or the turn bar
    from dnd_cli import character
    arena_data = arena.load(c, arena_id)
    sheet = character.load(c, "legolas")
    saved_hp = sheet["hp"]["current"]
    sheet["hp"]["current"] = 0
    character.save(c, "legolas", sheet)
    arena_data["spec"]["light"] = "dark"
    arena_data["seen"] = ["0" * arena_data["w"] for _ in range(arena_data["h"])]
    ax, ay = board.pos(arena_data, "aragorn")
    arena_data["units"]["goblin#2"] = {"x": min(arena_data["w"] - 2, ax + 9), "y": ay}
    arena.save(c, arena_id, arena_data)
    status, dark_view = await api(app, "GET", f"/api/arena/{arena_id}")
    check("in the dark the board view has no creature out of sight", "goblin#2" not in json.dumps(dark_view) and dark_view["visible"] is not None)
    status, party_view = await api(app, "GET", "/api/party")
    check("and the turn bar shows it as Unseen", any(o["name"] == "Unseen" for o in party_view["combat"]["order"]) and "goblin#2" not in json.dumps(party_view["combat"]))
    status, r = await api(app, "POST", "/api/arena/attack", {"who": "aragorn", "target": "goblin#2", "weapon": "longbow"})
    check("a creature out of sight cannot be attacked", status == 400 and "cannot see" in r["error"])
    arena_data["spec"]["light"] = "lit"
    arena.save(c, arena_id, arena_data)
    sheet["hp"]["current"] = saved_hp
    character.save(c, "legolas", sheet)

    # the card's actions and End turn on a board: the board decides, the DM is not called
    sent = []

    async def fake(text):
        sent.append(text)
    stage.submit = fake
    status, r = await api(app, "POST", "/api/action", {"who": "aragorn", "action": "attack", "target": "goblin#2", "weapon": "Longsword"})
    check("an attack from the card follows the board's rules", status == 400 and "ft away" in r["error"])
    status, r = await api(app, "POST", "/api/action", {"who": "aragorn", "action": "shove", "target": "goblin#2"})
    check("an action the board does not run yet says so", status == 400 and "board" in r["error"], str(r))
    status, r = await api(app, "POST", "/api/action", {"who": "aragorn", "action": "feature:Second Wind"})
    check("a class feature from the card works and is not sent to the DM", status == 200 and not sent and r["lines"])

    # improvise: the DM hears the words and a suggested ruling
    status, r = await api(app, "POST", "/api/arena/improvise", {"who": "aragorn", "text": "I throw a bottle"})
    check("an improvised action with the action spent is refused", status == 400 and "action is used" in r["error"] and not sent, str(r))
    state0 = combat.load_state(c)
    state0["active_encounter"]["resources"]["aragorn"] = {}
    combat.save_state(c, state0)
    status, r = await api(app, "POST", "/api/arena/improvise", {"who": "aragorn", "text": "  "})
    check("empty words are refused", status == 400)
    status, r = await api(app, "POST", "/api/arena/improvise", {"who": "legolas", "text": "I throw a bottle"})
    check("out of turn is refused", status == 400 and "turn" in r["error"])
    status, r = await api(app, "POST", "/api/arena/improvise", {"who": "aragorn", "text": "I throw a bottle"}, device=OTHER)
    check("only the player of the character improvises", status == 403)
    status, r = await api(app, "POST", "/api/arena/improvise", {"who": "aragorn", "text": "I throw a bottle in the goblin's face"})
    check("the DM hears the words and the suggested ruling", status == 200 and len(sent) == 1 and "improvises" in sent[0] and "Suggested ruling" in sent[0] and "1d4" in sent[0], str(sent))
    sent.clear()
    state0 = combat.load_state(c)
    state0["active_encounter"]["resources"]["aragorn"] = {}
    combat.save_state(c, state0)
    status, r = await api(app, "POST", "/api/end-turn", {"who": "aragorn"})
    check("End turn moves the tracker and does not call the DM", status == 200 and not sent and combat.load_state(c)["active_encounter"]["current_turn"] == "legolas")
    await api(app, "POST", "/api/end-turn", {"who": "legolas"})
    check("the turn is a goblin's now", combat.load_state(c)["active_encounter"]["current_turn"] in ("goblin#1", "goblin#2"))
    stage.pump_due = True  # an event of the stage wakes the pump in play
    await stage.pump_board()
    now = combat.load_state(c)["active_encounter"]
    check("the pump played both goblins and stopped at the creature the DM plays, with a prompt",
          now["current_turn"] == "boss" and len(sent) == 1 and "[combat]" in sent[0] and "(boss)" in sent[0])
    check("the goblins' turns used the board (they moved)", now["resources"].get("goblin#1", {}).get("moved", 0) > 0 or now["resources"].get("goblin#2", {}).get("moved", 0) > 0
          or any(x for x in stage.state["feed"]))
    stage.state["dm"] = {"status": "busy"}
    stage.pump_due = True  # an event of the stage wakes the pump in play
    await stage.pump_board()
    check("a busy DM holds the pump", combat.load_state(c)["active_encounter"]["current_turn"] == "boss")
    stage.state["dm"] = {"status": "idle"}
    stage.pump_due = True  # an event of the stage wakes the pump in play
    await stage.pump_board()
    now = combat.load_state(c)["active_encounter"]
    check("when the DM is idle and has not ended its creature's turn, the stage ends it", now["current_turn"] == "aragorn" and now["round"] == 2)
    check("then the DM hears the round once, in one line", len(sent) == 2 and "Round 1 is over" in sent[1])
    st = combat.load_state(c)
    for foe in ("goblin#1", "goblin#2", "boss"):
        st["active_encounter"]["monsters"][foe]["hp"]["current"] = 0
    st["active_encounter"]["current_turn"] = "goblin#1"
    combat.save_state(c, st)
    stage.pump_due = True  # an event of the stage wakes the pump in play
    await stage.pump_board()
    check("with every creature down, the DM is told once to end the fight", len(sent) == 3 and "encounter end" in sent[2])
    stage.pump_due = True  # an event of the stage wakes the pump in play
    await stage.pump_board()
    check("and is not told again", len(sent) == 3)

    status, kind, body = await call(app, "GET", f"/asset/arena/{arena_id}.png")
    check("the tile atlas of the arena is a PNG", status == 200 and body[:4] == b"\x89PNG" and kind == "image/png")
    status, kind, body = await call(app, "GET", "/asset/prop/barrel.png")
    check("a prop is a PNG", status == 200 and body[:4] == b"\x89PNG")
    check("an unknown prop is a 404", (await call(app, "GET", "/asset/prop/dragon.png"))[0] == 404)
    check("an unknown arena atlas is a 404", (await call(app, "GET", "/asset/arena/none.png"))[0] == 404)
    await app.state.table.stop()


def test_routes() -> None:
    print("arena: stage routes")
    with tempfile.TemporaryDirectory() as tmp:
        c, state = prepare(Path(tmp))
        asyncio.run(routes(c, state))


if __name__ == "__main__":
    test_routes()
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
