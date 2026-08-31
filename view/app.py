"""Player-facing display: the DM's own terminal, plus a live state panel.

Runs unmodified as a local terminal TUI (`uv run dungeon-view <campaign>`) or
served to a browser (see view/serve.py) — same renderer, no duplicated UI
code for the two surfaces. The start menu (view/menu.py) launches a game by
running this `ViewApp` between menu loops, so it shares the renderer too.

The left pane is a real terminal (textual_tty.Terminal) running the DM agent
(`claude` by default; see view/settings.py). The agent's own UI — narration,
permission prompts, tool-call summaries — renders as-is; this app does not
parse or reconstruct any of it, unlike an earlier version that tailed the
session JSONL transcript.

Allowlist: the right-hand panel reads only state.json and characters/*.json
from the campaign directory. It never opens dm_story.md, session_log.md, or
world/* — those carry DM-only material. Do not add a broader read here; add
a specific file instead.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static
from textual_tty import Terminal

from dnd_cli.campaign import GAME_DIR, resolve_campaign_dir
from view.settings import build_dm_command, load_settings


def _format_character(data: dict) -> str:
    hp = data.get("hp", {})
    temp = hp.get("temp", 0)
    hp_line = f"HP: {hp.get('current', '?')}/{hp.get('max', '?')}"
    if temp:
        hp_line += f" (+{temp} temp)"

    lines = [
        f"[b]{escape(data.get('name', '?'))}[/b]",
        f"{escape(data.get('race', ''))} {escape(data.get('class', ''))} "
        f"(lvl {data.get('level', '?')})",
        hp_line,
        f"AC: {data.get('armor_class', '?')}",
        "",
        "[b]Inventory[/b]",
    ]
    for item in data.get("inventory", []):
        qty = item.get("quantity", 1)
        suffix = f" x{qty}" if qty and qty != 1 else ""
        lines.append(f"  • {escape(item.get('name', '?'))}{suffix}")
    return "\n".join(lines)


def _format_state(data: dict) -> str:
    lines = [
        f"[b]{escape(data.get('location', ''))}[/b]",
        escape(data.get("game_time", "")),
        "",
        "[b]Quests[/b]",
    ]
    for quest in data.get("quest_log", []):
        title = escape(quest.get("title", "?"))
        status = escape(quest.get("status", "?"))
        lines.append(f"  • {title} ({status})")
    return "\n".join(lines)


class GameScreen(Screen):
    """DM terminal plus a live state/character panel, for one campaign.

    Dismisses itself when the DM process exits. Under `ViewApp` that ends the
    app; pushed from the start menu it pops back to the title screen.
    """

    CSS = """
    #terminal { width: 70%; }
    #side { width: 30%; border: solid $accent; padding: 1; }
    """

    def __init__(
        self,
        campaign_dir: Path,
        dm_command: list[str],
        *,
        poll_seconds: float = 2.0,
    ):
        super().__init__()
        self.campaign_dir = campaign_dir
        self.dm_command = dm_command
        self.poll_seconds = poll_seconds

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield Terminal(command=self.dm_command, id="terminal")
            with VerticalScroll(id="side"):
                yield Static(id="state_panel")
                yield Static(id="character_panel")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_panels()
        self.set_interval(self.poll_seconds, self.refresh_panels)
        self.query_one("#terminal", Terminal).focus()

    def on_terminal_process_exited(self, message: Terminal.ProcessExited) -> None:
        self.dismiss()

    def refresh_panels(self) -> None:
        state_path = self.campaign_dir / "state.json"
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text())
                self.query_one("#state_panel", Static).update(_format_state(state))
            except (json.JSONDecodeError, OSError):
                pass

        characters_dir = self.campaign_dir / "characters"
        if characters_dir.is_dir():
            blocks = []
            for path in sorted(characters_dir.glob("*.json")):
                try:
                    blocks.append(_format_character(json.loads(path.read_text())))
                except (json.JSONDecodeError, OSError):
                    continue
            self.query_one("#character_panel", Static).update("\n\n".join(blocks))


class ViewApp(App):
    """Standalone player view for one campaign (the `dungeon-view` entry point)."""

    def __init__(
        self,
        campaign_dir: Path,
        *,
        game_dir: Path = GAME_DIR,
        session_id: str | None = None,
        dm_command: list[str] | None = None,
    ):
        super().__init__()
        self.campaign_dir = campaign_dir
        self.game_dir = game_dir
        self.session_id = session_id or str(uuid.uuid4())
        self.dm_command = dm_command
        self.title = f"DungeonOS — {campaign_dir.name}"

    def on_mount(self) -> None:
        command = self.dm_command
        if command is None:
            command = build_dm_command(
                load_settings(), self.game_dir, self.session_id
            )
        self.push_screen(
            GameScreen(self.campaign_dir, command), lambda _result: self.exit()
        )


def main() -> None:
    if len(sys.argv) not in (2, 3):
        print("usage: dungeon-view <campaign-slug> [session-id]", file=sys.stderr)
        raise SystemExit(2)

    campaign_dir = resolve_campaign_dir(sys.argv[1])
    session_id = sys.argv[2] if len(sys.argv) == 3 else None
    ViewApp(campaign_dir, session_id=session_id).run()


if __name__ == "__main__":
    main()
