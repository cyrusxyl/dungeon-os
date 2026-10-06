"""`dungeon-os` — the launcher for a DungeonOS session.

By default it opens the visual stage (stage/server.py) in a browser, at its
start menu (Resume, Load Game, New Game, Settings), or straight into the
campaign slug given. The DM runs in a PTY that the stage server owns.

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
import os
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from threading import Timer

from dnd_cli.campaign import REPO_ROOT, CampaignError, resolve_campaign_dir
from view.settings import new_dm_session

WEB_VIEW_URL = "http://127.0.0.1:8000"


def _newest(paths) -> float:
    return max((p.stat().st_mtime for p in paths if p.is_file()), default=0.0)


def ensure_web_build() -> None:
    """Build the stage UI if it is missing or older than its sources (after a pull or an edit)."""
    web = REPO_ROOT / "stage" / "web"
    built = web / "dist" / "index.html"
    sources = [*web.joinpath("src").rglob("*"), web / "index.html", web / "package.json", web / "vite.config.ts"]
    if built.exists() and built.stat().st_mtime >= _newest(sources):
        return
    if not shutil.which("npm"):
        print("dungeon-os: the stage UI needs a build and npm is not on PATH.", file=sys.stderr)
        return
    print("dungeon-os: building the stage UI…", file=sys.stderr)
    modules = web / "node_modules" / ".package-lock.json"
    if not modules.exists() or modules.stat().st_mtime < _newest([web / "package-lock.json"]):
        subprocess.run(["npm", "install", "--silent"], cwd=web, check=True)
    subprocess.run(["npm", "run", "build", "--silent"], cwd=web, check=True)


def lan_hosts() -> list[str]:
    """The names this computer answers to on the network: its address, its host name and the .local name. The IP comes
    from the route to a documentation address (RFC 5737); a UDP connect sends no packet."""
    name = socket.gethostname()
    found = [name, f"{name}.local"]
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            found.insert(0, probe.getsockname()[0])
    except OSError:
        pass  # no network route: the names still work
    return found


def run_stage(campaign: str | None, open_browser: bool, host: str, port: int, allowed_hosts: list[str]) -> None:
    """Serve the visual stage: the start menu, or straight into one campaign."""
    from stage.server import LOCAL_HOSTS, serve

    campaign_dir = None
    if campaign:
        try:
            campaign_dir = resolve_campaign_dir(campaign)
        except CampaignError as exc:
            print(f"dungeon-os: {exc}", file=sys.stderr)
            raise SystemExit(1)

    ensure_web_build()
    try:
        from stage.assets import ensure_dcss, ensure_lpc, ensure_tiles

        ensure_lpc()
        ensure_tiles()
        ensure_dcss()
        from stage import actors, lpc

        # Index the art in the background: the first portrait then shows at once.
        threading.Thread(target=lambda: (lpc.catalog(), actors.dcss_monsters()), daemon=True).start()
    except Exception as exc:  # The stage still runs, with silhouettes and blank rooms.
        print(f"dungeon-os: {exc}", file=sys.stderr)
    # Tell the owner the address to open on the table screen: a phone cannot join through "localhost".
    url = f"http://{host if host in LOCAL_HOSTS else (allowed_hosts[0] if allowed_hosts else 'localhost')}:{port}"
    if open_browser and host in LOCAL_HOSTS:
        Timer(1.5, webbrowser.open, args=(url,)).start()
    print(f"DungeonOS: {url}", file=sys.stderr)
    if host not in LOCAL_HOSTS:
        print("DungeonOS: no password. Allowed host names: " + (", ".join(allowed_hosts) or "none (add --allow-host)"),
              file=sys.stderr)
    serve(campaign_dir, host=host, port=port, allowed_hosts=allowed_hosts)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dungeon-os",
        description="Start DungeonOS on the visual stage: the start menu, or the "
        "campaign given. --classic opens the earlier terminal view.",
    )
    parser.add_argument(
        "campaign",
        nargs="?",
        help="Campaign slug: skip the menu and start this campaign directly",
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
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Address to listen on (default 127.0.0.1; use 0.0.0.0 for a home server). There is no password.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", 8000)),
        help="Port to listen on (default: $PORT, else 8000)",
    )
    parser.add_argument(
        "--allow-host",
        action="append",
        default=[],
        metavar="NAME",
        help="Host name or IP the browser may use besides localhost; repeat for more",
    )
    parser.add_argument(
        "--lan",
        action="store_true",
        help="Let phones and other computers on your network join: listen on every address and allow this computer's "
        "network address and name. Add --allow-host for any other name (a Tailscale name). There is no password.",
    )
    args = parser.parse_args()
    if args.lan:
        args.host = "0.0.0.0"
        args.allow_host = [*lan_hosts(), *args.allow_host]

    if not args.classic:
        run_stage(args.campaign, not args.no_browser, args.host, args.port, args.allow_host)
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
        session_id, dm_command = new_dm_session(campaign_dir)
        ViewApp(
            campaign_dir, session_id=session_id, dm_command=dm_command
        ).run()
        return

    from view.menu import run_menu_loop

    run_menu_loop()


if __name__ == "__main__":
    main()
