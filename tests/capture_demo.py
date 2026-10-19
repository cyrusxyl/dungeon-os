"""Record what the real server sends to the browser during a fight, for the demo build (stage/web/demo/).

Run from the repo root:  .venv/bin/python tests/capture_demo.py
It starts the real stage server on a test campaign (the party and two goblins in a hall), opens the page in Chrome at phone size,
and saves every GET answer (`/api/...`, `/asset/...`), the first state snapshot of the websocket, the blocked cells of the board and
the browser's saved choices to stage/web/demo/fixtures.json. The demo page replays them; nothing else is made up.
"""

from __future__ import annotations

import asyncio
import base64
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
from visual_stage_cast import show  # noqa: E402

OUT = v.REPO / "stage" / "web" / "demo" / "fixtures.json"
FACINGS = ("down", "up", "left", "right")


class Tab:
    """A Chrome tab that keeps the Network events, which the test pages throw away."""

    def __init__(self, ws):
        self.ws, self.n, self.events = ws, 0, []

    async def call(self, method: str, **params):
        self.n += 1
        mine = self.n
        await self.ws.send(json.dumps({"id": mine, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == mine:
                return msg.get("result", msg)
            self.events.append(msg)

    async def eval(self, js: str):
        r = await self.call("Runtime.evaluate", expression=js, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    async def pump(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            try:
                self.events.append(json.loads(await asyncio.wait_for(self.ws.recv(), 0.2)))
            except asyncio.TimeoutError:
                pass


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="demo-"))
    c = campaign(tmp)
    scenes.save(c, "hall", {"template": "tavern", "slots": {}, "add": [], "mood": "day"})
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
        tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{debug}/json").read())
        tab = next(t for t in tabs if t["type"] == "page")

        async def run() -> dict:
            async with websockets.connect(tab["webSocketDebuggerUrl"], max_size=None) as ws:
                page = Tab(ws)
                await page.call("Page.enable")
                await page.call("Network.enable")
                await page.call("Emulation.setDeviceMetricsOverride", width=390, height=800, deviceScaleFactor=2, mobile=True)
                await page.call("Page.navigate", url=f"http://127.0.0.1:{port}/")
                await page.pump(2.5)
                await page.eval("[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Play here')?.click()")
                await page.pump(1)
                await page.eval("[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Play all free')?.click()")
                await page.pump(1.2)
                beat.append(c, [{"type": "dm_status", "status": "idle"}])
                show(c, "@scene hall\n@enter goblin#1 hostile\n@enter goblin#2 hostile\n@walk goblin#1 still\n@walk goblin#2 still\n@narrate Steel is drawn.")
                await page.pump(2.5)
                stage = stage_state.replay(beat.log_path(c))
                board.start(c, state, [], stage)
                tracker.save_state(c, state)
                arena_id = state["active_encounter"]["arena"]
                beat.append(c, [{"type": "arena", "arena": arena_id}, {"type": "dm_status", "status": "idle"}])
                await page.pump(3)
                # Every picture the board may draw: each creature in each facing, and the portraits.
                a = arena.load(c, arena_id)
                ids = list(a["units"])
                urls = [f"/asset/actor/{i.replace('#', '%23')}/full.png?d={f}" for i in ids for f in FACINGS]
                urls += [f"/asset/actor/{i.replace('#', '%23')}/portrait/neutral.png" for i in ids]
                await page.eval("Promise.all(" + json.dumps(urls) + ".map(u => fetch(u).then(r => r.blob()).catch(() => null)))")
                await page.pump(1.5)
                ls = await page.eval("JSON.stringify(Object.fromEntries(Object.keys(localStorage).map(k => [k, localStorage.getItem(k)])))")
                responses, bodies, frames = {}, {}, []
                for e in page.events:
                    m, p = e.get("method"), e.get("params", {})
                    if m == "Network.responseReceived" and p["response"]["status"] == 200:
                        path = p["response"]["url"].split(f"127.0.0.1:{port}", 1)[-1]
                        if path.startswith(("/api/", "/asset/")) and "/ws" not in path:
                            responses[p["requestId"]] = (path, p["response"].get("mimeType", ""))
                    elif m == "Network.webSocketFrameReceived":
                        frames.append(p["response"]["payloadData"])
                for rid, (path, mime) in responses.items():
                    try:
                        body = await page.call("Network.getResponseBody", requestId=rid)
                    except Exception:
                        continue
                    if "body" in body:
                        bodies[path] = {"mime": mime, "b64": body["body"] if body.get("base64Encoded") else base64.b64encode(body["body"].encode()).decode()}
                snaps = [json.loads(f) for f in frames if '"snapshot"' in f[:40]]
                return {"urls": bodies, "snapshot": snaps[-1], "storage": json.loads(ls or "{}"), "arena": arena_id,
                        "blocked": sorted(list(x) for x in arena.blocked_cells(a)), "units": ids}

        data = asyncio.run(run())
    finally:
        chrome.terminate()
        server.should_exit = True
        shutil.rmtree(tmp, ignore_errors=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data))
    sizes = sum(len(x["b64"]) for x in data["urls"].values()) // 1024
    print(f"saved {len(data['urls'])} answers ({sizes} KB), arena {data['arena']}, to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
