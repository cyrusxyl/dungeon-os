"""Fetch the third-party pixel art the stage composes from, on first use.

The art is not committed and not redistributed: it is fetched into the
git-ignored `assets/` directory at the repo root. Each source keeps its
credits file next to it (LPC art is CC-BY-SA / GPL / OGA-BY; see those files).

- `assets/lpc/` — Universal LPC Spritesheet Character Generator, pinned to one
  commit (its sheet_definitions format changes over time and the composer
  depends on it). Only the walk sheets are fetched (~45 MB): frame 0 of a walk
  row is the standing pose the stage uses.
- `assets/tiles/` — LPC tile packs from OpenGameArt (walls, floors, city
  interior, base exterior and terrain atlases), for rooms and streets.
- `assets/dcss/` — the CC0 Dungeon Crawl Stone Soup tiles (Snowdrama's
  bundle), for beasts and monsters LPC has no body for.
"""

from __future__ import annotations

import io
import subprocess
import sys
import urllib.request
import zipfile
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


TILES_DIR = ASSETS_DIR / "tiles"
OGA = "https://opengameart.org/sites/default/files/"
# folder -> (archive, the file in it that proves it is unpacked)
TILE_PACKS = {
    "walls": ("lpc-walls.zip", "lpc-walls/walls.png"),
    "floors": ("lpc-floors.zip", "lpc-floors/floors.png"),
    "city_inside": ("LPC_city_inside.zip", "LPC_city_inside/city_inside.png"),
    "atlas": ("Atlas_0.zip", "base_out_atlas.png"),
}

DCSS_DIR = ASSETS_DIR / "dcss"
DCSS_REPO = "https://github.com/Snowdrama/CC0-Dungeon-Pack.git"
DCSS_COMMIT = "ce84ee3930ae2ed6449925a54cf847e754c8836e"


def ensure_tiles() -> Path:
    """Return the tile folder, downloading the LPC tile packs on first use."""
    for folder, (archive, marker) in TILE_PACKS.items():
        dest = TILES_DIR / folder
        if (dest / marker).exists():
            continue
        print(f"dungeon-os: fetching LPC tiles: {archive}…", file=sys.stderr)
        try:
            with urllib.request.urlopen(OGA + archive, timeout=60) as resp:
                data = resp.read()
            dest.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                z.extractall(dest, [n for n in z.namelist() if not n.startswith("__MACOSX")])
        except (OSError, zipfile.BadZipFile) as e:
            raise AssetError(f"Could not fetch {OGA + archive}: {e}. Check the network and start again.") from e
    return TILES_DIR


def ensure_dcss() -> Path:
    """Return the CC0 DCSS tiles, cloning them on first use (~35 MB)."""
    if (DCSS_DIR / "monster").is_dir():
        return DCSS_DIR
    print("dungeon-os: fetching CC0 monster tiles (first run only, ~35 MB)…", file=sys.stderr)
    try:
        if not (DCSS_DIR / ".git").is_dir():
            _git("clone", "--quiet", "--no-checkout", DCSS_REPO, str(DCSS_DIR))
        _git("checkout", "--quiet", DCSS_COMMIT, cwd=DCSS_DIR)
    except (AssetError, OSError) as e:
        raise AssetError(f"Could not fetch the DCSS tiles into {DCSS_DIR}: {e}. Delete it and start again.") from e
    return DCSS_DIR
