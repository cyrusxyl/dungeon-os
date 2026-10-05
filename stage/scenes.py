"""Compose a scene background from LPC tiles: templates, slots, zones, moods.

A scene spec is plain data, written by `dnd-cli scene set` to
`{campaign}/stage/scenes/<location-id>.json`:

    {"template": "chapel", "wall": "stone_dark", "mood": "dusk",
     "slots": {"wall_center": "bust"}, "add": [["barrel_pile", "back-right"]]}

The DM never gives a pixel position. A template fills the room and names a
default prop for some slots. The spec can change the wall or floor style,
replace or empty a slot, and add extra props into a zone; the composer finds
the spot. The stage is 10 x 6 tiles of 32 px (320 x 192).
"""

from __future__ import annotations

import hashlib
import io
import json
from functools import cache, lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from stage.assets import ASSETS_DIR, ensure_dcss, ensure_tiles
from stage.files import read_json, write_json

T = 32
COLS, ROWS = 10, 6
W, H = COLS * T, ROWS * T
WALL_ROWS = 3
CATALOG_PATH = Path(__file__).resolve().parent / "data" / "scenery.json"

WALL_SLOTS = {"wall_left": 48, "wall_left2": 104, "wall_center": 160, "wall_right2": 216, "wall_right": 272}
ZONE_X = {"left": 64, "center": 160, "right": 256}
ZONE_BASELINE = {"back": 120, "mid": 152, "front": 186}
ZONES = [f"{row}_{col}" for row in ZONE_BASELINE for col in ZONE_X]
SLOTS = list(WALL_SLOTS) + ZONES


# The DM's study: the loading screen of the stage, while the DM works. Not a campaign scene.
FILLER = {
    "template": "house", "wall": "timber", "floor": "planks_dark", "mood": "torchlit",
    "slots": {"wall_left": "window_arched", "wall_center": "fireplace", "wall_right": "tapestry",
              "wall_left2": "cabinet", "wall_right2": "dresser", "back_left": "chests", "back_center": None,
              "back_right": "barrel_pile", "mid_center": "table_long", "mid_left": None, "mid_right": None,
              "front_left": "plant", "front_right": "brazier"},
}


class SceneError(ValueError):
    """A bad scene spec. The message says how to fix it."""


@cache
def catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text())


@cache
def _sheet(name: str) -> Image.Image:
    if name.startswith("dcss:"):
        return Image.open(ensure_dcss() / name[5:]).convert("RGBA")
    ensure_tiles()
    return Image.open(ASSETS_DIR / catalog()["sheets"][name]).convert("RGBA")


def _crop(sheet: str, rect: list[int]) -> Image.Image:
    c, r, w, h = rect
    return _sheet(sheet).crop((c * T, r * T, (c + w) * T, (r + h) * T))


@cache
def prop_image(name: str) -> Image.Image:
    p = catalog()["props"][name]
    if "parts" in p:
        w, h = p["size"]
        img = Image.new("RGBA", (w * T, h * T))
        for part in p["parts"]:
            img.alpha_composite(_crop(part["sheet"], part["rect"]), (0, part.get("dy", 0) * T))
        return img
    if p["sheet"].startswith("dcss:"):
        return _sheet(p["sheet"]).copy()
    return _crop(p["sheet"], p["rect"])


def surface_tile(name: str, col: int, row: int) -> Image.Image:
    cat = catalog()
    if name in cat["floors"]:
        c, r = cat["floors"][name]
        return _crop("floors", [c + col % 2, r + row % 2, 1, 1])
    ground = cat["grounds"][name]
    # Pick a variant per tile, stable for the same spot.
    pick = int(hashlib.md5(f"{name}{col},{row}".encode()).hexdigest(), 16) % len(ground["tiles"])
    c, r = ground["tiles"][pick]
    return _crop(ground["sheet"], [c, r, 1, 1])


@cache
def _wall_width(style: str) -> int:
    """3 or 4: some wall blocks have no separate right-edge column."""
    c, r = catalog()["walls"][style]
    edge = _crop("walls", [c + 3, r, 1, WALL_ROWS]).getchannel("A")
    return 4 if sum(edge.getdata()) > 0.8 * 255 * edge.width * edge.height else 3


def _wall_tile(style: str, col: int, first: int, last: int) -> Image.Image:
    c, r = catalog()["walls"][style]
    if _wall_width(style) == 4:
        offset = 0 if col == first else 3 if col == last else 1 + (col - first) % 2
    else:
        offset = 0 if col == first else 2 if col == last else 1
    return _crop("walls", [c + offset, r, 1, WALL_ROWS])


