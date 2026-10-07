"""The stage server: one DM process per game, served to a browser.

- The DM agent runs in a PTY that this server owns. A browser reload, or a
  second tab, reconnects to the same DM; it never starts a second one.
- `/ws/pty` carries raw terminal bytes for the console drawer (xterm.js).
- `/ws` sends a snapshot of the current stage, and a new one after each batch
  of events the server reads from `{campaign}/stage/events.ndjson`. The
  server is the only place that folds events (stage/state.py).
- `/api/input` submits a line the player typed in the input box.

Who may do what: a device is a browser with a random token (X-Device header, `?d=` on a websocket; see
stage/seats.py). The first device is the host: Save, Load, Quit, Restart and the DM console are host-only. A
player acts only for the characters its device has claimed (a seat), and its lines reach the DM tagged
`[Player as Character]`. There is no password; the Host header check below still guards DNS rebinding.

Allowlist: besides `{campaign}/stage/`, this server reads only state.json,
config.json (pitch and party mode) and characters/*.json (for the party panel
and the creator). It writes characters/, players/ and state.json (through
`creation.register`, when the player makes a character), stage/actors/,
stage/effects.json (bonuses the player adds), and the combat tracker's
used actions in state.json; both only while the DM is idle. Saves (dnd_cli/saves.py) are git commits of the whole
campaign folder: git copies the files; this server never reads them for that.
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
import sys
import threading
import time
from collections.abc import Callable, Iterable
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

from dnd_cli import actions, character, combat, effects, resources, saves
from dnd_cli.sheet import GOLD
from stage import actors, beat, crawl, lpc, maps, party, scenes, state as stage_state
from stage.assets import AssetError
from stage.files import read_json
from stage.seats import DEVICE_RE, SeatError, Seats, sid

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
        self.client_device: dict[WebSocket, str | None] = {}  # who each stage socket is, to filter its snapshot
        self.intents: dict[str, str] = {}  # character id -> what the player said while the DM awaits everyone
        self.pty_clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.seats = Seats()
        self.creators: set[str] = set()  # the devices that have the character creator open (a phone each, at a party start)
        self.initial = False  # the creator phase is the first party: only the host starts the adventure
        self.reads: dict[str, int] = {}  # device -> seq of the story line it shows now; the table follows the furthest
        self.holdings: dict[str, dict[str, int]] = {}  # character id -> item -> quantity, to tell the owner what changed
        self.sheet_mtimes: dict[Path, int] = {}
        self.pending: list[str] = []  # prompts for the DM, sent one at a time when it is idle
        self.seen_ids = character_ids(campaign_dir)  # sheets that existed when the creator opened
        # Open from the start for a new party; it stays open until the player is done (not when the first sheet lands).
        self.opened = not self.seen_ids and self.party_mode() != "premade"
        self.initial = self.opened
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
        if not self.state.get("await"):
            self.intents.clear()
        return bool(events)

    def remember_session(self, session_id: str) -> None:
        from view.settings import get_last_session_id, load_settings, set_last_session_id

        if get_last_session_id(self.campaign_dir.name) != session_id:
            set_last_session_id(self.campaign_dir.name, session_id, load_settings()["agent_framework"])

    def autosave(self, label: str | None = None) -> None:
        """Save after each DM turn. The game goes on if git is missing or fails."""
        try:
            saves.save(self.campaign_dir, saves.AUTO, label or self.save_label())
        except (saves.SaveError, OSError) as exc:
            print(f"dungeon-os: autosave failed: {exc}", file=sys.stderr)

    def party_mode(self) -> str:
        return "premade" if (read_json(self.campaign_dir / "config.json") or {}).get("party") == "premade" else "create"

    def creating(self) -> bool:
        return self.opened

    def awaiting(self) -> dict | None:
        """Who the DM waits for: `waiting` still owe an answer, `answered` have given one. Public: no text."""
        aw = self.state.get("await")
        if not aw:
            return None
        if aw["who"] != "all":
            # A character that nobody plays, or whose player is away, awaits nobody: the table goes on.
            seated = aw["who"] in self.seats.owners and aw["who"] not in self.seats.away
            return {"who": aw["who"], "waiting": [aw["who"]] if seated else [], "answered": []}
        # One device is one answerer: a player who runs several characters answers once, as one of them.
        present = [who for who in self.seats.owners if who not in self.seats.away]
        done = {self.seats.owners[w] for w in self.intents if w in self.seats.owners}
        return {"who": "all", "waiting": [w for w in present if self.seats.owners[w] not in done],
                "answered": [w for w in present if self.seats.owners[w] in done]}

    def snapshot(self, device: str | None = None) -> dict:
        """The stage as one device may see it: whispers and targeted choices only for their player, the DM's log only for the host."""
        state = {**self.state, "creating": self.creating(), "party_mode": self.party_mode(), **self.seats.public(),
                 "creators": [sid(d) for d in sorted(self.creators)], "new_party": self.initial, "awaiting": self.awaiting(),
                 "shown_seq": self.shown_seq()}
        mine = set(self.seats.mine(device))
        state["private"] = [p for p in self.state["private"] if p["who"] in mine]
        state["notices"] = [n for n in self.state["notices"] if n["who"] in mine]
        choices = state.get("choices")
        if choices and choices.get("who") and choices["who"] not in mine:
            state["choices"] = None
        if not self.seats.is_host(device):
            state["dm_log"] = []
        req = state.get("roll_request")
        if req and req.get("hide"):
            # A hidden DC stays on the server: the roll uses the copy in self.state.
            state["roll_request"] = {k: v for k, v in req.items() if k != "dc"}
        return {"kind": "snapshot", "state": state, "campaign": self.campaign_dir.name}

    def open_creator(self, device: str | None = None) -> None:
        """Open the creator for a device. The first one to open starts the phase; later ones join it."""
        if not self.opened:
            self.opened = True
            self.seen_ids = character_ids(self.campaign_dir)
            self.initial = not self.seen_ids
        if device:
            self.creators.add(device)

    def leave_creator(self, device: str, is_host: bool, force: bool = False) -> bool:
        """A device is done with the creator. The first party starts when the host says so; a later joiner closes it when the last creator leaves."""
        self.creators.discard(device)
        if force or (not self.creators and (is_host or not self.initial)):
            self.close_creator()
            return True
        return False

    def close_creator(self) -> None:
        """Close the creator; queue one prompt that names the characters made since it opened."""
        self.opened = False
        self.creators.clear()
        now = character_ids(self.campaign_dir)
        new = [i for i in now if i not in self.seen_ids]
        if new:
            self.pending.append(creation_done_prompt(new, joined=bool(self.seen_ids)))
            if not self.seen_ids:
                self.show_start_scene()
        self.seen_ids = now

    def shown_seq(self) -> int | None:
        """The story line the players read now: the furthest of the seated devices. None until one of them reports."""
        seen = [seq for d, seq in self.reads.items() if self.seats.mine(d)]
        return max(seen) if seen else None

    def inventory_notices(self) -> list[dict]:
        """What each character gained or lost since the last look. A sheet seen for the first time sets the baseline and says nothing."""
        notices = []
        for path in sorted((self.campaign_dir / "characters").glob("*.json")):
            mtime = path.stat().st_mtime_ns
            if self.sheet_mtimes.get(path) == mtime:
                continue
            self.sheet_mtimes[path] = mtime
            if (sheet := read_json(path)) is None:
                continue
            now: dict[str, int] = {}
            for item in sheet.get("inventory", []):
                name = item.get("name", "?")
                now[name] = now.get(name, 0) + item.get("quantity", 1)
            before = self.holdings.get(path.stem)
            self.holdings[path.stem] = now
            if before is None:
                continue
            lines = []
            for name in {**before, **now}:
                delta = now.get(name, 0) - before.get(name, 0)
                if delta:
                    what = f"{abs(delta)} gp" if name == GOLD else name + (f" ×{abs(delta)}" if abs(delta) > 1 else "")
                    lines.append(("+" if delta > 0 else "−") + what)
            if lines:
                notices.append({"type": "notice", "who": path.stem, "lines": lines, "id": time.time_ns()})
        return notices

    def show_start_scene(self) -> None:
        """Put the starting scene and the new party on stage at once, before the DM writes the first beat.

        The DM sets the starting scene last while it builds the world, so it is the newest scene file.
        """
        scenes_dir = self.campaign_dir / "stage" / "scenes"
        newest = max(scenes_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, default=None)
        if newest is not None and self.state.get("scene") is None:
            beat.append(self.campaign_dir, [{"type": "scene", "location": newest.stem,
                                             "party": beat.party(self.campaign_dir)}])

    def save_label(self) -> str:
        """Where the story stands, for the save list: the last line on the log."""
        last = (self.state["log"] or [{}])[-1]
        text = " ".join(str(last.get("text", "")).split())
        who = f"{last['actor']}: " if last.get("actor") else ""
        return (who + text)[:80] or "start of the game"

    async def tail(self) -> None:
        while True:
            events = self.read_new_events()
            was_busy = self.state["dm"].get("status") != "idle"
            events += self.inventory_notices()  # a notice is for the owner's snapshot only (see `snapshot`); it is not in the log
            if self.fold(events):
                await self.broadcast()
            session = next((e["session"] for e in reversed(events) if e.get("session")), None)
            if session:
                await asyncio.to_thread(self.remember_session, session)
            if was_busy and self.state["dm"].get("status") == "idle":
                await asyncio.to_thread(self.autosave)
            if self.pending and self.dm_ready():
                await self.submit(self.pending.pop(0))  # busy at once: the next loop waits
            await asyncio.sleep(0.15)

    async def broadcast(self) -> None:
        """Send the stage to every stage socket. It is built again for each one, so it holds only what that device may see."""
        for ws in list(self.event_clients):
            try:
                await ws.send_json(self.snapshot(self.client_device.get(ws)))
            except Exception:
                self.event_clients.discard(ws)
                self.client_device.pop(ws, None)

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
        await self.broadcast()

    def away_note(self) -> str:
        names = [self.char_name(w) for w in sorted(self.seats.away) if w in self.seats.owners]
        return f" Away, skip their turns: {', '.join(names)}." if names else ""

    def char_name(self, who: str) -> str:
        try:
            return character.load(self.campaign_dir, who).get("name", who)
        except character.CharacterError:
            return who  # the DM named a character that has no sheet

    async def flush_intents(self, force: bool = False) -> bool:
        """Send the collected answers to the DM as one prompt, once every present player has answered (or the host forces it)."""
        aw = self.state.get("await")
        self.intents = {w: t for w, t in self.intents.items() if w in self.seats.owners}  # a freed seat answers no more
        if not (aw and aw["who"] == "all" and self.intents and self.dm_ready()):
            return False
        if self.awaiting()["waiting"] and not force:
            return False
        parts = " | ".join(f"[{self.seats.player(None, w)} as {self.char_name(w)}] {t}" for w, t in self.intents.items())
        self.intents.clear()
        await self._local_event({"type": "await_done"})
        await self.submit(f"[The players answer together] {parts} Resolve each answer, then narrate one beat." + self.away_note())
        return True

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


