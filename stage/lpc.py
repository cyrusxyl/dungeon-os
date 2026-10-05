"""Compose Universal LPC characters headlessly: full-body frames and portraits.

The LPC generator renders in a browser. This module reads the same data —
`sheet_definitions/` (layers, z-order, per-body-type paths) and
`palette_definitions/` (recolor palettes) — and composites one frame with
Pillow. Frame 0 of a walk row is the standing pose.

An actor spec is plain data, written by `dnd-cli actor set`:

    {"name": "Sister Gareth", "body": "female", "skin": "olive", "eyes": "blue",
     "items": ["heads_human_female_elderly", "hair_bob:gray", "robe:white"]}

Item ids are LPC definition names with a common prefix removed (`robe` for
`torso_clothes_robe`). One item per LPC type: a later item of the same type
replaces an earlier one. `:color` picks a palette color or a pre-colored
variant.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from PIL import Image

from stage.assets import ensure_lpc

FRAME = 64
ROWS = {"up": 0, "left": 1, "down": 2, "right": 3}
BODY_TYPES = ("male", "female", "muscular", "teen", "pregnant", "child")
DEFAULT_HEAD = {
    "male": "heads_human_male",
    "muscular": "heads_human_male",
    "female": "heads_human_female",
    "pregnant": "heads_human_female",
    "teen": "heads_human_female_small",
    "child": "heads_human_child",
}
EMOTION_FACES = {
    "happy": "face_happy",
    "angry": "face_angry",
    "sad": "face_sad",
    "shock": "face_shock",
    "blush": "face_blush",
    "shame": "face_shame",
    "eyeroll": "face_eyeroll",
    "closed": "face_closed",
}
# Removed from definition names to make short item ids, longest first.
PREFIXES = (
    "torso_clothes_", "torso_jacket_", "torso_aprons_", "torso_armour_", "torso_",
    "hat_helmet_", "hat_", "head_ears_", "head_nose_", "head_", "legs_", "feet_",
    "beards_", "neck_", "facial_", "dress_", "arms_", "shoulders_", "wrists_",
)


class ActorError(ValueError):
    """A bad actor spec. The message says how to fix it."""


@dataclass
class Item:
    id: str
    def_name: str
    type: str
    label: str
    layers: list[tuple[int, dict]]
    recolors: list[dict] = field(default_factory=list)
    variants: list[str] = field(default_factory=list)
    match_body: bool = False
    replace_in_path: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def bodies(self) -> set[str]:
        return {b for _, paths in self.layers for b in paths if b in BODY_TYPES}

    def colors(self) -> list[str]:
        if self.variants:
            return list(self.variants)
        if self.recolors:
            return list(palette_names(self.recolors[0]["material"]))
        return []


@cache
def catalog() -> dict[str, Item]:
    """All LPC items by short id."""
    items: list[Item] = []
    for path in sorted((ensure_lpc() / "sheet_definitions").rglob("*.json")):
        if path.name.startswith("meta"):
            continue
        d = json.loads(path.read_text())
        if "type_name" not in d:
            continue
        rc = d.get("recolors") or {}
        recolors = [rc[k] for k in sorted(rc) if k.startswith("color_")] or ([rc] if rc else [])
        layers = [
            (v.get("zPos", 0), {b: p for b, p in v.items() if b in BODY_TYPES})
            for k, v in sorted(d.items()) if k.startswith("layer_")
        ]
        items.append(Item(
            id=path.stem, def_name=path.stem, type=d["type_name"], label=d.get("name", path.stem),
            layers=layers, recolors=recolors, variants=d.get("variants", []),
            match_body=bool(d.get("match_body_color")), replace_in_path=d.get("replace_in_path", {}),
            tags=d.get("tags", []),
        ))
    # Short ids: strip a known prefix, unless that would collide.
    def short(stem: str) -> str:
        for p in PREFIXES:
            if stem.startswith(p) and len(stem) > len(p):
                return stem[len(p):]
        return stem
    shorts = {it.def_name: short(it.def_name) for it in items}
    counts = Counter(shorts.values())
    out: dict[str, Item] = {}
    for it in items:
        s = shorts[it.def_name]
        # A short id must be unique, and must not be another item's full name.
        it.id = s if counts[s] == 1 and (s == it.def_name or s not in shorts) else it.def_name
        out[it.id] = it
    # The full definition name always works too.
    for it in items:
        out.setdefault(it.def_name, it)
    return out


@cache
def _palette_file(material: str) -> tuple[str, dict[str, list[str]]]:
    folder = ensure_lpc() / "palette_definitions" / material
    base = json.loads((folder / f"meta_{material}.json").read_text())["base"]
    return base, json.loads((folder / f"{material}_ulpc.json").read_text())


def palette_names(material: str) -> list[str]:
    return list(_palette_file(material)[1])


def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _mapping(material: str, target: str, rc: dict | None = None) -> dict:
    """Source colors → target palette colors. A recolor may name its own
    source colors (`source`) or a different base palette (`base`)."""
    rc = rc or {}
    base, pals = _palette_file(material)
    if target not in pals:
        return {}
    if rc.get("source"):
        return dict(zip(map(_hex, rc["source"]), map(_hex, pals[target])))
    if rc.get("base"):
        base = rc["base"].split(".")[-1]
    if base not in pals or target == base:
        return {}
    return dict(zip(map(_hex, pals[base]), map(_hex, pals[target])))


def _recolor(img: Image.Image, mapping: dict) -> Image.Image:
    if not mapping:
        return img
    data = [
        (*mapping[(r, g, b)], a) if a and (r, g, b) in mapping else (r, g, b, a)
        for r, g, b, a in img.getdata()
    ]
    img.putdata(data)
    return img


def _split(entry: str) -> tuple[str, str | None]:
    name, _, color = entry.partition(":")
    return name.strip(), (color.strip() or None)


def _match_color(item: Item, color: str | None) -> str | None:
    """The item's own spelling of a color; '_' matches ' ' ('dark_brown' → 'dark brown')."""
    if not color:
        return None
    wanted = color.lower().replace("_", " ")
    for c in item.colors():
        if c.lower().replace("_", " ") == wanted:
            return c
    return color


