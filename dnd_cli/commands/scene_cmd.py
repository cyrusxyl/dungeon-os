"""scene command - set how a location looks on the visual stage"""

import json
import os
import sys
from datetime import date

from dnd_cli.campaign import CampaignError
from dnd_cli.commands.show_cmd import _stage_campaign_dir
from stage import beat, scenes
from stage.assets import AssetError


def _run(campaign, fn) -> int:
    try:
        return fn(_stage_campaign_dir(campaign))
    except (CampaignError, OSError, KeyError, scenes.SceneError, AssetError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def execute_set(campaign, location: str, tokens: list[str]) -> int:
    def go(campaign_dir):
        if not beat.ID_RE.match(location):
            raise scenes.SceneError(f"location id {location!r}: use lower-case letters, digits, '-' or '_'.")
        spec = scenes.build(tokens, scenes.load(campaign_dir, location))
        try:
            scenes.resolve(spec)
        except scenes.UnknownProp as e:
            # Record the gap, so the catalog can grow where play needs it.
            log = campaign_dir / "stage" / "missing.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a") as f:
                f.write(f"{date.today().isoformat()}\t{location}\t{e.prop}\n")
            raise scenes.SceneError(f"{e} Pick the closest prop and describe the difference in the story.") from e
        saved = scenes.save(campaign_dir, location, spec)
        if os.environ.get("DUNGEON_STAGE_LOG"):
            beat.append(campaign_dir, [{"type": "scene_updated", "location": location}])
        print(f"Saved {saved.relative_to(campaign_dir)}: template {spec['template']}.")
        print(f"Check it with: uv run dnd-cli scene preview {location}")
        return 0
    return _run(campaign, go)


def execute_show(campaign, location: str) -> int:
    def go(campaign_dir):
        spec = scenes.load(campaign_dir, location)
        if spec is None:
            print(f"No scene for {location!r} yet. Set one with: uv run dnd-cli scene set {location} template=...",
                  file=sys.stderr)
            return 1
        print(json.dumps({"spec": spec, "resolved": scenes.resolve(spec)}, indent=2))
        return 0
    return _run(campaign, go)


def execute_preview(campaign, location: str) -> int:
    def go(campaign_dir):
        spec = scenes.load(campaign_dir, location)
        if spec is None:
            print(f"No scene for {location!r} yet.", file=sys.stderr)
            return 1
        out = campaign_dir / ".cache" / "stage" / f"scene-{location}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        img = scenes.render(spec)
        img.resize((img.width * 3, img.height * 3), 0).save(out)  # 0 = nearest neighbor
        print(f"Preview: {out}")
        return 0
    return _run(campaign, go)


def execute_options(what: str | None) -> int:
    cat = scenes.catalog()
    groups = {
        "templates": {k: f"wall {v.get('wall')}, floor {v['floor']}, slots {', '.join(f'{s}={p}' for s, p in v.get('slots', {}).items())}"
                      for k, v in cat["templates"].items()},
        "walls": list(cat["walls"]),
        "floors": list(cat["floors"]) + list(cat["grounds"]),
        "props": {k: f"{'wall' if v.get('on') == 'wall' else 'floor'}{', flat' if v.get('flat') else ''}"
                  for k, v in cat["props"].items()},
        "moods": cat["moods"],
        "slots": scenes.SLOTS,
    }
    if what is None:
        print("Usage: uv run dnd-cli scene set <location-id> template=<t> [wall=<w>] [floor=<f>] [mood=<m>] "
              "[<slot>=<prop>|none] [+<prop>@<zone>] [clear=add]")
        print("Zones (for +prop@zone) are the floor slots: " + ", ".join(scenes.ZONES))
        for k, v in groups.items():
            print(f"\n{k}: " + ", ".join(v))
        return 0
    if what not in groups:
        print(f"Error: choose one of {', '.join(groups)}", file=sys.stderr)
        return 1
    v = groups[what]
    for line in (f"{k:16} {d}" for k, d in v.items()) if isinstance(v, dict) else v:
        print(line)
    return 0