def _suggest(name: str, options) -> str:
    from rapidfuzz import process

    best = process.extract(name, list(options), limit=3)
    return ", ".join(b[0] for b in best)


def resolve(spec: dict) -> dict:
    """Merge the template with the spec's changes; raise SceneError if anything is unknown."""
    cat = catalog()
    template_name = spec.get("template")
    if template_name not in cat["templates"]:
        raise SceneError(f"template {template_name!r} is not one of {', '.join(cat['templates'])}.")
    t = cat["templates"][template_name]
    wall = spec.get("wall", t.get("wall"))
    out = {
        "walls": wall if isinstance(wall, list) else [wall] if wall else [],
        "floor": spec.get("floor", t["floor"]),
        "rows": dict(t.get("rows", {})),
        "slots": {**t.get("slots", {}), **spec.get("slots", {})},
        "add": list(spec.get("add", [])),
        "mood": spec.get("mood") or t.get("mood") or "day",
    }
    surfaces = {**cat["floors"], **cat["grounds"]}
    for w in out["walls"]:
        if w not in cat["walls"]:
            raise SceneError(f"wall {w!r} is not known. Close: {_suggest(w, cat['walls'])}.")
    for s in [out["floor"], *out["rows"].values()]:
        if s not in surfaces:
            raise SceneError(f"floor {s!r} is not known. Close: {_suggest(s, surfaces)}.")
    if out["mood"] not in cat["moods"]:
        raise SceneError(f"mood {out['mood']!r} is not one of {', '.join(cat['moods'])}.")
    for slot, prop in out["slots"].items():
        if slot not in SLOTS:
            raise SceneError(f"slot {slot!r} is not one of {', '.join(SLOTS)}.")
    for prop, zone in out["add"]:
        if zone not in ZONES:
            raise SceneError(f"zone {zone!r} is not one of {', '.join(ZONES)}.")
    for prop in [*filter(None, out["slots"].values()), *(p for p, _ in out["add"])]:
        if prop not in cat["props"]:
            raise UnknownProp(prop, f"prop {prop!r} is not in the catalog. Close: {_suggest(prop, cat['props'])}.")
    return out


class UnknownProp(SceneError):
    def __init__(self, prop: str, message: str):
        super().__init__(message)
        self.prop = prop


def _place(img: Image.Image, name: str, slot: str, nudge: int = 0) -> tuple[int, int]:
    """Top-left corner for a prop image at a slot."""
    prop = catalog()["props"][name]
    w, h = img.size
    if slot in WALL_SLOTS:
        x = WALL_SLOTS[slot] - w // 2
        # Doors stand on the floor line; other wall pieces hang near the top.
        y = WALL_ROWS * T - h if h >= 2 * T and prop.get("on") == "wall" and "door" in name else 12
        return x, y
    row, col = slot.split("_")
    baseline = ZONE_BASELINE[row]
    if prop.get("flat"):
        baseline += h // 2 - 16
    return ZONE_X[col] - w // 2 + nudge, baseline - h


