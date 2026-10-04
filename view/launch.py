"""`dungeon-os` — the launcher for a DungeonOS session.

By default it opens the visual stage (stage/server.py) in a browser for the
active campaign, or for the campaign slug given. The DM runs in a PTY that the
stage server owns.

`--classic` keeps the earlier terminal flow: with no arguments it opens the
start menu (view/menu.py): Resume, New Game, Settings. Give a campaign slug to
skip the menu and drop straight into that campaign with a fresh DM
conversation.

`--web` serves the menu to a browser via textual-serve instead of running in
this terminal. Note that each browser connection there spawns its own DM
process (textual-serve starts a fresh app subprocess per connection) — fine
for solo play in one tab, but a second tab or a reload starts a second,
independent session.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import uuid
import webbrowser
from threading import Timer

from dnd_cli.campaign import (
    GAME_DIR,
    REPO_ROOT,
    CampaignError,
    resolve_campaign_dir,
    set_active_campaign,
)
from dnd_cli.campaign import active_campaign_slug
from view.settings import build_dm_command, load_settings, set_last_session_id

WEB_VIEW_URL = "http://127.0.0.1:8000"
def stage_first_prompt(campaign_slug: str) -> str:
    # Name the campaign: without it, the DM may "correct" active.json from memory.
    return (
        f"Start the session for the campaign `{campaign_slug}`. campaigns/active.json "
        "already points at it; do not change that file. The players watch the visual "
        "stage, so show every scene, narration line and NPC line with "
        "`uv run dnd-cli show beat` (load the `stage` skill first)."
    )


def ensure_web_build() -> None:
    """Build the stage UI once, if it is missing and npm is available."""
    web = REPO_ROOT / "stage" / "web"
    if (web / "dist" / "index.html").exists():
        return
    if not shutil.which("npm"):
        print("dungeon-os: the stage UI is not built and npm is not on PATH.", file=sys.stderr)
        return
    print("dungeon-os: building the stage UI (first run only)…", file=sys.stderr)
    subprocess.run(["npm", "install", "--silent"], cwd=web, check=True)
    subprocess.run(["npm", "run", "build", "--silent"], cwd=web, check=True)


def run_stage(campaign: str | None, open_browser: bool) -> None:
    from stage.server import serve

    try:
        campaign_dir = resolve_campaign_dir(campaign or active_campaign_slug())
    except (CampaignError, OSError, KeyError) as exc:
        print(f"dungeon-os: {exc}", file=sys.stderr)
        raise SystemExit(1)

    ensure_web_build()
    set_active_campaign(campaign_dir.name)
    session_id = str(uuid.uuid4())
    set_last_session_id(campaign_dir.name, session_id)
    dm_command = build_dm_command(
        load_settings(), GAME_DIR, session_id, initial_prompt=stage_first_prompt(campaign_dir.name)
    )
    if open_browser:
        Timer(1.5, webbrowser.open, args=(WEB_VIEW_URL,)).start()
    print(f"DungeonOS stage for {campaign_dir.name}: {WEB_VIEW_URL}", file=sys.stderr)
    serve(campaign_dir, dm_command)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dungeon-os",
        description="Start a DungeonOS session on the visual stage, for the "
        "active campaign or the one given. --classic opens the earlier terminal "
        "start menu (Resume / New Game / Settings).",
    )
    parser.add_argument(
        "campaign",
        nargs="?",
        help="Campaign slug (default: the active campaign)",
    )
    parser.add_argument(
        "--classic",
        action="store_true",
        help="Use the earlier terminal view and start menu instead of the visual stage",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="With --classic: serve the terminal view in a browser (see caveat in --help header)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the server but don't auto-open a browser tab",
    )
    args = parser.parse_args()

    if not args.classic:
        run_stage(args.campaign, open_browser=not args.no_browser)
        return

    if args.web:
        if not args.no_browser:
            Timer(1.5, webbrowser.open, args=(WEB_VIEW_URL,)).start()
        print(f"Player view: {WEB_VIEW_URL}", file=sys.stderr)
        subprocess.run([sys.executable, "-m", "view.serve"])
        return

    if args.campaign:
        try:
            campaign_dir = resolve_campaign_dir(args.campaign)
        except CampaignError as exc:
            print(f"dungeon-os: {exc}", file=sys.stderr)
            raise SystemExit(1)

        from view.app import ViewApp

        # The DM reads campaigns/active.json at session start, and the side
        # panel follows it too — keep both pointed at what we are launching.
        set_active_campaign(campaign_dir.name)
        session_id = str(uuid.uuid4())
        set_last_session_id(campaign_dir.name, session_id)
        dm_command = build_dm_command(load_settings(), GAME_DIR, session_id)
        ViewApp(
            campaign_dir, session_id=session_id, dm_command=dm_command
        ).run()
        return

    from view.menu import run_menu_loop

    run_menu_loop()


if __name__ == "__main__":
    main()
