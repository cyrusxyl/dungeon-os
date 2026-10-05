"""Fetch the third-party pixel art the stage composes from, on first use.

The art is not committed and not redistributed: it is fetched into the
git-ignored `assets/` directory at the repo root. Each source keeps its
credits file next to it (LPC art is CC-BY-SA / GPL / OGA-BY; see those files).

- `assets/lpc/` — Universal LPC Spritesheet Character Generator, pinned to one
  commit (its sheet_definitions format changes over time and the composer
  depends on it). Only the walk sheets are fetched (~45 MB): frame 0 of a walk
  row is the standing pose the stage uses.
- `assets/tiles/` — LPC tile packs from OpenGameArt (walls, floors, city
  interior, base exterior and terrain atlases, house interior, medieval
  decorations, cavern and ruins, winter tiles), for rooms, streets and camps.
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


def _clone_pinned(dest: Path, repo: str, commit: str, what: str, sparse: list[str] | None = None) -> None:
    """Clone a repository at one pinned commit (optionally sparse) into dest."""
    print(f"dungeon-os: fetching {what} (first run only)…", file=sys.stderr)
    ASSETS_DIR.mkdir(exist_ok=True)
    try:
        if not (dest / ".git").is_dir():
            _git("clone", "--quiet", *(["--filter=blob:none"] if sparse else []), "--no-checkout", repo, str(dest))
        if sparse:
            _git("sparse-checkout", "set", "--no-cone", *sparse, cwd=dest)
        _git("checkout", "--quiet", commit, cwd=dest)
    except (AssetError, OSError) as e:
        raise AssetError(f"Could not fetch {what} into {dest}: {e}. Check the network, delete {dest}, and start again.") from e


def ensure_lpc() -> Path:
    """Return the LPC checkout, cloning it on first use (~45 MB)."""
    if not ((LPC_DIR / "sheet_definitions").is_dir() and (LPC_DIR / "spritesheets").is_dir()):
        _clone_pinned(LPC_DIR, LPC_REPO, LPC_COMMIT, "LPC character art (~45 MB)", LPC_SPARSE)
    return LPC_DIR


TILES_DIR = ASSETS_DIR / "tiles"
OGA = "https://opengameart.org/sites/default/files/"
# folder -> (archive, the file in it that proves it is unpacked). A list of
# PNG names instead of an archive downloads each PNG into the folder, and
# CREDITS writes the credit line that the PNGs do not carry.
TILE_PACKS = {
    "walls": ("lpc-walls.zip", "lpc-walls/walls.png"),
    "floors": ("lpc-floors.zip", "lpc-floors/floors.png"),
    "city_inside": ("LPC_city_inside.zip", "LPC_city_inside/city_inside.png"),
    "atlas": ("Atlas_0.zip", "base_out_atlas.png"),
    "interior": ("LPC_house_interior_0.zip", "LPC_house_interior/interior.png"),
    "decor": ("decoration_medieval.zip", "decoration_medieval/decorations-medieval.png"),
    "ruins": ("LPC_cavern_ruins.zip", "LPC_cavern_ruins/cavern_ruins.png"),
    "winter": (["TilesA2.png", "TilesB.png"], "TilesB.png"),
    "animals": ("lpc_animals_2022_v1.1.zip", "lpc animals 2022 v1.1/individual creature spritesheets/lion.png"),
    "horses": ("horse-1.1.zip", "PNG/64x64/horse-brown.png"),
    "pets": (["cat_0.png", "dog_2.png", "chicken_walk.png", "cow_walk.png", "llama_walk_0.png", "pig_walk.png",
              "sheep_walk.png", "pegasus.png", "unicorn_0.png"], "unicorn_0.png"),
}
CREDITS = {
    "winter": "LPC Winter Tiles by Demetrius, https://opengameart.org/content/lpc-winter-tiles\n"
              "Based on LPC Modified Base tiles by Lanea Zimmerman. Licenses: CC-BY 3.0, OGA-BY 3.0, GPL 3.0, CC-BY-SA 3.0.\n",
    "animals": "[LPC] bears, deer, lions and more, https://opengameart.org/content/lpc-bears-deer-lions-and-more\n"
               "License: CC-BY 4.0. Adapted from work by Sevarihk (shiba dog, shark, giant rat, mushroom walker) under CC-BY 4.0.\n",
    "horses": "[LPC] Horses by bluecarrot16, reworked by Jordan Irwin (AntumDeluge), https://opengameart.org/content/lpc-horses-rework\n"
              "Licenses: CC-BY 3.0, CC-BY-SA 3.0, GPL 3.0, GPL 2.0, OGA-BY 3.0.\n",
    "pets": "[LPC] Cats and Dogs by bluecarrot16, https://opengameart.org/content/lpc-cats-and-dogs (CC-BY 3.0, GPL 3.0, GPL 2.0, OGA-BY 3.0).\n"
            "LPC style farm animals (chicken, cow, llama, pig, sheep), https://opengameart.org/content/lpc-style-farm-animals (CC-BY 3.0, GPL 2.0).\n"
            "Pegasus and unicorn from LPC Horses Rework, https://opengameart.org/content/lpc-horses-rework (CC-BY 3.0, CC-BY-SA 3.0).\n",
}

DCSS_DIR = ASSETS_DIR / "dcss"
DCSS_REPO = "https://github.com/Snowdrama/CC0-Dungeon-Pack.git"
DCSS_COMMIT = "ce84ee3930ae2ed6449925a54cf847e754c8836e"


def _download(name: str) -> bytes:
    try:
        with urllib.request.urlopen(OGA + name, timeout=60) as resp:
            return resp.read()
    except OSError as e:
        raise AssetError(f"Could not fetch {OGA + name}: {e}. Check the network and start again.") from e


def ensure_tiles() -> Path:
    """Return the tile folder, downloading the LPC tile packs on first use."""
    for folder, (archive, marker) in TILE_PACKS.items():
        dest = TILES_DIR / folder
        if (dest / marker).exists():
            continue
        print(f"dungeon-os: fetching LPC tiles: {folder}…", file=sys.stderr)
        dest.mkdir(parents=True, exist_ok=True)
        if isinstance(archive, list):
            for name in archive:
                (dest / name).write_bytes(_download(name))
        else:
            try:
                with zipfile.ZipFile(io.BytesIO(_download(archive))) as z:
                    z.extractall(dest, [n for n in z.namelist() if not n.startswith("__MACOSX")])
            except zipfile.BadZipFile as e:
                raise AssetError(f"Could not unpack {OGA + archive}: {e}. Check the network and start again.") from e
        if folder in CREDITS:
            (dest / "CREDITS.txt").write_text(CREDITS[folder])
    return TILES_DIR


def ensure_dcss() -> Path:
    """Return the CC0 DCSS tiles, cloning them on first use (~35 MB)."""
    if not (DCSS_DIR / "monster").is_dir():
        _clone_pinned(DCSS_DIR, DCSS_REPO, DCSS_COMMIT, "CC0 Dungeon Crawl tiles (~35 MB)")
    return DCSS_DIR
