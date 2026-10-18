"""The stage cast in a real browser: 12 actors by side, a companion that comes with every scene, a seat on a prop.

Run from the repo root:  .venv/bin/python tests/visual_stage_cast.py [screenshot-dir]
(or `tests/run_all.py --visual`). Needs Google Chrome and a built web UI (`npm run build` in stage/web).
It starts the stage on a temp copy of the example campaign, puts the beats in through `dnd-cli show beat` (the real
path: roster, sides, the cast report) and asserts on what the page draws. It skips (exit 0) without Chrome.
"""

from __future__ import annotations

import asyncio
import io
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

from dnd_cli.commands import show_cmd  # noqa: E402
from stage import actors, beat, scenes  # noqa: E402
from stage.cast import apart  # noqa: E402
from stage.server import create_app  # noqa: E402
from test_rules import campaign  # noqa: E402

check, REPO = v.check, v.REPO
LOOKS = {"aragorn": "knight", "legolas": "bandit", "pc-priest": "priest", "pc-wizard": "wizard", "ilvuur": "thug", "qorlia": "noble",
         "sharael": "noble", "arbiter": "priest", "sentry": "guard", "guard": "guard"}
# The stage draws the room on one canvas; it lists its actors in `data-cast`: id, side, cell, seated, on a prop.
CAST = "JSON.parse(document.querySelector('canvas[data-cast]')?.dataset.cast || '[]')"


def show(c: Path, text: str) -> str:
    out = io.StringIO()
    old, sys.stdin, sys.stdout = sys.stdin, io.StringIO(text), out
    try:
        show_cmd.execute_beat(str(c), None)
    finally:
        sys.stdin, sys.stdout = old, sys.__stdout__
    return out.getvalue()


def main() -> int:
    if not shutil.which("google-chrome"):
        print("skipped: Google Chrome is not installed")
        return 0
    if not (REPO / "stage" / "web" / "dist" / "index.html").exists():
        print("skipped: build the web UI first (npm run build in stage/web)")
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="visual-"))
    c = campaign(tmp)
    scenes.save(c, "hall", {"template": "throne_room", "slots": {}, "add": [], "mood": "torchlit", "shape": "h", "seed": 2})
    scenes.save(c, "court", {"template": "throne_room", "slots": {}, "add": [], "mood": "torchlit"})
    for aid, kind in LOOKS.items():
        actors.save(c, aid, actors.presets()[kind])
    state = json.loads((c / "state.json").read_text())
    state["party_members"] = ["aragorn", "legolas", "pc-priest", "pc-wizard"]
    (c / "state.json").write_text(json.dumps(state))
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

                print("a companion joins and comes to the next scene by itself")
                show(c, "@join ilvuur\n@join qorlia\n@scene court\n@walk ilvuur still\n@walk qorlia still\n@narrate The court is silent.")  # a placement test: everyone stands still
                await asyncio.sleep(2)
                check("the party and both companions are drawn", len(await page.eval(CAST)) == 6, str(await page.eval(CAST)))
                out = show(c, "@scene court")
                check("the readback lists the companions with their side", "ilvuur (ally)" in out and "qorlia (ally)" in out, out)

                print("twelve actors, one of them seated on the throne")
                show(c, "@enter sharael\n@enter arbiter on back_center\n@enter goblin#1\n@enter goblin#2\n@enter guard\n@enter sentry\n" + "".join(f"@walk {i} still\n" for i in ("sharael", "goblin#1", "goblin#2", "guard", "sentry")) + "@narrate Steel is drawn.")
                await asyncio.sleep(2.5)
                await page.shot("cast-12")
                cast = await page.eval(CAST)
                check("twelve figures are drawn", len(cast) == 12, str(cast))
                cells = [tuple(f["cell"]) for f in cast]
                check("no two figures stand on the same cell", len(set(cells)) == 12, str(cells))
                arbiter = next(f for f in cast if f["id"] == "arbiter")
                ax, ay = arbiter["cell"]
                front = {(ax + 1, ay), (ax, ay + 1), (ax + 1, ay + 1)}
                check("no one stands in front of the seated arbiter", not any(tuple(f["cell"]) in front for f in cast if f["id"] != "arbiter"), str(front))
                check("the arbiter is seated on a prop", arbiter["sit"] and arbiter["onProp"])
                standing = [f for f in cast if not f["sit"]]
                check("every figure but the seated one has a ring (it stands on the floor or on a prop)", len(standing) == 11, str(len(standing)))
                check("green, yellow and red rings are all there",
                      {"g" if f["side"] in ("party", "ally") else f["side"] for f in standing} == {"g", "neutral", "hostile"}, str({f["side"] for f in standing}))

                print("a companion sneaks out of the next scene")
                out = show(c, "@scene court -ilvuur")
                await asyncio.sleep(1.5)
                check("the companion is left out of the scene", "ilvuur" not in out and len(await page.eval(CAST)) == 11, out)
                await page.shot("cast-sneak")

                print("a big room with wings: each side stays together")
                show(c, "@scene hall\n@enter goblin#1\n@enter goblin#2\n@enter goblin#3\n" + "".join(f"@walk {i} still\n" for i in ("ilvuur", "qorlia", "goblin#1", "goblin#2", "goblin#3")) + "@narrate Steel is drawn.")
                await asyncio.sleep(2.5)
                await page.shot("cast-wings")
                cast = await page.eval(CAST)

                def together(cells: list[tuple[int, int]]) -> bool:
                    seen, todo = {cells[0]}, [cells[0]]
                    while todo:
                        a = todo.pop()
                        for b in cells:
                            if b not in seen and max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 3:
                                seen.add(b)
                                todo.append(b)
                    return len(seen) == len(cells)

                friends = [tuple(f["cell"]) for f in cast if f["side"] in ("party", "ally")]
                foes = [tuple(f["cell"]) for f in cast if f["side"] == "hostile"]
                check("the party and its companions stand together in a room with wings", len(friends) == 6 and together(friends), str(friends))
                spread = [tuple(f["cell"]) for f in cast if not f["onProp"]]
                check("no two figures overlap on the screen (2 or more across or deep)",
                      all(apart(p, q) for i, p in enumerate(spread) for q in spread[i + 1:]), str(spread))

        asyncio.run(run())
    finally:
        chrome.terminate()
        server.should_exit = True
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{v.PASS} passed, {v.FAIL} failed")
    return 1 if v.FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
