"""The DungeonOS start screen: a text-adventure title menu.

`Resume` continues the active campaign (the last one played) from its game
files (state.json, session_log.md, canon.json) with a fresh DM session — it
does not need a saved conversation. `Load Game` picks any other saved campaign
and plays it the same way. `New Game` scaffolds a brand-new campaign from the
template and starts Session Zero. `Settings` chooses the agent framework and
model.

`run_menu_loop` is the whole session loop: `MenuApp.run()` returns the chosen
game (or None to quit), the loop runs it as a `ViewApp` in the same process,
and on exit loops back to a fresh `MenuApp`. One process serves the terminal
and the browser (via view/serve.py) alike.
"""

from __future__ import annotations

import uuid

from textual.app import App, ComposeResult
from textual.containers import Center, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

from dnd_cli.campaign import (
    GAME_DIR,
    CampaignError,
    active_campaign_slug,
    campaign_display_name,
    create_campaign,
    list_campaigns,
    resolve_campaign_dir,
    set_active_campaign,
)
from view.app import ViewApp
from view.settings import (
    FRAMEWORKS,
    build_dm_command,
    campaign_in_progress,
    framework_available,
    load_settings,
    save_settings,
    set_last_session_id,
)

# "DUNGEON" over "OS" in the ANSI Shadow block font — a chunky, pixel-art
# style splash. DUNGEON rows are 63 cells wide; the OS rows carry 23 leading
# spaces so they sit centred under it (the banner is left-aligned, then the
# whole 63-wide block is centred by CSS). Keep those widths if you edit it.
BANNER = "\n".join(
    [
        "██████╗ ██╗   ██╗███╗   ██╗ ██████╗ ███████╗ ██████╗ ███╗   ██╗",
        "██╔══██╗██║   ██║████╗  ██║██╔════╝ ██╔════╝██╔═══██╗████╗  ██║",
        "██║  ██║██║   ██║██╔██╗ ██║██║  ███╗█████╗  ██║   ██║██╔██╗ ██║",
        "██║  ██║██║   ██║██║╚██╗██║██║   ██║██╔══╝  ██║   ██║██║╚██╗██║",
        "██████╔╝╚██████╔╝██║ ╚████║╚██████╔╝███████╗╚██████╔╝██║ ╚████║",
        "╚═════╝  ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝ ╚══════╝ ╚═════╝ ╚═╝  ╚═══╝",
        "                        ██████╗ ███████╗",
        "                       ██╔═══██╗██╔════╝",
        "                       ██║   ██║███████╗",
        "                       ██║   ██║╚════██║",
        "                       ╚██████╔╝███████║",
        "                        ╚═════╝ ╚══════╝",
    ]
)

TAGLINE = "An operating system for collaborative storytelling"

