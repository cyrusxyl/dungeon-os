"""show command - put a beat (scene, actors, narration, dialogue, choices) on the stage"""

import os
import sys
from pathlib import Path

from dnd_cli.campaign import CampaignError, active_campaign_slug, resolve_campaign_dir
from stage import actors, beat, crawl, maps, scenes


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

    # Put the party in a site before the stage reads the event.
    for e in events:
        if e["type"] == "explore":
            site = crawl.load(campaign_dir, e["site"])
            if site is None:
                continue
            try:
                crawl.arrive(site, e.get("at"))
            except crawl.SiteError as err:
                print(f"Error: @explore {e['site']} {e.get('at')}: {err}", file=sys.stderr)
                return 1
            crawl.save(campaign_dir, e["site"], site)

    # A scene or site that is a place on a map moves the party marker there.
    out = []
    for e in events:
        out.append(e)
        place = e.get("location") if e["type"] == "scene" else e.get("site") if e["type"] == "explore" else None
        map_id = maps.visit(campaign_dir, place) if place else None
        if map_id:
            out.append({"type": "at", "map": map_id, "place": place})
    beat.append(campaign_dir, out)

    # An unknown actor is not an error: the stage shows a silhouette.
    for actor in sorted({e["actor"] for e in events if "actor" in e}):
        if actors.load(campaign_dir, actor) is None:
            print(f"Warning: no appearance for {actor!r} yet; the stage shows a silhouette. "
                  f"Set one with: uv run dnd-cli actor set {actor.split('#')[0]} ... "
                  "(see: uv run dnd-cli actor options). The stage updates the picture by itself: do not send this beat again.", file=sys.stderr)

    # Same for a place: the stage shows a blank room until it has a look.
    for location in sorted({e["location"] for e in events if e["type"] == "scene"}):
        if scenes.load(campaign_dir, location) is None:
            print(f"Warning: no look for location {location!r} yet; the stage shows a blank room. "
                  f"Set one with: uv run dnd-cli scene set {location} template=... "
                  "(see: uv run dnd-cli scene options). The stage updates the picture by itself: do not send this beat again.", file=sys.stderr)

    for site_id in sorted({e["site"] for e in events if e["type"] == "explore"}):
        if crawl.load(campaign_dir, site_id) is None:
            print(f"Warning: no site {site_id!r} yet; the stage shows an empty map. "
                  f"Set one with: uv run dnd-cli site set {site_id} theme=... poi=<id>@<where> "
                  "(see: uv run dnd-cli site options). The stage updates by itself: do not send this beat again.", file=sys.stderr)

    print(f"Shown: {len(events)} event(s): " + ", ".join(e["type"] for e in events))
    return 0
