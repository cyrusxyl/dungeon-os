"""The stage server: one DM process per game, served to a browser.

- The DM agent runs in a PTY that this server owns. A browser reload, or a
  second tab, reconnects to the same DM; it never starts a second one.
- `/ws/pty` carries raw terminal bytes for the console drawer (xterm.js).
- `/ws` sends a snapshot of the current stage, and a new one after each batch
  of events the server reads from `{campaign}/stage/events.ndjson`. The
  server is the only place that folds events (stage/state.py).
- `/api/input` submits a line the player typed in the input box.

Allowlist: besides `{campaign}/stage/`, this server reads only state.json,
config.json (pitch and party mode) and characters/*.json (for the party panel
and the creator). It writes characters/, players/ and state.json (through
`creation.register`, when the player makes a character), stage/actors/,
stage/effects.json (bonuses the player adds), and the combat tracker's
used actions in state.json; both only while the DM is idle.
Site and map files under `stage/` hold secrets (the whole layout, hidden
places): the routes send only what the party has seen or been told. It never
opens dm_story.md (it only checks that the file exists), canon.json,
session_log.md, or world/*. The console drawer shows the DM's raw
terminal, which can include DM-only tool output; the UI keeps it closed by
default, as the classic view shows the same terminal.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
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

from dnd_cli import actions, character, combat, effects, resources
from stage import actors, beat, crawl, lpc, maps, party, scenes, state as stage_state
from stage.assets import AssetError
from stage.files import read_json

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
        self.pending: list[str] = []  # prompts for the DM, sent one at a time when it is idle
        self.seen_ids = character_ids(campaign_dir)  # sheets that existed when the creator opened
        # Open from the start for a new party; it stays open until the player is done (not when the first sheet lands).
        self.opened = not self.seen_ids and self.party_mode() != "premade"
        env = {
            **os.environ,
            "TERM": "xterm-256color",
            "DUNGEON_STAGE_LOG": str(self.log_path),
            "DUNGEON_STAGE_HOOK": str(HOOK_SCRIPT),
        }
        self.dm = DMSession(dm_command, env, self._pty_output, self._dm_exited)

    # -- event log -------------------------------------------------------

    def read_new_events(self) -> list[dict]:
        if self.log_path.stat().st_size <= self.offset:
            return []
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

    def fold(self, events: list[dict]) -> bool:
        for event in events:
            self.state = stage_state.apply(self.state, event)
        return bool(events)

    def party_mode(self) -> str:
        return "premade" if (read_json(self.campaign_dir / "config.json") or {}).get("party") == "premade" else "create"

    def creating(self) -> bool:
        return self.opened

    def snapshot(self) -> dict:
        state = {**self.state, "creating": self.creating(), "party_mode": self.party_mode()}
        req = state.get("roll_request")
        if req and req.get("hide"):
            # A hidden DC stays on the server: the roll uses the copy in self.state.
            state["roll_request"] = {k: v for k, v in req.items() if k != "dc"}
        return {"kind": "snapshot", "state": state, "campaign": self.campaign_dir.name}

    def open_creator(self) -> None:
        self.opened = True
        self.seen_ids = character_ids(self.campaign_dir)

    def close_creator(self) -> None:
        """Close the creator; queue one prompt that names the characters made since it opened."""
        self.opened = False
        now = character_ids(self.campaign_dir)
        new = [i for i in now if i not in self.seen_ids]
        if new:
            self.pending.append(creation_done_prompt(new, joined=bool(self.seen_ids)))
            if not self.seen_ids:
                self.show_start_scene()
        self.seen_ids = now

    def show_start_scene(self) -> None:
        """Put the starting scene and the new party on stage at once, before the DM writes the first beat.

        The DM sets the starting scene last while it builds the world, so it is the newest scene file.
        """
        scenes_dir = self.campaign_dir / "stage" / "scenes"
        newest = max(scenes_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, default=None)
        if newest is not None and self.state.get("scene") is None:
            beat.append(self.campaign_dir, [{"type": "scene", "location": newest.stem,
                                             "party": beat.party(self.campaign_dir)}])

    async def tail(self) -> None:
        while True:
            if self.fold(self.read_new_events()):
                await self.broadcast(self.snapshot())
            if self.pending and self.dm_ready():
                await self.submit(self.pending.pop(0))  # busy at once: the next loop waits
            await asyncio.sleep(0.15)

    async def broadcast(self, message: dict) -> None:
        for ws in list(self.event_clients):
            try:
                await ws.send_json(message)
            except Exception:
                self.event_clients.discard(ws)

    # -- DM process ------------------------------------------------------

    def _pty_output(self, data: bytes) -> None:
        # The scrollback keeps the output; send it only when a console is open.
        if self.loop and self.pty_clients:
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
        self.fold([event])
        await self.broadcast(self.snapshot())

    async def submit(self, text: str) -> None:
        """Type a player's line into the DM's prompt and press Enter."""
        line = " ".join(text.split())
        if not line:
            return
        if self.dm.alive:
            # Busy at once, not when the hook reports it: no walk or travel slips into the gap.
            await self._local_event({"type": "dm_status", "status": "busy"})
        self.dm.write(line)
        # A short gap so the TUI does not take the Enter as part of a paste.
        await asyncio.sleep(0.08)
        self.dm.write("\r")


    def dm_ready(self) -> bool:
        return self.state["dm"].get("status") == "idle"


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


def _lead(campaign_dir: Path) -> str | None:
    """The actor id of the party marker: the first party member, else the first character."""
    members = (read_json(campaign_dir / "state.json") or {}).get("party_members") or []
    if members:
        return str(members[0])
    first = next(iter(sorted((campaign_dir / "characters").glob("*.json"))), None)
    return first.stem if first else None


def site_view(campaign_dir: Path, site_id: str, site: dict) -> dict:
    return {**crawl.view(site_id, site), "lead": _lead(campaign_dir)}


async def png_response(render, *args, static: bool = False) -> Response:
    """Render a PNG off the event loop; 404 when the art cannot be made.

    `static` art (templates, tiles, icons) never changes. Campaign art changes
    under the same URL when the DM edits a look, so the browser must ask again.
    """
    try:
        png = await run_in_threadpool(render, *args)
    except (AssetError, ValueError, OSError):
        png = None
    if not png:
        return Response(status_code=404)
    return Response(png, media_type="image/png",
                    headers={"Cache-Control": "max-age=86400" if static else "no-cache"})


def error(text: str, status: int = 409) -> JSONResponse:
    return JSONResponse({"error": text}, status_code=status)


def character_ids(campaign_dir: Path) -> list[str]:
    return sorted(p.stem for p in (campaign_dir / "characters").glob("*.json"))


def stage_first_prompt(campaign_dir: Path) -> str:
    """The DM's first prompt, chosen from the files. Written for a small model: short, explicit, one paragraph."""
    slug = campaign_dir.name
    config = read_json(campaign_dir / "config.json") or {}
    premade = config.get("party") == "premade"
    # Name the campaign: without it, the DM may "correct" active.json from memory.
    pointer = f"campaigns/active.json already points at `{slug}`; do not change that file."
    if not (campaign_dir / "dm_story.md").exists():  # exists() only: the server never reads the story bible
        pitch = str(config.get("pitch") or "").strip()
        text = (
            f"Build a new world for the campaign `{slug}`. {pointer} Run `uv run dnd-cli session brief`. "
            "Load the `worldbuilding` skill. Save the story bible (dm_story.md), the canon file with its "
            "villains and clocks, the look of the starting scene, and the map. "
            + (f"The player's pitch: {pitch.rstrip('.')}. " if pitch else "")
        )
        if premade:
            return (
                f"Build a new world for the campaign `{slug}`. {pointer} Run `uv run dnd-cli session brief`. "
                "Load the `worldbuilding` skill and the `stage` skill. "
                + (f"The player's pitch: {pitch.rstrip('.')}. " if pitch else "")
                + "Do these steps in this order. 1: save the story bible (dm_story.md). 2: add the canon villains "
                "and clocks (canon.json exists: do not run `canon init`). 3: set the look of the starting scene "
                "(`scene set`) and put it on the map (`map place`). 4: make each character the pitch names: "
                "`uv run dnd-cli character new` at level 1 (add --help), then `character level-up <id>` up to the "
                "level the pitch implies (add --asi on an Ability Score Improvement level). The SRD has one "
                "background (Acolyte) and no drow: use `--race elf --subrace high-elf` and a custom "
                '`--background "<name>" --background-skills a,b` (two skills that neither the class picks nor the '
                "race gives), and give the look with `actor set <id> race=drow ...`. 5: set each character's look "
                "with `uv run dnd-cli actor set`. 6: open the first scene with `uv run dnd-cli show beat`. "
                "Do not write files under world/ by hand. In the first beat the program puts the player character "
                "on stage: write only `@scene`, narration and `@choices`. Use the second person only if the "
                "character is the player's. Do not narrate what the player's character does or says, unless "
                "the beat sets up a choice."
            )
        return text + (
            "Set the starting scene LAST: the program shows the newest scene when the player is ready. "
            "Then load the `stage` skill now, so that the first beat is fast. "
            "Show no beat. Make no characters. Do not ask for a player name: the player makes characters on "
            'the creation screen. When all is saved, end your turn with the words "World ready."'
        )
    if not character_ids(campaign_dir) and not premade:
        return (
            f"The world for the campaign `{slug}` exists. {pointer} The player is on the creation screen and "
            "makes the characters. Show no beat. Do not ask for a player name. Do nothing and wait for the next prompt."
        )
    return (
        f"Start the session for the campaign `{slug}`. {pointer} Begin with `uv run dnd-cli session brief`. "
        "The players watch the visual "
        "stage, so show every scene, narration line and NPC line with "
        "`uv run dnd-cli show beat` (load the `stage` skill first)."
    )


