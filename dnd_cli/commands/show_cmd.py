"""show command - put a beat (scene, actors, narration, dialogue, choices) on the stage"""

import os
import sys
from pathlib import Path

from dnd_cli.campaign import CampaignError, active_campaign_slug, resolve_campaign_dir
from stage import actors, beat, scenes


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
    for actor in sorted({e["actor"] for e in events if "actor" in e}):
        if actors.load(campaign_dir, actor) is None:
            print(f"Warning: no appearance for {actor!r} yet; the stage shows a silhouette. "
                  f"Set one with: uv run dnd-cli actor set {actor.split('#')[0]} ... "
                  "(see: uv run dnd-cli actor options)", file=sys.stderr)

    # Same for a place: the stage shows a blank room until it has a look.
    for location in sorted({e["location"] for e in events if e["type"] == "scene"}):
        if scenes.load(campaign_dir, location) is None:
            print(f"Warning: no look for location {location!r} yet; the stage shows a blank room. "
                  f"Set one with: uv run dnd-cli scene set {location} template=... "
                  "(see: uv run dnd-cli scene options)", file=sys.stderr)

    print(f"Shown: {len(events)} event(s): " + ", ".join(e["type"] for e in events))
    return 0
