"""The damage dice tray and the Gameplay settings in a real browser: the checks that unit tests cannot make.

Run from the repo root:  .venv/bin/python tests/visual_dice_tray.py [screenshot-dir]
(or `tests/run_all.py --visual`). Needs Google Chrome and a built web UI (`npm run build` in stage/web).

It starts the stage on a temp copy of the example campaign, drives headless Chrome over the DevTools protocol, sends
roll events to the stage and asserts on what the page shows. It skips (exit 0) without Chrome.
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

from stage import beat  # noqa: E402
from stage.server import create_app  # noqa: E402
from test_rules import campaign  # noqa: E402

check, REPO = v.check, v.REPO

DAMAGE = [
    {"type": "slashing", "expr": "1d8+3", "faces": [6], "groups": [{"die": "1d8", "faces": [6]}], "total": 9},
    {"type": "fire", "expr": "2d6", "faces": [4, 5], "groups": [{"die": "2d6", "faces": [4, 5]}], "total": 9},
]
ORDER = """(() => { const rect = (e) => e.getBoundingClientRect(); const dlg = [...document.querySelectorAll('p')].find((p) => p.textContent.includes('Decide, Lady')).closest('[class*="border-4"]');
    const first = [...document.querySelectorAll('button')].find((b) => b.textContent.trim().startsWith('Burn the page')), input = document.querySelector('#player-input');
    return rect(first).top >= rect(dlg).bottom - 1 && rect(input).top >= rect(first).bottom - 1 })()"""
# The blocks of the page body, two levels deep: none may overflow its own box (a squeezed block spills onto the next one; 12 px lets the buttons' pixel borders stick out), and no two siblings may intersect.
NO_OVERLAP = """(() => { const kids = [...document.querySelector('main').children], bad = [];
    const visit = (e) => { if (!['auto', 'scroll', 'hidden'].includes(getComputedStyle(e).overflowY) && e.scrollHeight > e.clientHeight + 12) bad.push('overflow ' + e.tagName + ' ' + String(e.className).slice(0, 50)) };
    kids.forEach((k) => { visit(k); [...k.children].forEach(visit) });
    for (const g of [kids, ...kids.map((k) => [...k.children])]) for (let i = 0; i < g.length; i++) for (let j = i + 1; j < g.length; j++) {
      const a = g[i].getBoundingClientRect(), b = g[j].getBoundingClientRect();
      if (a.width && a.height && b.width && b.height && a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) bad.push('overlap ' + String(g[i].className).slice(0, 30) + ' / ' + String(g[j].className).slice(0, 30)) }
    return bad })()"""
STATUS = "document.querySelector('[role=status]')"
CANVASES = "document.querySelectorAll('[role=status] canvas').length"
HAS_THROW = "[...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'Throw')"
# Every thrown die has its centre inside the box that holds it. `skip`: canvases before the dice (the d20).
INSIDE = """((skip) => { const cs = [...document.querySelectorAll('[role=status] canvas')].slice(skip); const b = cs[0].parentElement.getBoundingClientRect();
  return cs.every((c) => { const r = c.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2; return x >= b.left && x <= b.right && y >= b.top && y <= b.bottom }) })(%d)"""


def attack(outcome: str, damage: list[dict] | None) -> dict:
    detail = {"kind": "attack", "title": "Flame Tongue", "subtitle": "Attack Roll · Aragorn → Goblin 1",
              "rolls": [{"who": "aragorn", "name": "Aragorn", "d20": [17], "kept": 0, "mode": "normal", "mods": [{"label": "Attack Bonus", "value": 6}],
                         "bonus": [], "total": 23, "outcome": outcome}]}
    return {**detail, "damage": damage} if damage else detail


def roll(c: Path, detail: dict | None = None, expr: str = "Flame Tongue", total: int = 23, dice: list | None = None) -> None:
    beat.append(c, [{"type": "roll", "expr": expr, "total": total, "dice": dice or [], **({"detail": detail} if detail else {})}])


async def wait_for(page: v.Page, js: str, timeout: float = 10) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if await page.eval(js):
            return True
        await asyncio.sleep(0.2)
    return False


async def closed(page: v.Page, timeout: float = 14) -> bool:
    return await wait_for(page, f"!{STATUS}", timeout)


async def reload_with(page: v.Page, url: str, prefs: dict | None) -> None:
    await page.eval(f"localStorage.setItem('dungeon-gameplay', {json.dumps(json.dumps(prefs))})" if prefs is not None else "localStorage.removeItem('dungeon-gameplay')")
    await page.call("Page.navigate", url=url)
    await asyncio.sleep(2.5)


async def scenarios(page: v.Page, c: Path, url: str) -> None:
    print("a hit: the d20 first, then the rows, then the throw")
    roll(c, attack("hit", DAMAGE))
    check("the d20 comes alone: no tray yet", await wait_for(page, f"{CANVASES} === 1", 3))
    check("then the rows wait with a Throw button", await wait_for(page, HAS_THROW, 8))
    await page.shot("tray-rows")
    text = (await page.eval(f"{STATUS}.innerText")).lower()
    check("each damage type has its row and its roll", "slashing" in text and "fire" in text and "1d8+3" in text and "2d6" in text, text.replace("\n", " | "))
    check("the d20 and the three damage dice are on screen", await page.eval(f"{CANVASES} === 4"))
    check("a hit has no gold glow", await page.eval("document.querySelectorAll('.die-crit').length") == 0)
    await page.eval("[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Throw').click()")
    await asyncio.sleep(1.0)
    await page.shot("tray-thrown")
    check("while the dice fly, no total is shown yet", "Total" not in await page.eval(f"{STATUS}.innerText"))
    check("every die is inside the box", await page.eval(INSIDE % 1))
    check("the totals show when the dice have landed", await wait_for(page, f"/Total\\s*18/.test({STATUS}.innerText)", 6), await page.eval(f"{STATUS}.innerText"))
    await page.shot("tray-landed")
    check("the dice are still inside the box", await page.eval(INSIDE % 1))
    check("the window closes by itself", await closed(page))

    print("a click on the window throws, and a click during the throw lands the dice")
    roll(c, attack("hit", DAMAGE))
    await wait_for(page, HAS_THROW, 8)
    await page.eval(f"{STATUS}.click()")
    await asyncio.sleep(0.8)
    check("the click threw the dice (the Throw button is gone)", not await page.eval(HAS_THROW))
    await page.eval(f"{STATUS}.click()")
    check("a second click lands them at once", await wait_for(page, f"/Total\\s*18/.test({STATUS}.innerText)", 2))
    await page.eval(f"{STATUS}.click()")
    check("a third click closes the window", await closed(page, 2))

    print("a critical hit: gold glow on the damage dice")
    roll(c, attack("crit", DAMAGE))
    await wait_for(page, HAS_THROW, 8)
    check("the thrown dice glow", await page.eval("document.querySelectorAll('.die-crit').length") == 3)
    await page.eval(f"{STATUS}.click()")
    await closed(page)

    print("a miss: no tray at all")
    roll(c, attack("miss", None))
    await asyncio.sleep(5)
    await page.shot("tray-miss")
    check("a miss rolls only the d20", await page.eval(f"{CANVASES} === 1") and not await page.eval(HAS_THROW))
    await closed(page)

    print("an old roll without dice groups shows the damage as text")
    roll(c, attack("hit", [{k: x for k, x in d.items() if k != "groups"} for d in DAMAGE]))
    await asyncio.sleep(5)
    check("text, and no tray", not await page.eval(HAS_THROW) and "slashing" in (await page.eval(f"{STATUS}.innerText")).lower())
    await closed(page)

    print("a plain roll: the dice, thrown after a wait")
    roll(c, None, "2d6+3", 12, [{"die": "2d6", "faces": [4, 5]}])
    check("two dice and a Throw button", await wait_for(page, f"{CANVASES} === 2 && {HAS_THROW}", 5))
    check("the wait ends by itself and the total shows", await wait_for(page, f"/12/.test({STATUS}.innerText) && !{HAS_THROW}", 8), await page.eval(f"{STATUS}.innerText"))
    await page.shot("tray-plain")
    await closed(page)

    print("a plain roll with a d20 keeps the d20 look: nothing is thrown")
    roll(c, None, "1d20", 17, [{"die": "1d20", "faces": [17]}, {"die": "1d20 dropped", "faces": [6]}])
    check("advantage: two d20 side by side, no tray", await wait_for(page, f"{CANVASES} === 2 && !({HAS_THROW})", 5))
    check("the dropped one fades and the kept one is lit", await wait_for(page, "document.querySelectorAll('[role=status] canvas.die-dropped').length === 1 && document.querySelectorAll('[role=status] canvas.die-kept').length === 1", 6))
    await closed(page)
    roll(c, None, "1d20", 20, [{"die": "1d20", "faces": [20]}])
    check("a natural 20 is one d20 and says critical", await wait_for(page, f"{CANVASES} === 1 && /critical/.test({STATUS}.innerText)", 6), await page.eval(f"{STATUS}.innerText"))
    await closed(page)
    roll(c, None, "1d20", 1, [{"die": "1d20", "faces": [1]}])
    check("a natural 1 says fumble", await wait_for(page, f"/fumble/.test({STATUS}.innerText)", 6), await page.eval(f"{STATUS}.innerText"))
    await closed(page)
    roll(c, None, "1d20+1d6", 16, [{"die": "1d20", "faces": [12]}, {"die": "1d6", "faces": [4]}])
    await asyncio.sleep(3)
    check("a d20 with other dice also keeps the d20 look", await page.eval(f"{CANVASES} === 1") and not await page.eval(HAS_THROW))
    await closed(page)

    print("a d100 and mixed dice")
    roll(c, None, "1d100+1d12", 59, [{"die": "1d100", "faces": [47]}, {"die": "1d12", "faces": [12]}])
    check("a d100 is two dice, so three dice in all", await wait_for(page, f"{CANVASES} === 3", 5))
    await page.eval(f"{STATUS}.click()")
    await closed(page)

    print("a die the game cannot draw falls back to the plain d20 look")
    roll(c, None, "1d7", 5, [{"die": "1d7", "faces": [5]}])
    await asyncio.sleep(2)
    check("one d20 shape and no Throw button", await page.eval(f"{CANVASES} === 1") and not await page.eval(HAS_THROW))
    await closed(page)

    print("the options: Text, Off, Instant and Click to throw")
    await reload_with(page, url, {"dice": "text"})
    roll(c, attack("hit", DAMAGE))
    await asyncio.sleep(5)
    check("Text: only the d20, and the damage as text", await page.eval(f"{CANVASES} === 1") and "1d8+3" in await page.eval(f"{STATUS}.innerText"))
    await closed(page)
    await reload_with(page, url, {"dice": "off"})
    roll(c, attack("hit", DAMAGE))
    await asyncio.sleep(3)
    check("Off: no roll window", not await page.eval(f"Boolean({STATUS})"))
    await reload_with(page, url, {"speed": "instant"})
    roll(c, attack("hit", DAMAGE))
    check("Instant: the dice are already landed, with the totals", await wait_for(page, f"{CANVASES} === 4 && /Total\\s*18/.test({STATUS}.innerText)", 3) and not await page.eval(HAS_THROW))
    await closed(page)
    await reload_with(page, url, {"throw": "click"})
    roll(c, attack("hit", DAMAGE))
    await wait_for(page, HAS_THROW, 8)
    await asyncio.sleep(2.5)
    check("Click to throw: the dice wait longer than a second", await page.eval(HAS_THROW))
    await page.eval(f"{STATUS}.click()")
    await closed(page)
    await reload_with(page, url, {"tiles": False})
    roll(c, attack("hit", DAMAGE))
    await asyncio.sleep(3)
    check("tiles off: the Attack Bonus tile is hidden", "Attack Bonus" not in await page.eval(f"{STATUS}.innerText"))
    await page.eval(f"{STATUS}.click()")
    await closed(page)
    await reload_with(page, url, {"hold": "click"})
    roll(c, attack("hit", DAMAGE))
    await wait_for(page, HAS_THROW, 8)
    await page.eval(f"{STATUS}.click()")
    await page.eval(f"{STATUS}.click()")
    await asyncio.sleep(9)
    check("Until I click: the window stays open past the normal hold", await page.eval(f"Boolean({STATUS})"))
    await page.eval(f"{STATUS}.click()")
    check("and a click closes it", await closed(page, 2))
    await reload_with(page, url, None)

    print("a roll that is queued behind another one is thrown at once")
    roll(c, attack("hit", DAMAGE))
    roll(c, attack("hit", DAMAGE))
    await asyncio.sleep(3.5)
    await page.shot("tray-queued")
    check("no Throw wait for a queued roll", not await page.eval(HAS_THROW))
    await page.eval(f"{STATUS}.click()")
    await asyncio.sleep(0.3)
    await page.eval(f"{STATUS}.click()")
    await asyncio.sleep(0.3)
    await closed(page, 20)

    print("a roll that waits for a click is thrown when another roll queues behind it")
    await reload_with(page, url, {"throw": "click"})
    roll(c, attack("hit", DAMAGE))
    await wait_for(page, HAS_THROW, 8)
    roll(c, attack("hit", DAMAGE))
    check("the Throw button goes away by itself", await wait_for(page, f"!({HAS_THROW})", 2))
    await page.eval(f"{STATUS}.click()")
    await asyncio.sleep(0.3)
    await page.eval(f"{STATUS}.click()")
    await closed(page, 20)
    await reload_with(page, url, None)


async def settings(page: v.Page, url: str) -> None:
    print("the Gameplay tab")
    await reload_with(page, url, None)
    await page.eval("document.querySelector('[aria-label=Menu]').click()")
    await asyncio.sleep(0.4)
    await page.click("Settings")
    await asyncio.sleep(0.6)
    await page.shot("settings-gameplay")
    tabs = await page.eval("[...document.querySelectorAll('[role=tab]')].map((t) => t.textContent.trim())")
    check("in a game: Gameplay, Combat and Voice, no DM tab", tabs == ["Gameplay", "Combat", "Voice"], str(tabs))
    text = await page.eval("document.querySelector('[role=dialog]').innerText")
    check("the options are there", all(w in text for w in ("Dice display", "Damage throw", "Roll speed", "Keep the window open", "Show what adds to the roll")))
    fonts = await page.eval("""(() => { const d = document.querySelector('[role=dialog]'); const l = [...d.querySelectorAll('legend')].map((e) => getComputedStyle(e).fontFamily);
        const tab = getComputedStyle(d.querySelector('[role=tab]')).fontFamily; return {legend: l, tab} })()""")
    check("the labels use the body font and the tabs the pixel font, as in the Voice tab",
          all("Pixel Digits" in f for f in fonts["legend"]) and "Press Start 2P" in fonts["tab"], str(fonts))
    await page.eval("[...document.querySelectorAll('[role=dialog] label')].find((l) => l.textContent.trim() === 'Fast').click()")
    await page.eval("[...document.querySelectorAll('[role=dialog] label')].find((l) => l.textContent.trim() === 'Text').click()")
    saved = json.loads(await page.eval("localStorage.getItem('dungeon-gameplay')") or "{}")
    check("a choice applies at once and is saved in the browser", saved.get("speed") == "fast" and saved.get("dice") == "text", str(saved))
    await page.eval("[...document.querySelectorAll('[role=dialog] button')].find((b) => b.textContent.trim() === 'Close').click()")
    await reload_with(page, url, None)


async def phone_story(page: v.Page, c: Path, url: str) -> None:
    """A phone is shorter than the page. The story, the choices and the cards must stack and scroll, not overlap."""
    print("a phone: the dialogue, the choices and the cards do not overlap")
    await page.call("Emulation.setDeviceMetricsOverride", width=448, height=1000, deviceScaleFactor=1, mobile=True)
    for scene in ("false", "true"):
        await page.eval(f"localStorage.setItem('dungeon-hand', JSON.stringify({{scene: {scene}, layout: 'portrait'}}))")
        await page.call("Page.navigate", url=url + "?view=player")
        await asyncio.sleep(2.5)
        beat.append(c, [{"type": "say", "actor": "ilvuur", "emotion": "neutral", "text": "Decide, Lady. Every hour we stand here, someone in your house wonders why you have not come home."},
                        {"type": "choices", "options": ["Burn the page and say nothing", "Confront the Matron with the ledger", "Warn House Mizzrym'th", "Agree and take Ilvuur as a witness"]},
                        {"type": "dm_status", "status": "idle"}])
        await wait_for(page, "[...document.querySelectorAll('button')].some((b) => b.textContent.trim().startsWith('Burn the page'))", 8)
        await asyncio.sleep(3)
        await page.shot(f"phone-story-scene-{scene}")
        check(f"the choices sit under the dialogue, the input under the choices (scene {scene})", await page.eval(ORDER))
        check(f"no block overflows its box and no two blocks overlap (scene {scene})", await page.eval(NO_OVERLAP) == [], str(await page.eval(NO_OVERLAP)))
    await page.call("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
    await page.eval("localStorage.removeItem('dungeon-hand')")


async def menu_settings(page: v.Page, url: str) -> None:
    print("the Gameplay tab in the main menu (no game running)")
    await page.call("Page.navigate", url=url)
    await asyncio.sleep(2.5)
    await page.click("Settings")
    await asyncio.sleep(0.8)
    tabs = await page.eval("[...document.querySelectorAll('[role=tab]')].map((t) => t.textContent.trim())")
    check("the menu has the DM, Gameplay and Voice tabs", tabs == ["DM", "Gameplay", "Voice"], str(tabs))
    await page.eval("[...document.querySelectorAll('[role=tab]')].find((t) => t.textContent.trim() === 'Gameplay').click()")
    await asyncio.sleep(0.4)
    await page.shot("settings-menu-gameplay")
    check("the Gameplay options show, and the DM options do not", await page.eval("/Dice display/.test(document.body.innerText) && !/Who runs the DM/.test(document.body.innerText)"))
    check("the tab says that its options apply at once", "take effect at once" in await page.eval("document.body.innerText"))


async def crowd(page: v.Page, c: Path, url: str) -> None:
    print("40 dice on a phone")
    await page.call("Emulation.setDeviceMetricsOverride", width=390, height=800, deviceScaleFactor=2, mobile=True)
    await page.call("Page.navigate", url=url + "?view=hand")
    await asyncio.sleep(2.5)
    faces = [(i * 5) % 6 + 1 for i in range(20)]
    dmg = [{"type": t, "expr": "20d6", "faces": faces, "groups": [{"die": "20d6", "faces": faces}], "total": sum(faces)} for t in ("fire", "bludgeoning")]
    roll(c, attack("hit", dmg))
    await wait_for(page, HAS_THROW, 8)
    await page.shot("tray-phone-rows")
    check("40 dice and the d20 are on screen", await page.eval(f"{CANVASES} === 41"))
    check("all the rows are inside the box", await page.eval(INSIDE % 1))
    await page.eval(f"{STATUS}.click()")
    await wait_for(page, f"/Total/.test({STATUS}.innerText)", 8)
    await page.shot("tray-phone-landed")
    check("every die landed inside the box", await page.eval(INSIDE % 1))
    check("the page has no sideways scroll", await page.eval("document.documentElement.scrollWidth <= window.innerWidth + 1"))
    await page.call("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)


def main() -> int:
    if not shutil.which("google-chrome"):
        print("skipped: Google Chrome is not installed")
        return 0
    if not (REPO / "stage" / "web" / "dist" / "index.html").exists():
        print("skipped: build the web UI first (npm run build in stage/web)")
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="visual-tray-"))
    c = campaign(tmp)
    port, debug, port2 = v.free_port(), v.free_port(), v.free_port()
    # A second stage with no campaign shows the start menu.
    threading.Thread(target=uvicorn.Server(uvicorn.Config(create_app(dm_command=["sleep", "3600"]), host="127.0.0.1", port=port2, log_level="warning")).run, daemon=True).start()
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
        url = f"http://127.0.0.1:{port}/"

        async def run() -> None:
            async with websockets.connect(tab["webSocketDebuggerUrl"], max_size=None) as ws:
                page = v.Page(ws)
                await page.call("Page.enable")
                await page.call("Emulation.setDeviceMetricsOverride", width=1500, height=950, deviceScaleFactor=1, mobile=False)
                await page.call("Page.navigate", url=url)
                await asyncio.sleep(2.5)
                await page.click("Play here")
                await asyncio.sleep(1)
                await page.click("Play all free")
                await asyncio.sleep(1.2)
                import os
                os.environ["DUNGEON_STAGE_LOG"] = str(beat.log_path(c))
                beat.append(c, [{"type": "dm_status", "status": "idle"}])
                await asyncio.sleep(1)
                await scenarios(page, c, url)
                await settings(page, url)
                await crowd(page, c, url)
                await phone_story(page, c, url)
                await menu_settings(page, f"http://127.0.0.1:{port2}/")

        asyncio.run(run())
    finally:
        chrome.terminate()
        server.should_exit = True
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{v.PASS} passed, {v.FAIL} failed")
    return 1 if v.FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