def creation_done_prompt(ids: list[str], joined: bool) -> str:
    """The prompt after the player made characters. `joined`: the campaign already had a party."""
    names = ", ".join(f"`{i}`" for i in ids)
    text = (
        f"The player made new characters: {names}. For each one run `uv run dnd-cli character show <id>`. "
        "Do not set a look: the looks are saved. "
    )
    hooks = ("After the beat, add each character's `hooks` and `backstory` to the Player-Specific Hooks "
             "in dm_story.md.")
    if joined:
        return text + (
            "Each new character joins a party that has already played. Run `uv run dnd-cli character level-up <id>` "
            "until it has the party's level (add --asi on a level that gives an Ability Score Improvement). "
            "Bring them into the story at a fitting moment, with `uv run dnd-cli show beat` (load the `stage` skill first). "
            + hooks
        )
    return text + (
        "Then send the first beat at once with `uv run dnd-cli show beat` (the scene and the party are already "
        "on stage; load the `stage` skill if you have not). Do not ask for a player name. " + hooks
    )


def default_command(campaign_dir: Path) -> list[str]:
    """Make the campaign active and build a fresh DM session for it."""
    from view.settings import new_dm_session

    return new_dm_session(campaign_dir, stage_first_prompt(campaign_dir), stage=True)[1]


