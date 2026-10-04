"""Fetch the third-party pixel art the stage composes from, on first use.

The art is not committed and not redistributed: it is fetched into the
git-ignored `assets/` directory at the repo root. Each source keeps its
credits file next to it (LPC art is CC-BY-SA / GPL / OGA-BY; see those files).

- `assets/lpc/` — Universal LPC Spritesheet Character Generator, pinned to one
  commit (its sheet_definitions format changes over time and the composer
  depends on it). Only the walk sheets are fetched (~45 MB): frame 0 of a walk
  row is the standing pose the stage uses.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from dnd_cli.campaign import REPO_ROOT

ASSETS_DIR = REPO_ROOT / "assets"
LPC_DIR = ASSETS_DIR / "lpc"
LPC_REPO = "https://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator.git"
LPC_COMMIT = "ba4beebe6d3d54c7125aeb23848ac9afbacb7369"
LPC_SPARSE = ["/*", "!/spritesheets/", "/spritesheets/**/walk.png", "/spritesheets/**/walk/*.png"]


class AssetError(RuntimeError):
    """Art could not be fetched. The message says what to run by hand."""


def _git(*args: str, cwd: Path | None = None) -> None:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssetError(f"git {' '.join(args[:2])} failed: {result.stderr.strip()[:300]}")


def ensure_lpc() -> Path:
    """Return the LPC checkout, cloning it on first use."""
    if (LPC_DIR / "sheet_definitions").is_dir() and (LPC_DIR / "spritesheets").is_dir():
        return LPC_DIR
    print("dungeon-os: fetching LPC character art (first run only, ~45 MB)…", file=sys.stderr)
    ASSETS_DIR.mkdir(exist_ok=True)
    try:
        if not (LPC_DIR / ".git").is_dir():
            _git("clone", "--quiet", "--filter=blob:none", "--no-checkout", LPC_REPO, str(LPC_DIR))
        _git("sparse-checkout", "set", "--no-cone", *LPC_SPARSE, cwd=LPC_DIR)
        _git("checkout", "--quiet", LPC_COMMIT, cwd=LPC_DIR)
    except (AssetError, OSError) as e:
        raise AssetError(
            f"Could not fetch the LPC art into {LPC_DIR}: {e}. Check the network, "
            f"delete {LPC_DIR}, and start again."
        ) from e
    return LPC_DIR
