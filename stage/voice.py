"""Client for the narration TTS service (see tts/DECISIONS.md). It never raises: no service means silence."""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path

import httpx

from stage.files import read_json

CONNECT = httpx.Timeout(30.0, connect=0.3)  # a dead service must answer "no" fast; a live one may take time to speak
HEALTH_TTL = 10.0
_health: dict[str, tuple[float, bool]] = {}
_tasks: set[asyncio.Task] = set()
transport: httpx.AsyncBaseTransport | None = None  # tests set a MockTransport


def configured_url() -> str | None:
    """The service URL from the env or the settings, whether voice is on or off."""
    from view.settings import load_settings

    url = os.environ.get("DUNGEON_TTS_URL") or load_settings().get("tts_url")
    return str(url).rstrip("/") if url else None


def tts_url() -> str | None:
    from view.settings import load_settings

    return configured_url() if load_settings()["voice"] else None


def forget_health() -> None:
    """Drop the cached answers of `healthy()`."""
    _health.clear()


async def probe(url: str, timeout: object = 2.0) -> bool:
    """Ask the service at `url` if it is up. Not read from the cache; the answer goes into it."""
    try:
        ok = (await _client().get(f"{url}/health", timeout=timeout)).json().get("ok") is True
    except (httpx.HTTPError, OSError, ValueError, AttributeError):
        ok = False
    _health[url] = (time.monotonic(), ok)
    return ok


_shared: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    """One client for all calls, made on first use."""
    global _shared
    if _shared is None or _shared.is_closed:
        _shared = httpx.AsyncClient(timeout=CONNECT, transport=transport)
    return _shared


async def close() -> None:
    global _shared
    if _shared is not None:
        await _shared.aclose()
        _shared = None


class Speech:
    """An open upstream reply: `headers` and PCM16 `chunks()`. Call `close()` when done."""

    def __init__(self, response: httpx.Response):
        self.response, self.headers = response, response.headers

    async def chunks(self):
        try:
            async for chunk in self.response.aiter_raw():
                yield chunk
        finally:
            await self.close()

    async def close(self) -> None:
        await self.response.aclose()


async def speak(text: str, voice: str = "narrator", style: str | None = None, id: str = "") -> Speech | None:
    """Start the stream for `text`, or None when there is no service or it fails."""
    url = tts_url()
    if not url or not text.strip():
        return None
    client = _client()
    try:
        request = client.build_request("POST", f"{url}/speak", json={"text": text, "voice": voice, "style": style, "id": id})
        response = await client.send(request, stream=True)
    except (httpx.HTTPError, OSError):
        return None
    if response.status_code != 200:
        await response.aclose()
        return None
    return Speech(response)


def plain(text: str) -> str:
    """Text without markup, as it is read aloud."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # [label](url) -> label
    text = re.sub(r"<[^>]+>|[*_`~#]", "", text)
    return " ".join(text.split())


_voices: dict[Path, tuple[tuple[int, int], dict[str, str]]] = {}


def voices_map(campaign_dir: Path | None) -> dict[str, str]:
    """actor-id -> voice slug from `<campaign>/stage/voices.json`. Empty when the file is missing or bad. Cached by file mtime and size."""
    if not campaign_dir:
        return {}
    path = Path(campaign_dir) / "stage" / "voices.json"
    try:
        st = path.stat()
    except OSError:
        return {}
    stamp = (st.st_mtime_ns, st.st_size)  # the size too: two quick writes can share one coarse mtime
    hit = _voices.get(path)
    if hit and hit[0] == stamp:
        return hit[1]
    data = read_json(path) or {}
    found = {str(k): str(v) for k, v in data.items() if isinstance(v, str) and k != "_comment"}
    _voices[path] = (stamp, found)
    return found


def item(event: dict, campaign_dir: Path | None) -> dict | None:
    """What to speak for a log event: {text, voice, style}, or None when it stays silent."""
    kind, text = event.get("type"), plain(str(event.get("text", "")))
    if not text or kind not in ("narrate", "say", "pc_say"):
        return None
    from view.settings import load_settings

    settings = load_settings()
    parts = settings["voice_parts"]
    if not settings["voice"]:
        return None
    if kind == "narrate" and parts["narration"]:
        return {"text": text, "voice": "narrator", "style": str(event.get("mood") or "neutral")}
    if (kind == "say" and parts["npc"]) or (kind == "pc_say" and parts["player"]):
        slug = voices_map(campaign_dir).get(str(event.get("actor", "")))
        emotion = str(event.get("emotion") or "neutral")
        if slug:
            return {"text": text, "voice": slug, "style": emotion}
    return None


async def _warm(url: str, items: list[dict]) -> None:
    try:
        await _client().post(f"{url}/warm", json={"items": items})
    except (httpx.HTTPError, OSError):
        pass


def warm(items: list[dict]) -> None:
    """Fire and forget: ask the service to fill its cache. Each item is {text, voice, style}."""
    url = tts_url()
    items = [i for i in items if i and i.get("text", "").strip()]
    if not url or not items:
        return
    task = asyncio.get_running_loop().create_task(_warm(url, items))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def healthy() -> bool:
    """Is the service up? Cached for 10 seconds."""
    url = tts_url()
    if not url:
        return False
    now = time.monotonic()
    hit = _health.get(url)
    if hit and now - hit[0] < HEALTH_TTL:
        return hit[1]
    return await probe(url, timeout=httpx.USE_CLIENT_DEFAULT)
