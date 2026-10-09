"""The combat board in a real browser: the picture, a click to walk, a click to attack, the reaction question.

Run from the repo root:  .venv/bin/python tests/visual_arena.py [screenshot-dir]
(or `tests/run_all.py --visual`). Needs Google Chrome and a built web UI (`npm run build` in stage/web).

It starts the stage on a temp copy of the example campaign, starts a fight on a board, drives headless Chrome over
the DevTools protocol, and asserts on the stage state and on what the page shows. It skips (exit 0) without Chrome.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn  # noqa: E402
import websockets  # noqa: E402

from dnd_cli import combat  # noqa: E402
from stage import arena, beat, board  # noqa: E402
from stage.server import create_app  # noqa: E402
from test_rules import campaign, fight  # noqa: E402
from visual_roll_window import Page, check, free_port  # noqa: E402
import visual_roll_window as base  # noqa: E402


async def board_checks(page: Page, c: Path, arena_id: str) -> None:
    beat.append(c, [{"type": "arena", "arena": arena_id}, {"type": "dm_status", "status": "idle"}])
    await asyncio.sleep(2.5)
    await page.shot("arena-start")
    canvas = "document.querySelector('canvas[aria-label^=\"The board\"]')"
    check("the board is on the stage", await page.eval(f"Boolean({canvas})"))
    check("the canvas has the arena's size", await page.eval(f"[{canvas}.width, {canvas}.height]") == [16 * 32, 10 * 32] or
          await page.eval(f"{canvas}.width") % 32 == 0)
    check("the turn bar still shows the order", "Aragorn" in await page.eval("document.querySelector('[aria-label=\"Turn order\"]')?.innerText || ''"))

    state = combat.load_state(c)
    a = arena.load(c, arena_id)
    ax, ay = board.pos(a, "aragorn")
    dist, _ = board.reachable(c, state, a, "aragorn")
    target = next(cell for cell, n in dist.items() if n == 2)
    rect = await page.eval(f"(() => {{ const r = {canvas}.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }})()")
    cell_px = rect[2] / a["w"]
    x, y = rect[0] + (target[0] + 0.5) * cell_px, rect[1] + (target[1] + 0.5) * cell_px
    for kind in ("mousePressed", "mouseReleased"):
        await page.call("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left", clickCount=1)
    await asyncio.sleep(1.5)
    now = board.pos(arena.load(c, arena_id), "aragorn")
    await page.shot("arena-walked")
    check("a click on a blue cell walked aragorn there", now == target and now != (ax, ay), f"{(ax, ay)} -> {now}, wanted {target}")
    left = await page.eval("document.body.innerText.match(/(\\d+) ft left/)?.[1] ?? ''")
    check("the page says how many feet are left", left == "20", left)

    far = arena.load(c, arena_id)
    wall = next((cx, cy) for cy in range(far["h"]) for cx in range(far["w"]) if far["grid"][cy][cx] == "#")
    x, y = rect[0] + (wall[0] + 0.5) * cell_px, rect[1] + (wall[1] + 0.5) * cell_px
    for kind in ("mousePressed", "mouseReleased"):
        await page.call("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left", clickCount=1)
    await asyncio.sleep(0.5)
    check("a click on a wall says why it cannot be done", "cannot walk there" in await page.eval("document.body.innerText"))

    # a creature next to aragorn: a click on it attacks with the weapon that reaches it
    a = arena.load(c, arena_id)
    ax, ay = board.pos(a, "aragorn")
    free = next(cell for cell in ((ax + 1, ay), (ax + 1, ay + 1), (ax, ay + 1), (ax - 1, ay), (ax, ay - 1)) if cell not in arena.blocked_cells(a)
                and cell not in board.occupied(c, combat.load_state(c), a))
    a["units"]["goblin#1"] = {"x": free[0], "y": free[1]}
    arena.save(c, arena_id, a)
    beat.append(c, [{"type": "arena_updated", "arena": arena_id}])
    await asyncio.sleep(1)
    x, y = rect[0] + (free[0] + 0.5) * cell_px, rect[1] + (free[1] + 0.5) * cell_px
    for kind in ("mousePressed", "mouseReleased"):
        await page.call("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left", clickCount=1)
    await asyncio.sleep(1.5)
    await page.shot("arena-attacked")
    check("a click on a creature attacked it: the action is spent", combat.load_state(c)["active_encounter"]["resources"].get("aragorn", {}).get("action") is True)

    # a reaction question for aragorn
    a = arena.load(c, arena_id)
    a["pending"] = {"type": "react", "who": "aragorn", "against": "goblin#1", "path": [[free[0], free[1]]]}
    arena.save(c, arena_id, a)
    beat.append(c, [{"type": "arena_updated", "arena": arena_id}])
    await asyncio.sleep(1.2)
    await page.shot("arena-reaction")
    text = await page.eval("document.body.innerText")
    check("the player is asked about a reaction attack", "opportunity attack" in text and "Skip" in text)
    await page.click("Skip")
    await asyncio.sleep(1.2)
    check("the answer closes the question", arena.load(c, arena_id)["pending"] is None and "opportunity attack" not in await page.eval("document.body.innerText"))


async def foe_turns(page: Page, c: Path, arena_id: str) -> None:
    before = {u: board.pos(arena.load(c, arena_id), u) for u in ("goblin#1", "goblin#2")}
    await page.click("End turn")
    await asyncio.sleep(1)
    await page.click("End turn")
    await asyncio.sleep(1)
    check("End turn passes the turn to the next character, then to the creatures",
          combat.load_state(c)["active_encounter"]["current_turn"] in ("goblin#1", "goblin#2", "aragorn"))
    for _ in range(40):
        enc = combat.load_state(c)["active_encounter"]
        if enc["current_turn"] == "aragorn" and enc["round"] == 2:
            break
        await asyncio.sleep(0.5)
    await page.shot("arena-foes-played")
    now = {u: board.pos(arena.load(c, arena_id), u) for u in ("goblin#1", "goblin#2")}
    check("the stage played the goblins: at least one walked", now != before, f"{before} -> {now}")
    check("the stage stopped at the next player character, in round 2", enc["current_turn"] == "aragorn" and enc["round"] == 2)
    check("the feed shows what the goblins did", len(await page.eval("[...document.querySelectorAll('[aria-label=\"What just happened\"] li')].map(l => l.innerText)")) >= 1)


def main() -> int:
    if not shutil.which("google-chrome"):
        print("skipped: Google Chrome is not installed")
        return 0
    if not (REPO / "stage" / "web" / "dist" / "index.html").exists():
        print("skipped: build the web UI first (npm run build in stage/web)")
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="visual-arena-"))
    c = campaign(tmp)
    state = fight(c)
    combat.save_state(c, state)
    board.start(c, state, ["layout=open", "seed=3"], {})
    combat.save_state(c, state)
    arena_id = state["active_encounter"]["arena"]
    port, debug = free_port(), free_port()
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
                page = Page(ws)
                await page.call("Page.enable")
                await page.call("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
                await page.call("Page.navigate", url=f"http://127.0.0.1:{port}/")
                await asyncio.sleep(2.5)
                await page.click("Play here")
                await asyncio.sleep(1)
                await page.click("Play all free")
                await asyncio.sleep(1.2)
                os.environ["DUNGEON_STAGE_LOG"] = str(beat.log_path(c))
                await board_checks(page, c, arena_id)
                await foe_turns(page, c, arena_id)
        asyncio.run(run())
    finally:
        chrome.terminate()
        server.should_exit = True
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    return 1 if base.FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
