"""LPC-style animals as stage actors: one frame cut from a walk sheet in assets/tiles.

Data lives in stage/data/creatures.json. A creature spec is `{"tile": "creature:<id>"}`
(see stage/actors.py); `frame` gives the picture for a facing, trimmed to the animal.
"""

from __future__ import annotations

import colorsys
import json
from functools import cache, lru_cache
from pathlib import Path

from PIL import Image

from stage.assets import TILES_DIR, ensure_tiles

DATA_PATH = Path(__file__).resolve().parent / "data" / "creatures.json"
PREFIX = "creature:"
OPPOSITE = {"left": "right", "right": "left"}


@cache
def data() -> dict:
    return json.loads(DATA_PATH.read_text())


def catalog() -> dict[str, dict]:
    return data()["creatures"]


@cache
def names() -> dict[str, str]:
    """Every name that picks a creature: its id (with '-'), and the D&D names."""
    return {**{cid.replace("_", "-"): cid for cid in catalog()}, **data()["names"]}


def find(name: str) -> str | None:
    """The spec tile for a name, like 'creature:horse', or None."""
    cid = names().get(name.lower().replace("_", "-").replace(" ", "-"))
    return PREFIX + cid if cid else None


def scale(tile: str) -> float:
    return catalog()[tile.removeprefix(PREFIX)].get("scale", 1)


def recolor(img: Image.Image, hue: float = 0, sat: float = 1, value: float = 1) -> Image.Image:
    """Shift the colours of a picture; the transparent pixels stay clear."""
    px = []
    for r, g, b, a in img.getdata():
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        r, g, b = colorsys.hsv_to_rgb((h + hue / 360) % 1, min(1, s * sat), min(1, v * value))
        px.append((round(r * 255), round(g * 255), round(b * 255), a))
    out = Image.new("RGBA", img.size)
    out.putdata(px)
    return out


@lru_cache(maxsize=128)
def frame(tile: str, facing: str) -> Image.Image:
    """The animal facing `facing` (down, up, left or right), trimmed to its pixels."""
    c = catalog()[tile.removeprefix(PREFIX)]
    ensure_tiles()
    fw, fh = c["frame"]
    rows = c["rows"]
    flip = False
    if facing in rows:
        row = rows[facing]
    elif OPPOSITE.get(facing) in rows:
        row, flip = rows[OPPOSITE[facing]], True
    else:
        row = rows.get("down", next(iter(rows.values())))
    col = c.get("col", 0)
    img = Image.open(TILES_DIR / c["file"]).convert("RGBA").crop((col * fw, row * fh, (col + 1) * fw, (row + 1) * fh))
    if c.get("recolor"):
        img = recolor(img, **c["recolor"])
    if flip:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return img.crop(img.getbbox() or (0, 0, fw, fh))