# Modal titles in the same ANSI Shadow block font as the banner. A terminal
# app cannot pick a typeface (every widget renders in the user's terminal
# font), so block wordmarks are how the menu carries the pixel-game look.
HEADING_SETTINGS = "\n".join(
    [
        "███████╗███████╗████████╗████████╗██╗███╗   ██╗ ██████╗ ███████╗",
        "██╔════╝██╔════╝╚══██╔══╝╚══██╔══╝██║████╗  ██║██╔════╝ ██╔════╝",
        "███████╗█████╗     ██║      ██║   ██║██╔██╗ ██║██║  ███╗███████╗",
        "╚════██║██╔══╝     ██║      ██║   ██║██║╚██╗██║██║   ██║╚════██║",
        "███████║███████╗   ██║      ██║   ██║██║ ╚████║╚██████╔╝███████║",
        "╚══════╝╚══════╝   ╚═╝      ╚═╝   ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚══════╝",
    ]
)
HEADING_NEW_GAME = "\n".join(
    [
        "███╗   ██╗███████╗██╗    ██╗   ██████╗  █████╗ ███╗   ███╗███████╗",
        "████╗  ██║██╔════╝██║    ██║  ██╔════╝ ██╔══██╗████╗ ████║██╔════╝",
        "██╔██╗ ██║█████╗  ██║ █╗ ██║  ██║  ███╗███████║██╔████╔██║█████╗  ",
        "██║╚██╗██║██╔══╝  ██║███╗██║  ██║   ██║██╔══██║██║╚██╔╝██║██╔══╝  ",
        "██║ ╚████║███████╗╚███╔███╔╝  ╚██████╔╝██║  ██║██║ ╚═╝ ██║███████╗",
        "╚═╝  ╚═══╝╚══════╝ ╚══╝╚══╝    ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝",
    ]
)
HEADING_LOAD_GAME = "\n".join(
    [
        "██╗      ██████╗  █████╗ ██████╗    ██████╗  █████╗ ███╗   ███╗███████╗",
        "██║     ██╔═══██╗██╔══██╗██╔══██╗  ██╔════╝ ██╔══██╗████╗ ████║██╔════╝",
        "██║     ██║   ██║███████║██║  ██║  ██║  ███╗███████║██╔████╔██║█████╗  ",
        "██║     ██║   ██║██╔══██║██║  ██║  ██║   ██║██╔══██║██║╚██╔╝██║██╔══╝  ",
        "███████╗╚██████╔╝██║  ██║██████╔╝  ╚██████╔╝██║  ██║██║ ╚═╝ ██║███████╗",
        "╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝    ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝",
    ]
)


def _safe_active_slug() -> str | None:
    """The active campaign slug, or None if the pointer is missing or broken."""
    try:
        return active_campaign_slug()
    except (OSError, ValueError, KeyError):
        return None


CUSTOM = "__custom__"  # the model dropdown's "type your own" entry


class SettingsScreen(ModalScreen):
    """Choose the agent framework that runs the DM, and the model it uses.

    Modal so the title screen's r/n/s/q shortcuts do not fire while it is open.
    """

    BINDINGS = [("escape", "app.pop_screen", "Back")]

    CSS = """
    SettingsScreen { align: center middle; }
    #settings-box {
        width: 80; height: auto; padding: 0 2;
        border: round $accent; background: $panel;
    }
    .block-heading { color: $accent; }
    #settings-box Label { margin-top: 1; color: $text-muted; }
    #settings-buttons { height: auto; margin-top: 1; align-horizontal: right; }
    #settings-buttons Button { margin-left: 2; }
    """

    def compose(self) -> ComposeResult:
        saved = load_settings()
        # Track the framework the model dropdown currently belongs to. The
        # framework Select emits a Changed on mount carrying this same value,
        # which the handler then ignores; only a real switch to a different
        # framework resets the model to that framework's first preset.
        framework = saved["agent_framework"]
        self._model_framework = framework
        model = saved.get("model", "")
        presets = FRAMEWORKS[framework]["models"]
        custom = model not in presets  # a saved model outside the presets is edited as Custom
        yield Header()
        with Vertical(id="settings-box"):
            yield Static(HEADING_SETTINGS, classes="block-heading")
            yield Label("Agent framework")
            yield Select(
                self._framework_options(),
                value=saved["agent_framework"],
                allow_blank=False,
                id="framework",
            )
            yield Label("Model")
            yield Select(
                self._model_options(framework),
                value=CUSTOM if custom else model,
                allow_blank=False,
                id="model",
            )
            custom_input = Input(
                value=model if custom else "",
                placeholder="alias or full model id (empty = the CLI default)",
                id="model-custom",
            )
            custom_input.display = custom
            yield custom_input
            with Horizontal(id="settings-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Save", variant="success", id="save")
        yield Footer()

    @staticmethod
    def _framework_options() -> list[tuple[str, str]]:
        options = []
        for key, spec in FRAMEWORKS.items():
            label = spec["label"]
            if not framework_available(key):
                label += "  (not installed)"
            options.append((label, key))
        return options

    @staticmethod
    def _model_options(framework: str) -> list[tuple[str, str]]:
        options = [(m, m) for m in FRAMEWORKS[framework]["models"]]
        options.append(("Custom…", CUSTOM))
        return options

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "model":
            self.query_one("#model-custom", Input).display = event.value == CUSTOM
            return
        if event.select.id != "framework" or event.value not in FRAMEWORKS:
            return
        if event.value == self._model_framework:
            return  # mount echo, or a switch back to where the model already fits
        self._model_framework = event.value
        model = self.query_one("#model", Select)
        model.set_options(self._model_options(event.value))
        model.value = FRAMEWORKS[event.value]["models"][0]
        self.query_one("#model-custom", Input).value = ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            model = self.query_one("#model", Select).value
            if model == CUSTOM:
                model = self.query_one("#model-custom", Input).value.strip()
            save_settings(
                {
                    "agent_framework": self.query_one("#framework", Select).value,
                    "model": model,
                }
            )
            self.notify("Settings saved.")
        self.app.pop_screen()


