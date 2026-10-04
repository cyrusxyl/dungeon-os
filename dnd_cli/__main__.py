#!/usr/bin/env python3
"""DungeonOS D&D 5e API CLI Wrapper

Usage:
    dnd-cli list <resource>
    dnd-cli get <endpoint>
    dnd-cli search <resource> [--filters]
    dnd-cli random <resource> [--count N] [--filters]
    dnd-cli info <resource> <index>
    dnd-cli cache-info
    dnd-cli clear-cache [resource]
"""

import sys
import argparse
from dnd_cli.commands import list as cmd_list
from dnd_cli.commands import get as cmd_get
from dnd_cli.commands import search as cmd_search
from dnd_cli.commands import random as cmd_random
from dnd_cli.commands import info as cmd_info
from dnd_cli.commands import cache_cmd
from dnd_cli.commands import canon_cmd
from dnd_cli.commands import character_cmd
from dnd_cli.commands import show_cmd
from dnd_cli.commands import actor_cmd
from dnd_cli.commands import scene_cmd
from dnd_cli.commands import site_cmd
from dnd_cli.commands import map_cmd
from dnd_cli.commands import session_cmd
from dnd_cli.cache_warmup import warmup_cache, warmup_all_resources


def create_parser():
    """Create argument parser"""
    parser = argparse.ArgumentParser(
        description="D&D 5e API wrapper with caching and DM utilities",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # List command
    list_parser = subparsers.add_parser("list", help="List all resources")
    list_parser.add_argument("resource", help="Resource type (monsters, spells, etc.)")

    # Get command
    get_parser = subparsers.add_parser("get", help="Get specific resource")
    get_parser.add_argument("endpoint", help="API endpoint (e.g., monsters/goblin)")
    get_parser.add_argument("--json", action="store_true", help="Output raw JSON")
    get_parser.add_argument("--fields", default=None, help="Only these top-level fields, comma-separated (e.g. name,desc)")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search resources with filters")
    search_parser.add_argument("resource", help="Resource type")
    search_parser.add_argument("--cr", help="Challenge rating (e.g., 5-7, 3+)")
    search_parser.add_argument("--type", help="Monster type (undead, dragon, etc.)")
    search_parser.add_argument("--size", help="Size (tiny, small, medium, large, huge, gargantuan)")
    search_parser.add_argument("--level", help="Spell level (0-9 or cantrip)")
    search_parser.add_argument("--school", help="Spell school (evocation, etc.)")
    search_parser.add_argument("--class", dest="spell_class", help="Spell class (wizard, cleric, etc.)")
    search_parser.add_argument("--category", help="Equipment category")
    search_parser.add_argument("--name", help="Name search (fuzzy matching)")
    search_parser.add_argument("--text", help="Text search in descriptions/abilities")

    # Random command
    random_parser = subparsers.add_parser("random", help="Random resource selection")
    random_parser.add_argument("resource", help="Resource type")
    random_parser.add_argument("--count", type=int, default=1, help="Number to select")
    random_parser.add_argument("--cr", help="Challenge rating filter")
    random_parser.add_argument("--type", help="Type filter")
    random_parser.add_argument("--level", help="Level filter")

    # Info command
    info_parser = subparsers.add_parser("info", help="Quick reference lookup")
    info_parser.add_argument("resource", help="Resource type (conditions, skills, damage-types)")
    info_parser.add_argument("index", help="Resource index")

    # Cache commands
    cache_info_parser = subparsers.add_parser("cache-info", help="Show cache statistics")
    clear_cache_parser = subparsers.add_parser("clear-cache", help="Clear cache")
    clear_cache_parser.add_argument("resource", nargs="?", help="Specific resource to clear (optional)")

    # Warmup command
    warmup_parser = subparsers.add_parser(
        "warmup",
        help="Pre-cache full resource data for filtering"
    )
    warmup_parser.add_argument(
        "resource",
        nargs="?",
        help="Resource to warmup (monsters, spells, etc.) or 'all'"
    )
    warmup_parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-fetch even if cached"
    )

    # Canon command group
    canon_parser = subparsers.add_parser(
        "canon",
        help="Canon file bookkeeping: clocks, threads, facts (no LLM arithmetic)"
    )
    canon_sub = canon_parser.add_subparsers(dest="canon_command", help="Canon subcommand")

    p = canon_sub.add_parser("init", help="Create an empty canon.json for a campaign")
    p.add_argument("campaign")

    p = canon_sub.add_parser("validate", help="Validate canon.json against the schema")
    p.add_argument("campaign")

    p = canon_sub.add_parser("show", help="Print canon.json")
    p.add_argument("campaign")

    p = canon_sub.add_parser("add-villain", help="Add a villain to Part A (Checklist 2.1-2.5)")
    p.add_argument("campaign")
    p.add_argument("name")
    p.add_argument("goal")
    p.add_argument("trait")
    p.add_argument("--escape-plan", default="", help="How this villain escapes capture (Checklist 2.4)")

    p = canon_sub.add_parser("add-clock", help="Add a clock (quest) to a villain (OG 2.1-2.3)")
    p.add_argument("campaign")
    p.add_argument("villain")
    p.add_argument("clock")
    p.add_argument("segments_total", type=int, choices=[4, 6, 8], help="OG 2.2: a clock has 4, 6, or 8 segments")
    p.add_argument("--description", default="")

    p = canon_sub.add_parser("advance-clock", help="Advance a villain's clock (OG 2.4-2.6)")
    p.add_argument("campaign")
    p.add_argument("villain")
    p.add_argument("clock")
    p.add_argument("--action-taken", action="store_true", help="Players took direct action against this quest: do not advance")
    p.add_argument("--warning-ignored", action="store_true", help="Players ignored a clear warning: advance by 2")

    p = canon_sub.add_parser("touch-clock", help="Record the clock the session's arc-touch scene connected to (OG 4.3)")
    p.add_argument("campaign")
    p.add_argument("villain")
    p.add_argument("clock")

    p = canon_sub.add_parser("sweep-threads", help="Update thread staleness at session end (OG 3.3-3.6)")
    p.add_argument("campaign")
    p.add_argument("--appeared", default="", help="Comma-separated thread ids that appeared in play this session")

    p = canon_sub.add_parser("add-thread", help="Open a new thread (enforces the 5-thread cap, OG 3.7-3.8)")
    p.add_argument("campaign")
    p.add_argument("thread_id")
    p.add_argument("description")

    p = canon_sub.add_parser("close-thread", help="Close or merge away a thread")
    p.add_argument("campaign")
    p.add_argument("thread_id")

    p = canon_sub.add_parser("add-fact", help="Record a canon-level fact (Part C)")
    p.add_argument("campaign")
    p.add_argument("session", type=int)
    p.add_argument("source", help="'DM' or the player's name")
    p.add_argument("fact")

    p = canon_sub.add_parser("add-item", help="Record an item given to a player (Part E)")
    p.add_argument("campaign")
    p.add_argument("session", type=int)
    p.add_argument("recipient")
    p.add_argument("item")

    p = canon_sub.add_parser("add-promise", help="Record a promise made to a player (Part F)")
    p.add_argument("campaign")
    p.add_argument("session", type=int)
    p.add_argument("made_to")
    p.add_argument("promise")

    p = canon_sub.add_parser("fulfill-promise", help="Mark a promise fulfilled by its index in 'canon show'")
    p.add_argument("campaign")
    p.add_argument("index", type=int)

    p = canon_sub.add_parser("add-ruling", help="Record a ruling (Part G)")
    p.add_argument("campaign")
    p.add_argument("session", type=int)
    p.add_argument("context")
    p.add_argument("ruling")

    p = canon_sub.add_parser("session-report", help="Show what is on record for a session, and any gaps (OG Section 11)")
    p.add_argument("campaign")
    p.add_argument("session", type=int)

    p = canon_sub.add_parser("close-session", help="Set last_session_written after checking the session report is clean")
    p.add_argument("campaign")
    p.add_argument("session", type=int)
    p.add_argument("--force", action="store_true", help="Close even if the session report has warnings")

    # Character command group
    character_parser = subparsers.add_parser(
        "character",
        help="Character file bookkeeping: HP and spell slots (no LLM arithmetic)"
    )
    character_sub = character_parser.add_subparsers(dest="character_command", help="Character subcommand")

    p = character_sub.add_parser("show", help="Print a character file")
    p.add_argument("campaign")
    p.add_argument("name", help="Character file name, without .json")

    p = character_sub.add_parser("validate", help="Validate a character file against the schema")
    p.add_argument("campaign")
    p.add_argument("name")

    p = character_sub.add_parser("apply-damage", help="Apply damage: temp HP absorbs first, then current HP, floored at 0")
    p.add_argument("campaign")
    p.add_argument("name")
    p.add_argument("amount", type=int)

    p = character_sub.add_parser("heal", help="Heal: current HP capped at max, does not restore temp HP")
    p.add_argument("campaign")
    p.add_argument("name")
    p.add_argument("amount", type=int)

    p = character_sub.add_parser("add-temp-hp", help="Set temp HP: does not stack, higher value wins")
    p.add_argument("campaign")
    p.add_argument("name")
    p.add_argument("amount", type=int)

    p = character_sub.add_parser("cast", help="Spend one spell slot at the given level")
    p.add_argument("campaign")
    p.add_argument("name")
    p.add_argument("level", type=int, choices=range(1, 10))

    p = character_sub.add_parser("restore-slots", help="Long rest: restore one level's slots, or all levels if --level omitted")
    p.add_argument("campaign")
    p.add_argument("name")
    p.add_argument("--level", type=int, choices=range(1, 10), default=None)

    # Show command group (the visual stage)
    show_parser = subparsers.add_parser(
        "show",
        help="Put story on the visual stage: scene, actors, narration, dialogue, choices"
    )
    show_sub = show_parser.add_subparsers(dest="show_command", help="Show subcommand")
    p = show_sub.add_parser("beat", help="Read beat markup from stdin (or --file) and show it")
    p.add_argument("--campaign", default=None, help="Campaign slug (default: the active campaign)")
    p.add_argument("--file", default=None, help="Read the beat from this file instead of stdin")

    # Actor command group (how characters look on the visual stage)
    actor_parser = subparsers.add_parser(
        "actor",
        help="Set how a character looks on the visual stage (LPC pixel art)"
    )
    actor_sub = actor_parser.add_subparsers(dest="actor_command", help="Actor subcommand")
    p = actor_sub.add_parser("set", help="Set or change an actor's look: name= body= skin= eyes= preset= and items like robe:white")
    p.add_argument("actor_id")
    p.add_argument("tokens", nargs="*")
    p.add_argument("--change", action="store_true", help="Change a look that already exists (the story changed it)")
    p.add_argument("--campaign", default=None)
    p = actor_sub.add_parser("show", help="Print an actor's look (its file, else the preset for its kind)")
    p.add_argument("actor_id")
    p.add_argument("--campaign", default=None)
    p = actor_sub.add_parser("preview", help="Render front, side and portrait to a PNG you can look at")
    p.add_argument("actor_id")
    p.add_argument("--emotion", default=None)
    p.add_argument("--campaign", default=None)
    p = actor_sub.add_parser("options", help="List settings, item types, or the items of one type")
    p.add_argument("item_type", nargs="?", default=None)
    p.add_argument("--body", default=None, help="Only items that fit this body type")

    # Scene command group (how a location looks on the visual stage)
    scene_parser = subparsers.add_parser(
        "scene",
        help="Set how a location looks on the visual stage: template, wall, floor, mood, props"
    )
    scene_sub = scene_parser.add_subparsers(dest="scene_command", help="Scene subcommand")
    p = scene_sub.add_parser("set", help="template= wall= floor= mood= <slot>=<prop|none> +<prop>@<zone> clear=add")
    p.add_argument("location")
    p.add_argument("tokens", nargs="*")
    p.add_argument("--change", action="store_true", help="Change a place that already has a look (the story changed it)")
    p.add_argument("--campaign", default=None)
    p = scene_sub.add_parser("show", help="Print a location's scene spec and what it resolves to")
    p.add_argument("location")
    p.add_argument("--campaign", default=None)
    p = scene_sub.add_parser("preview", help="Render a location's scene to a PNG you can look at")
    p.add_argument("location")
    p.add_argument("--campaign", default=None)
    p = scene_sub.add_parser("options", help="List templates, walls, floors, props, moods, slots")
    p.add_argument("what", nargs="?", default=None)

    # Session command group
    session_parser = subparsers.add_parser("session", help="Session helpers for the DM")
    session_sub = session_parser.add_subparsers(dest="session_command", help="Session subcommand")
    p = session_sub.add_parser("brief", help="Print state, party, players, canon, story bible and recent log in one go")
    p.add_argument("--campaign", default=None)

    # Site command group (generated buildings and dungeons the party walks through)
    site_parser = subparsers.add_parser("site", help="Set a building or dungeon the party explores on the visual stage")
    site_sub = site_parser.add_subparsers(dest="site_command", help="Site subcommand")
    p = site_sub.add_parser("set", help="theme= size= danger= name= poi=<id>@<where>[:<icon>] ...")
    p.add_argument("site_id")
    p.add_argument("tokens", nargs="*")
    p.add_argument("--change", action="store_true", help="Add points of interest, or change name= or danger=")
    p.add_argument("--campaign", default=None)
    for name, text in (("show", "Print a site's settings and points of interest"),
                       ("preview", "Render the whole layout (DM only) to a PNG you can look at")):
        p = site_sub.add_parser(name, help=text)
        p.add_argument("site_id")
        p.add_argument("--campaign", default=None)
    site_sub.add_parser("options", help="List themes, depths and icons")

    # Map command group (region and city maps)
    map_parser = subparsers.add_parser("map", help="Region and city maps on the visual stage: places, routes, reveals")
    map_sub = map_parser.add_subparsers(dest="map_command", help="Map subcommand")
    p = map_sub.add_parser("place", help="Add a place: name= icon= from= dir= travel= in= hidden=yes")
    p.add_argument("map_id")
    p.add_argument("place_id")
    p.add_argument("tokens", nargs="*")
    p.add_argument("--campaign", default=None)
    p = map_sub.add_parser("route", help="Make a route between two places known: travel=")
    p.add_argument("map_id")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("tokens", nargs="*")
    p.add_argument("--campaign", default=None)
    p = map_sub.add_parser("reveal", help="Show a hidden place to the players")
    p.add_argument("map_id")
    p.add_argument("place_id")
    p.add_argument("--campaign", default=None)
    p = map_sub.add_parser("show", help="Print a map (or all maps), hidden places too")
    p.add_argument("map_id", nargs="?", default=None)
    p.add_argument("--campaign", default=None)
    map_sub.add_parser("options", help="Show the map command forms and icons")

    return parser