def _item(entry: str) -> tuple[Item, str | None]:
    name, color = _split(entry)
    item = catalog().get(name)
    if not item:
        raise ActorError(f"no LPC item {name!r}. List them with: uv run dnd-cli actor options")
    return item, color


def normalize_items(items: list[str]) -> list[str]:
    """One entry per LPC type, the later one winning, in first-seen order."""
    return list({_item(entry)[0].type: entry for entry in items}.values())


SEX_OF_BODY = {"male": "male", "muscular": "male", "female": "female", "pregnant": "female"}


def matching_sex(item: Item, body: str) -> Item:
    """The item's counterpart for the body's sex, if the item is made for the other one.

    `heads_human_male_elderly` on a female body becomes `heads_human_female_elderly`.
    Teen and child bodies take either.
    """
    want = SEX_OF_BODY.get(body)
    parts = item.id.split("_")
    other = {"male": "female", "female": "male"}.get(want or "")
    if not want or other not in parts:
        return item
    twin = catalog().get("_".join(want if p == other else p for p in parts))
    return twin or item


def sex_fixed(items: list[str], body: str) -> list[str]:
    """Item entries with each one for the other sex replaced by its counterpart (colors kept)."""
    out = []
    for entry in items:
        item, _ = _item(entry)
        twin = matching_sex(item, body)
        out.append(entry if twin is item else twin.id + entry[len(entry.split(":")[0]):])
    return out


def resolve(spec: dict) -> tuple[str, list[tuple[Item, str | None]]]:
    """Body type and the final item list (one per LPC type), defaults filled in."""
    body = spec.get("body", "male")
    if body not in BODY_TYPES:
        raise ActorError(f"body {body!r} is not one of {', '.join(BODY_TYPES)}.")
    cat = catalog()
    chosen: dict[str, tuple[Item, str | None]] = {}
    for entry in spec.get("items", []):
        item, color = _item(entry)
        item = matching_sex(item, body)
        chosen[item.type] = (item, _match_color(item, color))
    chosen.setdefault("body", (cat["body"], None))
    chosen.setdefault("head", (cat[DEFAULT_HEAD[body]], None))
    return body, list(chosen.values())


