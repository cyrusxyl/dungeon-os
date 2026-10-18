"""A fight with every kind of actor, in a real browser: a green companion, a yellow faction, a red goblin, and a bystander that
takes no part until the player attacks it (after a confirmation).

Run from the repo root:  .venv/bin/python tests/visual_fight_teams.py [screenshot-dir]
(or `tests/run_all.py --visual`). Needs Google Chrome and a built web UI (`npm run build` in stage/web). It skips (exit 0) without Chrome.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import uvicorn  # noqa: E402
import visual_roll_window as v  # noqa: E402
import websockets  # noqa: E402

from dnd_cli.combat import encounters, tracker  # noqa: E402
from stage import actors, arena, beat, board, scenes, state as stage_state  # noqa: E402
from stage.server import create_app  # noqa: E402
from test_rules import GOBLIN, Fixed, campaign  # noqa: E402
from test_teams import fighter  # noqa: E402
from visual_stage_cast import CAST, show  # noqa: E402
from visual_walk import until  # noqa: E402

check, REPO = v.check, v.REPO
# The board canvas: `data-geom` is ox, oy, width, height. The ground centre of cell (x, y) is (ox + (x - y) * 32, oy + (x + y) * 16 + 16).
CLICK = """((x, y) => {
  const c = document.querySelector('canvas[aria-label^="The board"]'); const [ox, oy, w, h] = c.dataset.geom.split(',').map(Number);
  const r = c.getBoundingClientRect(); const px = ox + (x - y) * 32, py = oy + (x + y) * 16 + 16;
  c.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: r.left + px / w * r.width, clientY: r.top + py / h * r.height }));
})"""


def main() -> int:
    if not shutil.which("google-chrome"):
        print("skipped: Google Chrome is not installed")
        return 0
    if not (REPO / "stage" / "web" / "dist" / "index.html").exists():
        print("skipped: build the web UI first (npm run build in stage/web)")
        return 0
    encounters.api_get = lambda path: (dict(GOBLIN, index=path.split("/")[1]), None, None)
    tmp = Path(tempfile.mkdtemp(prefix="visual-"))
    c = campaign(tmp)
    for name in ("ilvuur", "qorlia"):
        (c / "world" / "npcs" / f"{name}.json").write_text(json.dumps(fighter(name)))
    (c / "world" / "npcs" / "mara-shop.json").write_text(json.dumps({"name": "Mara", "role": "shopkeeper", "personality": "Sells rope"}))
    scenes.save(c, "hall", {"template": "tavern", "slots": {}, "add": [], "mood": "day", "shape": "fixed"})
    for aid, kind in {"aragorn": "knight", "legolas": "bandit", "ilvuur": "priest", "qorlia": "noble", "goblin": "thug", "mara-shop": "wizard"}.items():
        actors.save(c, aid, actors.presets()[kind])
    shots = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    port, debug = v.free_port(), v.free_port()
    app = create_app(campaign_dir=c, dm_command=["sleep", "3600"])
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    chrome = subprocess.Popen(
        ["google-chrome", "--headless=new", f"--remote-debugging-port={debug}", "--no-sandbox", "--window-size=1500,950", "--hide-scrollbars",
         f"--user-data-dir={tmp / 'chrome'}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1.5)
        tabs = None
        for _ in range(50):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{debug}/json").read())
                break
            except OSError:
                time.sleep(0.2)
        tab = next(t for t in tabs if t["type"] == "page")

        async def run() -> None:
            async with websockets.connect(tab["webSocketDebuggerUrl"], max_size=None) as ws:
                page = v.Page(ws)
                if shots:
                    v.SHOTS = shots
                await page.call("Page.enable")
                await page.call("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
                await page.call("Page.navigate", url=f"http://127.0.0.1:{port}/")
                await asyncio.sleep(2.5)
                await page.click("Play here")
                await asyncio.sleep(1)
                await page.click("Play all free")
                await asyncio.sleep(1.2)
                beat.append(c, [{"type": "dm_status", "status": "idle"}])
                show(c, "@join ilvuur ally\n@scene hall\n@enter qorlia neutral\n@enter goblin#1 hostile\n@enter mara-shop\n"
                        + "".join(f"@walk {i} still\n" for i in ("ilvuur", "qorlia", "goblin#1", "mara-shop")))
                await asyncio.sleep(2.5)
                cast = {f["id"]: f for f in await page.eval(CAST)}
                check("the scene shows all six, a bystander among them with the yellow ring", len(cast) == 6 and cast["mara-shop"]["side"] == "bystander", str(list(cast)))
                await page.shot("teams-scene")

                print("the fight")
                state = tracker.load_state(c)
                stage = stage_state.replay(beat.log_path(c))
                encounters.start(c, state, [], None, rng=Fixed(20, 1, 1, 1, 1, 1), stage=stage["actors"])
                board.start(c, state, [], stage)
                state["active_encounter"]["current_turn"] = "aragorn"
                tracker.save_state(c, state)
                arena_id = state["active_encounter"]["arena"]
                a = arena.load(c, arena_id)
                by = a["bystanders"]["mara-shop"]
                held = {(u["x"], u["y"]) for u in a["units"].values()} | {(by["x"], by["y"])}
                reach = next((x, y) for x in range(by["x"] - 1, by["x"] + 2) for y in range(by["y"] - 1, by["y"] + 2)
                             if (x, y) not in held and 0 <= y < a["h"] and 0 <= x < a["w"] and a["grid"][y][x] == arena.FLOOR and (x, y) not in arena.blocked_cells(a))
                a["units"]["aragorn"] = {"x": reach[0], "y": reach[1]}  # next to the bystander, so a melee attack can be made
                arena.save(c, arena_id, a)
                check("everyone but the bystander is in the order", set(state["active_encounter"]["participants"]) == {"aragorn", "legolas", "ilvuur", "qorlia", "goblin#1"})
                beat.append(c, [{"type": "dm_status", "status": "busy"}])  # the party panel reads the fight again when the DM's status changes
                await asyncio.sleep(0.6)
                beat.append(c, [{"type": "arena", "arena": arena_id}, {"type": "dm_status", "status": "idle"}])
                await asyncio.sleep(3)
                await page.shot("teams-fight")
                board_up = await until(page, "Boolean(document.querySelector('canvas[aria-label^=\"The board\"]'))", 10)
                check("the board is up", bool(board_up))
                by = a["bystanders"]["mara-shop"]

                print("attacking the bystander asks first")
                await page.eval(f"({CLICK})({by['x']}, {by['y']})")
                asked = await until(page, "document.querySelector('[role=alertdialog]')?.textContent || ''", 8)
                await page.shot("teams-confirm")
                check("a click on the bystander asks: it says what the attack does", bool(asked) and "Mara" in asked and "bystander" in asked and "Attack anyway" in asked, str(asked))
                check("nothing started yet", "mara-shop" in arena.load(c, arena_id)["bystanders"])
                await page.click("Attack anyway")
                for _ in range(20):
                    if "mara-shop" in arena.load(c, arena_id)["units"]:
                        break
                    await asyncio.sleep(0.5)
                a = arena.load(c, arena_id)
                check("after the confirmation the bystander is a unit of the fight", "mara-shop" in a["units"] and "mara-shop" not in a["bystanders"])
                await asyncio.sleep(2)
                await page.shot("teams-after")

                print("the fight ends")
                a = arena.load(c, arena_id)
                fallen = "goblin#1"
                end = {"type": "arena_end", "cells": {i: {"cell": [u["x"], u["y"]], "facing": "down"} for i, u in a["units"].items()}, "down": [fallen], "sides": {"mara-shop": "hostile"}}
                beat.append(c, [end, {"type": "dm_status", "status": "idle"}])
                await asyncio.sleep(3)
                await page.shot("teams-after-fight")
                scene = {f["id"]: f for f in await page.eval(CAST)}
                check("the scene is back, everyone where the fight left them, the goblin lying where it fell", scene[fallen]["down"] is True and not scene["aragorn"]["down"]
                      and scene[fallen]["cell"] == [a["units"][fallen]["x"], a["units"][fallen]["y"]] and scene["mara-shop"]["side"] == "hostile")

        asyncio.run(run())
    finally:
        chrome.terminate()
        server.should_exit = True
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{v.PASS} passed, {v.FAIL} failed")
    return 1 if v.FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
