"""Browser entry point: the start menu (and the game it launches), over the web.

Uses textual-serve's Server directly rather than the `textual serve` CLI
subcommand — that CLI ships with textual-dev, a heavier dev-tooling
dependency this project doesn't otherwise need. textual-serve alone is
enough to run any Textual app in a browser.

Binds to 127.0.0.1 by default: this is a local viewer for one player at
their own machine, not something to expose on the network.
"""

from __future__ import annotations

import shlex
import sys

from textual_serve.server import Server


def main() -> None:
    command = f"{shlex.quote(sys.executable)} -m view.menu"
    server = Server(command, host="127.0.0.1", port=8000)
    server.serve()


if __name__ == "__main__":
    main()
