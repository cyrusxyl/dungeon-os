"""Checks for walking in a scene on the stage server: a player's order (seat, way), the tick (state, not log, not seq), the small
`cells` message, and the file that lets a fight start where the actors stand.

Run from the repo root:  .venv/bin/python tests/test_scene_walk.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from stage import arena, beat, scenes, state as stage_state  # noqa: E402
from stage import server  # noqa: E402
from stage.server import create_app  # noqa: E402
from tests.test_rules import campaign  # noqa: E402
from tests.test_stage import HOST_DEVICE, api  # noqa: E402

PASS = FAIL = 0
OTHER = "other-device-00000000"


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}{'' if cond or not detail else f'  ({detail})'}")


class Client:
    """A stage socket that keeps what it is sent."""

    def __init__(self):
        self.got: list[dict] = []

    async def send_json(self, msg):
        self.got.append(msg)


async def main() -> None:
    import view.settings as saved_settings

    saved_settings.SETTINGS_PATH = Path(tempfile.mkdtemp()) / "settings.json"
    tmp = Path(tempfile.mkdtemp())
    c = campaign(tmp)
    scenes.save(c, "hall", {"template": "tavern", "slots": {}, "add": [], "mood": "day", "shape": "fixed"})
    beat.append(c, [{"type": "scene", "location": "hall", "party": ["aragorn", "legolas"]}, {"type": "enter", "actor": "gareth"}])
    app = create_app(None)
    stage = await app.state.table.start(c, ["cat"])
    stage.seats.claim(HOST_DEVICE, "aragorn", "Alex")
    stage.seats.ensure_host(HOST_DEVICE)
    stage.state["dm"] = {"status": "idle"}
    actors = lambda: stage.state["actors"]  # noqa: E731
    check("the party and an NPC have cells at the start", all("cell" in a for a in actors().values()) and len(actors()) == 3)
    start = tuple(actors()["aragorn"]["cell"])
    g = stage.ground_of("hall")
    others = {tuple(a["cell"]) for i, a in actors().items() if i != "aragorn"}
    goal = next(cell for cell in reversed(g.floor) if cell not in others and len(__import__("stage.walk", fromlist=["x"]).find_path(g, start, cell, others) or []) >= 4)

    # The order.
    status, r = await api(app, "POST", "/api/scene/walk", {"who": "aragorn", "to": list(goal)})
    check("a player sends their character to a cell", status == 200 and r["steps"] >= 4, str(r))
    status, r = await api(app, "POST", "/api/scene/walk", {"who": "aragorn", "to": list(goal)}, device=OTHER)
    check("a device that does not play the character is refused", status == 403)
    status, _ = await api(app, "POST", "/api/scene/walk", {"who": "legolas", "to": list(goal)})
    check("a character the device does not play is refused", status == 403)
    status, r = await api(app, "POST", "/api/scene/walk", {"who": "aragorn", "to": [0, 0]})
    check("a wall cell has no way", status == 400 and "way" in r["error"], str(r))
    status, _ = await api(app, "POST", "/api/scene/walk", {"who": "aragorn", "to": "x"})
    check("a bad target is refused", status == 400)
    status, _ = await api(app, "POST", "/api/scene/walk", {"who": "nobody", "to": [3, 3]})
    check("an unknown character is 404", status == 404)
    status, r = await api(app, "POST", "/api/scene/walk", {"who": "aragorn", "to": list(others)[0]})
    check("a cell someone stands on is refused", status == 400)

    # The tick: steps go in the state, the small message goes out, the log and the seq do not change.
    client = Client()
    stage.event_clients.add(client)
    seq, log_size = stage.state["seq"], stage.log_path.stat().st_size
    await api(app, "POST", "/api/scene/walk", {"who": "aragorn", "to": list(goal)})
    client.got.clear()  # the order itself sends a snapshot (a character that stood up must lose its seat in every browser); the steps do not
    now = time.time()
    for _ in range(80):
        moves = stage.walk_tick(now)
        if moves:
            await stage.broadcast_cells(moves)
        now += 0.2
        if tuple(actors()["aragorn"]["cell"]) == goal:
            break
    check("the character walks to the cell", tuple(actors()["aragorn"]["cell"]) == goal)
    check("the steps went out as small `cells` messages, not snapshots", client.got and all(m["kind"] == "cells" and m["scene"] == "hall" for m in client.got))
    check("walking changes neither the seq nor the log", stage.state["seq"] == seq and stage.log_path.stat().st_size == log_size)
    check("the party member left, the other stayed", tuple(actors()["legolas"]["cell"]) != goal)

    # Nothing walks in a fight, or with no one watching.
    stage.state["arena"] = "a1"
    check("no one walks in a fight", stage.walk_tick(now + 50) == {} and stage.walk_tick(now + 60) == {})
    stage.state["arena"] = None
    stage.event_clients.discard(client)
    check("no one walks when no one watches", stage.walk_tick(now + 70) == {})
    stage.event_clients.add(client)

    # The file for a fight: where the actors stand, not where they were placed.
    stage.save_cells()
    replayed = stage_state.replay(stage.log_path)
    check("a replay of the log with the file puts the actors where they walked", tuple(replayed["actors"]["aragorn"]["cell"]) == goal)
    src = arena.source_of(c, {"scene": "hall", "actors": replayed["actors"]}, {})
    check("a fight starts from there", next(m for m in src["cast"] if m["id"] == "aragorn")["cell"] == list(goal))
    elsewhere = {"scene": "elsewhere", "actors": {"aragorn": {"cell": [1, 1], "facing": "down"}}}
    check("the file of another scene is ignored", stage_state.with_cells(elsewhere, stage.log_path)["actors"]["aragorn"]["cell"] == [1, 1])

    # A restart: the actors come back where they had walked.
    stage2 = await app.state.table.start(c, ["cat"])
    check("a restart keeps the walked cell", tuple(stage2.state["actors"]["aragorn"]["cell"]) == goal)

    st = stage2
    st.event_clients.add(Client())
    g = st.ground_of("hall")
    # Walkers keep to the ground the placer allows: after a minute of wandering and patrolling a new beat places no one again.
    beat.append(c, [{"type": "walk", "actor": "gareth", "walk": "patrol"}, {"type": "walk", "actor": "legolas", "walk": "wander"}])
    st.fold(st.read_new_events())
    solid = {(p["x"], p["y"]) for p in st.room_of("hall")["props"] if not p.get("flat")}
    on_bad = False
    places = lambda: sum('"place"' in line for line in st.log_path.read_text().splitlines())  # noqa: E731
    before = places()
    t = time.time()
    for _ in range(400):
        st.walk_tick(t)
        t += 0.15
        on_bad |= any(tuple(a["cell"]) in solid or tuple(a["cell"]) in g.blocked for a in st.state["actors"].values())
    beat.append(c, [{"type": "narrate", "text": "Time passes."}])
    st.fold(st.read_new_events())
    st.settle()
    check("no walker stands on a prop or a wall, and a new beat places no one again", not on_bad and places() == before)

    # The look of the room changes under the walkers: no step goes into the new walls.
    scenes.save(c, "hall", {"template": "tavern", "slots": {}, "add": [], "mood": "day", "shape": "h", "seed": 2})
    new_ground = st.ground_of("hall")
    st.settle()
    check("a changed room has other ground", new_ground is not g)
    bad = False
    for _ in range(300):
        st.walk_tick(t)
        t += 0.15
        bad |= any(tuple(a["cell"]) in new_ground.blocked for a in st.state["actors"].values())
    check("after the look changes, no step lands in a wall of the new room", not bad)

    # A character seated on a prop stands up when its player sends it walking, and stays up through a restart.
    scenes.save(c, "court", {"template": "throne_room", "slots": {}, "add": [], "mood": "day", "shape": "fixed"})
    beat.append(c, [{"type": "scene", "location": "court", "party": ["aragorn", "legolas"]}, {"type": "enter", "actor": "aragorn", "on": "back_center"}])
    st.fold(st.read_new_events())
    st.settle()
    seat = tuple(st.state["actors"]["aragorn"]["cell"])
    check("a character is seated on the throne", st.state["actors"]["aragorn"].get("on") == "back_center")
    g2 = st.ground_of("court")
    goal2 = next(cell for cell in reversed(g2.floor) if cell not in {tuple(a["cell"]) for a in st.state["actors"].values()})
    st.seats.claim(HOST_DEVICE, "aragorn", "Alex")  # a restarted stage has no seats of its own
    st.seats.ensure_host(HOST_DEVICE)
    status, r = await api(app, "POST", "/api/scene/walk", {"who": "aragorn", "to": list(goal2)})
    stood = st.state["actors"]["aragorn"]
    check("the order stands them up: no seat, a floor cell beside it, and the walk begins", status == 200 and "on" not in stood and tuple(stood["cell"]) in g2.floor
          and max(abs(stood["cell"][0] - seat[0]), abs(stood["cell"][1] - seat[1])) <= 2, str(stood))
    st2 = await app.state.table.start(c, ["cat"])
    check("a restart keeps them standing", "on" not in st2.state["actors"]["aragorn"] and tuple(st2.state["actors"]["aragorn"]["cell"]) in g2.floor)

    await app.state.table.stop()
    print(f"\n{PASS} passed, {FAIL} failed")


if __name__ == "__main__":
    server.BOARD_PACE = 0
    asyncio.run(main())
    raise SystemExit(1 if FAIL else 0)
