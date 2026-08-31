"""`dungeon-os` — the launcher for a DungeonOS session.

With no arguments it opens the start menu (view/menu.py): Resume, New Game,
Settings. Give a campaign slug to skip the menu and drop straight into that
campaign with a fresh DM conversation.

`--web` serves the menu to a browser via textual-serve instead of running in
this terminal. Note that each browser connection there spawns its own DM
process (textual-serve starts a fresh app subprocess per connection) — fine
for solo play in one tab, but a second tab or a reload starts a second,
independent session.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import uuid
import webbrowser
from threading import Timer

from dnd_cli.campaign import (
    GAME_DIR,
    CampaignError,
    resolve_campaign_dir,
    set_active_campaign,
)
from view.settings import build_dm_command, load_settings, set_last_session_id

WEB_VIEW_URL = "http://127.0.0.1:8000"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dungeon-os",
        description="Start a DungeonOS session. With no campaign, opens the "
        "start menu (Resume / New Game / Settings).",
    )
    parser.add_argument(
        "campaign",
        nargs="?",
        help="Campaign slug: skip the menu and start this campaign directly",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Serve in a browser instead of this terminal (see caveat in --help header)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="With --web, start the server but don't auto-open a browser tab",
    )
    args = parser.parse_args()

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
