"""A fight starts in the room of the scene, with the party where it stood (isometric-view.md, Goal 4), at the same relative place (compact-set.md).

Run from the repo root:  .venv/bin/python tests/visual_scene_fight.py [screenshot-dir]
(or `tests/run_all.py --visual`). Needs Google Chrome and a built web UI (`npm run build` in stage/web).
It saves a scene, shows it, reads the cells of the party from the page, starts a fight on the board, and checks that every
character of the party stands on the cell it stood on (a seated one may have moved off its seat). It skips (exit 0) without Chrome.
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

from dnd_cli.combat import tracker  # noqa: E402
from stage import arena, beat, board, scenes, state as stage_state  # noqa: E402
from stage.cast import scale_cell as cast_cell  # noqa: E402
from stage.server import create_app  # noqa: E402
from test_rules import campaign, fight  # noqa: E402
from visual_stage_cast import CAST, show  # noqa: E402

check, REPO = v.check, v.REPO


def main() -> int:
    if not shutil.which("google-chrome"):
        print("skipped: Google Chrome is not installed")
        return 0
    if not (REPO / "stage" / "web" / "dist" / "index.html").exists():
        print("skipped: build the web UI first (npm run build in stage/web)")
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="visual-"))
    c = campaign(tmp)
    shape = sys.argv[2] if len(sys.argv) > 2 else None  # a second argument gives the scene a room shape: ... cross
    scenes.save(c, "hall", {"template": "tavern", "slots": {}, "add": [], "mood": "day", **({"shape": shape, "seed": 4} if shape else {})})
    state = fight(c)
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
                if len(sys.argv) > 1:
                    v.SHOTS = Path(sys.argv[1])
                await page.call("Page.enable")
                await page.call("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
                await page.call("Page.navigate", url=f"http://127.0.0.1:{port}/")
                await asyncio.sleep(2.5)
                await page.click("Play here")
                await asyncio.sleep(1)
                await page.click("Play all free")
                await asyncio.sleep(1.2)
                beat.append(c, [{"type": "dm_status", "status": "idle"}])
                show(c, "@scene hall\n@enter goblin#1 hostile\n@enter goblin#2 hostile\n@walk goblin#1 still\n@walk goblin#2 still\n@narrate Steel is drawn.")  # the cells are read from the page, so no one walks
                await asyncio.sleep(2.5)
                await page.shot("scene-before")
                cast = {f["id"]: tuple(f["cell"]) for f in await page.eval(CAST)}
                check("the scene shows the party and the goblins", {"aragorn", "legolas", "goblin#1", "goblin#2"} <= set(cast), str(cast))

                stage = stage_state.replay(beat.log_path(c))
                board.start(c, state, [], stage)
                tracker.save_state(c, state)
                arena_id = state["active_encounter"]["arena"]
                a = arena.load(c, arena_id)
                small, full = scenes.room(a["scene_spec"])["grid"], a["grid"]
                want = {who: cast_cell(c_, small, full) for who, c_ in cast.items()}  # the story set is smaller: each one keeps the relative place
                near = lambda who: max(abs(board.pos(a, who)[0] - want[who][0]), abs(board.pos(a, who)[1] - want[who][1])) <= 3  # noqa: E731
                moved = [who for who in ("aragorn", "legolas") if not near(who)]
                check("every character stands at the same relative place as in the scene", not moved, f"{moved}: {[(board.pos(a, w), want[w]) for w in moved]}")
                foes = [who for who in ("goblin#1", "goblin#2") if who in a["units"] and not near(who)]
                check("and so does each creature the scene shows", not foes, str(foes))
                check("the arena is the room of the scene", a["spec"]["shape"] == "scene" and a["grid"] == scenes.room(a["scene_spec"], full=True)["grid"])

                beat.append(c, [{"type": "arena", "arena": arena_id}, {"type": "dm_status", "status": "idle"}])
                await asyncio.sleep(3)
                await page.shot("scene-fight")
                canvas = "document.querySelector('canvas[aria-label^=\"The board\"]')"
                size = await page.eval(f"[{canvas}.width, {canvas}.height]")
                check("the board draws the scene's room", size == [((a["w"] + a["h"]) * 32 + 16) * 2, (118 + (a["w"] + a["h"]) * 16 + 36) * 2], str(size))

        asyncio.run(run())
    finally:
        chrome.terminate()
        server.should_exit = True
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{v.PASS} passed, {v.FAIL} failed")
    return 1 if v.FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