def main():
    """Main entry point"""
    parser = create_parser()
    # `actor set` and `scene set` take free tokens; flags may sit between them.
    args, extra = parser.parse_known_args()
    if extra:
        if getattr(args, "tokens", None) is not None and not any(t.startswith("--") for t in extra):
            args.tokens += extra
        else:
            parser.error(f"unrecognized arguments: {' '.join(extra)}")

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "list":
            return cmd_list.execute(args.resource)

        elif args.command == "get":
            return cmd_get.execute(args.endpoint, args.json, args.fields)

        elif args.command == "search":
            filters = {}
            if args.cr:
                filters["cr"] = args.cr
            if args.type:
                filters["type"] = args.type
            if args.size:
                filters["size"] = args.size
            if args.level:
                filters["level"] = args.level
            if args.school:
                filters["school"] = args.school
            if args.spell_class:
                filters["class"] = args.spell_class
            if args.category:
                filters["category"] = args.category
            if args.name:
                filters["name"] = args.name
            if args.text:
                filters["text"] = args.text

            return cmd_search.execute(args.resource, filters)

        elif args.command == "random":
            filters = {}
            if hasattr(args, 'cr') and args.cr:
                filters["cr"] = args.cr
            if hasattr(args, 'type') and args.type:
                filters["type"] = args.type
            if hasattr(args, 'level') and args.level:
                filters["level"] = args.level

            return cmd_random.execute(args.resource, filters, args.count)

        elif args.command == "info":
            return cmd_info.execute(args.resource, args.index)

        elif args.command == "cache-info":
            return cache_cmd.execute_info()

        elif args.command == "clear-cache":
            return cache_cmd.execute_clear(args.resource)

        elif args.command == "canon":
            if not args.canon_command:
                print("Usage: dnd-cli canon <subcommand> ... (see --help)", file=sys.stderr)
                return 1

            cc = args.canon_command
            if cc == "init":
                return canon_cmd.execute_init(args.campaign)
            elif cc == "validate":
                return canon_cmd.execute_validate(args.campaign)
            elif cc == "show":
                return canon_cmd.execute_show(args.campaign)
            elif cc == "add-villain":
                return canon_cmd.execute_add_villain(args.campaign, args.name, args.goal, args.trait, args.escape_plan)
            elif cc == "add-clock":
                return canon_cmd.execute_add_clock(
                    args.campaign, args.villain, args.clock, args.segments_total, args.description
                )
            elif cc == "advance-clock":
                return canon_cmd.execute_advance_clock(
                    args.campaign, args.villain, args.clock, args.action_taken, args.warning_ignored
                )
            elif cc == "touch-clock":
                return canon_cmd.execute_touch_clock(args.campaign, args.villain, args.clock)
            elif cc == "sweep-threads":
                appeared = [t.strip() for t in args.appeared.split(",") if t.strip()]
                return canon_cmd.execute_sweep_threads(args.campaign, appeared)
            elif cc == "add-thread":
                return canon_cmd.execute_add_thread(args.campaign, args.thread_id, args.description)
            elif cc == "close-thread":
                return canon_cmd.execute_close_thread(args.campaign, args.thread_id)
            elif cc == "add-fact":
                return canon_cmd.execute_add_fact(args.campaign, args.session, args.source, args.fact)
            elif cc == "add-item":
                return canon_cmd.execute_add_item(args.campaign, args.session, args.recipient, args.item)
            elif cc == "add-promise":
                return canon_cmd.execute_add_promise(args.campaign, args.session, args.made_to, args.promise)
            elif cc == "fulfill-promise":
                return canon_cmd.execute_fulfill_promise(args.campaign, args.index)
            elif cc == "add-ruling":
                return canon_cmd.execute_add_ruling(args.campaign, args.session, args.context, args.ruling)
            elif cc == "session-report":
                return canon_cmd.execute_session_report(args.campaign, args.session)
            elif cc == "close-session":
                return canon_cmd.execute_close_session(args.campaign, args.session, args.force)
            else:
                print(f"Unknown canon subcommand: {cc}", file=sys.stderr)
                return 1

        elif args.command == "character":
            if not args.character_command:
                print("Usage: dnd-cli character <subcommand> ... (see --help)", file=sys.stderr)
                return 1

            cc = args.character_command
            if cc == "show":
                return character_cmd.execute_show(args.campaign, args.name)
            elif cc == "validate":
                return character_cmd.execute_validate(args.campaign, args.name)
            elif cc == "apply-damage":
                return character_cmd.execute_apply_damage(args.campaign, args.name, args.amount)
            elif cc == "heal":
                return character_cmd.execute_heal(args.campaign, args.name, args.amount)
            elif cc == "add-temp-hp":
                return character_cmd.execute_add_temp_hp(args.campaign, args.name, args.amount)
            elif cc == "cast":
                return character_cmd.execute_cast(args.campaign, args.name, args.level)
            elif cc == "restore-slots":
                return character_cmd.execute_restore_slots(args.campaign, args.name, args.level)
            else:
                print(f"Unknown character subcommand: {cc}", file=sys.stderr)
                return 1

        elif args.command == "show":
            if args.show_command == "beat":
                return show_cmd.execute_beat(args.campaign, args.file)
            print("Usage: dnd-cli show beat [--campaign C] [--file F] (see --help)", file=sys.stderr)
            return 1

        elif args.command == "actor":
            ac = args.actor_command
            if ac == "set":
                return actor_cmd.execute_set(args.campaign, args.actor_id, args.tokens, args.change)
            if ac == "show":
                return actor_cmd.execute_show(args.campaign, args.actor_id)
            if ac == "preview":
                return actor_cmd.execute_preview(args.campaign, args.actor_id, args.emotion)
            if ac == "options":
                return actor_cmd.execute_options(args.item_type, args.body)
            print("Usage: dnd-cli actor set|show|preview|options ... (see --help)", file=sys.stderr)
            return 1

        elif args.command == "scene":
            sc = args.scene_command
            if sc == "set":
                return scene_cmd.execute_set(args.campaign, args.location, args.tokens, args.change)
            if sc == "show":
                return scene_cmd.execute_show(args.campaign, args.location)
            if sc == "preview":
                return scene_cmd.execute_preview(args.campaign, args.location)
            if sc == "options":
                return scene_cmd.execute_options(args.what)
            print("Usage: dnd-cli scene set|show|preview|options ... (see --help)", file=sys.stderr)
            return 1

        elif args.command == "session":
            if args.session_command == "brief":
                return session_cmd.execute_brief(args.campaign)
            print("Usage: dnd-cli session brief [--campaign C]", file=sys.stderr)
            return 1

        elif args.command == "site":
            sc = args.site_command
            if sc == "set":
                return site_cmd.execute_set(args.campaign, args.site_id, args.tokens, args.change)
            if sc == "show":
                return site_cmd.execute_show(args.campaign, args.site_id)
            if sc == "preview":
                return site_cmd.execute_preview(args.campaign, args.site_id)
            if sc == "options":
                return site_cmd.execute_options()
            print("Usage: dnd-cli site set|show|preview|options ... (see --help)", file=sys.stderr)
            return 1

        elif args.command == "map":
            mc = args.map_command
            if mc == "place":
                return map_cmd.execute_place(args.campaign, args.map_id, args.place_id, args.tokens)
            if mc == "route":
                return map_cmd.execute_route(args.campaign, args.map_id, args.a, args.b, args.tokens)
            if mc == "reveal":
                return map_cmd.execute_reveal(args.campaign, args.map_id, args.place_id)
            if mc == "show":
                return map_cmd.execute_show(args.campaign, args.map_id)
            if mc == "options":
                return map_cmd.execute_options()
            print("Usage: dnd-cli map place|route|reveal|show|options ... (see --help)", file=sys.stderr)
            return 1

        elif args.command == "warmup":
            resource = args.resource or "all"

            if resource == "all":
                warmup_all_resources(force=args.force)
            else:
                cached, errors = warmup_cache(resource, force=args.force)
                if errors > 0:
                    return 1

            return 0

        else:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            parser.print_help()
            return 1

    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
