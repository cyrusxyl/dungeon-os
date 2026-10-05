"""Checks for the start menu and the DM-command builder.

Run from the repo root:  .venv/bin/python tests/test_menu.py

Plain asserts + asyncio so no test runner is needed. The menu screens never
mount the Terminal widget, so `run_test()` here does not spawn a DM process.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

import shutil

import dnd_cli.campaign as campaign
import view.settings as settings
from dnd_cli.campaign import GAME_DIR, create_campaign, list_campaigns, slugify
from view.menu import CUSTOM, LoadGameScreen, MenuApp, NewGameScreen, SettingsScreen

PASS = 0
FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}")


def test_build_dm_command() -> None:
    print("build_dm_command")
    fresh = settings.build_dm_command(
        {"agent_framework": "claude", "model": "sonnet"}, GAME_DIR, "sid-1"
    )
    check("returns an sh -c command", fresh[:2] == ["sh", "-c"])
    check("fresh uses --session-id", "--session-id sid-1" in fresh[2])
    check("fresh passes --model", "--model sonnet" in fresh[2])
    check("cd into the game dir", fresh[2].startswith(f"cd {GAME_DIR} &&"))

    resumed = settings.build_dm_command(
        {"agent_framework": "claude", "model": "sonnet"},
        GAME_DIR,
        "sid-2",
        resume=True,
    )
    check("resume uses --resume", "--resume sid-2" in resumed[2])
    check("resume has no --session-id", "--session-id" not in resumed[2])

    spaced = settings.build_dm_command(
        {"agent_framework": "claude", "model": "claude opus 5"}, GAME_DIR, "s"
    )
    check("model with a space is quoted", "--model 'claude opus 5'" in spaced[2])

    no_model = settings.build_dm_command(
        {"agent_framework": "claude", "model": ""}, GAME_DIR, "s"
    )
    check("empty model omits --model", "--model" not in no_model[2])

    agy = settings.build_dm_command(
        {"agent_framework": "agy", "model": "gemini-3.1-pro-high"}, GAME_DIR, "s"
    )
    check("agy builds --model", "--model gemini-3.1-pro-high" in agy[2])
    check("agy skips permission prompts", "exec agy --dangerously-skip-permissions" in agy[2])
    check("claude runs in auto mode", "--permission-mode auto" in fresh[2])

    try:
        settings.build_dm_command({"agent_framework": "bogus"}, GAME_DIR, "s")
        check("unknown framework raises", False)
    except ValueError:
        check("unknown framework raises", True)


def test_settings_roundtrip() -> None:
    print("settings load/save round-trip")
    original = settings.SETTINGS_PATH
    with tempfile.TemporaryDirectory() as tmp:
        settings.SETTINGS_PATH = Path(tmp) / "settings.json"
        try:
            defaults = settings.load_settings()
            check("defaults when no file", defaults["agent_framework"] == "claude")

            settings.save_settings({"agent_framework": "agy", "model": "x"})
            settings.set_last_session_id("example-campaign", "abc-123")
            reloaded = settings.load_settings()
            check("framework persisted", reloaded["agent_framework"] == "agy")
            check("model persisted", reloaded["model"] == "x")
            check(
                "session id persisted",
                settings.get_last_session_id("example-campaign") == "abc-123",
            )
            check(
                "save keeps the sessions block",
                (
                    settings.save_settings({"model": "y"})
                    or settings.get_last_session_id("example-campaign") == "abc-123"
                ),
            )
        finally:
            settings.SETTINGS_PATH = original


def test_list_campaigns() -> None:
    print("list_campaigns")
    slugs = [s for s, _ in list_campaigns()]
    check("finds example-campaign", "example-campaign" in slugs)
    check("excludes template", "template" not in slugs)


def test_create_campaign() -> None:
    print("create_campaign")
    check("slugify kebab-cases", slugify("The Shattered Crown!") == "the-shattered-crown")
    check("slugify strips edges", slugify("  --Hi--  ") == "hi")

    original = campaign.CAMPAIGNS_DIR
    with tempfile.TemporaryDirectory() as tmp:
        campaigns_dir = Path(tmp) / "campaigns"
        campaigns_dir.mkdir()
        shutil.copytree(original / "template", campaigns_dir / "template")
        campaign.CAMPAIGNS_DIR = campaigns_dir
        try:
            slug = create_campaign("My Test Game")
            check("returns the slug", slug == "my-test-game")
            check("directory created", (campaigns_dir / "my-test-game").is_dir())
            cfg = json.loads((campaigns_dir / slug / "config.json").read_text())
            check("config name set", cfg["campaign_name"] == "My Test Game")
            canon = json.loads((campaigns_dir / slug / "canon.json").read_text())
            check("canon id set", canon["campaign_id"] == "my-test-game")
            try:
                create_campaign("My Test Game")
                check("duplicate rejected", False)
            except campaign.CampaignError:
                check("duplicate rejected", True)
        finally:
            campaign.CAMPAIGNS_DIR = original


async def _drive_menu() -> None:
    print("menu navigation (run_test)")
    original = settings.SETTINGS_PATH
    active_backup = campaign.ACTIVE_PATH.read_text()  # LoadGameScreen writes this
    with tempfile.TemporaryDirectory() as tmp:
        settings.SETTINGS_PATH = Path(tmp) / "settings.json"
        settings.save_settings({"agent_framework": "claude", "model": "my-custom"})
        try:
            app = MenuApp()
            async with app.run_test() as pilot:
                from textual.widgets import Button

                # The active campaign (example-campaign) has real game files with a
                # closed session, so Resume works off those — no stored id.
                resume_btn = app.query_one("#resume", Button)
                check("Resume enabled for in-progress campaign", not resume_btn.disabled)
                check(
                    "Resume names the campaign",
                    str(resume_btn.label).startswith("Resume — "),
                )

                await pilot.press("s")
                await pilot.pause()
                check("Settings opens", isinstance(app.screen, SettingsScreen))

                # Save without touching anything: the saved model must survive
                # (Select fires a Changed on mount).
                await pilot.click("#save")
                await pilot.pause()
                check(
                    "untouched save keeps the model",
                    settings.load_settings()["model"] == "my-custom",
                )

                await pilot.press("s")
                await pilot.pause()
                from textual.widgets import Select

                app.screen.query_one("#framework", Select).value = "agy"
                await pilot.pause()
                check(
                    "switching framework resets the model",
                    app.screen.query_one("#model", Select).value
                    == settings.FRAMEWORKS["agy"]["models"][0],
                )
                second = settings.FRAMEWORKS["agy"]["models"][1]
                app.screen.query_one("#model", Select).value = second
                await pilot.click("#save")
                await pilot.pause()
                check(
                    "Settings closes on save",
                    not isinstance(app.screen, SettingsScreen),
                )
                check("save wrote the preset model", settings.load_settings()["model"] == second)
                check(
                    "save wrote the framework",
                    settings.load_settings()["agent_framework"] == "agy",
                )

                # Custom entry: the text box appears and its text is what gets saved.
                await pilot.press("s")
                await pilot.pause()
                from textual.widgets import Input

                box = app.screen.query_one("#model-custom", Input)
                check("custom box hidden for a preset", not box.display)
                app.screen.query_one("#model", Select).value = CUSTOM
                await pilot.pause()
                check("custom box shown for Custom", box.display)
                box.value = " my-own-model "
                await pilot.click("#save")
                await pilot.pause()
                check("custom model saved, trimmed", settings.load_settings()["model"] == "my-own-model")

                await pilot.press("n")
                await pilot.pause()
                check("New Game opens", isinstance(app.screen, NewGameScreen))
                # Empty name is rejected, not acted on.
                await pilot.click("#create")
                await pilot.pause()
                check("New Game still open on empty name", isinstance(app.screen, NewGameScreen))
                from textual.widgets import Static

                check(
                    "empty name shows an error",
                    bool(str(app.screen.query_one("#newgame-error", Static).render())),
                )
                await pilot.press("escape")
                await pilot.pause()
                check("New Game cancels back", not isinstance(app.screen, NewGameScreen))

                await pilot.press("l")
                await pilot.pause()
                check("Load Game opens", isinstance(app.screen, LoadGameScreen))
                check(
                    "Load Game lists example-campaign",
                    bool(app.screen.query("#campaign-example-campaign")),
                )
                await pilot.press("escape")
                await pilot.pause()
                check("Load Game cancels back", not isinstance(app.screen, LoadGameScreen))

                await pilot.press("q")
                await pilot.pause()
            check("quit returns None", app.return_value is None)

            # Resume off game files: fresh session id, resume flag False.
            from dnd_cli.campaign import active_campaign_slug

            app2 = MenuApp()
            async with app2.run_test() as pilot:
                await pilot.press("r")
                await pilot.pause()
            check(
                "Resume targets the active campaign, fresh session",
                app2.return_value is not None
                and app2.return_value["campaign"] == active_campaign_slug()
                and app2.return_value["resume"] is False
                and len(app2.return_value["session_id"]) == 36,
            )

            # Load Game: pick a campaign -> it becomes active, app exits with it.
            targets = [s for s, _ in list_campaigns() if s != active_campaign_slug()]
            if targets:
                pick = targets[0]
                app3 = MenuApp()
                async with app3.run_test() as pilot:
                    from textual.widgets import Button

                    await pilot.press("l")
                    await pilot.pause()
                    app3.screen.query_one(f"#campaign-{pick}", Button).press()
                    await pilot.pause()
                check(
                    "Load Game selects and activates the campaign",
                    app3.return_value is not None
                    and app3.return_value["campaign"] == pick
                    and app3.return_value["resume"] is False
                    and active_campaign_slug() == pick,
                )
        finally:
            settings.SETTINGS_PATH = original
            campaign.ACTIVE_PATH.write_text(active_backup)


def test_menu_loop_orchestration() -> None:
    """run_menu_loop: run one game for a choice, then stop on None."""
    print("run_menu_loop orchestration")
    import view.menu as menu

    calls = {"menu": 0, "game": 0, "commands": []}

    class FakeMenu:
        def run(self):
            calls["menu"] += 1
            if calls["menu"] == 1:
                return {
                    "campaign": "example-campaign",
                    "session_id": "sid-x",
                    "resume": False,
                }
            return None

    class FakeView:
        def __init__(self, campaign_dir, *, session_id, dm_command):
            calls["commands"].append(dm_command)

        def run(self):
            calls["game"] += 1

    orig_menu, orig_view = menu.MenuApp, menu.ViewApp
    orig_settings = settings.SETTINGS_PATH
    menu.MenuApp, menu.ViewApp = FakeMenu, FakeView
    with tempfile.TemporaryDirectory() as tmp:
        settings.SETTINGS_PATH = Path(tmp) / "settings.json"
        try:
            menu.run_menu_loop()
        finally:
            menu.MenuApp, menu.ViewApp = orig_menu, orig_view
            settings.SETTINGS_PATH = orig_settings

    check("menu shown twice (choice, then quit)", calls["menu"] == 2)
    check("game run exactly once", calls["game"] == 1)
    check(
        "loop built a real DM command",
        bool(calls["commands"]) and calls["commands"][0][:2] == ["sh", "-c"],
    )


def main() -> int:
    test_build_dm_command()
    test_settings_roundtrip()
    # The real game/campaigns may hold anything (or nothing): use a fixed fixture.
    with fixture_campaigns():
        test_list_campaigns()
        test_create_campaign()
        test_menu_loop_orchestration()
        asyncio.run(_drive_menu())
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


@contextmanager
def fixture_campaigns():
    """A temp campaigns folder: the template and the example campaign (active), as play would see them."""
    saved = campaign.CAMPAIGNS_DIR, campaign.ACTIVE_PATH
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "campaigns"
        root.mkdir()
        shutil.copytree(saved[0] / "template", root / "template")
        shutil.copytree(Path(__file__).resolve().parent / "fixtures" / "example-campaign", root / "example-campaign")
        (root / "active.json").write_text('{"active_campaign_path": "campaigns/example-campaign"}')
        campaign.CAMPAIGNS_DIR, campaign.ACTIVE_PATH = root, root / "active.json"
        try:
            yield root
        finally:
            campaign.CAMPAIGNS_DIR, campaign.ACTIVE_PATH = saved


if __name__ == "__main__":
    raise SystemExit(main())
