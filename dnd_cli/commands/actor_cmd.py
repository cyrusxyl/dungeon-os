"""actor command - set and check how a character looks on the visual stage"""

import json
import os
import sys

from dnd_cli.commands.show_cmd import _stage_campaign_dir
from dnd_cli.campaign import CampaignError
from stage import actors, beat, lpc
from stage.assets import AssetError


def _run(campaign, fn) -> int:
    try:
        return fn(_stage_campaign_dir(campaign))
    except (CampaignError, OSError, KeyError, lpc.ActorError, AssetError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def execute_set(campaign, actor_id: str, tokens: list[str], change: bool = False) -> int:
    def go(campaign_dir):
        if not tokens:
            raise lpc.ActorError("give at least one setting, for example name=Sireth body=female.")
        if not lpc.slug(actor_id) == actor_id.split("#")[0] and "#" not in actor_id:
            raise lpc.ActorError(f"actor id {actor_id!r}: use lower-case letters, digits, '-' or '_'.")
        current = json.loads(path.read_text()) if (path := actors.actors_dir(campaign_dir) / f"{actor_id}.json").exists() else None
        if current is not None and not change:
            # A saved look is reused as is; a new DM session must not quietly redo it.
            print(f"{actor_id!r} already has a look; the stage uses it as saved:\n{json.dumps(current)}\n"
                  "Nothing changed. Add --change only if the story changes the look "
                  "(never for a player character unless that player asks).", file=sys.stderr)
            return 1
        spec = actors.build(actor_id, tokens, current)
        if "tile" in spec:
            warnings = []
        else:
            spec["items"] = lpc.normalize_items(spec["items"])
            warnings = lpc.validate(spec)
        saved = actors.save(campaign_dir, actor_id, spec)
        if os.environ.get("DUNGEON_STAGE_LOG"):
            # Tell a running stage to reload this actor's pictures.
            beat.append(campaign_dir, [{"type": "actor_updated", "actor": actor_id}])
        for w in warnings:
            print(f"Warning: {w}", file=sys.stderr)
        kind = f"tile {spec['tile']}" if "tile" in spec else f"{spec['body']}, {len(spec['items'])} items"
        print(f"Saved {saved.relative_to(campaign_dir)}: {spec['name']} ({kind}).")
        print(f"Check it with: uv run dnd-cli actor preview {actor_id}")
        return 0
    return _run(campaign, go)


def execute_show(campaign, actor_id: str) -> int:
    def go(campaign_dir):
        spec = actors.load(campaign_dir, actor_id)
        if spec is None:
            print(f"No appearance for {actor_id!r} and no preset for its kind.", file=sys.stderr)
            return 1
        print(json.dumps(spec, indent=2))
        return 0
    return _run(campaign, go)


def execute_preview(campaign, actor_id: str, emotion: str | None) -> int:
    def go(campaign_dir):
        spec = actors.load(campaign_dir, actor_id)
        if spec is None:
            print(f"No appearance for {actor_id!r} and no preset for its kind.", file=sys.stderr)
            return 1
        out = actors.preview(spec, campaign_dir / ".cache" / "stage" / f"preview-{actor_id}.png", emotion)
        print(f"Preview (front, side, portrait): {out}")
        return 0
    return _run(campaign, go)


def execute_options(item_type: str | None, body: str | None) -> int:
    try:
        groups = lpc.options()
    except AssetError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if item_type is None:
        print("Settings: name=<Display_Name> body=<" + "|".join(lpc.BODY_TYPES) + "> "
              "skin=<palette> eyes=<palette> preset=<kind>")
        print("skin: " + ", ".join(lpc.palette_names("body")))
        print("eyes: " + ", ".join(lpc.palette_names("eye")))
        print("presets: " + ", ".join(actors.presets()))
        print("\nItem types (show one with: uv run dnd-cli actor options <type> [--body B]):")
        print(", ".join(f"{t} ({len(v)})" for t, v in groups.items()))
        return 0
    if item_type not in groups:
        print(f"Error: no item type {item_type!r}. Types: {', '.join(groups)}", file=sys.stderr)
        return 1
    cat = lpc.catalog()
    for item_id in groups[item_type]:
        item = cat[item_id]
        if body and body not in item.bodies():
            continue
        colors = item.colors()
        fits = "/".join(sorted(item.bodies()))
        print(f"{item_id:32} bodies: {fits:40} colors: {', '.join(colors) if colors else '-'}")
    return 0
