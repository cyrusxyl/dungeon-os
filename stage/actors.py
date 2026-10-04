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
from functools import cache
from pathlib import Path

from PIL import Image

from stage import lpc

PRESETS_PATH = Path(__file__).resolve().parent / "data" / "presets.json"
SPEC_KEYS = ("body", "skin", "eyes")


@cache
def presets() -> dict[str, dict]:
    data = json.loads(PRESETS_PATH.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def actors_dir(campaign_dir: Path) -> Path:
    return campaign_dir / "stage" / "actors"


def load(campaign_dir: Path, actor_id: str) -> dict | None:
    base = actor_id.split("#")[0]
    for name in dict.fromkeys((actor_id, base)):
        path = actors_dir(campaign_dir) / f"{name}.json"
        if path.exists():
            try:
                return json.loads(path.read_text())
            except ValueError:
                return None
    return presets().get(base)


def build(actor_id: str, tokens: list[str], current: dict | None = None) -> dict:
    """Make a spec from `key=value` and item tokens.

    `preset=<kind>` starts from a preset; `name=...`, `body=`, `skin=`,
    `eyes=` set those fields; every other token is an item (`robe:white`).
    Items are added to the current spec, so a second `actor set` can change
    one piece; `reset=yes` starts empty instead.
    """
    spec: dict = dict(current or {})
    spec["items"] = list(spec.get("items", []))
    for token in tokens:
        key, eq, value = token.partition("=")
        if not eq:
            spec["items"].append(token)
            continue
        key = key.strip().lower()
        if key == "preset":
            if value not in presets():
                raise lpc.ActorError(f"no preset {value!r}. Presets: {', '.join(presets())}.")
            spec = {**presets()[value], "items": list(presets()[value]["items"])}
        elif key == "reset":
            spec = {"items": []}
        elif key == "name":
            spec["name"] = value.replace("_", " ").strip()
        elif key in SPEC_KEYS:
            spec[key] = value
        else:
            raise lpc.ActorError(
                f"unknown setting {key!r}. Use name=, body=, skin=, eyes=, preset=, reset=yes, "
                "or an item such as robe:white."
            )
    spec.setdefault("name", actor_id.split("#")[0].replace("-", " ").title())
    spec.setdefault("body", "male")
    return spec


def save(campaign_dir: Path, actor_id: str, spec: dict) -> Path:
    path = actors_dir(campaign_dir) / f"{actor_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2) + "\n")
    return path


FACING = {"left": "right", "far-left": "right", "right": "left", "far-right": "left"}


@cache
def _png(spec_json: str, kind: str, facing: str, emotion: str | None) -> bytes:
    spec = json.loads(spec_json)
    img = lpc.portrait(spec, emotion) if kind == "portrait" else lpc.render(spec, facing, emotion)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def png(spec: dict, kind: str, position: str | None = None, emotion: str | None = None) -> bytes:
    """Rendered PNG bytes, cached by spec. Stage actors turn toward the center."""
    facing = FACING.get(position or "", "down")
    return _png(json.dumps(spec, sort_keys=True), kind, facing, emotion)


def preview(spec: dict, out: Path, emotion: str | None = None) -> Path:
    """Full body, side view, and portrait in one image, for the DM to check."""
    parts = [lpc.render(spec, "down", emotion), lpc.render(spec, "right", emotion),
             lpc.portrait(spec, emotion).resize((64, 64), Image.NEAREST)]
    sheet = Image.new("RGBA", (64 * len(parts), 64), (40, 38, 52, 255))
    for i, part in enumerate(parts):
        sheet.alpha_composite(part, (64 * i, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.resize((sheet.width * 4, sheet.height * 4), Image.NEAREST).save(out)
    return out
