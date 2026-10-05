"""Actor appearance files: `{campaign}/stage/actors/<id>.json`.

An actor file is an LPC spec plus a display name (see stage/lpc.py). It holds
only what the players can see: the name on the dialogue box and the look. A
disguised NPC gets the disguise here, under an id the players know.

Lookup order for an actor id such as `goblin#2`:
1. `stage/actors/goblin#2.json`
2. `stage/actors/goblin.json`
3. the preset `goblin` in stage/data/presets.json
"""

from __future__ import annotations

import io
import json
from functools import cache, lru_cache
from pathlib import Path

from PIL import Image

from stage import beat, creatures, lpc
from stage.assets import ensure_dcss
from stage.files import read_json, write_json

PRESETS_PATH = Path(__file__).resolve().parent / "data" / "presets.json"
MONSTERS_PATH = Path(__file__).resolve().parent / "data" / "monsters.json"
SIZES_PATH = Path(__file__).resolve().parent / "data" / "sizes.json"
SCALES = (1, 1.5, 2, 3, 4)
CLASS_LOOKS_PATH = Path(__file__).resolve().parent / "data" / "class_looks.json"
RACES_PATH = Path(__file__).resolve().parent / "data" / "races.json"
SPEC_KEYS = ("body", "skin", "eyes")
# Everyday words for skin, mapped to LPC palette names.
SKIN_ALIASES = {
    "fair": "light", "pale": "light", "white": "light", "tan": "amber", "golden": "amber",
    "dark": "brown", "ebony": "black", "grey": "fur_grey", "gray": "fur_grey", "purple": "lavender",
}