def validate(spec: dict) -> list[str]:
    """Raise ActorError for a bad spec; return warnings for items that will not show."""
    body, items = resolve(spec)
    warnings = [f"{_item(e)[0].id} is made for the other sex; {matching_sex(_item(e)[0], body).id} is used."
                for e in spec.get("items", []) if matching_sex(_item(e)[0], body) is not _item(e)[0]]
    head = next((i for i, _ in items if i.type == "head"), None)
    if head and "human" in head.id and not any(i.type in ("hair", "updo", "ponytail", "hat", "headcover") for i, _ in items):
        warnings.append("no hair or headwear: the character is bald. Add hair (for example hair_long:white) "
                        "unless bald is meant.")
    if spec.get("skin") and spec["skin"] not in palette_names("body"):
        raise ActorError(f"skin {spec['skin']!r} is not one of {', '.join(palette_names('body'))}.")
    if spec.get("eyes") and spec["eyes"] not in palette_names("eye"):
        raise ActorError(f"eyes {spec['eyes']!r} is not one of {', '.join(palette_names('eye'))}.")
    for item, color in items:
        if body not in item.bodies():
            warnings.append(f"{item.id} has no sprite for body {body!r}; it will not show. "
                            f"It fits: {', '.join(sorted(item.bodies())) or 'none'}.")
        if color and color not in item.colors():
            raise ActorError(f"{item.id}: color {color!r} is not one of {', '.join(item.colors()) or '(no colors)'}.")
    return warnings


def _sheet_path(item: Item, rel: str, color: str | None) -> Path:
    base = ensure_lpc() / "spritesheets" / rel
    if item.variants:
        variant = color if color in item.variants else item.variants[0]
        return base / "walk" / f"{variant.replace(' ', '_')}.png"
    return base / "walk.png"


def render(spec: dict, facing: str = "down", emotion: str | None = None) -> Image.Image:
    """One 64x64 standing frame of the actor."""
    body, items = resolve(spec)
    face = EMOTION_FACES.get(emotion or "")
    head_item = next((i for i, _ in items if i.type == "head"), None)
    if face and head_item and "human" in head_item.tags:
        items = [p for p in items if p[0].type != "expression"] + [(catalog()[face], None)]
    by_type = {i.type: i for i, _ in items}
    skin = spec.get("skin")
    eyes = spec.get("eyes")
    row = ROWS.get(facing, ROWS["down"])

    layers = []
    for item, color in items:
        mapping: dict = {}
        for n, rc in enumerate(item.recolors):
            material = rc["material"]
            if material == "body" and (item.match_body or n == 0 and item.type in ("body", "head")):
                target = skin
            elif material == "eye":
                target = eyes
            else:
                target = color if n == 0 else None
            if target:
                mapping.update(_mapping(material, target, rc))
        for z, paths in item.layers:
            rel = paths.get(body)
            if not rel:
                continue
            for key, names in item.replace_in_path.items():
                owner = by_type.get(key)
                value = names.get(owner.label.replace(" ", "_")) if owner else None
                if value is None:
                    rel = None
                    break
                rel = rel.replace("${" + key + "}", value)
            if not rel:
                continue
            sheet = _sheet_path(item, rel, color)
            if not sheet.exists():
                continue
            with Image.open(sheet) as im:
                tile = im.convert("RGBA").crop((0, row * FRAME, FRAME, (row + 1) * FRAME))
            layers.append((z, _recolor(tile, mapping)))

    out = Image.new("RGBA", (FRAME, FRAME))
    for _, tile in sorted(layers, key=lambda t: t[0]):
        out.alpha_composite(tile)
    return out


PORTRAIT = 36


def portrait(spec: dict, emotion: str | None = None) -> Image.Image:
    """Head and shoulders, cut from the front-facing frame."""
    full = render(spec, "down", emotion)
    box = full.getbbox() or (0, 0, FRAME, FRAME)
    top = max(0, box[1] - 2)
    left = (FRAME - PORTRAIT) // 2
    return full.crop((left, top, left + PORTRAIT, top + PORTRAIT))


def options() -> dict[str, list[str]]:
    """Item ids grouped by LPC type, for `dnd-cli actor options`."""
    groups: dict[str, list[str]] = {}
    for key, item in catalog().items():
        if key == item.id:  # skip the full-name aliases
            groups.setdefault(item.type, []).append(item.id)
    return {k: sorted(v) for k, v in sorted(groups.items())}

