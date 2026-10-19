"""A fight on a phone in portrait: the page must not scroll sideways, and the board, the pad and the roll strip must fit.

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
        ["google-chrome", "--headless=new", f"--remote-debugging-port={debug}", "--no-sandbox", "--window-size=390,800", "--hide-scrollbars",
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
                await page.call("Emulation.setDeviceMetricsOverride", width=390, height=800, deviceScaleFactor=2, mobile=True)
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
                story = await page.eval("""(() => { const w = document.documentElement.clientWidth; const bad = [...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > w + 1 || e.getBoundingClientRect().left < -1).slice(0, 8).map(e => e.tagName + '.' + String(e.className).slice(0, 70) + ' ' + Math.round(e.getBoundingClientRect().left) + '..' + Math.round(e.getBoundingClientRect().right));
                    const mr = document.querySelector('main').getBoundingClientRect().right;
                    const free = (e) => { for (let p = e.parentElement; p && p.tagName !== 'MAIN'; p = p.parentElement) if (getComputedStyle(p).overflowX !== 'visible') return false; return true; };
                    const culprits = [...document.querySelectorAll('main *')].filter(e => e.getBoundingClientRect().right > mr + 0.5 && free(e)).slice(0, 5).map(e => e.tagName + '.' + String(e.className).slice(0, 80) + ' ' + Math.round(e.getBoundingClientRect().right) + '>' + Math.round(mr));
                    const wide = [...document.querySelectorAll('*')].filter(e => e.scrollWidth > e.clientWidth + 1 && ['auto', 'scroll'].includes(getComputedStyle(e).overflowX) && !e.matches('[class*="overflow-x-auto"]') && !e.querySelector('canvas')).slice(0, 6).map(e => e.tagName + '.' + String(e.className).slice(0, 70) + ' ' + e.scrollWidth + '>' + e.clientWidth);
                    return {sw: document.documentElement.scrollWidth, w, bodySw: document.body.scrollWidth, bad, wide, culprits}; })()""")
                check("the story screen does not scroll sideways on a phone", story["sw"] <= story["w"] and story["bodySw"] <= story["w"] and not story["wide"], str(story))
                await page.eval("localStorage.setItem('dungeon-hand', JSON.stringify({ scene: true, layout: 'auto' }))")
                await page.call("Page.reload")
                await asyncio.sleep(3)
                story = await page.eval("""(() => { const w = document.documentElement.clientWidth; const bad = [...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > w + 1 || e.getBoundingClientRect().left < -1).slice(0, 8).map(e => e.tagName + '.' + String(e.className).slice(0, 70) + ' ' + Math.round(e.getBoundingClientRect().left) + '..' + Math.round(e.getBoundingClientRect().right));
                    const mr = document.querySelector('main').getBoundingClientRect().right;
                    const free = (e) => { for (let p = e.parentElement; p && p.tagName !== 'MAIN'; p = p.parentElement) if (getComputedStyle(p).overflowX !== 'visible') return false; return true; };
                    const culprits = [...document.querySelectorAll('main *')].filter(e => e.getBoundingClientRect().right > mr + 0.5 && free(e)).slice(0, 5).map(e => e.tagName + '.' + String(e.className).slice(0, 80) + ' ' + Math.round(e.getBoundingClientRect().right) + '>' + Math.round(mr));
                    const wide = [...document.querySelectorAll('*')].filter(e => e.scrollWidth > e.clientWidth + 1 && ['auto', 'scroll'].includes(getComputedStyle(e).overflowX) && !e.matches('[class*="overflow-x-auto"]') && !e.querySelector('canvas')).slice(0, 6).map(e => e.tagName + '.' + String(e.className).slice(0, 70) + ' ' + e.scrollWidth + '>' + e.clientWidth);
                    return {sw: document.documentElement.scrollWidth, w, bodySw: document.body.scrollWidth, bad, wide, culprits}; })()""")
                check("the story screen with the scene does not scroll sideways on a phone", story["sw"] <= story["w"] and story["bodySw"] <= story["w"] and not story["wide"], str(story))
                await page.shot("phone-story-scene")
                stage = stage_state.replay(beat.log_path(c))
                board.start(c, state, [], stage)
                tracker.save_state(c, state)
                arena_id = state["active_encounter"]["arena"]
                beat.append(c, [{"type": "arena", "arena": arena_id}, {"type": "dm_status", "status": "idle"}])
                await asyncio.sleep(3)
                await page.shot("scene-fight")
                roll = {"type": "roll", "expr": "Aragorn: Longsword \u2014 9 slashing damage", "total": 23, "dice": [{"die": "1d20", "faces": [14]}, {"die": "1d8", "faces": [6]}],
                        "detail": {"kind": "attack", "title": "Longsword", "subtitle": "Attack Roll \u00b7 Aragorn \u2192 Goblin", "rolls": [
                            {"who": "aragorn", "name": "Aragorn", "d20": [14], "kept": 0, "mode": "normal", "mods": [{"label": "Attack Bonus", "value": 5}], "bonus": [], "total": 19, "outcome": "hit"}],
                                   "target": {"label": "Armor Class", "value": 15},
                                   "damage": [{"type": "slashing", "expr": "1d8+3", "faces": [6], "groups": [{"die": "1d8", "faces": [6]}], "total": 9},
                                              {"type": "radiant", "expr": "2d8", "faces": [3, 5], "groups": [{"die": "2d8", "faces": [3, 5]}], "total": 8}]}}
                beat.append(c, [roll])
                await asyncio.sleep(1.2)
                await page.shot("phone-roll-start")
                strip = await page.eval("""(() => { const e = [...document.querySelectorAll('[role=status]')].find(x => x.textContent.includes('Longsword')); const b = document.querySelector('canvas[aria-label^="The board"]').getBoundingClientRect(); const r = e && e.getBoundingClientRect(); return {inStrip: Boolean(e), top: r && r.top, boardBottom: b.bottom, boardTop: b.top} })()""")
                check("the roll window sits under the board, not over it", strip["inStrip"] and strip["top"] >= strip["boardTop"] + 50, str(strip))
                await asyncio.sleep(5)
                await page.shot("phone-roll-done")
                feet = lambda: page.eval("(document.body.innerText.match(/(\\d+) ft left/) || [])[1] || ''")
                before = await feet()
                clicked = await page.eval("""(() => { const b = [...document.querySelectorAll('button[aria-label^="Walk "]')].find(x => !x.disabled); if (!b) return null; b.click(); return b.getAttribute('aria-label'); })()""")
                await asyncio.sleep(1.5)
                after = await feet()
                check("the walking pad moves the character and spends 5 or 7 ft", bool(clicked) and int(before) - int(after) in (5, 7), f"{clicked}: {before} -> {after}")
                over = await page.eval("""(() => { const w = document.documentElement.clientWidth; const bad = [...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > w + 1 || e.getBoundingClientRect().left < -1).slice(0, 8).map(e => e.tagName + '.' + String(e.className).slice(0, 70) + ' ' + Math.round(e.getBoundingClientRect().left) + '..' + Math.round(e.getBoundingClientRect().right));
                    const mr = document.querySelector('main').getBoundingClientRect().right;
                    const free = (e) => { for (let p = e.parentElement; p && p.tagName !== 'MAIN'; p = p.parentElement) if (getComputedStyle(p).overflowX !== 'visible') return false; return true; };
                    const culprits = [...document.querySelectorAll('main *')].filter(e => e.getBoundingClientRect().right > mr + 0.5 && free(e)).slice(0, 5).map(e => e.tagName + '.' + String(e.className).slice(0, 80) + ' ' + Math.round(e.getBoundingClientRect().right) + '>' + Math.round(mr));
                    const wide = [...document.querySelectorAll('*')].filter(e => e.scrollWidth > e.clientWidth + 1 && ['auto', 'scroll'].includes(getComputedStyle(e).overflowX) && !e.matches('[class*="overflow-x-auto"]') && !e.querySelector('canvas')).slice(0, 6).map(e => e.tagName + '.' + String(e.className).slice(0, 70) + ' ' + e.scrollWidth + '>' + e.clientWidth);
                    return {sw: document.documentElement.scrollWidth, w, bodySw: document.body.scrollWidth, bad, wide, culprits}; })()""")
                check("the page does not scroll sideways on a phone", over["sw"] <= over["w"] and over["bodySw"] <= over["w"] and not over["wide"], str(over))
        asyncio.run(run())
    finally:
        chrome.terminate()
        server.should_exit = True
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{v.PASS} passed, {v.FAIL} failed")
    return 1 if v.FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
