"""The stage server: one DM process per game, served to a browser.

- The DM agent runs in a PTY that this server owns. A browser reload, or a
  second tab, reconnects to the same DM; it never starts a second one.
- `/ws/pty` carries raw terminal bytes for the console drawer (xterm.js).
- `/ws` sends one snapshot of the current stage, then each new event as the
  server reads it from `{campaign}/stage/events.ndjson`.
- `/api/input` submits a line the player typed in the input box.

Allowlist: besides `{campaign}/stage/`, this server reads only state.json and
characters/*.json (for the party panel). Site and map files under `stage/`
hold secrets (the whole layout, hidden places): the routes send only what the
party has seen or been told. It never opens dm_story.md,
canon.json, session_log.md, or world/*. The console drawer shows the DM's raw
terminal, which can include DM-only tool output; the UI keeps it closed by
default, as the classic view shows the same terminal.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

import ptyprocess
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from stage import actors, beat, crawl, maps, scenes, state as stage_state
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
        # True from a prompt we typed until the DM takes it (UserPromptSubmit
        # sets "busy"): no walking in that gap.
        self.awaiting_dm = False
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
            if event.get("type") == "dm_status" and event.get("status") != "idle":
                self.awaiting_dm = False
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
        self.awaiting_dm = True
        self.dm.write(line)
        # A short gap so the TUI does not take the Enter as part of a paste.
        await asyncio.sleep(0.08)
        self.dm.write("\r")


    def dm_ready(self) -> bool:
        return self.state["dm"].get("status") == "idle" and not self.awaiting_dm


LOCAL_HOSTS = {"127.0.0.1", "localhost"}


def request_allowed(scope_type: str, method: str, headers: dict[str, str]) -> bool:
    """Only this machine's own browser tab may drive the DM.

    The DM terminal accepts keystrokes, so a web page on another site must not
    reach it: WebSockets have no CORS, and a cross-site text/plain POST needs
    no preflight. Rules: the Host is a loopback name (also stops DNS
    rebinding); an Origin, when sent, is this same host and port; a POST is
    JSON (a plain cross-site form cannot send that without a preflight).
    """
    host = headers.get("host", "")
    if host.rsplit(":", 1)[0] not in LOCAL_HOSTS:
        return False
    origin = headers.get("origin")
    if origin is not None and origin.split("://", 1)[-1].rstrip("/") != host:
        return False
    if scope_type == "http" and method == "POST":
        return headers.get("content-type", "").split(";")[0].strip() == "application/json"
    return True


class LocalOnly:
    """ASGI middleware: refuse anything `request_allowed` refuses, websockets included."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
            if not request_allowed(scope["type"], scope.get("method", "GET"), headers):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await send({"type": "http.response.start", "status": 403,
                                "headers": [(b"content-type", b"text/plain")]})
                    await send({"type": "http.response.body", "body": b"Forbidden: local browser tab only."})
                return
        await self.app(scope, receive, send)


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


def _lead(campaign_dir: Path) -> str | None:
    """The actor id of the party marker: the first party member, else the first character."""
    try:
        members = json.loads((campaign_dir / "state.json").read_text()).get("party_members") or []
    except (OSError, ValueError):
        members = []
    if members:
        return str(members[0])
    first = next(iter(sorted((campaign_dir / "characters").glob("*.json"))), None)
    return first.stem if first else None


def site_view(campaign_dir: Path, site_id: str, site: dict) -> dict:
    view = crawl.view(site)
    for poi in view["pois"]:
        icon = poi.pop("icon")
        poi["url"] = (f"/asset/icon/{icon}.png" if icon in crawl.data()["icons"]
                      else f"/asset/actor/{icon}/full.png")
    return {**view, "id": site_id, "name": crawl.site_name(site_id, site), "lead": _lead(campaign_dir)}


def stage_first_prompt(campaign_slug: str) -> str:
    # Name the campaign: without it, the DM may "correct" active.json from memory.
    return (
        f"Start the session for the campaign `{campaign_slug}`. campaigns/active.json "
        "already points at it; do not change that file. The players watch the visual "
        "stage, so show every scene, narration line and NPC line with "
        "`uv run dnd-cli show beat` (load the `stage` skill first)."
    )


def default_command(campaign_dir: Path) -> list[str]:
    """Make the campaign active and build a fresh DM session for it."""
    from dnd_cli.campaign import GAME_DIR, set_active_campaign
    from view.settings import build_dm_command, load_settings, set_last_session_id

    set_active_campaign(campaign_dir.name)
    session_id = str(uuid.uuid4())
    set_last_session_id(campaign_dir.name, session_id)
    return build_dm_command(
        load_settings(), GAME_DIR, session_id, initial_prompt=stage_first_prompt(campaign_dir.name)
    )


