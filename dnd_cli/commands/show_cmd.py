"""show command - put a beat (scene, actors, narration, dialogue, choices) on the stage"""

import os
import sys
from pathlib import Path

from dnd_cli.campaign import CampaignError, active_campaign_slug, resolve_campaign_dir
from stage import beat


def _stage_campaign_dir(campaign: str | None) -> Path:
    """The campaign the running stage shows, else the one given, else the active one.

    The stage server sets DUNGEON_STAGE_LOG for the DM process. Following it
    keeps beats on the stage the players watch, even if the DM edits
    campaigns/active.json during play.
    """
    stage_log = os.environ.get("DUNGEON_STAGE_LOG")
    if stage_log and not campaign:
        return Path(stage_log).parent.parent
    return resolve_campaign_dir(campaign or active_campaign_slug())


def execute_beat(campaign: str | None, file: str | None) -> int:
    try:
        campaign_dir = _stage_campaign_dir(campaign)
    except (CampaignError, OSError, KeyError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    text = Path(file).read_text() if file else sys.stdin.read()
    try:
        events = beat.parse(text)
    except beat.BeatError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    beat.append(campaign_dir, events)

    # An unknown actor is not an error: the stage shows a silhouette.
    actors_dir = campaign_dir / "stage" / "actors"
    for actor in sorted({e["actor"].split("#")[0] for e in events if "actor" in e}):
        if not (actors_dir / f"{actor}.json").exists():
            print(f"Warning: no appearance for {actor!r} yet; the stage shows a silhouette. "
                  f"Set one with: uv run dnd-cli actor set {actor} ...", file=sys.stderr)

    print(f"Shown: {len(events)} event(s): " + ", ".join(e["type"] for e in events))
    return 0