class NewGameScreen(ModalScreen):
    """Name a new campaign; it is scaffolded from the template and set active.

    Dismisses with the new campaign's slug, or None if cancelled.
    """

    BINDINGS = [("escape", "cancel", "Back")]

    CSS = """
    NewGameScreen { align: center middle; }
    #newgame-box {
        width: 80; height: auto; padding: 1 2;
        border: round $accent; background: $panel;
    }
    .block-heading { color: $accent; margin-bottom: 1; }
    #newgame-box Input { margin: 1 0; }
    #newgame-error { color: $error; min-height: 1; }
    #newgame-buttons { height: auto; align-horizontal: right; }
    #newgame-buttons Button { margin-left: 2; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="newgame-box"):
            yield Static(HEADING_NEW_GAME, classes="block-heading")
            yield Label("Name your campaign")
            yield Input(placeholder="The Shattered Crown", id="name")
            yield Static("", id="newgame-error")
            yield Static(
                "[dim]A fresh campaign is created from the template. The DM "
                "runs Session Zero on first launch.[/dim]"
            )
            with Horizontal(id="newgame-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Create", variant="success", id="create")
        yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._create()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create":
            self._create()
        else:
            self.dismiss(None)

    def _create(self) -> None:
        name = self.query_one("#name", Input).value.strip()
        if not name:
            self.query_one("#newgame-error", Static).update("Enter a name.")
            return
        try:
            slug = create_campaign(name)
        except CampaignError as exc:
            self.query_one("#newgame-error", Static).update(str(exc))
            return
        set_active_campaign(slug)
        self.dismiss(slug)


class LoadGameScreen(ModalScreen):
    """Pick a saved campaign to play. Dismisses with its slug, or None."""

    BINDINGS = [("escape", "cancel", "Back")]

    CSS = """
    LoadGameScreen { align: center middle; }
    #loadgame-box {
        width: 80; height: auto; max-height: 90%; padding: 1 2;
        border: round $accent; background: $panel;
    }
    .block-heading { color: $accent; margin-bottom: 1; }
    #loadgame-list { height: auto; max-height: 16; }
    #loadgame-list Button { width: 100%; margin-bottom: 1; }
    #loadgame-cancel { width: 100%; margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="loadgame-box"):
            yield Static(HEADING_LOAD_GAME, classes="block-heading")
            active = _safe_active_slug()
            campaigns = list_campaigns()
            with Vertical(id="loadgame-list"):
                if not campaigns:
                    yield Static("[dim]No saved campaigns under game/campaigns/.[/dim]")
                for slug, name in campaigns:
                    tag = "  ·  active" if slug == active else ""
                    yield Button(f"{name}  ({slug}){tag}", id=f"campaign-{slug}")
            yield Button("Cancel", id="loadgame-cancel")
        yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "loadgame-cancel":
            self.dismiss(None)
        elif bid.startswith("campaign-"):
            slug = bid.removeprefix("campaign-")
            set_active_campaign(slug)
            self.dismiss(slug)


