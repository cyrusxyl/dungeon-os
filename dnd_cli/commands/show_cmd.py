"""show command - put a beat (scene, actors, narration, dialogue, choices) on the stage"""

import os
import sys
from pathlib import Path

from dnd_cli import world
from dnd_cli.campaign import CampaignError, active_campaign_slug, resolve_campaign_dir
from stage import actors, beat, crawl, maps, scenes
from stage.files import read_json, write_json


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


def run_stage(campaign: str | None, fn, *errors: type[Exception]) -> int:
    """Run fn(campaign_dir) for a stage command; print a known error and return 1."""
    try:
        return fn(_stage_campaign_dir(campaign))
    except (CampaignError, OSError, KeyError, *errors) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def notify_stage(campaign_dir: Path, event: dict) -> None:
    """Tell a running stage to reload something (an actor, a scene, a site, a map)."""
    if os.environ.get("DUNGEON_STAGE_LOG"):
        beat.append(campaign_dir, [event])


def preview_path(campaign_dir: Path, name: str) -> Path:
    out = campaign_dir / ".cache" / "stage" / f"{name}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def _set_location(campaign_dir: Path, m: dict, place: str) -> str | None:
    """Keep state.json's location, place and clock in step with the map, so the DM need not edit them.

    Returns a time line when the move along map routes cost travel time.
    """
    path = campaign_dir / "state.json"
    if (state := read_json(path)) is None:
        return None
    state["location"] = f"{m['places'][place]['name']}, {m['name']}"
    line = world.travel(state, m, place)
    write_json(path, state, indent=2)
    return line


def execute_beat(campaign: str | None, file: str | None) -> int:
    return run_stage(campaign, lambda campaign_dir: _beat(campaign_dir, file))


def _beat(campaign_dir: Path, file: str | None) -> int:
    text = Path(file).read_text() if file else sys.stdin.read()
    try:
        events = beat.parse(text)
    except beat.BeatError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Put the party in a site before the stage reads the event.
    missing_sites = set()
    for e in events:
        if e["type"] == "explore":
            site = crawl.load(campaign_dir, e["site"])
            if site is None:
                missing_sites.add(e["site"])
                continue
            try:
                crawl.arrive(site, e.get("at"))
            except crawl.SiteError as err:
                print(f"Error: @explore {e['site']} {e.get('at')}: {err}", file=sys.stderr)
                return 1
            crawl.save(campaign_dir, e["site"], site)

    # A roll request carries what the roll window shows before the roll (title, tiles).
    for e in events:
        if e["type"] != "roll_request":
            continue
        from dnd_cli import character, combat

        try:
            if not character.character_path(campaign_dir, e["who"]).exists():
                raise combat.RulesError(f"@roll is for player characters; {e['who']!r} has no sheet. "
                                        "Roll for others with `uv run dnd-cli check`.")
            e.update(combat.roll_preview(campaign_dir, combat.load_state(campaign_dir), e["who"], e["what"]))
        except (combat.RulesError, character.CharacterError) as err:
            print(f"Error: @roll {e['who']} {e['what']}: {err}", file=sys.stderr)
            return 1

    # A scene or site that is a place on a map moves the party marker there.
    found = maps.all_maps(campaign_dir)
    out = []
    members = beat.party(campaign_dir)
    for e in events:
        if e["type"] == "scene" and members:
            e["party"] = members
        out.append(e)
        place = e.get("location") if e["type"] == "scene" else e.get("site") if e["type"] == "explore" else None
        map_id = maps.visit(campaign_dir, found, place) if place else None
        if map_id:
            out.append({"type": "at", "map": map_id, "place": place})
    if out == beat.last_beat(beat.log_path(campaign_dir)):
        # A resent beat (often after setting a look): the players must not read it twice.
        print("This beat is already on the stage (same as the last one); not shown again. "
              "The stage updates pictures by itself.")
        return 0
    beat.append(campaign_dir, out)
    if at := next((e for e in reversed(out) if e["type"] == "at"), None):
        if line := _set_location(campaign_dir, found[at["map"]], at["place"]):
            print(line)

    # An unknown actor is not an error: the stage shows a silhouette.
    for actor in sorted({e["actor"] for e in events if "actor" in e}):
        if actors.load_own(campaign_dir, actor) is not None:
            continue
        # A kind's look (preset or monster tile) is fixed on first sight: later
        # changes to the presets or tiles must not change what players saw.
        if (spec := actors.load(campaign_dir, actor)) is not None:
            actors.save(campaign_dir, actor.split("#")[0], spec)
        else:
            print(f"Warning: no appearance for {actor!r} yet; the stage shows a silhouette. "
                  f"Set one with: uv run dnd-cli actor set {actor.split('#')[0]} ... "
                  "(see: uv run dnd-cli actor options). The stage updates the picture by itself.", file=sys.stderr)

    # Same for a place: the stage shows a blank room until it has a look.
    for location in sorted({e["location"] for e in events if e["type"] == "scene"}):
        if scenes.load(campaign_dir, location) is None:
            print(f"Warning: no look for location {location!r} yet; the stage shows a blank room. "
                  f"Set one with: uv run dnd-cli scene set {location} template=... "
                  "(see: uv run dnd-cli scene options). The stage updates the picture by itself.", file=sys.stderr)

    for site_id in sorted(missing_sites):
        print(f"Warning: no site {site_id!r} yet; the stage shows an empty map. "
              f"Set one with: uv run dnd-cli site set {site_id} theme=... poi=<id>@<where> "
              "(see: uv run dnd-cli site options). The stage updates by itself.", file=sys.stderr)

    print(f"Shown: {len(events)} event(s): " + ", ".join(e["type"] for e in events))
    return 0
