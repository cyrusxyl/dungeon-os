"""actor command - set and check how a character looks on the visual stage"""

import json
import os
import sys

from dnd_cli.commands.show_cmd import preview_path, run_stage
from stage import actors, lpc
from stage.assets import AssetError


def execute_set(campaign, actor_id: str, tokens: list[str], change: bool = False) -> int:
    def go(campaign_dir):
        try:
            spec, warnings, saved = actors.set_look(
                campaign_dir, actor_id, tokens, change, notify=bool(os.environ.get("DUNGEON_STAGE_LOG")))
        except actors.LookExists as e:
            # A saved look is reused as is; a new DM session must not quietly redo it.
            print(f"{actor_id!r} already has a look; the stage uses it as saved:\n{json.dumps(e.current)}\n"
                  "Nothing changed. Add --change only if the story changes the look "
                  "(never for a player character unless that player asks).", file=sys.stderr)
            return 1
        for w in warnings:
            print(f"Warning: {w}", file=sys.stderr)
        kind = f"tile {spec['tile']}" if "tile" in spec else f"{spec['body']}, {len(spec['items'])} items"
        print(f"Saved {saved.relative_to(campaign_dir)}: {spec['name']} ({kind}).")
        print(f"Check it with: uv run dnd-cli actor preview {actor_id}")
        return 0
    return run_stage(campaign, go, lpc.ActorError, AssetError)


def execute_show(campaign, actor_id: str) -> int:
    def go(campaign_dir):
        spec = actors.load(campaign_dir, actor_id)
        if spec is None:
            print(f"No appearance for {actor_id!r} and no preset for its kind.", file=sys.stderr)
            return 1
        print(json.dumps(spec, indent=2))
        return 0
    return run_stage(campaign, go, lpc.ActorError, AssetError)


def execute_preview(campaign, actor_id: str, emotion: str | None) -> int:
    def go(campaign_dir):
        spec = actors.load(campaign_dir, actor_id)
        if spec is None:
            print(f"No appearance for {actor_id!r} and no preset for its kind.", file=sys.stderr)
            return 1
        out = actors.preview(spec, preview_path(campaign_dir, f"preview-{actor_id}"), emotion)
        print(f"Preview (front, side, portrait): {out}")
        return 0
    return run_stage(campaign, go, lpc.ActorError, AssetError)


def execute_options(item_type: str | None, body: str | None) -> int:
    try:
        groups = lpc.options()
    except AssetError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if item_type is None:
        print("Settings: name=<Display_Name> body=<" + "|".join(lpc.BODY_TYPES) + "> "
              "skin=<palette> eyes=<palette> race=<race> preset=<kind>")
        print("skin: " + ", ".join(lpc.palette_names("body")))
        print("eyes: " + ", ".join(lpc.palette_names("eye")))
        print("races: " + ", ".join(actors.races()))
        print("presets: " + ", ".join(actors.presets()))
        print("\nItem types (show one with: uv run dnd-cli actor options <type> [--body B]):")
        print(", ".join(f"{t} ({len(v)})" for t, v in groups.items()))
        return 0
    if item_type not in groups:
        print(f"Error: no item type {item_type!r}. Types: {', '.join(groups)}", file=sys.stderr)
        return 1
    # Items that share bodies and colors print as one line: the color list is long.
    cat = lpc.catalog()
    lines: dict[tuple, list[str]] = {}
    for item_id in groups[item_type]:
        item = cat[item_id]
        if body and body not in item.bodies():
            continue
        fits = "" if body else "/".join(sorted(item.bodies()))
        lines.setdefault((fits, ", ".join(item.colors()) or "-"), []).append(item_id)
    for (fits, colors), ids in lines.items():
        print(", ".join(ids))
        print(f"  {'bodies: ' + fits + '; ' if fits else ''}colors: {colors}")
    return 0