class MenuApp(App):
    """The title screen. `run()` returns the game to launch, or None to quit."""

    TITLE = "DungeonOS"
    CSS = """
    MenuApp { align: center middle; }
    #title-block {
        width: auto; height: auto; padding: 1 2; align-horizontal: center;
    }
    #banner { width: 63; color: $accent; }
    #tagline { width: 63; text-align: center; color: $text-muted; margin-bottom: 1; }
    #menu-box { width: 62; height: auto; }
    #menu-box Button { width: 100%; margin-top: 1; }
    """

    BINDINGS = [
        ("r", "press('resume')", "Resume"),
        ("l", "press('load')", "Load Game"),
        ("n", "press('new')", "New Game"),
        ("s", "press('settings')", "Settings"),
        ("q", "press('quit')", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Center():
            with Vertical(id="title-block"):
                yield Static(BANNER, id="banner")
                yield Static(TAGLINE, id="tagline")
                with Vertical(id="menu-box"):
                    yield Button("Resume", id="resume", variant="success")
                    yield Button("Load Game", id="load", variant="primary")
                    yield Button("New Game", id="new", variant="primary")
                    yield Button("Settings", id="settings")
                    yield Button("Quit", id="quit", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        target = self._resume_target()
        resume = self.query_one("#resume", Button)
        if target is None:
            resume.disabled = True
        else:
            resume.label = f"Resume — {target[1]}"
        if not list_campaigns():
            self.query_one("#load", Button).disabled = True

    _DISABLED_HINT = {
        "resume": "No campaign in progress yet — use Load Game or New Game.",
        "load": "No saved campaigns yet — choose New Game.",
    }

    def action_press(self, button_id: str) -> None:
        button = self.query_one(f"#{button_id}", Button)
        if button.disabled:
            hint = self._DISABLED_HINT.get(button_id)
            if hint:
                self.notify(hint)
            return
        button.press()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handler = {
            "resume": self._resume,
            "load": self._load_game,
            "new": self._new_game,
            "settings": lambda: self.push_screen(SettingsScreen()),
            "quit": lambda: self.exit(None),
        }.get(event.button.id or "")
        if handler:
            handler()

    def _resume_target(self) -> tuple[str, str] | None:
        """(slug, display name) for the active campaign, if it is worth resuming."""
        try:
            campaign_dir = resolve_campaign_dir(active_campaign_slug())
        except (OSError, ValueError, KeyError, CampaignError):
            return None
        if not campaign_in_progress(campaign_dir):
            return None
        return campaign_dir.name, campaign_display_name(campaign_dir)

    def _resume(self) -> None:
        target = self._resume_target()
        if target is None:
            self.notify("No campaign in progress yet — choose New Game.")
            return
        slug, _name = target
        # A fresh session: the DM reads the campaign files and picks up the
        # story. We are resuming the campaign, not a specific conversation.
        self.exit(
            {"campaign": slug, "session_id": str(uuid.uuid4()), "resume": False}
        )

    def _load_game(self) -> None:
        self.push_screen(LoadGameScreen(), self._start_chosen_campaign)

    def _new_game(self) -> None:
        self.push_screen(NewGameScreen(), self._start_chosen_campaign)

    def _start_chosen_campaign(self, slug: str | None) -> None:
        # The Load/New screen has already set this campaign active; None means
        # the user backed out.
        if not slug:
            return
        self.exit(
            {"campaign": slug, "session_id": str(uuid.uuid4()), "resume": False}
        )


def run_menu_loop() -> None:
    """Show the menu; on a chosen game run it, then return to the menu."""
    while True:
        choice = MenuApp().run()
        if not choice:
            return
        try:
            campaign_dir = resolve_campaign_dir(choice["campaign"])
        except CampaignError as exc:
            print(f"dungeon-os: {exc}")
            return
        set_last_session_id(campaign_dir.name, choice["session_id"])
        dm_command = build_dm_command(
            load_settings(),
            GAME_DIR,
            choice["session_id"],
            resume=choice["resume"],
        )
        ViewApp(
            campaign_dir,
            session_id=choice["session_id"],
            dm_command=dm_command,
        ).run()


def main() -> None:
    run_menu_loop()


if __name__ == "__main__":
    main()
