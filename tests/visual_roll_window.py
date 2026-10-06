"""The roll window in a real browser: the checks that unit tests cannot make.

Run from the repo root:  .venv/bin/python tests/visual_roll_window.py [screenshot-dir]
(or `tests/run_all.py --visual`). Needs Google Chrome and a built web UI (`npm run build` in stage/web).

It starts the stage on a temp copy of the example campaign, drives headless Chrome over the DevTools protocol,
makes real rolls with the rules code, and asserts on what the page shows. It skips (exit 0) without Chrome.
Pass a directory to keep a screenshot of each step.
"""

from __future__ import annotations

import asyncio
import base64
import json
import shutil
import socket
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

from dnd_cli import combat, effects  # noqa: E402
from stage import beat  # noqa: E402
from stage.server import create_app  # noqa: E402
from test_rules import Fixed, campaign, fight  # noqa: E402

SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}{'' if cond or not detail else f'  ({detail})'}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Page:
    """One Chrome tab over the DevTools protocol."""

    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def call(self, method: str, **params):
        self.n += 1
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == self.n:
                return msg.get("result", msg)

    async def eval(self, js: str):
        r = await self.call("Runtime.evaluate", expression=js, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    async def shot(self, name: str) -> None:
        if SHOTS:
            SHOTS.mkdir(parents=True, exist_ok=True)
            (SHOTS / f"{name}.png").write_bytes(base64.b64decode((await self.call("Page.captureScreenshot", format="png"))["data"]))

    async def window_open(self) -> bool:
        return bool(await self.eval("Boolean(document.querySelector('[role=status] h2'))"))

    async def click(self, text: str) -> None:
        await self.eval(f"[...document.querySelectorAll('button')].find(b => b.textContent.trim() === {json.dumps(text)})?.click()")


def idle(c: Path) -> None:
    beat.append(c, [{"type": "dm_status", "status": "idle"}])


async def turn_over(c: Path) -> None:
    """A DM turn ends: the page reads the party again, as it does after the DM added an effect."""
    beat.append(c, [{"type": "dm_status", "status": "busy"}])
    await asyncio.sleep(0.5)
    idle(c)
    await asyncio.sleep(1)


async def scenarios(page: Page, c: Path) -> None:
    idle(c)
    state = combat.load_state(c)
    await asyncio.sleep(1)

    print("advantage: one die drops, one is kept")
    effects.add(c, "aragorn", "advantage")
    combat.check(c, state, ["aragorn"], "athletics", dc=14, rng=Fixed(6, 17))
    await asyncio.sleep(2.2)
    await page.shot("advantage")
    check("two dice, one dropped, one kept", await page.eval("[document.querySelectorAll('.die-dropped').length, document.querySelectorAll('.die-kept').length]") == [1, 1])

    print("the window closes on time while the DM keeps sending events")
    start = time.time()
    closed = None
    for i in range(30):
        beat.append(c, [{"type": "dm_activity", "text": f"Step {i}"}])
        await asyncio.sleep(0.5)
        if closed is None and i > 2 and not await page.window_open():
            closed = time.time() - start
    check("closed within 10 s (animation about 2.5 s, then a 4.5 s hold)", closed is not None and closed < 10, f"closed after {closed}")

    print("a roll request: a save uses the save bonuses")
    effects.add(c, "aragorn", "bless")
    effects.add(c, "aragorn", "guidance")
    await turn_over(c)
    beat.append(c, [{"type": "roll_request", "who": "aragorn", "what": "dex-save", "dc": 13, **combat.roll_preview(c, state, "aragorn", "dex-save")}])
    await asyncio.sleep(1.5)
    await page.shot("request-save")
    dialog = (await page.eval("document.querySelector('[role=dialog]')?.innerText || ''")).lower()
    check("Bless is offered, Guidance is not", "bless" in dialog and "guidance" not in dialog, dialog.replace("\n", " | "))
    check("the DC is shown", "difficulty class" in dialog and "13" in dialog)
    await page.click("Roll")
    await asyncio.sleep(1.2)
    check("the request closes when the roll starts", not await page.eval("Boolean(document.querySelector('[role=dialog]'))"))
    await asyncio.sleep(8)
    await turn_over(c)  # the click told the stub DM to work; a real DM would now finish its turn

    print("a hidden DC is not in the page")
    beat.append(c, [{"type": "roll_request", "who": "aragorn", "what": "athletics", "dc": 17, "hide": True,
                     **combat.roll_preview(c, state, "aragorn", "athletics")}])
    await asyncio.sleep(1.5)
    dialog = (await page.eval("document.querySelector('[role=dialog]')?.innerText || ''")).lower()
    check("the request window is open", "athletics" in dialog, dialog)
    check("no DC in the request window", "difficulty" not in dialog and "17" not in dialog, dialog.replace("\n", " | "))
    check("no DC anywhere in the page", "difficulty class" not in (await page.eval("document.body.innerText")).lower())
    beat.append(c, [{"type": "narrate", "text": "The DM moved on."}])
    await asyncio.sleep(1)

    print("Roll waits until the player has read the story")
    beat.append(c, [{"type": "narrate", "text": "First line."}, {"type": "narrate", "text": "Second line."},
                    {"type": "roll_request", "who": "aragorn", "what": "athletics", "dc": 12, **combat.roll_preview(c, state, "aragorn", "athletics")}])
    await asyncio.sleep(1.5)
    await page.shot("request-unread")
    status = await page.eval("document.body.innerText")
    check("the DM is idle, so only the unread story can hold the button back", "Your move" in status or "Wait for the DM" in status)
    check("the Roll button is disabled while narration is unread", await page.eval(
        "[...document.querySelectorAll('[role=dialog] button')].some(b => /Wait for the DM/.test(b.textContent) && b.disabled)"))
    await page.click("Roll")
    await asyncio.sleep(0.5)
    check("a click on it rolls nothing", await page.eval("Boolean(document.querySelector('[role=dialog]'))"))


async def click_starting(page: Page, text: str) -> bool:
    return bool(await page.eval(
        f"(() => {{ const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim().startsWith({json.dumps(text)}) && !b.disabled);"
        " b?.click(); return Boolean(b) })()"))


async def combat_turn(page: Page, c: Path) -> None:
    beat.append(c, [{"type": "narrate", "text": "The goblins attack."}])  # ends any open roll request
    await asyncio.sleep(0.5)
    await page.call("Page.reload")  # a reload counts the story as read: the card waits for that
    await asyncio.sleep(2.5)
    await turn_over(c)

    print("outside a combat: the turn icons and the common actions are there, greyed where they cannot work")
    await page.shot("card-exploring")
    text = await page.eval("document.body.innerText")
    check("the action, bonus action and reaction are shown", all(w in text for w in ("Action", "Bonus", "Reaction")))
    check("the common actions are on the card", all(w in text for w in ("Attack", "Dash", "Disengage", "Dodge", "Help", "Hide", "Shove")))
    check("Attack is greyed (no combat), Hide is on", await page.eval(
        "[...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'Attack' && b.disabled) && "
        "[...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'Hide' && !b.disabled)"))
    check("the turn icons cannot be clicked", await page.eval("document.querySelectorAll('[aria-label=\"This turn\"] button').length") == 0)
    check("no bonus can be added: no one in the party can give one", "+ Bonus" not in text)

    print("a combat: the turn bar, and Your turn")
    state = fight(c)
    combat.save_state(c, state)
    await turn_over(c)
    await page.shot("combat-your-turn")
    bar = await page.eval("document.querySelector('[aria-label=\"Turn order\"]')?.innerText || ''")
    check("the turn bar shows the round, the party and the creatures", "Round 1" in bar and "Aragorn" in bar and "Goblin 1" in bar and "Goblin 2" in bar, bar.replace("\n", " | "))
    check("a creature shows how hurt it is, in words", "unhurt" in bar)
    text = await page.eval("document.body.innerText")
    check("no creature number is in the page", not any(w in text for w in ("HP 7", "7/7", "HP 3")))
    check("Your turn and End turn are on the active card", "Your turn" in text and "End turn" in text)

    print("Attack from the card: weapon, target, then the roll")
    check("Attack is on", await click_starting(page, "Attack"))
    await asyncio.sleep(0.3)
    check("a weapon is asked for first", await click_starting(page, "Longsword"))
    await asyncio.sleep(0.3)
    await page.shot("attack-target")
    check("then a target", await click_starting(page, "Goblin 1"))
    await asyncio.sleep(1.5)
    await page.shot("attack-rolled")
    used = combat.load_state(c)["active_encounter"]["resources"].get("aragorn", {})
    check("the action is spent", used.get("action") is True)
    await asyncio.sleep(8)
    await turn_over(c)
    await page.shot("action-spent")
    check("Attack is now greyed, Shove is still on", await page.eval(
        "[...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'Attack' && b.disabled) && "
        "[...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'Shove' && !b.disabled)"))

    print("End turn")
    await page.click("End turn")
    await asyncio.sleep(1)
    await turn_over(c)
    await page.shot("legolas-turn")
    check("the tracker moved to the next character", combat.load_state(c)["active_encounter"]["current_turn"] == "legolas")
    check("the first character has Your turn no more", await page.eval("[...document.querySelectorAll('section')].filter(s => /Your turn/.test(s.innerText)).length") == 1)


def main() -> int:
    if not shutil.which("google-chrome"):
        print("skipped: Google Chrome is not installed")
        return 0
    if not (REPO / "stage" / "web" / "dist" / "index.html").exists():
        print("skipped: build the web UI first (npm run build in stage/web)")
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="visual-"))
    c = campaign(tmp)
    port, debug = free_port(), free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(campaign_dir=c, dm_command=["sleep", "3600"]), host="127.0.0.1", port=port, log_level="warning"))
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
                await page.shot("role-screen")
                role = "Boolean(document.querySelector('[aria-label=\"Set up this device\"]'))"
                check("the host device first says what it is", await page.eval(role))
                check("no seat picker before that", not await page.eval("Boolean(document.querySelector('[aria-label=\"Pick your seat\"]'))"))
                await page.click("Play here")
                await asyncio.sleep(1)
                await page.shot("seat-picker")
                check("then it sees the seat picker", await page.eval("Boolean(document.querySelector('[aria-label=\"Pick your seat\"]'))"))
                check("the first device is the host: it sees a host code", "Host code" in await page.eval("document.body.innerText"))
                await page.click("Play all free")
                await asyncio.sleep(1.2)
                check("sitting down closes the picker", not await page.eval("Boolean(document.querySelector('[aria-label=\"Pick your seat\"]'))"))
                import os
                os.environ["DUNGEON_STAGE_LOG"] = str(beat.log_path(c))
                await scenarios(page, c)
                await combat_turn(page, c)
                print("a whisper and an awaited answer")
                await page.call("Page.navigate", url=f"http://127.0.0.1:{port}/?view=full")
                await asyncio.sleep(2.5)
                beat.append(c, [{"type": "whisper", "who": "aragorn", "text": "A cold draft hints at a hidden door."},
                                {"type": "await", "who": "all"}, {"type": "dm_status", "status": "idle"}])
                await asyncio.sleep(1.5)
                await page.shot("whisper-await")
                text = await page.eval("document.body.innerText")
                check("the whisper shows to its player", "hidden door" in text and "Only you" in text)
                check("the awaited answers are shown", "Waiting for" in text)
                await page.call("Emulation.setDeviceMetricsOverride", width=390, height=800, deviceScaleFactor=2, mobile=True)
                await page.call("Page.navigate", url=f"http://127.0.0.1:{port}/?view=hand")
                await asyncio.sleep(2.5)
                await page.shot("whisper-await-hand")
                check("the hand screen shows the whisper above the input", "hidden door" in await page.eval("document.body.innerText"))
                await page.call("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
                await page.call("Page.navigate", url=f"http://127.0.0.1:{port}/?view=table")
                await asyncio.sleep(2.5)
                text = await page.eval("document.body.innerText")
                check("the table screen shows who is awaited but not the whisper", "Waiting for" in text and "hidden door" not in text)
                print("table and hand screens")
                await page.call("Page.navigate", url=f"http://127.0.0.1:{port}/?view=table")
                await asyncio.sleep(2.5)
                check("the table screen has no input box", not await page.eval("Boolean(document.querySelector('#player-input'))"))
                check("the table screen shows the party", "Aragorn" in await page.eval("document.body.innerText"))
                await page.call("Page.navigate", url=f"http://127.0.0.1:{port}/?view=hand")
                await asyncio.sleep(2.5)
                await page.shot("hand")
                check("the hand screen has the input box", bool(await page.eval("Boolean(document.querySelector('#player-input'))")))
                check("the hand screen shows only this player's cards", await page.eval("document.querySelectorAll('main section h2').length") >= 1
                      and "Where" not in await page.eval("document.body.innerText"))

                print("the table role")
                await page.eval("""(async () => {
                    const h = {'Content-Type': 'application/json', 'X-Device': localStorage.getItem('dungeon-device')}
                    for (const who of ['aragorn', 'legolas']) await fetch('/api/seat/release', {method: 'POST', headers: h, body: JSON.stringify({who})})
                    localStorage.removeItem('dungeon-view')
                    Object.keys(localStorage).filter((k) => k.startsWith('dungeon-seats')).forEach((k) => localStorage.removeItem(k))
                })()""")
                await page.call("Page.navigate", url=f"http://127.0.0.1:{port}/")
                await asyncio.sleep(2.5)
                check("a host with no seat and no saved choice is asked again", await page.eval(role))
                await page.click("Table screen")
                await asyncio.sleep(1)
                check("the table role: no seat picker, a join box, no input", not await page.eval("Boolean(document.querySelector('[aria-label=\"Pick your seat\"]'))")
                      and "Join" in await page.eval("document.body.innerText") and not await page.eval("Boolean(document.querySelector('#player-input'))"))

                print("a phone that joins")
                await page.eval("localStorage.setItem('dungeon-device', 'f0e1d2c3b4a5968778695a4b3c2d1e0f'); localStorage.removeItem('dungeon-view')")
                await page.call("Page.navigate", url=f"http://127.0.0.1:{port}/")
                await asyncio.sleep(2.5)
                check("a joining device is not asked what it is: it goes straight to the seat picker",
                      not await page.eval(role) and await page.eval("Boolean(document.querySelector('[aria-label=\"Pick your seat\"]'))"))

        asyncio.run(run())
    finally:
        chrome.terminate()
        server.should_exit = True
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