def make_character(campaign_dir: Path, body: dict) -> dict:
    """Build the sheet, the player file and the party entry with `creation.create`, then the story fields and the look.

    Blocking (the 5e API, files): run it in a thread. Raises RulesError, or ActorError for a bad look.
    """
    from dnd_cli import character, creation
    from dnd_cli.campaign import slugify
    from dnd_cli.combat import RulesError
    from dnd_cli.commands import rules_cmd

    def text(key: str) -> str:
        return str(body.get(key) or "").strip()

    def csv(key: str) -> str:
        value = body.get(key) or []
        return ",".join(str(v) for v in value) if isinstance(value, list) else str(value)

    name = text("name")
    char_id = base = slugify(name)
    if not char_id:
        raise RulesError("Give the character a name.")
    n = 1
    # An NPC look with the same id would make set_look fail after the sheet is written.
    while character.character_path(campaign_dir, char_id).exists() or (actors.actors_dir(campaign_dir) / f"{char_id}.json").exists():
        n += 1
        char_id = f"{base}-{n}"
    player_name = text("player_name") or "Player"
    look = body.get("look") if isinstance(body.get("look"), dict) else {}
    tokens = actors.creator_tokens(look, text("class"), name)
    actors.look_spec(char_id, tokens)  # a bad look fails before anything is written
    lines = creation.create(
        campaign_dir, rules_cmd._api, char_id, player_name=player_name, player=slugify(player_name) or "player",
        name=name, race=text("race"), subrace=text("subrace") or None, cls=text("class"), background=text("background"),
        scores=csv("scores"), assign=csv("assign"), skills=csv("skills"), background_skills=csv("background_skills") or None,
        cantrips=csv("cantrips") or None, spells=csv("spells") or None, equipment=csv("equipment") or None,
        alignment=text("alignment"), bonus_abilities=csv("bonus_abilities") or None)
    data = character.load(campaign_dir, char_id)
    for key in ("personality_traits", "ideals", "bonds", "flaws", "backstory"):
        if text(key):
            data[key] = text(key)
    if isinstance(body.get("hooks"), dict):
        data["hooks"] = {str(k): str(v).strip() for k, v in body["hooks"].items() if str(v).strip()}
    character.save(campaign_dir, char_id, data)
    actors.set_look(campaign_dir, char_id, tokens)
    return {"id": char_id, "lines": lines[:-1]}  # the last line asks the DM to ask the player: the creator did


