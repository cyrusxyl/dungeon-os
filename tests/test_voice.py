"""Checks for the TTS proxy: silence when there is no service, pass-through when there is one.

Run from the repo root:  .venv/bin/python tests/test_voice.py

Plain asserts so no test runner is needed.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import httpx  # noqa: E402

import view.settings as saved_settings  # noqa: E402
from stage import voice  # noqa: E402
from stage.beat import EMOTIONS, MOODS  # noqa: E402
from stage.server import create_app  # noqa: E402
from tests.test_stage import call, fixture_campaign  # noqa: E402

PASS = FAIL = 0
PCM = b"\x01\x00\x02\x00" * 100


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}{'' if cond or not detail else f'  ({detail})'}")


def dead_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Chunks(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield PCM[:100]
        yield PCM[100:]


def fake_service(seen: list) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, json.loads(request.content or b"{}")))
        if request.url.path == "/health":
            return httpx.Response(200, json={"ok": True, "engine": "mock", "sample_rate": 24000, "voices": ["narrator"]})
        if request.url.path == "/speak":
            return httpx.Response(200, stream=Chunks(), headers={"X-Sample-Rate": "24000", "X-Cache": "miss"})
        return httpx.Response(202)
    return httpx.MockTransport(handle)


async def main() -> None:
    saved_settings.SETTINGS_PATH = Path(tempfile.mkdtemp()) / "settings.json"  # never the real settings of this machine
    os.environ.pop("DUNGEON_TTS_URL", None)
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(None)
        stage = await app.state.table.start(fixture_campaign(tmp), ["cat"])
        stage.fold([{"type": "narrate", "text": "The door creaks open."}, {"type": "say", "actor": "x", "text": "Hello."},
                    {"type": "say", "actor": "astarion", "emotion": "disgusted", "text": "*Oh*, **lovely**."}])
        nar = next(e["seq"] for e in stage.state["log"] if e["type"] == "narrate")
        say = next(e["seq"] for e in stage.state["log"] if e.get("actor") == "x")
        mapped = next(e["seq"] for e in stage.state["log"] if e.get("actor") == "astarion")

        print("voice: no service")
        check("tts_url is None when unset", voice.tts_url() is None)
        start = time.monotonic()
        status, _, body = await call(app, "GET", f"/api/tts/line/{nar}")
        check("204 when the URL is unset", status == 204 and body == b"" and time.monotonic() - start < 0.5)
        os.environ["DUNGEON_TTS_URL"] = f"http://127.0.0.1:{dead_port()}/"
        check("the env URL is used, without a trailing slash", voice.tts_url().startswith("http://127.0.0.1:") and not voice.tts_url().endswith("/"))
        start = time.monotonic()
        status, _, body = await call(app, "GET", f"/api/tts/line/{nar}")
        check("204 when the port is dead, fast", status == 204 and time.monotonic() - start < 0.5)
        status, _, body = await call(app, "GET", "/api/tts/health")
        check("health is false when the port is dead", status == 200 and json.loads(body) == {"ok": False})
        voice.warm([{"text": "x", "voice": "narrator", "style": None}])
        await asyncio.sleep(0.1)
        check("warm does not raise on a dead port", True)

        print("voice: fake service")
        seen: list = []
        voice.transport = fake_service(seen)
        await voice.close()  # the shared client is made again with the fake transport
        voice._health.clear()
        os.environ["DUNGEON_TTS_URL"] = "http://tts.test"
        status, _, body = await call(app, "GET", f"/api/tts/line/{say}")
        check("204 for a say line with no voice mapped", status == 204 and not seen)
        (stage.campaign_dir / "stage").mkdir(exist_ok=True)
        (stage.campaign_dir / "stage" / "voices.json").write_text(json.dumps({"astarion": "astarion"}))
        status, _, body = await call(app, "GET", f"/api/tts/line/{say}")
        check("204 for an unmapped actor when a map exists", status == 204 and not seen)
        status, _, body = await call(app, "GET", f"/api/tts/line/{mapped}")
        check("a mapped say line streams", status == 200 and body == PCM)
        check("say body has voice, style, plain text",
              ("POST", "/speak", {"text": "Oh, lovely.", "voice": "astarion", "style": "disgusted", "id": str(mapped)}) in seen)
        seen.clear()
        status, _, body = await call(app, "GET", "/api/tts/line/9999")
        check("204 for an unknown seq", status == 204)
        status, ctype, body = await call(app, "GET", f"/api/tts/line/{nar}")
        check("a narrate line streams the PCM through", status == 200 and body == PCM and ctype == "application/octet-stream")
        check("the service got the text", ("POST", "/speak", {"text": "The door creaks open.", "voice": "narrator", "style": "neutral", "id": str(nar)}) in seen)
        it = voice.item({"type": "narrate", "text": "Dark.", "mood": "ominous"}, None)
        check("a narrate mood is the style", it == {"text": "Dark.", "voice": "narrator", "style": "ominous"})
        check("no mood is neutral", voice.item({"type": "narrate", "text": "Dark."}, None)["style"] == "neutral")
        style = lambda e: voice.item({"type": "say", "actor": "astarion", "text": "Hi.", "emotion": e}, stage.campaign_dir)["style"]
        check("say style is the emotion", style("angry") == "angry" and style("fearful") == "fearful")
        check("every emotion is its own voice style", all(style(e) == e for e in EMOTIONS))
        from stage.lpc import EMOTION_FACES
        check("every emotion but neutral has a face", set(EMOTION_FACES) == set(EMOTIONS) - {"neutral"})
        from stage import beat
        check("parser accepts every emotion", all(beat.parse(f"@say a {e} Hi there")[0]["emotion"] == e for e in EMOTIONS))
        check("an old name is plain text", beat.parse("@say a shock Hi there")[0]["emotion"] == "neutral")
        check("usage lists every emotion", all(e in beat.USAGE for e in EMOTIONS))
        skill = (Path(__file__).resolve().parent.parent / "game/.claude/skills/stage/SKILL.md").read_text()
        row = next(l for l in skill.splitlines() if l.startswith("| `@say"))
        check("SKILL.md emotions equal EMOTIONS", tuple(re.findall(r"`(\w+)`", row.split("Emotions:")[1].split(".")[0])) == tuple(EMOTIONS))
        status, _, body = await call(app, "GET", "/api/tts/health")
        check("health is true", json.loads(body) == {"ok": True})
        await call(app, "GET", "/api/tts/health")
        check("health is cached", sum(1 for s in seen if s[1] == "/health") == 1)
        voice.warm([{"text": "One.", "voice": "narrator", "style": None}, {"text": "Two.", "voice": "gale", "style": "warm"}])
        await asyncio.sleep(0.1)
        check("warm posts the texts", any(s[1] == "/warm" and [(i["text"], i["voice"]) for i in s[2]["items"]] == [("One.", "narrator"), ("Two.", "gale")] for s in seen))
        saved_settings.SETTINGS_PATH.write_text(json.dumps({"tts_url": "http://from.settings"}))
        os.environ.pop("DUNGEON_TTS_URL")
        check("the settings key is used without the env", voice.tts_url() == "http://from.settings")
        check("tts_url is a default setting", "tts_url" in saved_settings.DEFAULTS)
        await app.state.table.stop()

    print("voice: moods")
    doc = (REPO / "game/.claude/skills/stage/SKILL.md").read_text()
    listed = tuple(re.findall(r"^- `(\w+)`: ", doc.split("The moods are:")[1], re.M))
    check("SKILL.md lists exactly the moods in stage.beat.MOODS", listed == MOODS, f"SKILL.md has {listed}, MOODS is {MOODS}")
    voice.transport = None
    await voice.close()


if __name__ == "__main__":
    asyncio.run(main())
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
