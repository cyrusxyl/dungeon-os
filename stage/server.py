"""The stage server: one DM process per game, served to a browser.

- The DM agent runs in a PTY that this server owns. A browser reload, or a
  second tab, reconnects to the same DM; it never starts a second one.
- `/ws/pty` carries raw terminal bytes for the console drawer (xterm.js).
- `/ws` sends one snapshot of the current stage, then each new event as the
  server reads it from `{campaign}/stage/events.ndjson`.
- `/api/input` submits a line the player typed in the input box.

Allowlist: besides `{campaign}/stage/`, this server reads only state.json and
characters/*.json (for the party panel). It never opens dm_story.md,
canon.json, session_log.md, or world/*. The console drawer shows the DM's raw
terminal, which can include DM-only tool output; the UI keeps it closed by
default, as the classic view shows the same terminal.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import ptyprocess
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from stage import actors, beat, scenes, state as stage_state
from stage.assets import AssetError

STAGE_DIR = Path(__file__).resolve().parent
WEB_DIST = STAGE_DIR / "web" / "dist"
HOOK_SCRIPT = STAGE_DIR / "hook.py"
SCROLLBACK_LIMIT = 512 * 1024


class DMSession:
    """The DM agent in a PTY. A reader thread drains it, so it never blocks."""

    def __init__(self, command: list[str], env: dict, on_output, on_exit):
        self.command = command
        self.env = env
        self.on_output = on_output
        self.on_exit = on_exit
        self.scrollback = bytearray()
        self.proc: ptyprocess.PtyProcess | None = None
        self.size = (40, 120)

    def start(self) -> None:
        self.scrollback.clear()
        self.proc = ptyprocess.PtyProcess.spawn(self.command, env=self.env, dimensions=self.size)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        proc = self.proc
        while True:
            try:
                data = proc.read(65536)
            except EOFError:
                break
            self.scrollback += data
            if len(self.scrollback) > SCROLLBACK_LIMIT:
                del self.scrollback[: len(self.scrollback) - SCROLLBACK_LIMIT]
            self.on_output(data)
        self.on_exit()

    @property
    def alive(self) -> bool:
        return bool(self.proc and self.proc.isalive())

    def write(self, data: str) -> None:
        if self.alive:
            self.proc.write(data.encode())

    def resize(self, rows: int, cols: int) -> None:
        self.size = (max(rows, 5), max(cols, 20))
        if self.alive:
            self.proc.setwinsize(*self.size)

    def stop(self) -> None:
        if self.alive:
            self.proc.terminate(force=True)


class Stage:
    """Shared server state: the DM session, the derived stage, and clients."""

    def __init__(self, campaign_dir: Path, dm_command: list[str]):
        self.campaign_dir = campaign_dir
        self.log_path = beat.log_path(campaign_dir)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.touch()
        self.state = stage_state.empty()
        self.offset = 0
        self.event_clients: set[WebSocket] = set()
        self.pty_clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        env = {
            **os.environ,
            "TERM": "xterm-256color",
            "DUNGEON_STAGE_LOG": str(self.log_path),
            "DUNGEON_STAGE_HOOK": str(HOOK_SCRIPT),
        }
        self.dm = DMSession(dm_command, env, self._pty_output, self._dm_exited)

    # -- event log -------------------------------------------------------

    def read_new_events(self) -> list[dict]:
        with open(self.log_path, "rb") as f:
            f.seek(self.offset)
            chunk = f.read()
        # Only consume whole lines; a writer may be mid-line.
        end = chunk.rfind(b"\n") + 1
        self.offset += end
        events = []
        for line in chunk[:end].splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        return events

    def fold(self, events: list[dict]) -> list[dict]:
        out = []
        for event in events:
            self.state = stage_state.apply(self.state, event)
            out.append({**event, "seq": self.state["seq"]})
        return out

    async def tail(self) -> None:
        while True:
            events = self.fold(self.read_new_events())
            for event in events:
                await self.broadcast({"kind": "event", "event": event})
            await asyncio.sleep(0.15)

    async def broadcast(self, message: dict) -> None:
        for ws in list(self.event_clients):
            try:
                await ws.send_json(message)
            except Exception:
                self.event_clients.discard(ws)

    # -- DM process ------------------------------------------------------

    def _pty_output(self, data: bytes) -> None:
        if self.loop:
            self.loop.call_soon_threadsafe(asyncio.ensure_future, self._send_pty(data))

    async def _send_pty(self, data: bytes) -> None:
        for ws in list(self.pty_clients):
            try:
                await ws.send_bytes(data)
            except Exception:
                self.pty_clients.discard(ws)

    def _dm_exited(self) -> None:
        if self.loop:
            event = {"type": "dm_status", "status": "exited"}
            self.loop.call_soon_threadsafe(asyncio.ensure_future, self._local_event(event))

    async def _local_event(self, event: dict) -> None:
        # Server-side status, not written to the log: a restart must not
        # replay "exited".
        self.state = stage_state.apply(self.state, event)
        await self.broadcast({"kind": "event", "event": {**event, "seq": self.state["seq"]}})

    async def submit(self, text: str) -> None:
        """Type a player's line into the DM's prompt and press Enter."""
        line = " ".join(text.split())
        if not line:
            return
        self.dm.write(line)
        # A short gap so the TUI does not take the Enter as part of a paste.
        await asyncio.sleep(0.08)
        self.dm.write("\r")


def _party(campaign_dir: Path) -> dict:
    """Player-visible party panel: allowlisted files only."""
    out: dict = {"characters": [], "location": None, "game_time": None, "quests": []}
    try:
        st = json.loads((campaign_dir / "state.json").read_text())
        out["location"] = st.get("location")
        out["game_time"] = st.get("game_time")
        out["quests"] = [
            {"title": q.get("title"), "status": q.get("status")} for q in st.get("quest_log", [])
        ]
    except (OSError, ValueError):
        pass
    for path in sorted((campaign_dir / "characters").glob("*.json")):
        try:
            c = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        out["characters"].append({
            "id": path.stem,
            "name": c.get("name"),
            "race": c.get("race"),
            "class": c.get("class"),
            "level": c.get("level"),
            "hp": c.get("hp", {}),
            "armor_class": c.get("armor_class"),
            "inventory": [
                {"name": i.get("name"), "quantity": i.get("quantity", 1)} for i in c.get("inventory", [])
            ],
        })
    return out


def create_app(campaign_dir: Path, dm_command: list[str]) -> Starlette:
    stage = Stage(campaign_dir, dm_command)
    # Restore the stage from earlier sessions without broadcasting it.
    stage.fold(stage.read_new_events())
    stage.state["dm"] = {"status": "starting"}

    async def index(request: Request):
        page = WEB_DIST / "index.html"
        if not page.exists():
            return HTMLResponse(
                "<p>The stage UI is not built. Run: <code>npm --prefix stage/web install && "
                "npm --prefix stage/web run build</code></p>", status_code=503
            )
        return FileResponse(page)

    async def ws_events(ws: WebSocket):
        await ws.accept()
        await ws.send_json({"kind": "snapshot", "state": stage.state, "campaign": campaign_dir.name})
        stage.event_clients.add(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            stage.event_clients.discard(ws)

    async def ws_pty(ws: WebSocket):
        await ws.accept()
        await ws.send_bytes(bytes(stage.dm.scrollback))
        stage.pty_clients.add(ws)
        try:
            while True:
                msg = json.loads(await ws.receive_text())
                if msg.get("type") == "input":
                    stage.dm.write(msg.get("data", ""))
                elif msg.get("type") == "resize":
                    stage.dm.resize(int(msg["rows"]), int(msg["cols"]))
        except WebSocketDisconnect:
            stage.pty_clients.discard(ws)

    async def api_input(request: Request):
        body = await request.json()
        await stage.submit(str(body.get("text", "")))
        return JSONResponse({"ok": True})

    async def api_restart(request: Request):
        if not stage.dm.alive:
            stage.dm.start()
            await stage._local_event({"type": "dm_status", "status": "starting"})
        return JSONResponse({"ok": True, "alive": stage.dm.alive})

    async def asset_actor(request: Request):
        actor_id = request.path_params["actor_id"]
        spec = actors.load(campaign_dir, actor_id)
        if spec is None:
            return Response(status_code=404)
        emotion = request.path_params.get("emotion")
        kind = "portrait" if emotion else "full"
        try:
            png = await run_in_threadpool(
                actors.png, spec, kind, request.query_params.get("f"), emotion if emotion != "neutral" else None
            )
        except (AssetError, ValueError, OSError):
            return Response(status_code=404)
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-cache"})

    async def asset_scene(request: Request):
        spec = scenes.load(campaign_dir, request.path_params["location"])
        if spec is None:
            return Response(status_code=404)
        try:
            png = await run_in_threadpool(scenes.png, spec)
        except (AssetError, ValueError, OSError):
            return Response(status_code=404)
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-cache"})

    async def api_scene(request: Request):
        spec = scenes.load(campaign_dir, request.path_params["location"])
        try:
            mood = scenes.resolve(spec)["mood"] if spec else "day"
        except ValueError:
            mood = "day"
        return JSONResponse({"mood": mood, "has_look": spec is not None})

    async def api_actor(request: Request):
        actor_id = request.path_params["actor_id"]
        spec = actors.load(campaign_dir, actor_id) or {}
        name = spec.get("name") or actor_id.split("#")[0].replace("-", " ").title()
        if "#" in actor_id and actor_id.split("#")[1]:
            name = f"{name} {actor_id.split('#')[1]}"
        return JSONResponse({"id": actor_id, "name": name, "has_look": bool(spec)})

    async def api_party(request: Request):
        return JSONResponse(_party(campaign_dir))

    @asynccontextmanager
    async def lifespan(app):
        stage.loop = asyncio.get_running_loop()
        stage.dm.start()
        tail = asyncio.ensure_future(stage.tail())
        yield
        tail.cancel()
        stage.dm.stop()

    routes = [
        Route("/", index),
        Route("/api/input", api_input, methods=["POST"]),
        Route("/api/restart", api_restart, methods=["POST"]),
        Route("/api/party", api_party),
        Route("/api/actor/{actor_id}", api_actor),
        Route("/asset/scene/{location}.png", asset_scene),
        Route("/api/scene/{location}", api_scene),
        Route("/asset/actor/{actor_id}/full.png", asset_actor),
        Route("/asset/actor/{actor_id}/portrait/{emotion}.png", asset_actor),
        WebSocketRoute("/ws", ws_events),
        WebSocketRoute("/ws/pty", ws_pty),
    ]
    if (WEB_DIST / "assets").is_dir():
        routes.append(Mount("/assets", StaticFiles(directory=WEB_DIST / "assets")))
    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.stage = stage
    return app


def serve(campaign_dir: Path, dm_command: list[str], host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(create_app(campaign_dir, dm_command), host=host, port=port, log_level="warning")