class Table:
    """The one game this server runs, or none (the start menu)."""

    def __init__(self, command_factory: Callable[[Path], list[str]]):
        self.command_factory = command_factory
        self.stage: Stage | None = None
        self.tail_task: asyncio.Task | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.on_start: Callable[[], None] = lambda: None

    async def start(self, campaign_dir: Path, dm_command: list[str] | None = None) -> Stage:
        await self.stop()
        self.on_start()
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
        await ws.send_json(stage.snapshot())
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
                slug = create_campaign(str(body["new_name"]), str(body.get("pitch") or ""),
                                       str(body.get("party") or "create"))
            else:
                slug = str(body.get("campaign", ""))
            campaign = resolve_campaign_dir(slug)
        except (CampaignError, OSError) as e:
            return error(str(e), 400)
        await table.start(campaign)
        return JSONResponse({"game": campaign.name})

    async def api_game_quit(request: Request):
        await table.stop()
        return JSONResponse({"game": None})

    async def api_settings(request: Request):
        from view.settings import FRAMEWORKS, save_settings

        body = await request.json()
        if body.get("agent_framework") not in FRAMEWORKS:
            return error("unknown agent framework", 400)
        save_settings({"agent_framework": body["agent_framework"], "model": str(body.get("model", ""))})
        return JSONResponse(_menu(table))

    async def asset_actor(request: Request):
        campaign = need().campaign_dir
        actor_id = request.path_params["actor_id"]
        emotion = request.path_params.get("emotion")
        q = request.query_params

        def render():
            spec = actors.load(campaign, actor_id)
            return spec and actors.png(spec, "portrait" if emotion else "full", q.get("f"),
                                       emotion if emotion != "neutral" else None, q.get("d"))
        return await png_response(render)

    # -- character creation ---------------------------------------------

    rules = {"lock": threading.Lock(), "doc": None}

    def options_doc() -> dict:
        """The creator's options, built once (slow on a cold cache). Raises RulesError."""
        from dnd_cli import creation
        from dnd_cli.commands import rules_cmd

        with rules["lock"]:
            if rules["doc"] is None:
                rules["doc"] = creation.options(rules_cmd._api)
            return rules["doc"]

    def prefetch() -> None:
        def run():
            try:
                options_doc()
            except Exception:
                pass  # the route reports it when the player asks
        threading.Thread(target=run, daemon=True).start()
    table.on_start = prefetch

    async def api_creation_options(request: Request):
        from dnd_cli.combat import RulesError

        try:
            return JSONResponse(await run_in_threadpool(options_doc))
        except (RulesError, OSError, KeyError):
            return error("The 5e rules API cannot be reached. Check the network and try again.", 503)

    async def asset_look(request: Request):
        q = request.query_params
        look = {k: q[k] for k in ("race", "body", "skin", "eyes", "hair") if q.get(k)}

        def render():
            spec, _ = actors.look_spec("preview", actors.creator_tokens(look, q.get("class", "")))
            return actors.png(spec, "full" if q.get("kind") == "full" else "portrait")
        return await png_response(render)

    async def api_creation_character(request: Request):
        from dnd_cli.character import CharacterError
        from dnd_cli.combat import RulesError

        stage = need()
        body = await request.json()
        try:
            made = await run_in_threadpool(make_character, stage.campaign_dir, body)
        except (RulesError, CharacterError, lpc.ActorError, AssetError) as e:
            return error(str(e), 400)
        return JSONResponse(made)

    async def api_creation_open(request: Request):
        stage = need()
        stage.open_creator()
        await stage.broadcast(stage.snapshot())
        return JSONResponse({"ok": True})

    async def api_creation_done(request: Request):
        stage = need()
        stage.close_creator()
        await stage.broadcast(stage.snapshot())
        return JSONResponse({"ok": True})

    async def asset_scene(request: Request):
        campaign = need().campaign_dir
        location = request.path_params["location"]

        def render():
            spec = scenes.load(campaign, location)
            return spec and scenes.png(spec)
        return await png_response(render)

    async def asset_template(request: Request):
        """A template with no campaign, for the start menu's backdrop."""
        spec = {"template": request.path_params["name"], "mood": request.query_params.get("mood", "day")}
        return await png_response(scenes.png, spec, static=True)

    async def asset_filler(request: Request):
        return await png_response(scenes.filler_png, static=True)

    async def api_scene(request: Request):
        spec = scenes.load(need().campaign_dir, request.path_params["location"])
        try:
            mood = scenes.resolve(spec)["mood"] if spec else "day"
        except ValueError:
            mood = "day"
        return JSONResponse({"mood": mood, "has_look": spec is not None})

    async def api_actor(request: Request):
        actor_id = request.path_params["actor_id"]
        # The kind fallback can search the monster tiles: not on the event loop.
        spec = await run_in_threadpool(actors.load, need().campaign_dir, actor_id) or {}
        name = spec.get("name") or beat.title(actor_id)
        if "#" in actor_id and actor_id.split("#")[1]:
            name = f"{name} {actor_id.split('#')[1]}"
        return JSONResponse({"id": actor_id, "name": name, "has_look": bool(spec)})

    async def api_party(request: Request):
        return JSONResponse(await run_in_threadpool(party.view, need().campaign_dir))

    # -- the player's own bonuses, actions and rolls (only while the DM is idle) ----

    def idle_stage() -> Stage:
        stage = need()
        if not stage.dm_ready():
            raise HTTPException(409, "The DM is busy.")
        return stage

    def pc_or_404(stage: Stage, who: object) -> str:
        who = str(who)
        if not beat.ID_RE.match(who) or not character.character_path(stage.campaign_dir, who).exists():
            raise HTTPException(404, "No such character.")
        return who

    rolling = threading.Lock()

    def with_rules(stage: Stage, fn):
        """Run rules code on the campaign's state with the stage log set (so rolls show), and save the state."""
        with rolling:
            os.environ["DUNGEON_STAGE_LOG"] = str(stage.log_path)
            try:
                state = combat.load_state(stage.campaign_dir)
                out = fn(state)
                combat.save_state(stage.campaign_dir, state)
                return out
            finally:
                del os.environ["DUNGEON_STAGE_LOG"]

    async def api_effects(request: Request):
        """A party member gives a bonus (a spell they know, Bardic Inspiration). The cost is spent; nothing else is on offer."""
        stage = idle_stage()
        body = await request.json()
        who = pc_or_404(stage, body.get("who"))
        src = pc_or_404(stage, body.get("from") or who)
        try:
            await run_in_threadpool(with_rules, stage, lambda st: actions.grant(stage.campaign_dir, st, src, who, str(body.get("effect"))))
        except (combat.RulesError, character.CharacterError) as e:
            return error(str(e), 400)
        return JSONResponse({"ok": True})

    async def api_action(request: Request):
        """A common action or class feature from the character card. An attack or a feature goes to the DM to narrate."""
        stage = idle_stage()
        body = await request.json()
        who = pc_or_404(stage, body.get("who"))
        target = body.get("target")
        weapon = body.get("weapon")
        try:
            done = await run_in_threadpool(with_rules, stage, lambda st: actions.perform(
                stage.campaign_dir, st, who, str(body.get("action")), str(target) if target else None,
                str(weapon) if weapon else None))
        except (combat.RulesError, character.CharacterError) as e:
            return error(str(e), 400)
        name = character.load(stage.campaign_dir, who).get("name", who)
        if roll := done.get("roll"):
            # Hide and Shove: the player rolls in the roll window like for any check the DM asks for.
            state = combat.load_state(stage.campaign_dir)
            preview = combat.roll_preview(stage.campaign_dir, state, who, roll["what"])
            await stage._local_event({"type": "roll_request", "who": who, "what": roll["what"], "hide": True,
                                      "note": roll["note"], **preview, "title": roll["title"]})
            return JSONResponse({"roll": True})
        look = ""
        if target and str(body.get("action")) == "attack":
            # The player sees no numbers: the story must show how hard the blow was and how the creature looks now.
            state = combat.load_state(stage.campaign_dir)
            band = combat.health_band(combat.combatant(stage.campaign_dir, state, str(target)))
            look = (f" {target} now looks {band}: describe the blow and its wound so the player can tell how much damage "
                    "it did and how much the creature may have left, with no numbers.")
        await stage.submit(f"[{name} acts from the character card] " + " ".join(done["lines"]) + look
                           + " Narrate it. It is still their turn: wait for what they do next.")
        return JSONResponse({"lines": done["lines"]})

    async def api_end_turn(request: Request):
        """The player ends their turn: the tracker moves on, and the DM runs the creatures until a player character is up."""
        stage = idle_stage()
        body = await request.json()
        who = pc_or_404(stage, body.get("who"))
        try:
            lines = await run_in_threadpool(with_rules, stage, lambda st: combat.end_turn(stage.campaign_dir, st, who))
        except combat.RulesError as e:
            return error(str(e), 400)
        state = combat.load_state(stage.campaign_dir)
        now = state["active_encounter"]["current_turn"]
        name = character.load(stage.campaign_dir, who).get("name", who)
        if character.character_path(stage.campaign_dir, now).exists():
            todo = "It is a player character's turn now: narrate the change in one beat, then wait for the player."
        else:
            todo = (f"It is {now}'s turn: run it with the rules commands (attack, save), narrate it, then `encounter next`. "
                    "Repeat for each creature until a player character is up, then wait for the player.")
        await stage.submit(f"[{name} ends their turn] " + " ".join(lines) + " " + todo)
        return JSONResponse({"lines": lines})

    async def api_resource(request: Request):
        """Spend (or give back) one use of a class resource."""
        stage = idle_stage()
        body = await request.json()
        who = pc_or_404(stage, body.get("who"))

        def go():
            sheet = character.load(stage.campaign_dir, who)
            resources.spend(sheet, str(body.get("name")), -1 if body.get("back") else 1)
            character.save(stage.campaign_dir, who, sheet)
        try:
            await run_in_threadpool(go)
        except KeyError:
            return error("No such resource.", 400)
        return JSONResponse({"ok": True})

    def roll_for(stage: Stage, req: dict, skip: list[str]) -> list[str]:
        """The roll the DM asked for, made with the same rules code as `dnd-cli check`; the stage shows it."""
        return with_rules(stage, lambda st: combat.check(stage.campaign_dir, st, [req["who"]], req["what"], dc=req.get("dc"),
                                                    hide_dc=bool(req.get("hide")), skip=skip))

    async def api_roll(request: Request):
        """The player clicks Roll in the roll window: roll it, show it, and tell the DM the result."""
        stage = idle_stage()
        body = await request.json()
        req = stage.state.get("roll_request")
        if not req:
            return error("No roll is waiting.", 409)
        skip = [str(x) for x in body.get("skip", []) if isinstance(x, str)]
        # Clear the request at once: a double click must not roll twice.
        await stage._local_event({"type": "roll_done"})
        try:
            lines = await run_in_threadpool(roll_for, stage, req, skip)
        except (combat.RulesError, character.CharacterError) as e:
            return error(str(e), 400)
        await stage.submit(f"[{req.get('name', req['who'])} rolled in the roll window] " + " ".join(lines)
                           + (f" {req['note']}" if req.get("note") else "") + " Narrate the outcome.")
        return JSONResponse({"lines": lines})

    async def api_spell_levels(request: Request):
        """Spell index -> level, to group a spell list by level (the 5e API's spell list, cached on disk)."""
        from dnd_cli.api import api_get

        data, err, _ = await run_in_threadpool(api_get, "spells")
        if err or not data:
            return JSONResponse({})
        return JSONResponse({s["index"]: s.get("level", 0) for s in data.get("results", [])})

    async def api_spell(request: Request):
        """One spell for the spell tooltip, from the 5e API (cached on disk)."""
        index = request.path_params["index"].lower().replace("'", "")
        if not beat.SLUG_RE.match(index):
            return error("No such spell.", 404)
        from dnd_cli.api import api_get

        data, err, _ = await run_in_threadpool(api_get, f"spells/{index}")
        if err or not data:
            return error("The spell is not in the 5e API.", 404)
        return JSONResponse({
            "index": index, "name": data.get("name"), "level": data.get("level"),
            "school": (data.get("school") or {}).get("name"), "casting_time": data.get("casting_time"),
            "range": data.get("range"), "duration": data.get("duration"), "concentration": data.get("concentration"),
            "ritual": data.get("ritual"), "components": data.get("components"),
            "desc": " ".join(data.get("desc", []))[:600],
            "higher_level": " ".join(data.get("higher_level", []))[:300],
            "damage": ((data.get("damage") or {}).get("damage_type") or {}).get("name"),
            "save": ((data.get("dc") or {}).get("dc_type") or {}).get("name"),
        })

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

    async def exploring(request: Request):
        """(stage, body, site_id, site), or an error response, for an action in the site the party explores."""
        stage = need()
        # Read the body first: no await between loading and saving the site.
        body = await request.json()
        site_id, site = site_or_none(stage, request)
        if site is None or site["party"] is None or stage.state.get("explore") != site_id:
            return error("The party is not exploring this site.")
        if not stage.dm_ready():
            return error("The DM is busy.")
        return stage, body, site_id, site

    async def api_site_move(request: Request):
        got = await exploring(request)
        if isinstance(got, Response):
            return got
        stage, body, site_id, site = got
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
        got = await exploring(request)
        if isinstance(got, Response):
            return got
        stage, body, site_id, site = got
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
        found = maps.all_maps(stage.campaign_dir)
        out = []
        for level in maps.chain(found, stage.state.get("explore"), stage.state.get("place")):
            if level["kind"] == "site":
                site = crawl.load(stage.campaign_dir, level["id"])
                name = crawl.site_name(level["id"], site) if site else beat.title(level["id"])
            else:
                name = found[level["id"]]["name"]
            out.append({**level, "name": name})
        return JSONResponse({"levels": out})

    async def api_map(request: Request):
        stage = need()
        map_id = request.path_params["map_id"]
        found = maps.all_maps(stage.campaign_dir)
        m = found.get(map_id)
        if m is None:
            return error("No such map.", 404)
        here = maps.here(found, map_id, stage.state.get("explore"), stage.state.get("place"))
        return JSONResponse(maps.view(m, map_id, here))

    async def api_map_travel(request: Request):
        stage = need()
        body = await request.json()
        map_id, dest = str(body.get("map", "")), str(body.get("to", ""))
        found = maps.all_maps(stage.campaign_dir)
        m = found.get(map_id)
        if m is None or dest not in m["places"] or not m["places"][dest]["known"]:
            return error("No such known place.", 400)
        origin = maps.here(found, map_id, stage.state.get("explore"), stage.state.get("place"))
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
        return await png_response(crawl.atlas_png, theme, static=True)

    async def asset_icon(request: Request):
        return await png_response(crawl.icon_png, request.path_params["name"], static=True)

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
        Route("/api/effects", api_effects, methods=["POST"]),
        Route("/api/action", api_action, methods=["POST"]),
        Route("/api/end-turn", api_end_turn, methods=["POST"]),
        Route("/api/resource", api_resource, methods=["POST"]),
        Route("/api/roll", api_roll, methods=["POST"]),
        Route("/api/spells", api_spell_levels),
        Route("/api/spell/{index}", api_spell),
        Route("/api/actor/{actor_id}", api_actor),
        Route("/api/creation/options", api_creation_options),
        Route("/api/creation/character", api_creation_character, methods=["POST"]),
        Route("/api/creation/open", api_creation_open, methods=["POST"]),
        Route("/api/creation/done", api_creation_done, methods=["POST"]),
        Route("/asset/look.png", asset_look),
        Route("/asset/scene/{location}.png", asset_scene),
        Route("/api/scene/{location}", api_scene),
        Route("/asset/template/{name}.png", asset_template),
        Route("/asset/filler.png", asset_filler),
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
    async def http_error(request: Request, exc: HTTPException):
        return error(str(exc.detail), exc.status_code)

    app = Starlette(routes=routes, lifespan=lifespan, middleware=[Middleware(LocalOnly)],
                    exception_handlers={HTTPException: http_error})
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
