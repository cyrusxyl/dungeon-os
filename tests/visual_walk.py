"""Walking in a scene, in a real browser: a click sends the player's character across the room, and an NPC that wanders moves by itself.

Run from the repo root:  .venv/bin/python tests/visual_walk.py [screenshot-dir]
(or `tests/run_all.py --visual`). Needs Google Chrome and a built web UI (`npm run build` in stage/web).
It skips (exit 0) without Chrome.
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

from stage import actors, beat, scenes  # noqa: E402
from stage.server import create_app  # noqa: E402
from test_rules import campaign  # noqa: E402

check, REPO = v.check, v.REPO
CAST = "JSON.parse(document.querySelector('canvas[data-cast]')?.dataset.cast || '[]')"
# The canvas draws the room in logical pixels: `data-geom` is ox, oy, width, height. The ground centre of cell (x, y) is
# (ox + (x - y) * 32, oy + (x + y) * 16 + 16); the page shows the canvas scaled, so the click goes to the scaled point.
CLICK = """((x, y) => {
  const c = document.querySelector('canvas[data-cast]'); const [ox, oy, w, h] = c.dataset.geom.split(',').map(Number);
  const r = c.getBoundingClientRect(); const px = ox + (x - y) * 32, py = oy + (x + y) * 16 + 16;
  c.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: r.left + px / w * r.width, clientY: r.top + py / h * r.height }));
})"""


async def until(page: v.Page, js: str, seconds: float):
    end = time.time() + seconds
    while time.time() < end:
        if got := await page.eval(js):
            return got
        await asyncio.sleep(0.25)
    return None


def main() -> int:
    if not shutil.which("google-chrome"):
        print("skipped: Google Chrome is not installed")
        return 0
    if not (REPO / "stage" / "web" / "dist" / "index.html").exists():
        print("skipped: build the web UI first (npm run build in stage/web)")
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="visual-"))
    c = campaign(tmp)
    scenes.save(c, "court", {"template": "throne_room", "slots": {}, "add": [], "mood": "torchlit"})
    for aid, kind in {"aragorn": "knight", "legolas": "bandit", "pc-priest": "priest", "pc-wizard": "wizard", "gareth": "priest"}.items():
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
                beat.append(c, [{"type": "scene", "location": "court", "party": ["aragorn", "legolas"]}, {"type": "enter", "actor": "gareth"},
                                {"type": "walk", "actor": "gareth", "walk": "wander"}])
                await asyncio.sleep(2)
                cast = await page.eval(CAST)
                check("the party and the wanderer are drawn", len(cast) == 3, str(cast))
                await page.shot("walk-start")

                print("a click sends the player's character across the room")
                held = {tuple(f["cell"]) for f in cast}
                floor = [(x, y) for x in range(1, 10) for y in range(1, 8)]
                me = next(f for f in cast if f["id"] in ("aragorn", "legolas"))  # the first seat the device took
                goal = max((cell for cell in floor if cell not in held), key=lambda cell: abs(cell[0] - me["cell"][0]) + abs(cell[1] - me["cell"][1]))
                await page.eval(f"({CLICK})({goal[0]}, {goal[1]})")
                got = await until(page, f"{CAST}.some(f => f.cell[0] === {goal[0]} && f.cell[1] === {goal[1]} && f.side === 'party')", 25)
                await page.shot("walk-arrived")
                check("a party character stands on the cell that was clicked", bool(got), str(await page.eval(CAST)))

                print("a wanderer moves by itself")
                first = next(f for f in await page.eval(CAST) if f["id"] == "gareth")["cell"]
                moved = await until(page, f"{CAST}.some(f => f.id === 'gareth' && (f.cell[0] !== {first[0]} || f.cell[1] !== {first[1]}))", 30)
                check("the wandering NPC has changed cell", bool(moved))

        asyncio.run(run())
    finally:
        chrome.terminate()
        server.should_exit = True
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{v.PASS} passed, {v.FAIL} failed")
    return 1 if v.FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
