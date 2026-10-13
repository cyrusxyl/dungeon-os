"""Start and stop the local TTS service from the settings.

The command is fixed: `tts/run.sh f5` (or `mock` when DUNGEON_TTS_ENGINE=mock). No text from a request reaches
it. Only a service started here can be stopped here. The service runs in its own process group.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from stage import voice

RUN_SH = Path(__file__).resolve().parent.parent / "tts" / "run.sh"
LOG = RUN_SH.parent / "cache" / "service.log"
START_TIMEOUT = 180.0  # seconds the model may take to load before the UI calls it failed

_proc: subprocess.Popen | None = None
_started_at = 0.0
_start_lock = asyncio.Lock()


def argv() -> list[str]:
    return [str(RUN_SH), "mock" if os.environ.get("DUNGEON_TTS_ENGINE") == "mock" else "f5"]


def is_local(url: str | None) -> bool:
    """True when `url` is a loopback address with an explicit port. tts/run.sh binds 127.0.0.1 only. No DNS lookup."""
    try:
        parts = urlparse(url or "")
        return (parts.hostname or "").lower() in ("localhost", "127.0.0.1", "::1") and parts.port is not None
    except ValueError:
        return False


def alive() -> bool:
    return _proc is not None and _proc.poll() is None


def can_start(url: str | None) -> bool:
    """A local URL and an installed service. A machine that gets its voice over a tunnel has no `tts/.venv`."""
    return is_local(url) and RUN_SH.is_file() and (RUN_SH.parent / ".venv").is_dir()


async def status() -> dict:
    url = voice.configured_url()
    reachable = await voice.probe(url) if url else False
    ours = alive()
    age = time.monotonic() - _started_at
    return {
        "url": url or "",
        "reachable": reachable,
        "started_by_us": ours,
        "starting": ours and not reachable and age < START_TIMEOUT,
        "failed": _proc is not None and not reachable and (not ours or age >= START_TIMEOUT),
        "can_start": can_start(url),
    }


async def start() -> tuple[int, dict]:
    """Start the service. Returns (http status, body). The caller polls `status()` until it is reachable."""
    async with _start_lock:  # the probe awaits: two starts must not both pass the checks and spawn
        return await _start()


async def _start() -> tuple[int, dict]:
    global _proc, _started_at
    url = voice.configured_url()
    if not can_start(url):
        return 409, {"error": "The voice server cannot start from here. Set a URL on this machine, for example http://127.0.0.1:8770."}
    if alive():
        return 409, {"error": "The voice server was already started."}
    if await voice.probe(url):
        return 409, {"error": "The voice server is already running."}
    env = dict(os.environ)
    env["TTS_PORT"] = str(urlparse(url).port)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "ab") as log:
            _proc = subprocess.Popen(argv(), cwd=RUN_SH.parent, env=env, stdin=subprocess.DEVNULL, stdout=log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
    except OSError as exc:
        return 500, {"error": f"Could not start the voice server: {exc}"}
    _started_at = time.monotonic()
    return 200, await status()


async def stop() -> tuple[int, dict]:
    """Stop the service this server started. Any other service is left alone."""
    if not alive():
        return 409, {"error": "This server did not start the voice server, so it cannot stop it."}
    await asyncio.to_thread(shutdown)
    voice.forget_health()
    return 200, await status()


def shutdown(wait: float = 5.0) -> None:
    """Stop our own process group, if it runs."""
    global _proc
    proc = _proc
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(wait)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    except (ProcessLookupError, PermissionError):
        pass
    _proc = None
