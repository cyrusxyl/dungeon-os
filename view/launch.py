"""`dungeon-os` — one-liner launcher for a DungeonOS session.

Resolves the campaign (defaulting to the active one) and hands off to the
view: a real terminal running `claude` on the left, a live state/character
panel on the right (see view/app.py). By default this runs as a local TUI —
one process, one terminal, no ambiguity about who's driving the session.

`--web` instead serves it to a browser via textual-serve. Note that each
browser connection there spawns its own `claude` process (textual-serve
starts a fresh app subprocess per connection) — fine for solo play in one
tab, but opening a second tab or reloading starts a second, independent DM
session rather than sharing the first one.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
import webbrowser
from pathlib import Path
from threading import Timer

from dnd_cli.campaign import GAME_DIR, CampaignError, resolve_campaign_dir

WEB_VIEW_URL = "http://127.0.0.1:8000"


def _active_campaign_slug() -> str:
    active_path = GAME_DIR / "campaigns" / "active.json"
    active = json.loads(active_path.read_text())
    return Path(active["active_campaign_path"]).name


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dungeon-os",
        description="Start a DungeonOS session: a real terminal running the DM, "
        "plus a live state panel.",
    )
    parser.add_argument(
        "campaign", nargs="?", help="Campaign slug (default: the active campaign)"
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

    campaign_slug = args.campaign or _active_campaign_slug()
    try:
        resolve_campaign_dir(campaign_slug)
    except CampaignError as exc:
        print(f"dungeon-os: {exc}", file=sys.stderr)
        raise SystemExit(1)

    if args.web:
        if not args.no_browser:
            Timer(1.5, webbrowser.open, args=(WEB_VIEW_URL,)).start()
        print(f"Player view: {WEB_VIEW_URL}", file=sys.stderr)
        subprocess.run([sys.executable, "-m", "view.serve", campaign_slug])
        return

    from view.app import ViewApp

    session_id = str(uuid.uuid4())
    ViewApp(resolve_campaign_dir(campaign_slug), session_id=session_id).run()


if __name__ == "__main__":
    main()
