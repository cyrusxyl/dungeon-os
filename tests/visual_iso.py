"""Pictures of the isometric view: five rooms of different shapes and themes, and five props in their tuned poses.

Run from the repo root:  .venv/bin/python tests/visual_iso.py [screenshot-dir]
(or `tests/run_all.py --visual`). Needs Google Chrome and a built web UI (`npm run build` in stage/web).
It saves scenes, shows each one, and asserts on what the canvas draws: a room fills part of the picture, the walls and floor are
there, and a prop changes the picture where it stands. Screenshots go to the directory, for a person to look at. It skips (exit 0)
without Chrome.
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

from stage import beat, scenes  # noqa: E402
from stage.server import create_app  # noqa: E402
from test_rules import campaign  # noqa: E402
from visual_stage_cast import show  # noqa: E402

check, REPO = v.check, v.REPO
ROOMS = {
    "tavern": {"template": "tavern"},
    "cross-chapel": {"template": "chapel", "shape": "cross", "seed": 4},
    "cave": {"template": "cavern", "shape": "cave", "seed": 2},
    "clearing": {"template": "forest", "shape": "ellipse", "seed": 3},
    "crypt": {"template": "crypt", "shape": "twin", "seed": 5},
}
# Five props, each posed another way: a table (flat top and legs), a bench (seat), a throne (tall), a cabinet, a tree (upright).
PROPS = {"back_left": "table_long", "back_center": "throne", "back_right": "bench_long", "mid_left": "cabinet", "mid_right": "oak"}
EMPTY = {s: None for s in PROPS}
PIXELS = "(() => { const c = document.querySelector('canvas[data-cast]'); return c.getContext('2d').getImageData(0, 0, c.width, c.height).data; })()"
# The share of pixels of the canvas that are not dark: the picture is there.
LIT = ("(() => { const c = document.querySelector('canvas[data-cast]'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; "
       "let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i + 3] && d[i] + d[i + 1] + d[i + 2] > 60) n++; return n / (c.width * c.height); })()")


def main() -> int:
    if not shutil.which("google-chrome"):
        print("skipped: Google Chrome is not installed")
        return 0
    if not (REPO / "stage" / "web" / "dist" / "index.html").exists():
        print("skipped: build the web UI first (npm run build in stage/web)")
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="visual-"))
    c = campaign(tmp)
    for name, spec in ROOMS.items():
        scenes.save(c, name, {"slots": {}, "add": [], "mood": "day", **spec})
    scenes.save(c, "props", {"template": "hall", "slots": {**EMPTY, **PROPS}, "add": [], "mood": "day"})
    scenes.save(c, "bare", {"template": "hall", "slots": EMPTY, "add": [], "mood": "day"})
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

        async def look(page, name: str) -> float:
            show(c, f"@scene {name}\n@narrate {name}.")
            await asyncio.sleep(2)
            await page.shot(f"iso-{name}")
            return await page.eval(LIT)

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
                print("five rooms")
                shares = {}
                for name in ROOMS:
                    shares[name] = await look(page, name)
                    check(f"the {name} room fills part of the picture with floor and walls", 0.12 < shares[name] < 0.9, f"{shares[name]:.2f}")
                check("the rooms differ from each other", len({round(s, 2) for s in shares.values()}) >= 4, str(shares))
                print("five props")
                await look(page, "bare")
                await page.eval(f"window.__bare = {PIXELS}.slice()")
                await look(page, "props")
                changed = await page.eval(f"(() => {{ const d = {PIXELS}, b = window.__bare; let n = 0; for (let i = 0; i < d.length; i += 4) if (Math.abs(d[i] - b[i]) + Math.abs(d[i + 1] - b[i + 1]) > 40) n++; return n; }})()")
                check("five props with five poses change the picture where they stand", changed > 20000, f"{changed} pixels differ")

        asyncio.run(run())
    finally:
        chrome.terminate()
        server.should_exit = True
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{v.PASS} passed, {v.FAIL} failed")
    return 1 if v.FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