def _mood(img: Image.Image, mood: str) -> Image.Image:
    if mood == "day":
        return img
    rgb = img.convert("RGB")
    if mood == "dusk":
        rgb = Image.blend(rgb, Image.new("RGB", rgb.size, (255, 130, 60)), 0.18)
        rgb = Image.blend(rgb, Image.new("RGB", rgb.size, (40, 20, 50)), 0.15)
    elif mood == "night":
        rgb = Image.blend(rgb, Image.new("RGB", rgb.size, (18, 24, 64)), 0.5)
    elif mood == "rain":
        rgb = Image.blend(rgb, Image.new("RGB", rgb.size, (30, 40, 70)), 0.35)
        streaks = Image.new("RGBA", rgb.size)
        d = ImageDraw.Draw(streaks)
        for i in range(90):
            x = (i * 37) % (W + 40) - 20
            y = (i * 53) % H
            d.line((x, y, x - 4, y + 10), fill=(200, 210, 255, 90))
        rgb = Image.alpha_composite(rgb.convert("RGBA"), streaks).convert("RGB")
    elif mood == "fog":
        fog = Image.new("L", rgb.size)
        d = ImageDraw.Draw(fog)
        for y in range(H):
            d.line((0, y, W, y), fill=int(40 + 110 * y / H))
        rgb = Image.composite(Image.new("RGB", rgb.size, (210, 215, 220)), rgb, fog.point(lambda v: v // 2))
    elif mood == "torchlit":
        dark = Image.blend(rgb, Image.new("RGB", rgb.size, (10, 8, 16)), 0.55)
        light = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(light).ellipse((W * 0.1, H * 0.05, W * 0.9, H * 1.3), fill=255)
        light = light.filter(ImageFilter.GaussianBlur(40))
        warm = Image.blend(rgb, Image.new("RGB", rgb.size, (255, 170, 90)), 0.12)
        rgb = Image.composite(warm, dark, light)
    return rgb.convert("RGBA")


def render(spec: dict) -> Image.Image:
    r = resolve(spec)
    cat = catalog()
    img = Image.new("RGBA", (W, H), (20, 18, 24, 255))
    walls = r["walls"]
    first_floor_row = WALL_ROWS if walls else 0
    for row in range(first_floor_row, ROWS):
        surface = r["rows"].get(str(row), r["floor"])
        for col in range(COLS):
            img.alpha_composite(surface_tile(surface, col, row), (col * T, row * T))
    if walls:
        span = COLS // len(walls)
        for i, style in enumerate(walls):
            first = i * span
            last = COLS - 1 if i == len(walls) - 1 else first + span - 1
            for col in range(first, last + 1):
                img.alpha_composite(_wall_tile(style, col, first, last), (col * T, 0))

    placed = []
    for slot, name in r["slots"].items():
        if name:
            placed.append((name, slot, 0))
    per_zone: dict[str, int] = {}
    for name, zone in r["add"]:
        n = per_zone.get(zone, 0) + (1 if r["slots"].get(zone) else 0)
        per_zone[zone] = per_zone.get(zone, 0) + 1
        nudge = 0 if n == 0 else (36 * ((n + 1) // 2)) * (1 if n % 2 else -1)
        placed.append((name, zone, nudge))

    def order(entry):
        name, slot, _ = entry
        prop = cat["props"][name]
        if slot in WALL_SLOTS:
            return (0, 0)
        if prop.get("flat"):
            return (1, 0)
        return (2, ZONE_BASELINE[slot.split("_")[0]])

    for name, slot, nudge in sorted(placed, key=order):
        pimg = prop_image(name)
        x, y = _place(pimg, name, slot, nudge)
        img.alpha_composite(pimg, (max(-pimg.width // 2, min(W - pimg.width // 2, x)), y))
    return _mood(img, r["mood"])


def scenes_dir(campaign_dir: Path) -> Path:
    return campaign_dir / "stage" / "scenes"


def load(campaign_dir: Path, location: str) -> dict | None:
    return read_json(scenes_dir(campaign_dir) / f"{location}.json")


def save(campaign_dir: Path, location: str, spec: dict) -> Path:
    return write_json(scenes_dir(campaign_dir) / f"{location}.json", spec, indent=2)


def build(tokens: list[str], current: dict | None) -> dict:
    """Make a spec from tokens: template= wall= floor= mood= <slot>=<prop|none> +<prop>@<zone> clear=add."""
    spec = json.loads(json.dumps(current or {}))
    spec.setdefault("slots", {})
    spec.setdefault("add", [])
    for token in tokens:
        if token.startswith("+"):
            prop, at, zone = token[1:].partition("@")
            if not at:
                raise SceneError(f"{token!r}: write an extra prop as +<prop>@<zone>, for example +barrel@back_right.")
            spec["add"].append([prop, zone.replace("-", "_")])
            continue
        key, eq, value = token.partition("=")
        if not eq:
            raise SceneError(f"{token!r}: use key=value (template=, wall=, floor=, mood=, <slot>=<prop>) or +<prop>@<zone>.")
        key = key.replace("-", "_")
        if key == "template":
            spec = {"template": value, "slots": {}, "add": [], **({"mood": spec["mood"]} if "mood" in spec else {})}
        elif key in ("wall", "floor", "mood"):
            spec[key] = value.split(",") if key == "wall" and "," in value else value
        elif key == "clear" and value == "add":
            spec["add"] = []
        elif key in SLOTS:
            spec["slots"][key] = None if value in ("none", "") else value
        else:
            raise SceneError(f"unknown setting {key!r}. Slots: {', '.join(SLOTS)}.")
    if "template" not in spec:
        raise SceneError("a new scene needs template=<name>. Templates: " + ", ".join(catalog()["templates"]))
    return spec


@lru_cache(maxsize=256)
def _png(spec_json: str) -> bytes:
    buf = io.BytesIO()
    render(json.loads(spec_json)).save(buf, "PNG")
    return buf.getvalue()


def png(spec: dict) -> bytes:
    return _png(json.dumps(spec, sort_keys=True))