class Table:
    """The one game this server runs, or none (the start menu)."""

    def __init__(self, command_factory: Callable[[Path], list[str]]):
        self.command_factory = command_factory
        self.stage: Stage | None = None
        self.tail_task: asyncio.Task | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    async def start(self, campaign_dir: Path, dm_command: list[str] | None = None) -> Stage:
        await self.stop()
        stage = Stage(campaign_dir, dm_command or self.command_factory(campaign_dir))
        stage.loop = self.loop
        # Restore the stage from earlier sessions without broadcasting it.
        stage.fold(stage.read_new_events())
        stage.state["dm"] = {"status": "starting"}
        stage.dm.start()
        self.tail_task = asyncio.ensure_future(stage.tail())
        self.stage = stage
        return stage

    async def stop(self) -> None:
        stage, self.stage = self.stage, None
        if stage is None:
            return
        if self.tail_task:
            self.tail_task.cancel()
        stage.dm.stop()
        # Clients of the old game go back to the menu.
        for ws in list(stage.event_clients) + list(stage.pty_clients):
            try:
                await ws.close()
            except Exception:
                pass


def _menu(table: Table) -> dict:
    from dnd_cli.campaign import CAMPAIGNS_DIR, active_campaign_slug, list_campaigns
    from view.settings import FRAMEWORKS, campaign_in_progress, framework_available, load_settings

    campaigns = [
        {"slug": slug, "name": name, "in_progress": campaign_in_progress(CAMPAIGNS_DIR / slug)}
        for slug, name in list_campaigns()
    ]
    try:
        active = active_campaign_slug()
    except (OSError, ValueError, KeyError):
        active = None
    resume = next((c for c in campaigns if c["slug"] == active and c["in_progress"]), None)
    settings = load_settings()
    return {
        "game": table.stage.campaign_dir.name if table.stage else None,
        "campaigns": campaigns,
        "resume": resume,
        "settings": {"agent_framework": settings["agent_framework"], "model": settings["model"]},
        "frameworks": [
            {"key": k, "label": v["label"], "available": framework_available(k), "models": v["models"]}
            for k, v in FRAMEWORKS.items()
        ],
    }