@cache
def presets() -> dict[str, dict]:
    data = json.loads(PRESETS_PATH.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


@cache
def dcss_monsters() -> dict[str, str]:
    """DCSS monster tiles by name: 'wolf' -> 'monster/animals/wolf.png'."""
    root = ensure_dcss()
    out: dict[str, str] = {}
    for path in sorted((root / "monster").rglob("*.png")):
        out.setdefault(path.stem, str(path.relative_to(root)))
    return out


@cache
def monster_aliases() -> dict[str, str]:
    """D&D names DCSS spells differently: 'owlbear' -> 'grizzly_bear' (stem) or a path with a '/'."""
    data = json.loads(MONSTERS_PATH.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


# Size and age words that do not change the picture: 'giant spider' looks like 'spider'.
MODIFIERS = {"dire", "giant", "young", "adult", "ancient", "elder", "greater", "lesser", "wild"}


@lru_cache(maxsize=512)
def find_tile(name: str, cutoff: float = 90) -> str | None:
    """The tile for a monster name: an LPC animal, a DCSS alias, an exact or close DCSS match, each then without size words."""
    from rapidfuzz import fuzz, process

    tiles = dcss_monsters()
    words = name.lower().replace("_", "-").replace(" ", "-").split("-")
    for i in range(len(words)):
        if i and words[i - 1] not in MODIFIERS:
            break
        key = "-".join(words[i:])
        if found := creatures.find(key):
            return found
        if key in (aliases := monster_aliases()):
            return aliases[key] if "/" in aliases[key] else tiles[aliases[key]]
        key = key.replace("-", "_")
        if key in tiles:
            return tiles[key]
        best = process.extractOne(key, list(tiles), scorer=fuzz.ratio, score_cutoff=cutoff)
        if best:
            return tiles[best[0]]
    return None


def actors_dir(campaign_dir: Path) -> Path:
    return campaign_dir / "stage" / "actors"


def load_own(campaign_dir: Path, actor_id: str) -> dict | None:
    """The actor's own saved look (the id's file, else its kind's file), no fallback."""
    base = actor_id.split("#")[0]
    for name in dict.fromkeys((actor_id, base)):
        if (spec := read_json(actors_dir(campaign_dir) / f"{name}.json")) is not None:
            return spec
    return None


def load(campaign_dir: Path, actor_id: str) -> dict | None:
    """The saved look, else the preset of its kind, else a DCSS tile that matches its name."""
    if (spec := load_own(campaign_dir, actor_id)) is not None:
        return spec
    base = actor_id.split("#")[0]
    if base in presets():
        return presets()[base]
    # A preset kind with a size word ('young-goblin') stays an LPC figure the DM styles: no tile.
    kind = base.lower().replace("_", "-").split("-")
    while len(kind) > 1 and kind[0] in MODIFIERS:
        kind.pop(0)
    if "-".join(kind) in presets():
        return None
    # A beast or monster LPC has no body for: a CC0 DCSS tile, if the name matches.
    try:
        tile = find_tile(base)
    except OSError:
        tile = None
    return {"name": beat.title(base), "tile": tile} if tile else None


@cache
def races() -> dict[str, dict]:
    return {k: v for k, v in json.loads(RACES_PATH.read_text()).items() if not k.startswith("_")}


def race_of(text: str) -> str | None:
    """The race key named in free text, e.g. 'Drow (High Elf)' -> 'drow', 'Half-Elf' -> 'half-elf'."""
    t = text.lower().replace(" ", "-")
    return next((r for r in sorted(races(), key=len, reverse=True) if r in t), None)


def creator_tokens(look: dict, cls: str = "", name: str = "") -> list[str]:
    """`actor set` tokens for a look chosen in the creator: the player's picks, then the class outfit."""
    tokens = [f"name={name.replace(' ', '_')}"] if name.strip() else []
    for key in ("race", "body", "skin", "eyes"):
        if look.get(key):
            tokens.append(f"{key}={look[key]}")
    hair = [str(look["hair"])] if look.get("hair") else []
    outfit = json.loads(CLASS_LOOKS_PATH.read_text()).get(cls.lower().strip(), [])
    items = [*hair, *outfit]
    if any("=" in i for i in items):
        raise lpc.ActorError("an item has no '=' in it.")
    return tokens + items


def _apply_race(spec: dict, race: str, given: set[str], notes: list[str], fill: bool = True) -> None:
    """Add the race's features (`fill`: a new look) and keep the skin within the race's colors."""
    kit = races()[race]
    for key in ("body", "skin", "eyes"):
        if fill and key in kit and key not in given:
            spec[key] = kit[key]
    fits = kit.get("skins")
    if fits and spec.get("skin") and spec["skin"] not in fits:
        default = kit.get("skin", fits[0])
        notes.append(f"skin {spec['skin']!r} does not fit a {race}; used {default!r}. Skins that fit: {', '.join(fits)}.")
        spec["skin"] = default
    if fill:
        sex = "female" if spec.get("body", "male") in ("female", "pregnant") else "male"
        spec["items"] = [i.replace("{sex}", sex) for i in kit.get("items", [])] + spec["items"]
        heads = ("hair_", "updo", "ponytail", "hat", "headcover")
        if kit.get("hair") and not any(i.split(":")[0].startswith(heads) for i in spec["items"]):
            spec["items"].insert(0, kit["hair"])


def build(actor_id: str, tokens: list[str], current: dict | None = None, race: str | None = None,
          notes: list[str] | None = None) -> dict:
    """Make a spec from `key=value` and item tokens.

    `preset=<kind>` starts from a preset; `name=...`, `body=`, `skin=`,
    `eyes=` set those fields; `race=<race>` adds the race's features (ears,
    horns, skin; `race` is the default); every other token is an item (`robe:white`).
    Items are added to the current spec, so a second `actor set` can change
    one piece; `reset=yes` starts empty instead.
    """
    spec: dict = dict(current or {})
    spec["items"] = list(spec.get("items", []))
    given: set[str] = set()
    scale = None
    for token in tokens:
        key, eq, value = token.partition("=")
        if not eq:
            spec["items"].append(token)
            continue
        key = key.strip().lower()
        if key == "scale":
            try:
                scale = float(value)
            except ValueError:
                scale = None
            if scale not in SCALES:
                raise lpc.ActorError(f"scale is one of {', '.join(map(str, SCALES))} (1 small, 1.5 human-sized, 2 large, 3 huge).")
        elif key == "preset":
            if value not in presets():
                raise lpc.ActorError(f"no preset {value!r}. Presets: {', '.join(presets())}.")
            spec = {**presets()[value], "items": list(presets()[value]["items"])}
        elif key == "reset":
            spec = {"items": []}
        elif key == "tile":
            tile = find_tile(value, cutoff=70)
            if not tile:
                raise lpc.ActorError(f"no DCSS monster tile like {value!r}. Try a plainer name (wolf, giant_spider, ogre).")
            spec = {"name": spec.get("name"), "tile": tile} if spec.get("name") else {"tile": tile}
        elif key == "race":
            if value.lower() not in races():
                raise lpc.ActorError(f"no race {value!r}. Races: {', '.join(races())}.")
            race = value.lower()
            given.add("race")
        elif key == "name":
            spec["name"] = value.replace("_", " ").strip()
        elif key == "skin":
            spec[key] = SKIN_ALIASES.get(value.lower(), value)
            given.add(key)
        elif key in SPEC_KEYS:
            spec[key] = value
            given.add(key)
        else:
            raise lpc.ActorError(
                f"unknown setting {key!r}. Use name=, body=, skin=, eyes=, race=, preset=, reset=yes, "
                "scale= (a monster tile), or an item such as robe:white."
            )
    spec.setdefault("name", beat.title(actor_id))
    if "tile" in spec:
        spec.pop("items", None)
        if scale:
            spec["scale"] = scale
        return spec
    if scale:
        raise lpc.ActorError("scale= only fits a monster tile (tile=...).")
    if race:
        _apply_race(spec, race, given, notes if notes is not None else [], fill=current is None or "race" in given)
    spec.setdefault("body", "male")
    return spec


def look_spec(actor_id: str, tokens: list[str], current: dict | None = None, race: str | None = None,
              notes: list[str] | None = None) -> tuple[dict, list[str]]:
    """A look from tokens, ready to save, and its warnings. Saves nothing.

    `race` is the default race (a player character's, from its sheet); a `race=` token wins.
    """
    notes = [] if notes is None else notes
    spec = build(actor_id, tokens, current, race, notes)
    if "tile" in spec:
        return spec, []
    spec["items"] = lpc.normalize_items(spec["items"])
    warnings = notes + lpc.validate(spec)
    spec["items"] = lpc.sex_fixed(spec["items"], spec["body"])
    return spec, warnings


class LookExists(lpc.ActorError):
    def __init__(self, actor_id: str, current: dict):
        super().__init__(f"{actor_id!r} already has a look")
        self.current = current


def set_look(campaign_dir: Path, actor_id: str, tokens: list[str], change: bool = False,
             notify: bool = True) -> tuple[dict, list[str], Path]:
    """Build, save and announce a look: (spec, warnings, path). The one path of `actor set` and the creator.

    A saved look is kept unless `change`: LookExists. A player character's race comes from its sheet.
    """
    if not tokens:
        raise lpc.ActorError("give at least one setting, for example name=Sireth body=female.")
    if not beat.ID_RE.match(actor_id):
        raise lpc.ActorError(f"actor id {actor_id!r}: {beat.ID_RULE}.")
    current = read_json(actors_dir(campaign_dir) / f"{actor_id}.json")
    if current is not None and not change:
        raise LookExists(actor_id, current)
    sheet = read_json(campaign_dir / "characters" / f"{actor_id}.json")
    spec, warnings = look_spec(actor_id, tokens, current, race_of(str(sheet.get("race", ""))) if sheet else None)
    saved = save(campaign_dir, actor_id, spec)
    if notify:
        beat.append(campaign_dir, [{"type": "actor_updated", "actor": actor_id}])
    return spec, warnings, saved


@cache
def sizes() -> dict:
    return json.loads(SIZES_PATH.read_text())


def tile_scale(spec: dict) -> float:
    """How much to stretch a tile: the actor's own `scale`, else by its name, else by its folder."""
    if spec.get("scale"):
        return spec["scale"]
    if spec["tile"].startswith(creatures.PREFIX):
        return creatures.scale(spec["tile"])
    path = Path(spec["tile"])
    table = sizes()
    if path.stem in table["stems"]:
        return table["stems"][path.stem]
    if path.parts[0] != "monster":
        return 1
    folder = path.parts[1] if len(path.parts) > 2 else ""
    return table["folders"].get(folder, 1)


def _tile_frame(spec: dict, facing: str = "down", scale: float | None = None) -> Image.Image:
    """A monster or animal stretched to its size and standing at the bottom of a frame, like an LPC sprite.

    The frame is 64 px, or bigger when the figure is: the stage reads its size from the PNG.
    """
    scale = tile_scale(spec) if scale is None else scale
    if spec["tile"].startswith(creatures.PREFIX):
        tile = creatures.frame(spec["tile"], facing)
    else:
        tile = Image.open(ensure_dcss() / spec["tile"]).convert("RGBA")
        if facing == "left":  # DCSS monsters look right
            tile = tile.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if scale != 1:
        tile = tile.resize((round(tile.width * scale), round(tile.height * scale)), Image.Resampling.NEAREST)
    side = max(lpc.FRAME, tile.width, tile.height)
    frame = Image.new("RGBA", (side, side))
    frame.alpha_composite(tile, ((side - tile.width) // 2, side - tile.height - 2))
    return frame


def save(campaign_dir: Path, actor_id: str, spec: dict) -> Path:
    return write_json(actors_dir(campaign_dir) / f"{actor_id}.json", spec, indent=2)


FACING = {"left": "right", "far-left": "right", "right": "left", "far-right": "left"}


@lru_cache(maxsize=256)
def _png(spec_json: str, kind: str, facing: str, emotion: str | None) -> bytes:
    spec = json.loads(spec_json)
    if "tile" in spec:
        if spec["tile"].startswith(creatures.PREFIX) and facing not in ("left", "right"):
            facing = "right"  # an animal is best seen from the side
        if kind == "portrait":
            frame = _tile_frame(spec, facing, scale=1)
            img = frame.crop(frame.getbbox() or (0, 0, lpc.FRAME, lpc.FRAME))
        else:
            img = _tile_frame(spec, facing)
    else:
        img = lpc.portrait(spec, emotion) if kind == "portrait" else lpc.render(spec, facing, emotion)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def png(spec: dict, kind: str, position: str | None = None, emotion: str | None = None,
        facing: str | None = None) -> bytes:
    """Rendered PNG bytes, cached by spec. Stage actors turn toward the center, unless `facing` is given."""
    if facing not in lpc.ROWS:
        facing = FACING.get(position or "", "down")
    return _png(json.dumps(spec, sort_keys=True), kind, facing, emotion)


def preview(spec: dict, out: Path, emotion: str | None = None) -> Path:
    """Full body, side view, and portrait in one image, for the DM to check."""
    if "tile" in spec:
        frame = _tile_frame(spec)
        out.parent.mkdir(parents=True, exist_ok=True)
        frame.resize((frame.width * 4, frame.height * 4), Image.NEAREST).save(out)
        return out
    parts = [lpc.render(spec, "down", emotion), lpc.render(spec, "right", emotion),
             lpc.portrait(spec, emotion).resize((64, 64), Image.NEAREST)]
    sheet = Image.new("RGBA", (64 * len(parts), 64), (40, 38, 52, 255))
    for i, part in enumerate(parts):
        sheet.alpha_composite(part, (64 * i, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.resize((sheet.width * 4, sheet.height * 4), Image.NEAREST).save(out)
    return out
