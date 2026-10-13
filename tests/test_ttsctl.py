"""Start and stop the voice service from the settings. A fake script stands in for tts/run.sh; no real service runs."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

import view.settings as saved_settings  # noqa: E402
from stage import ttsctl, voice  # noqa: E402
from stage.server import create_app  # noqa: E402
from tests.test_stage import HOST_DEVICE, call, fixture_campaign  # noqa: E402

PASS = FAIL = 0
GUEST = "device-guest-0000000"


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + bool(cond), FAIL + (not cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}{'' if cond or not detail else f'  ({detail})'}")


async def main() -> None:
    saved_settings.SETTINGS_PATH = Path(tempfile.mkdtemp()) / "settings.json"
    os.environ.pop("DUNGEON_TTS_URL", None)
    up = {"ok": False}  # the fake service answers /health when this is true
    voice.transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"ok": up["ok"]}) if up["ok"] else httpx.Response(503)
    )
    await voice.close()
    work = Path(tempfile.mkdtemp())
    script = work / "run.sh"
    script.write_text("#!/bin/sh\nexec sleep 60\n")
    script.chmod(0o755)
    ttsctl.RUN_SH, ttsctl.LOG = script, work / "cache" / "service.log"
    (work / ".venv").mkdir()

    async def post(app, path, body=None, device=HOST_DEVICE):
        status, _, raw = await call(app, "POST", path, body or {}, device=device)
        return status, json.loads(raw or b"{}")

    async def get_status(app):
        _, _, raw = await call(app, "GET", "/api/tts/status")
        return json.loads(raw)

    print("ttsctl: no game")
    app = create_app(None)
    st = await get_status(app)
    check("no URL: cannot start", st["can_start"] is False and st["reachable"] is False)
    status, r = await post(app, "/api/tts/start")
    check("start without a URL is refused", status == 409 and not ttsctl.alive())

    status, r = await post(app, "/api/settings", {"tts_url": "ftp://x"})
    check("a bad URL is refused", status == 400)
    status, r = await post(app, "/api/settings", {"tts_url": "http://example.com:8770"})
    check("a remote URL is saved", status == 200 and r["settings"]["tts_url"] == "http://example.com:8770")
    st = await get_status(app)
    check("a remote URL cannot start", st["can_start"] is False)
    status, r = await post(app, "/api/tts/start")
    check("start for a remote URL is refused", status == 409 and not ttsctl.alive())
    status, r = await post(app, "/api/tts/stop")
    check("stop with nothing of ours is refused", status == 409)

    print("ttsctl: local URL")
    await post(app, "/api/settings", {"tts_url": "http://127.0.0.1:18770"})
    st = await get_status(app)
    check("a local URL can start", st["can_start"] is True and not st["starting"])
    (work / ".venv").rmdir()
    check("no .venv (a machine with a tunnel): cannot start", (await get_status(app))["can_start"] is False)
    (work / ".venv").mkdir()
    ttsctl.RUN_SH = work / "missing.sh"
    check("no script: cannot start", (await get_status(app))["can_start"] is False)
    ttsctl.RUN_SH = script
    try:
        status, r = await post(app, "/api/tts/start")
        check("start works", status == 200 and r["started_by_us"] and r["starting"] and not r["reachable"], str(r))
        pid = ttsctl._proc.pid
        status, r = await post(app, "/api/tts/start")
        check("a second start is refused", status == 409 and ttsctl._proc.pid == pid)
        ttsctl.shutdown()
        results = await asyncio.gather(post(app, "/api/tts/start"), post(app, "/api/tts/start"))
        check("two concurrent starts spawn one process", sorted(r[0] for r in results) == [200, 409], str(results))
        pid = ttsctl._proc.pid
        up["ok"] = True
        voice.forget_health()
        st = await get_status(app)
        check("ready: reachable and no longer starting", st["reachable"] and not st["starting"] and st["started_by_us"])
        up["ok"] = False
        status, r = await post(app, "/api/tts/stop")
        check("stop kills our process", status == 200 and not r["started_by_us"] and ttsctl._proc is None)
        try:
            os.killpg(pid, 0)
            gone = False
        except ProcessLookupError:
            gone = True
        check("the process group is gone", gone)

        up["ok"] = True
        status, r = await post(app, "/api/tts/start")
        check("start is refused when the service already answers", status == 409 and ttsctl._proc is None)
        status, r = await post(app, "/api/tts/stop")
        check("stop leaves a service we did not start", status == 409)
        up["ok"] = False

        print("ttsctl: guest during a game")
        with tempfile.TemporaryDirectory() as tmp:
            stage = await app.state.table.start(fixture_campaign(tmp), ["cat"])
            stage.seats.ensure_host(HOST_DEVICE)
            status, r = await post(app, "/api/tts/start", device=GUEST)
            check("a guest cannot start", status == 403 and ttsctl._proc is None)
            status, r = await post(app, "/api/settings", {"tts_url": "http://127.0.0.1:1"}, device=GUEST)
            check("a guest cannot save the URL", status == 403)
            status, r = await post(app, "/api/tts/start")
            check("the host can start", status == 200 and ttsctl.alive())
            status, r = await post(app, "/api/tts/stop", device=GUEST)
            check("a guest cannot stop", status == 403 and ttsctl.alive())
            status, r = await post(app, "/api/tts/stop")
            check("the host can stop", status == 200 and not ttsctl.alive())
            await app.state.table.stop()
    finally:
        ttsctl.shutdown()
        voice.transport = None
        await voice.close()

    check("the real run.sh exists", (Path(__file__).resolve().parent.parent / "tts" / "run.sh").is_file())
    check("the argv is fixed", ttsctl.argv()[1] in ("f5", "mock") and len(ttsctl.argv()) == 2)
    check("is_local sees localhost", ttsctl.is_local("http://localhost:1") and ttsctl.is_local("http://[::1]:1"))
    check("is_local rejects a far host", not ttsctl.is_local("http://example.com:1") and not ttsctl.is_local(""))
    import socket

    check("is_local rejects this machine's own hostname", not ttsctl.is_local(f"http://{socket.gethostname()}:8770"))
    check("is_local rejects a URL with no port", not ttsctl.is_local("http://127.0.0.1") and not ttsctl.is_local("http://localhost"))
    check("is_local rejects a bad port", not ttsctl.is_local("http://127.0.0.1:99999x"))

    from view import voicecmd

    argv = voicecmd.tunnel_argv("pi", 8770)
    check("the tunnel is a reverse forward bound to the far loopback", argv[-3:] == ["-R", "127.0.0.1:8770:127.0.0.1:8770", "pi"])
    check("the tunnel fails fast and keeps alive", "ExitOnForwardFailure=yes" in argv and "ServerAliveInterval=15" in argv)


if __name__ == "__main__":
    asyncio.run(main())
    print(f"\n{PASS} passed, {FAIL} failed")
    raise SystemExit(1 if FAIL else 0)