def request_allowed(scope_type: str, method: str, headers: dict[str, str], hosts: frozenset[str] = frozenset(LOCAL_HOSTS)) -> bool:
    """Only a browser tab of this site may talk to the server, and only on a host name the owner allowed.

    The DM terminal accepts keystrokes, so a web page on another site must not
    reach it: WebSockets have no CORS, and a cross-site text/plain POST needs
    no preflight. Rules: the Host is a loopback name or one the owner allowed
    with `--allow-host` (this also stops DNS rebinding); an Origin, when sent, is this same host and port; a POST is
    JSON (a plain cross-site form cannot send that without a preflight).
    """
    host = headers.get("host", "")
    if host.rsplit(":", 1)[0].lower() not in hosts:
        return False
    origin = headers.get("origin")
    if origin is not None and origin.split("://", 1)[-1].rstrip("/") != host:
        return False
    if scope_type == "http" and method == "POST":
        return headers.get("content-type", "").split(";")[0].strip() == "application/json"
    return True


class LocalOnly:
    """ASGI middleware: refuse anything `request_allowed` refuses, websockets included."""

    def __init__(self, app, hosts: frozenset[str] = frozenset(LOCAL_HOSTS)):
        self.app = app
        self.hosts = hosts

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
            if not request_allowed(scope["type"], scope.get("method", "GET"), headers, self.hosts):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await send({"type": "http.response.start", "status": 403,
                                "headers": [(b"content-type", b"text/plain")]})
                    await send({"type": "http.response.body", "body": b"Forbidden: this host name or page origin is not allowed."})
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


