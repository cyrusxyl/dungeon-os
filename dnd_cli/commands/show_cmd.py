"""show command - put a beat (scene, actors, narration, dialogue, choices) on the stage"""

import os
import sys
from pathlib import Path

from dnd_cli import world
from dnd_cli.campaign import CampaignError, active_campaign_slug, resolve_campaign_dir
from dnd_cli.errors import RulesError
from stage import actors, beat, cast, crawl, maps, scenes, state
from core.files import read_json, write_json


def stage_campaign_dir(campaign: str | None) -> Path:
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
        return fn(stage_campaign_dir(campaign))
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


def _slot_warnings(campaign_dir: Path, scene: str | None, events: list[dict]) -> None:
    """Warn when `@enter <id> on <slot>` or `near <slot>` names a slot that holds nothing in the room: the engine places that actor
    by its side instead, and the DM should know."""
    asked = [e for e in events if e["type"] == "enter" and (e.get("on") or e.get("near"))]
    try:
        room = scenes.room(spec) if asked and scene and (spec := scenes.load(campaign_dir, scene)) else None
    except ValueError:
        room = None
    if not room:
        return
    for e in asked:
        if e.get("on") and not any(st["slot"] == e["on"] for st in room["stand"]):
            print(f"Warning: @enter {e['actor']} on {e['on']}: no prop in that slot takes an actor, so the stage places {e['actor']} on the floor.", file=sys.stderr)
        if e.get("near") and cast.near_cell(room, e["near"]) is None:
            print(f"Warning: @enter {e['actor']} near {e['near']}: nothing is in that slot, so the stage places {e['actor']} by their side.", file=sys.stderr)


def _cast_report(campaign_dir: Path, events: list[dict]) -> str:
    """Fold the beat into the stage as it is now. Warn about what the beat does that the stage will not do, and
    return who is on stage after it, so the DM sees the cast and does not have to remember it."""
    s = state.replay(beat.log_path(campaign_dir))
    for e in events:
        who = e.get("actor")
        if e["type"] in ("exit", "leave") and who not in s["actors"]:
            print(f"Warning: @{e['type']} {who}: {who} is not on stage, so nothing happens. A new @scene clears the stage "
                  "and brings only the party and the companions; leave one of them out with '@scene <loc> -<id>'.", file=sys.stderr)
        s = state.apply(s, e)
    if s["explore"] or not s["actors"]:
        return ""
    _slot_warnings(campaign_dir, s["scene"], events)
    if len(s["actors"]) > beat.MAX_ACTORS:
        print(f"Warning: {len(s['actors'])} actors are on stage; the stage fits {beat.MAX_ACTORS}. Send @exit for some.", file=sys.stderr)
    return "On stage: " + ", ".join(f"{a} ({v.get('side', 'neutral')}{', on ' + v['on'] if v.get('on') else ''})"
                                     for a, v in s["actors"].items())


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
        from dnd_cli import character
        from dnd_cli.combat import rolls, tracker

        try:
            if not character.character_path(campaign_dir, e["who"]).exists():
                raise RulesError(f"@roll is for player characters; {e['who']!r} has no sheet. "
                                        "Roll for others with `uv run dnd-cli check`.")
            e.update(rolls.roll_preview(campaign_dir, tracker.load_state(campaign_dir), e["who"], e["what"]))
        except (RulesError, character.CharacterError) as err:
            print(f"Error: @roll {e['who']} {e['what']}: {err}", file=sys.stderr)
            return 1

    # A scene or site that is a place on a map moves the party marker there.
    found = maps.all_maps(campaign_dir)
    out = []
    members = beat.party(campaign_dir)
    roster = beat.companions(campaign_dir)
    for e in events:
        # The roster is kept in state.json; the stage folds events only, so each event carries what it needs.
        if e["type"] == "join":
            roster = [c for c in roster if c["id"] != e["actor"]] + [{"id": e["actor"], "side": e["side"]}]
        elif e["type"] == "leave":
            roster = [c for c in roster if c["id"] != e["actor"]]
        elif e["type"] == "side":
            roster = [{**c, "side": e["side"]} if c["id"] == e["actor"] else c for c in roster]
        elif e["type"] in ("enter", "say") and (c := next((c for c in roster if c["id"] == e["actor"]), None)):
            e.setdefault("side", c["side"])
        elif e["type"] == "scene":
            if members:
                e["party"] = members
            if roster:
                e["companions"] = roster
        out.append(e)
        place = e.get("location") if e["type"] == "scene" else e.get("site") if e["type"] == "explore" else None
        map_id = maps.visit(campaign_dir, found, place) if place else None
        if map_id:
            out.append({"type": "at", "map": map_id, "place": place})
    if roster != beat.companions(campaign_dir):
        beat.set_companions(campaign_dir, roster)
    cast = _cast_report(campaign_dir, out)
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
    if cast:
        print(cast)
    return 0