def create_app(
    campaign_dir: Path | None = None,
    dm_command: list[str] | None = None,
    command_factory: Callable[[Path], list[str]] = default_command,
) -> Starlette:
    """Serve the stage. With a campaign, start it at once; without one, open the start menu."""
    table = Table(command_factory)

    def need() -> Stage:
        if table.stage is None:
            raise HTTPException(409, "No game is running.")
        return table.stage

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
        stage = table.stage
        if stage is None:
            await ws.close(code=4000)
            return
        await ws.send_json({"kind": "snapshot", "state": stage.state, "campaign": stage.campaign_dir.name})
        stage.event_clients.add(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            stage.event_clients.discard(ws)

    async def ws_pty(ws: WebSocket):
        await ws.accept()
        stage = table.stage
        if stage is None:
            await ws.close(code=4000)
            return
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
        await need().submit(str(body.get("text", "")))
        return JSONResponse({"ok": True})

    async def api_restart(request: Request):
        stage = need()
        if not stage.dm.alive:
            stage.dm.command = table.command_factory(stage.campaign_dir)
            stage.dm.start()
            await stage._local_event({"type": "dm_status", "status": "starting"})
        return JSONResponse({"ok": True, "alive": stage.dm.alive})

    async def api_menu(request: Request):
        return JSONResponse(_menu(table))

    async def api_game_start(request: Request):
        from dnd_cli.campaign import CampaignError, create_campaign, resolve_campaign_dir

        body = await request.json()
        try:
            if body.get("new_name"):
                slug = create_campaign(str(body["new_name"]))
            else:
                slug = str(body.get("campaign", ""))
            campaign = resolve_campaign_dir(slug)
        except (CampaignError, OSError) as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        await table.start(campaign)
        return JSONResponse({"game": campaign.name})

    async def api_game_quit(request: Request):
        await table.stop()
        return JSONResponse({"game": None})

    async def api_settings(request: Request):
        from view.settings import FRAMEWORKS, save_settings

        body = await request.json()
        if body.get("agent_framework") not in FRAMEWORKS:
            return JSONResponse({"error": "unknown agent framework"}, status_code=400)
        save_settings({"agent_framework": body["agent_framework"], "model": str(body.get("model", ""))})
        return JSONResponse(_menu(table))

    async def asset_actor(request: Request):
        campaign = need().campaign_dir
        actor_id = request.path_params["actor_id"]
        spec = actors.load(campaign, actor_id)
        if spec is None:
            return Response(status_code=404)
        emotion = request.path_params.get("emotion")
        kind = "portrait" if emotion else "full"
        try:
            png = await run_in_threadpool(
                actors.png, spec, kind, request.query_params.get("f"), emotion if emotion != "neutral" else None,
                request.query_params.get("d"),
            )
        except (AssetError, ValueError, OSError):
            return Response(status_code=404)
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-cache"})

    async def asset_scene(request: Request):
        spec = scenes.load(need().campaign_dir, request.path_params["location"])
        if spec is None:
            return Response(status_code=404)
        try:
            png = await run_in_threadpool(scenes.png, spec)
        except (AssetError, ValueError, OSError):
            return Response(status_code=404)
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-cache"})

    async def asset_template(request: Request):
        """A template with no campaign, for the start menu's backdrop."""
        name = request.path_params["name"]
        spec = {"template": name, "mood": request.query_params.get("mood", "day")}
        try:
            png = await run_in_threadpool(scenes.png, spec)
        except (AssetError, ValueError, OSError):
            return Response(status_code=404)
        return Response(png, media_type="image/png")

    async def api_scene(request: Request):
        spec = scenes.load(need().campaign_dir, request.path_params["location"])
        try:
            mood = scenes.resolve(spec)["mood"] if spec else "day"
        except ValueError:
            mood = "day"
        return JSONResponse({"mood": mood, "has_look": spec is not None})

    async def api_actor(request: Request):
        actor_id = request.path_params["actor_id"]
        spec = actors.load(need().campaign_dir, actor_id) or {}
        name = spec.get("name") or actor_id.split("#")[0].replace("-", " ").title()
        if "#" in actor_id and actor_id.split("#")[1]:
            name = f"{name} {actor_id.split('#')[1]}"
        return JSONResponse({"id": actor_id, "name": name, "has_look": bool(spec)})

    async def api_party(request: Request):
        return JSONResponse(_party(need().campaign_dir))

    def error(text: str, status: int = 409) -> JSONResponse:
        return JSONResponse({"error": text}, status_code=status)

    def site_or_none(stage: Stage, request: Request) -> tuple[str, dict | None]:
        site_id = request.path_params["site_id"]
        return site_id, crawl.load(stage.campaign_dir, site_id)

    async def api_site(request: Request):
        stage = need()
        site_id, site = site_or_none(stage, request)
        if site is None:
            return error("No such site yet.", 404)
        if site["party"] is None:
            if stage.state.get("explore") != site_id:
                return error("The party has not been in this site.", 404)
            # The DM sent @explore before it set the site: arrive now.
            crawl.arrive(site)
            crawl.save(stage.campaign_dir, site_id, site)
        return JSONResponse(site_view(stage.campaign_dir, site_id, site))

    async def api_site_move(request: Request):
        stage = need()
        # Read the body first: no await between loading and saving the site.
        body = await request.json()
        site_id, site = site_or_none(stage, request)
        if site is None or site["party"] is None or stage.state.get("explore") != site_id:
            return error("The party is not exploring this site.")
        if not stage.dm_ready():
            return error("The DM is busy.")
        px, py = site["party"]
        if body.get("dir") in crawl.STEPS:
            dx, dy = crawl.STEPS[body["dir"]]
            path = [(px + dx, py + dy)]
        else:
            try:
                target = (int(body["to"][0]), int(body["to"][1]))
            except (KeyError, TypeError, ValueError, IndexError):
                return error("Give dir or to.", 400)
            path = crawl.path_to(site, target)
            if path is None:
                return error("No known way there.", 400)
        result = crawl.walk(site, path)
        crawl.save(stage.campaign_dir, site_id, site)
        if result["stopped"] == "poi":
            await stage.submit(crawl.prompt_found(site_id, site, result["pois"]))
        elif result["stopped"] == "wander":
            await stage.submit(crawl.prompt_wander(site_id, site))
        return JSONResponse({**site_view(stage.campaign_dir, site_id, site),
                             "path": result["path"], "stopped": result["stopped"]})

    async def api_site_act(request: Request):
        stage = need()
        body = await request.json()
        site_id, site = site_or_none(stage, request)
        if site is None or site["party"] is None or stage.state.get("explore") != site_id:
            return error("The party is not exploring this site.")
        if not stage.dm_ready():
            return error("The DM is busy.")
        px, py = site["party"]
        if body.get("kind") == "examine":
            poi = site["pois"].get(str(body.get("poi")))
            if poi is None or not poi["found"] or max(abs(poi["x"] - px), abs(poi["y"] - py)) > 1:
                return error("Stand next to a found point of interest to examine it.", 400)
            await stage.submit(crawl.prompt_examine(site_id, site, str(body["poi"])))
        elif body.get("kind") == "leave":
            if [px, py] != site["entrance"]:
                return error("Stand on the entrance to leave.", 400)
            await stage.submit(crawl.prompt_leave(site_id, site))
        else:
            return error("kind is examine or leave.", 400)
        return JSONResponse({"ok": True})

    async def api_map_levels(request: Request):
        stage = need()
        out = []
        for level in maps.chain(stage.campaign_dir, stage.state.get("explore"), stage.state.get("place")):
            if level["kind"] == "site":
                site = crawl.load(stage.campaign_dir, level["id"])
                name = crawl.site_name(level["id"], site) if site else crawl.title(level["id"])
            else:
                name = (maps.load(stage.campaign_dir, level["id"]) or {}).get("name", level["id"])
            out.append({**level, "name": name})
        return JSONResponse({"levels": out})

    async def api_map(request: Request):
        stage = need()
        map_id = request.path_params["map_id"]
        m = maps.load(stage.campaign_dir, map_id)
        if m is None:
            return error("No such map.", 404)
        here = maps.here(stage.campaign_dir, map_id, stage.state.get("explore"), stage.state.get("place"))
        return JSONResponse(maps.view(m, map_id, here))

    async def api_map_travel(request: Request):
        stage = need()
        body = await request.json()
        map_id, dest = str(body.get("map", "")), str(body.get("to", ""))
        m = maps.load(stage.campaign_dir, map_id)
        if m is None or dest not in m["places"] or not m["places"][dest]["known"]:
            return error("No such known place.", 400)
        origin = maps.here(stage.campaign_dir, map_id, stage.state.get("explore"), stage.state.get("place"))
        if origin is None:
            return error("The party is not on this map.", 400)
        if origin == dest:
            return error("The party is already there.", 400)
        if not stage.dm_ready():
            return error("The DM is busy.")
        await stage.submit(maps.travel_prompt(m, origin, dest))
        return JSONResponse({"ok": True})

    async def asset_crawl(request: Request):
        theme = request.path_params["theme"]
        if theme not in crawl.themes():
            return Response(status_code=404)
        try:
            png = await run_in_threadpool(crawl.atlas_png, theme)
        except (AssetError, ValueError, OSError):
            return Response(status_code=404)
        return Response(png, media_type="image/png")

    async def asset_icon(request: Request):
        try:
            png = await run_in_threadpool(crawl.icon_png, request.path_params["name"])
        except (AssetError, OSError):
            png = None
        return Response(png, media_type="image/png") if png else Response(status_code=404)

    @asynccontextmanager
    async def lifespan(app):
        table.loop = asyncio.get_running_loop()
        if campaign_dir is not None:
            await table.start(campaign_dir, dm_command)
        yield
        await table.stop()

    routes = [
        Route("/", index),
        Route("/api/menu", api_menu),
        Route("/api/game/start", api_game_start, methods=["POST"]),
        Route("/api/game/quit", api_game_quit, methods=["POST"]),
        Route("/api/settings", api_settings, methods=["POST"]),
        Route("/api/input", api_input, methods=["POST"]),
        Route("/api/restart", api_restart, methods=["POST"]),
        Route("/api/party", api_party),
        Route("/api/actor/{actor_id}", api_actor),
        Route("/asset/scene/{location}.png", asset_scene),
        Route("/api/scene/{location}", api_scene),
        Route("/asset/template/{name}.png", asset_template),
        Route("/asset/actor/{actor_id}/full.png", asset_actor),
        Route("/asset/actor/{actor_id}/portrait/{emotion}.png", asset_actor),
        Route("/api/site/{site_id}", api_site),
        Route("/api/site/{site_id}/move", api_site_move, methods=["POST"]),
        Route("/api/site/{site_id}/act", api_site_act, methods=["POST"]),
        Route("/api/map", api_map_levels),
        Route("/api/map/travel", api_map_travel, methods=["POST"]),
        Route("/api/map/{map_id}", api_map),
        Route("/asset/crawl/{theme}.png", asset_crawl),
        Route("/asset/icon/{name}.png", asset_icon),
        WebSocketRoute("/ws", ws_events),
        WebSocketRoute("/ws/pty", ws_pty),
    ]
    if (WEB_DIST / "assets").is_dir():
        routes.append(Mount("/assets", StaticFiles(directory=WEB_DIST / "assets")))
    app = Starlette(routes=routes, lifespan=lifespan, middleware=[Middleware(LocalOnly)])
    app.state.table = table
    return app


def serve(
    campaign_dir: Path | None = None,
    dm_command: list[str] | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    import uvicorn

    uvicorn.run(create_app(campaign_dir, dm_command), host=host, port=port, log_level="warning")