def stage_first_prompt(campaign_dir: Path, resumed: bool = False) -> str:
    """The DM's first prompt, chosen from the files. Written for a small model: short, explicit, one paragraph.

    `resumed`: the DM keeps its conversation, so it knows the world and the skills. It needs only a nudge.
    """
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
    if resumed:
        return (
            f"The player is back. The game goes on in this same conversation, for the campaign `{slug}`. "
            "The stage already shows your last beat; do not repeat it. The characters or the files may have "
            "changed while you were away: run `uv run dnd-cli session brief` only if you need to look. "
            "Then go on from where you stopped, with `uv run dnd-cli show beat`."
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


def default_command(campaign_dir: Path, resume: bool = False) -> list[str]:
    """Make the campaign active and build the DM session for it: the saved conversation if `resume` and it can
    be continued, else a new one that reads the files."""
    from view.settings import can_continue, new_dm_session

    resume = resume and can_continue(campaign_dir.name)
    prompt = stage_first_prompt(campaign_dir, resumed=resume)
    return new_dm_session(campaign_dir, prompt, stage=True, resume=resume)[1]


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

    def __init__(self, command_factory: Callable[..., list[str]]):
        self.command_factory = command_factory
        self.stage: Stage | None = None
        self.tail_task: asyncio.Task | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.on_start: Callable[[], None] = lambda: None

    async def start(self, campaign_dir: Path, dm_command: list[str] | None = None, resume: bool = False,
                    seats: Seats | None = None) -> Stage:
        await self.stop()
        self.on_start()
        stage = Stage(campaign_dir, dm_command or self.command_factory(campaign_dir, resume=resume))
        if seats is not None:  # a load keeps the host and the seats
            stage.seats = seats
        # A save of the files as they are, before the DM touches them.
        await asyncio.to_thread(stage.autosave, "session start")
        stage.loop = self.loop
        # Restore the stage from earlier sessions without broadcasting it.
        stage.fold(stage.read_new_events())
        stage.state["dm"] = {"status": "starting"}
        stage.dm.start()
        # The host code is also on the server's log: if the host's device dies, the owner can read it there.
        print(f"dungeon-os: host code {stage.seats.code}", file=sys.stderr, flush=True)
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


def _last_played(campaign_dir: Path) -> int:
    """Unix time of the newest save, or of the config file when there is no save."""
    found = saves.list_saves(campaign_dir, 1)
    if found:
        return found[0]["time"]
    try:
        return int((campaign_dir / "config.json").stat().st_mtime)
    except OSError:
        return 0


def _menu(table: Table) -> dict:
    from dnd_cli.campaign import CAMPAIGNS_DIR, active_campaign_slug, list_campaigns
    from view.settings import FRAMEWORKS, campaign_in_progress, can_continue, framework_available, load_settings

    settings = load_settings()
    campaigns = [
        {"slug": slug, "name": name, "in_progress": campaign_in_progress(CAMPAIGNS_DIR / slug),
         "can_continue": can_continue(slug, settings), "last_played": _last_played(CAMPAIGNS_DIR / slug)}
        for slug, name in list_campaigns()
    ]
    campaigns.sort(key=lambda c: c["last_played"], reverse=True)  # the campaign played last comes first
    try:
        active = active_campaign_slug()
    except (OSError, ValueError, KeyError):
        active = None
    resume = next((c for c in campaigns if c["slug"] == active and c["in_progress"]), None)
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
    command_factory: Callable[..., list[str]] = default_command,
    allowed_hosts: Iterable[str] = (),
) -> Starlette:
    """Serve the stage. With a campaign, start it at once; without one, open the start menu."""
    table = Table(command_factory)

    def need() -> Stage:
        if table.stage is None:
            raise HTTPException(409, "No game is running.")
        return table.stage

    # -- who is asking ---------------------------------------------------

    def device_of(request: Request | WebSocket) -> str | None:
        token = request.headers.get("x-device") or request.query_params.get("d") or ""
        return token if DEVICE_RE.match(token) else None

    def require_device(request: Request) -> str:
        device = device_of(request)
        if device is None:
            raise HTTPException(403, "This browser has no device id. Reload the page.")
        return device

    def menu_gate(request: Request) -> str:
        """A menu action: anyone may use it while no game runs; with a game, only the host."""
        device = require_device(request)
        if table.stage and not table.stage.seats.is_host(device):
            raise HTTPException(403, "Only the host can do that.")
        return device

    def host_only(request: Request) -> Stage:
        stage = need()
        if not stage.seats.is_host(require_device(request)):
            raise HTTPException(403, "Only the host can do that.")
        return stage

    def own(request: Request, stage: Stage, who: str) -> str:
        """The device, when it plays `who`. Nobody acts for another player's character."""
        device = require_device(request)
        if not stage.seats.owns(device, who):
            raise HTTPException(403, "That is not your character. Take a seat first.")
        return device

    def can_play(request: Request, stage: Stage) -> None:
        if not stage.seats.can_play(require_device(request)):
            raise HTTPException(403, "Take a seat first.")

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
        device = device_of(ws)
        stage.client_device[ws] = device
        await ws.send_json(stage.snapshot(device))
        stage.event_clients.add(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            stage.event_clients.discard(ws)
            stage.client_device.pop(ws, None)

    async def ws_pty(ws: WebSocket):
        await ws.accept()
        stage = table.stage
        if stage is None:
            await ws.close(code=4000)
            return
        if not stage.seats.is_host(device_of(ws)):
            await ws.close(code=1008)  # the console takes keystrokes into the DM: host only
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
        """A line for the DM. A player's line carries the player and the character; the host may speak untagged."""
        stage = need()
        device = require_device(request)
        body = await request.json()
        mine = stage.seats.mine(device)
        who = str(body["who"]) if body.get("who") else (mine[0] if len(mine) == 1 else None)
        text = str(body.get("text", ""))
        as_host = bool(body.get("as_host")) and stage.seats.is_host(device)
        if as_host:
            who = None  # a host control (End session): the DM must not read it as a character's words
        whisper = bool(body.get("whisper")) and bool(who)
        if who:
            own(request, stage, who)
            name = stage.char_name(who)
            text = f"[{stage.seats.player(device, who)} as {name}{', private' if whisper else ''}] {text}"
        elif not stage.seats.is_host(device):
            raise HTTPException(403, "Take a seat first.")
        if not stage.dm_ready():
            raise HTTPException(409, "The DM is busy.")
        if who and not whisper:
            # In a combat, only the player whose turn it is may speak or act; a whisper to the DM is always allowed.
            enc = combat.load_state(stage.campaign_dir).get("active_encounter") or {}
            turn = enc.get("current_turn") if enc.get("type") == "combat" else None
            if turn and character.character_path(stage.campaign_dir, turn).exists():
                if who != turn:
                    raise HTTPException(409, f"It is {stage.char_name(turn)}'s turn.")
            elif (aw := stage.state.get("await")) and aw["who"] != "all" and aw["who"] != who and aw["who"] in stage.awaiting()["waiting"]:
                raise HTTPException(409, f"The DM waits for {stage.char_name(aw['who'])}.")
            elif aw and aw["who"] == who:
                await stage._local_event({"type": "await_done"})  # the awaited player answers: the answer goes out below
            elif aw and aw["who"] == "all":
                stage.intents[who] = str(body.get("text", ""))
                await stage.broadcast()
                await stage.flush_intents()
                return JSONResponse({"ok": True, "queued": True})
        await stage.submit(text)
        return JSONResponse({"ok": True})

    async def api_send_now(request: Request):
        """The host sends the answers collected so far, without waiting for the players who have not answered."""
        stage = host_only(request)
        if not await stage.flush_intents(force=True):
            return error("There is nothing to send.")
        return JSONResponse({"ok": True})

    async def api_restart(request: Request):
        stage = host_only(request)
        if not stage.dm.alive:
            stage.dm.command = table.command_factory(stage.campaign_dir, resume=True)
            stage.dm.start()
            await stage._local_event({"type": "dm_status", "status": "starting"})
        return JSONResponse({"ok": True, "alive": stage.dm.alive})

    async def api_me(request: Request):
        """This device: its public id, and the host code when it is the host."""
        stage = need()
        device = require_device(request)
        had_host = stage.seats.host is not None
        host = stage.seats.ensure_host(device)
        if not had_host:
            await stage.broadcast()
        return JSONResponse({"sid": sid(device), "host": host, "host_code": stage.seats.code if host else None})

    async def seat_call(request: Request, fn):
        stage = need()
        device = require_device(request)
        body = await request.json()
        who = pc_or_404(stage, body.get("who"))
        try:
            fn(stage.seats, device, who, body)
        except SeatError as e:
            return error(str(e), 403)
        await stage.broadcast()
        await stage.flush_intents()  # a player who leaves or goes away may have been the last one awaited
        return JSONResponse({"ok": True})

    async def api_seat_claim(request: Request):
        return await seat_call(request, lambda s, d, who, b: s.claim(d, who, str(b.get("name") or "")))

    async def api_seat_release(request: Request):
        return await seat_call(request, lambda s, d, who, b: s.release(d, who))

    async def api_seat_away(request: Request):
        return await seat_call(request, lambda s, d, who, b: s.set_away(d, who, bool(b.get("away"))))

    async def api_host_claim(request: Request):
        stage = need()
        device = require_device(request)
        try:
            stage.seats.take_host(device, str((await request.json()).get("code", "")))
        except SeatError as e:
            return error(str(e), 403)
        print(f"dungeon-os: new host code {stage.seats.code}", file=sys.stderr, flush=True)
        await stage.broadcast()
        return JSONResponse({"ok": True})

    async def api_menu(request: Request):
        return JSONResponse(_menu(table))

    async def api_game_start(request: Request):
        from dnd_cli.campaign import CampaignError, create_campaign, resolve_campaign_dir

        device = menu_gate(request)
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
        # "continue": the DM keeps its conversation. Anything else: a new DM session that reads the files.
        stage = await table.start(campaign, resume=body.get("dm") == "continue")
        stage.seats.ensure_host(device)  # whoever starts the game is the host
        if body.get("play") == "here" and stage.opened:
            stage.open_creator(device)  # the host makes a character on this device; "phones" leaves the creator to the phones
        return JSONResponse({"game": campaign.name})

    async def api_saves(request: Request):
        from dnd_cli.campaign import CampaignError, resolve_campaign_dir

        try:
            campaign = resolve_campaign_dir(request.path_params["slug"])
        except CampaignError as e:
            return error(str(e), 404)
        return JSONResponse({"saves": await asyncio.to_thread(saves.list_saves, campaign)})

    async def api_game_save(request: Request):
        stage = host_only(request)
        if not stage.dm_ready():
            return error("Wait until the DM has finished its turn.")
        name = " ".join(str((await request.json()).get("name", "")).split())
        try:
            save_id = await asyncio.to_thread(saves.save, stage.campaign_dir, saves.SAVE, name or stage.save_label(), True)
        except (saves.SaveError, OSError) as e:
            return error(str(e), 500)
        return JSONResponse({"id": save_id})

    async def api_game_load(request: Request):
        """Put a campaign back to a save, then start it with a new DM session (the old conversation is from later)."""
        from dnd_cli.campaign import CampaignError, resolve_campaign_dir
        from view.settings import clear_session

        device = menu_gate(request)
        seats = table.stage.seats if table.stage else None
        body = await request.json()
        try:
            campaign = resolve_campaign_dir(str(body.get("campaign", "")))
            await table.stop()  # no DM may write while the files change
            await asyncio.to_thread(saves.restore, campaign, str(body.get("save", "")))
        except (CampaignError, OSError) as e:
            return error(str(e), 400)
        clear_session(campaign.name)
        stage = await table.start(campaign, seats=seats)
        stage.seats.ensure_host(device)
        return JSONResponse({"game": campaign.name})

    async def api_campaign_delete(request: Request):
        from dnd_cli.campaign import CampaignError, delete_campaign
        from view.settings import clear_session

        menu_gate(request)
        slug = str((await request.json()).get("campaign", ""))
        if table.stage and table.stage.campaign_dir.name == slug:
            return error("This campaign is running. Quit the game first.", 409)
        try:
            await asyncio.to_thread(delete_campaign, slug)
        except (CampaignError, OSError) as e:
            return error(str(e), 400)
        clear_session(slug)
        return JSONResponse(_menu(table))

    async def api_game_quit(request: Request):
        menu_gate(request)
        await table.stop()
        return JSONResponse({"game": None})

    async def api_settings(request: Request):
        from view.settings import FRAMEWORKS, save_settings

        menu_gate(request)
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
        device = require_device(request)
        body = await request.json()
        try:
            made = await run_in_threadpool(make_character, stage.campaign_dir, body)
        except (RulesError, CharacterError, lpc.ActorError, AssetError) as e:
            return error(str(e), 400)
        stage.seats.claim(device, made["id"], str(body.get("player_name") or ""))  # the maker plays it
        await stage.broadcast()
        return JSONResponse(made)

    async def api_creation_open(request: Request):
        stage = need()
        stage.open_creator(require_device(request))
        await stage.broadcast()
        return JSONResponse({"ok": True})

    async def api_creation_done(request: Request):
        """A device leaves the creator. `force` (host only) closes it for everyone: the host starts the adventure."""
        stage = need()
        device = require_device(request)
        body = await request.json() if await request.body() else {}
        host = stage.seats.is_host(device)
        if not (host or device in stage.creators):
            raise HTTPException(403, "Only a player who has the creator open, or the host, can close it.")
        stage.leave_creator(device, host, force=host and bool(body.get("force")))
        await stage.broadcast()
        return JSONResponse({"ok": True})

    async def api_read(request: Request):
        """A seated device says which story line it shows. The table screen shows the furthest one."""
        stage = need()
        device = require_device(request)
        if not stage.seats.mine(device):
            raise HTTPException(403, "Take a seat first.")
        seq = (await request.json()).get("seq")
        if not isinstance(seq, int):
            return error("seq must be a number.", 400)
        if stage.reads.get(device) != seq:
            stage.reads[device] = seq
            await stage.broadcast()
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
        own(request, stage, src)  # the giver acts; the receiver may be anyone in the party
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
        own(request, stage, who)
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
        own(request, stage, who)
        def end_and_skip(st):
            """End the turn, then end the turn of each player who is away, so the order never waits for them."""
            out = combat.end_turn(stage.campaign_dir, st, who)
            for _ in st["active_encounter"].get("participants", []):
                cur = st["active_encounter"]["current_turn"]
                if cur not in stage.seats.away or cur not in stage.seats.owners:
                    break
                out += [f"{stage.char_name(cur)} is away: turn skipped."] + combat.end_turn(stage.campaign_dir, st, cur)
            return out
        try:
            lines = await run_in_threadpool(with_rules, stage, end_and_skip)
        except combat.RulesError as e:
            return error(str(e), 400)
        state = combat.load_state(stage.campaign_dir)
        now = state["active_encounter"]["current_turn"]
        name = stage.char_name(who)
        if character.character_path(stage.campaign_dir, now).exists():
            todo = "It is a player character's turn now: narrate the change in one beat, then wait for the player."
        else:
            todo = (f"It is {now}'s turn: run it with the rules commands (attack, save), narrate it, then `encounter next`. "
                    "Repeat for each creature until a player character is up, then wait for the player.")
        await stage.submit(f"[{name} ends their turn] " + " ".join(lines) + " " + todo + stage.away_note())
        return JSONResponse({"lines": lines})

    async def api_resource(request: Request):
        """Spend (or give back) one use of a class resource."""
        stage = idle_stage()
        body = await request.json()
        who = pc_or_404(stage, body.get("who"))
        own(request, stage, who)

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
        own(request, stage, req["who"])
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
        can_play(request, stage)
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
        can_play(request, stage)
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
        Route("/api/game/save", api_game_save, methods=["POST"]),
        Route("/api/campaign/delete", api_campaign_delete, methods=["POST"]),
        Route("/api/game/load", api_game_load, methods=["POST"]),
        Route("/api/saves/{slug}", api_saves),
        Route("/api/settings", api_settings, methods=["POST"]),
        Route("/api/input", api_input, methods=["POST"]),
        Route("/api/restart", api_restart, methods=["POST"]),
        Route("/api/me", api_me),
        Route("/api/send-now", api_send_now, methods=["POST"]),
        Route("/api/seat/claim", api_seat_claim, methods=["POST"]),
        Route("/api/seat/release", api_seat_release, methods=["POST"]),
        Route("/api/seat/away", api_seat_away, methods=["POST"]),
        Route("/api/host/claim", api_host_claim, methods=["POST"]),
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
        Route("/api/read", api_read, methods=["POST"]),
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

    app = Starlette(routes=routes, lifespan=lifespan, middleware=[Middleware(LocalOnly, hosts=frozenset(LOCAL_HOSTS) | {h.lower() for h in allowed_hosts})],
                    exception_handlers={HTTPException: http_error})
    app.state.table = table
    return app


def serve(
    campaign_dir: Path | None = None,
    dm_command: list[str] | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    allowed_hosts: Iterable[str] = (),
) -> None:
    import uvicorn

    uvicorn.run(create_app(campaign_dir, dm_command, allowed_hosts=allowed_hosts), host=host, port=port, log_level="warning")
