#!/usr/bin/env python3
"""DungeonOS command line: the D&D 5e API (list, get, search, random, info, cache) and the DM tools
(canon, character, encounter, attack, save, check, rest, loot, show, actor, scene, site, map, session, state, quest, npc, faction).

Run `dnd-cli <command> --help`. Each parser names its handler with `set_defaults(fn=...)`; main() parses and calls it.
A command that works on a campaign takes `--campaign` (default: the one the stage shows, else the active one).
"""

import argparse
import sys

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
from dnd_cli.commands import arena_cmd, site_cmd
from dnd_cli.commands import map_cmd
from dnd_cli.commands import session_cmd
from dnd_cli.commands import rules_cmd
from dnd_cli.commands import world_cmd


def bind(fn, *names):
    """A handler that calls `fn` with these attributes of the parsed arguments, in order."""
    return lambda args: fn(*(getattr(args, n) for n in names))


def with_args(fn):
    """A handler for `fn(campaign, args)`: it reads what it needs from the parsed arguments itself."""
    return lambda args: fn(args.campaign, args)


def filters(args) -> dict:
    """The API filters that were given (search and random)."""
    return {k: v for k in ("cr", "type", "size", "level", "school", "class", "category", "name", "text")
            if (v := getattr(args, k, None))}


def option_parent(*flags: str) -> argparse.ArgumentParser:
    """A parent parser (for `parents=`) that holds options shared by many commands."""
    p = argparse.ArgumentParser(add_help=False)
    if "campaign" in flags:
        p.add_argument("--campaign", default=None, help="Campaign slug or path (default: the one the stage shows, else the active one)")
    if "session" in flags:
        p.add_argument("--session", type=int, default=None, help="Session number (default: the one being played, last_session_written + 1)")
    if "name" in flags:
        p.add_argument("name", help="Character file name, without .json")
    return p


def group(subparsers, name: str, dest: str, help: str):
    """A command with subcommands (one is required); returns the subparsers to add them to."""
    return subparsers.add_parser(name, help=help).add_subparsers(dest=dest, required=True)


def create_parser():
    """Create argument parser"""
    parser = argparse.ArgumentParser(
        description="D&D 5e API wrapper with caching and DM utilities",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Command to execute")
    camp, sess, char = option_parent("campaign"), option_parent("session"), option_parent("name")

    # API lookups
    p = subparsers.add_parser("list", help="List all resources")
    p.add_argument("resource", help="Resource type (monsters, spells, etc.)")
    p.set_defaults(fn=bind(cmd_list.execute, "resource"))

    p = subparsers.add_parser("get", help="Get specific resource")
    p.add_argument("endpoint", help="API endpoint (e.g., monsters/goblin)")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.add_argument("--fields", default=None, help="Only these top-level fields, comma-separated (e.g. name,desc)")
    p.set_defaults(fn=bind(cmd_get.execute, "endpoint", "json", "fields"))

    p = subparsers.add_parser("search", help="Search resources with filters")
    p.add_argument("resource", help="Resource type")
    p.add_argument("--cr", help="Challenge rating (e.g., 5-7, 3+)")
    p.add_argument("--type", help="Monster type (undead, dragon, etc.)")
    p.add_argument("--size", help="Size (tiny, small, medium, large, huge, gargantuan)")
    p.add_argument("--level", help="Spell level (0-9 or cantrip)")
    p.add_argument("--school", help="Spell school (evocation, etc.)")
    p.add_argument("--class", help="Spell class (wizard, cleric, etc.)")
    p.add_argument("--category", help="Equipment category")
    p.add_argument("--name", help="Name search (fuzzy matching)")
    p.add_argument("--text", help="Text search in descriptions/abilities")
    p.set_defaults(fn=lambda a: cmd_search.execute(a.resource, filters(a)))

    p = subparsers.add_parser("random", help="Random resource selection")
    p.add_argument("resource", help="Resource type")
    p.add_argument("--count", type=int, default=1, help="Number to select")
    p.add_argument("--cr", help="Challenge rating filter")
    p.add_argument("--type", help="Type filter")
    p.add_argument("--level", help="Level filter")
    p.set_defaults(fn=lambda a: cmd_random.execute(a.resource, filters(a), a.count))

    p = subparsers.add_parser("info", help="Quick reference lookup")
    p.add_argument("resource", help="Resource type (conditions, skills, damage-types)")
    p.add_argument("index", help="Resource index")
    p.set_defaults(fn=bind(cmd_info.execute, "resource", "index"))

    # Cache
    subparsers.add_parser("cache-info", help="Show cache statistics").set_defaults(fn=lambda a: cache_cmd.execute_info())
    p = subparsers.add_parser("clear-cache", help="Clear cache")
    p.add_argument("resource", nargs="?", help="Specific resource to clear (optional)")
    p.set_defaults(fn=bind(cache_cmd.execute_clear, "resource"))
    p = subparsers.add_parser("warmup", help="Pre-cache full resource data for filtering")
    p.add_argument("resource", nargs="?", help="Resource to warmup (monsters, spells, etc.) or 'all'")
    p.add_argument("--force", action="store_true", help="Force re-fetch even if cached")
    p.set_defaults(fn=bind(cache_cmd.execute_warmup, "resource", "force"))

    # Canon: the campaign and the session number may be left out
    canon_sub = group(subparsers, "canon", "canon_command", "Canon file bookkeeping: clocks, threads, facts (no LLM arithmetic)")

    def canon_cmd_parser(name, help, fn, *attrs, parents=(camp,)):
        p = canon_sub.add_parser(name, help=help, parents=list(parents))
        p.set_defaults(fn=bind(fn, "campaign", *attrs))
        return p

    canon_cmd_parser("init", "Create an empty canon.json for a campaign", canon_cmd.execute_init)
    canon_cmd_parser("validate", "Validate canon.json against the schema", canon_cmd.execute_validate)
    canon_cmd_parser("show", "Print canon.json", canon_cmd.execute_show)

    p = canon_cmd_parser("add-villain", "Add a villain to Part A (Checklist 2.1-2.5)", canon_cmd.execute_add_villain,
                         "name", "goal", "trait", "escape_plan")
    p.add_argument("name")
    p.add_argument("goal")
    p.add_argument("trait")
    p.add_argument("--escape-plan", default="", help="How this villain escapes capture (Checklist 2.4)")

    p = canon_cmd_parser("add-clock", "Add a clock (quest) to a villain (OG 2.1-2.3)", canon_cmd.execute_add_clock,
                         "villain", "clock", "segments_total", "description", "waiting")
    p.add_argument("villain")
    p.add_argument("clock")
    p.add_argument("segments_total", type=int, choices=[4, 6, 8], help="OG 2.2: a clock has 4, 6, or 8 segments")
    p.add_argument("--description", default="")
    p.add_argument("--waiting", action="store_true", help="The clock starts only when its trigger happens")

    p = canon_cmd_parser("clock-status", "Set a clock active, waiting (trigger not yet happened) or stopped",
                         canon_cmd.execute_clock_status, "villain", "clock", "status")
    p.add_argument("villain")
    p.add_argument("clock")
    p.add_argument("status", choices=["active", "waiting", "stopped"])

    p = canon_cmd_parser("advance-clock", "Advance a villain's clock (OG 2.4-2.6)", canon_cmd.execute_advance_clock,
                         "villain", "clock", "action_taken", "warning_ignored")
    p.add_argument("villain")
    p.add_argument("clock")
    p.add_argument("--action-taken", action="store_true", help="Players took direct action against this quest: do not advance")
    p.add_argument("--warning-ignored", action="store_true", help="Players ignored a clear warning: advance by 2")

    p = canon_cmd_parser("touch-clock", "Record the clock the session's arc-touch scene connected to (OG 4.3)",
                         canon_cmd.execute_touch_clock, "villain", "clock")
    p.add_argument("villain")
    p.add_argument("clock")

    p = canon_cmd_parser("sweep-threads", "Update thread staleness at session end (OG 3.3-3.6)",
                         canon_cmd.execute_sweep_threads, "appeared")
    p.add_argument("--appeared", default="", help="Comma-separated thread ids that appeared in play this session")

    p = canon_cmd_parser("add-thread", "Open a new thread (enforces the 5-thread cap, OG 3.7-3.8)",
                         canon_cmd.execute_add_thread, "thread_id", "description")
    p.add_argument("thread_id")
    p.add_argument("description")

    p = canon_cmd_parser("close-thread", "Close or merge away a thread", canon_cmd.execute_close_thread, "thread_id")
    p.add_argument("thread_id")

    p = canon_cmd_parser("add-fact", "Record a canon-level fact (Part C)", canon_cmd.execute_add_fact,
                         "session", "source", "fact", parents=(camp, sess))
    p.add_argument("source", help="'DM' or the player's name")
    p.add_argument("fact")

    p = canon_cmd_parser("add-item", "Record an item given to a player (Part E)", canon_cmd.execute_add_item,
                         "session", "recipient", "item", parents=(camp, sess))
    p.add_argument("recipient")
    p.add_argument("item")

    p = canon_cmd_parser("add-promise", "Record a promise made to a player (Part F)", canon_cmd.execute_add_promise,
                         "session", "made_to", "promise", parents=(camp, sess))
    p.add_argument("made_to")
    p.add_argument("promise")

    p = canon_cmd_parser("fulfill-promise", "Mark a promise fulfilled by its index in 'canon show'",
                         canon_cmd.execute_fulfill_promise, "index")
    p.add_argument("index", type=int)

    p = canon_cmd_parser("add-ruling", "Record a ruling (Part G)", canon_cmd.execute_add_ruling,
                         "session", "context", "ruling", parents=(camp, sess))
    p.add_argument("context")
    p.add_argument("ruling")

    canon_cmd_parser("session-report", "Show what is on record for a session, and any gaps (OG Section 11)",
                     canon_cmd.execute_session_report, "session", parents=(camp, sess))

    p = canon_cmd_parser("close-session", "Set last_session_written after checking the session report is clean",
                         canon_cmd.execute_close_session, "session", "force", parents=(camp, sess))
    p.add_argument("--force", action="store_true", help="Close even if the session report has warnings")

    # Character sheets: character <command> <name> ... [--campaign C]
    character_sub = group(subparsers, "character", "character_command", "Character sheets: HP, slots, items, gold, XP, levels (no LLM arithmetic)")

    def character_cmd_parser(name, help, fn, *attrs, parents=(camp, char)):
        p = character_sub.add_parser(name, help=help, parents=list(parents))
        p.set_defaults(fn=bind(fn, "campaign", *attrs))
        return p

    character_cmd_parser("show", "Print a character file", character_cmd.execute_show, "name")

    p = character_cmd_parser("validate", "Validate a character file against the schema and the 5e class data",
                             character_cmd.execute_validate, "name", "fix")
    p.add_argument("--fix", action="store_true", help="Fix spellcasting block, slot maximums, spell DC and proficiency")

    for cmd_name, text, fn in (("apply-damage", "Apply damage: temp HP absorbs first, then current HP, floored at 0", character_cmd.execute_apply_damage),
                               ("heal", "Heal: current HP capped at max, does not restore temp HP", character_cmd.execute_heal),
                               ("add-temp-hp", "Set temp HP: does not stack, higher value wins", character_cmd.execute_add_temp_hp)):
        character_cmd_parser(cmd_name, text, fn, "name", "amount").add_argument("amount", type=int)

    character_cmd_parser("cast", "Spend one spell slot at the given level", character_cmd.execute_cast, "name", "level"
                         ).add_argument("level", type=int, choices=range(1, 10))

    p = character_cmd_parser("use", "Spend one use of a class resource (Rage, Ki, Second Wind...): use <name> \"<resource>\" [--amount N] [--back]",
                             character_cmd.execute_use, "name", "resource", "amount", "back")
    p.add_argument("resource")
    p.add_argument("--back", action="store_true", help="Give a use back instead")
    p.add_argument("--amount", type=int, default=1, help="How many uses (Lay on Hands points)")

    p = character_cmd_parser("set", "Record a choice: set <name> subclass|fighting_style \"<value>\"",
                             character_cmd.execute_set, "name", "field", "value")
    p.add_argument("field", choices=["subclass", "fighting_style"])
    p.add_argument("value")

    p = character_cmd_parser("add", "Add a spell or a feat: add <name> spell|feat \"<value>\" [--prepared] [--desc TEXT]",
                             character_cmd.execute_add, "name", "kind", "value", "prepared", "desc")
    p.add_argument("kind", choices=["spell", "feat"])
    p.add_argument("value")
    p.add_argument("--prepared", action="store_true", help="For a spell: add it to spells_prepared instead of spells_known")
    p.add_argument("--desc", default="", help="For a feat: a short description")

    # character item <name> add|remove|equip|unequip|profile "<item>": each verb has its own flags
    p = character_sub.add_parser("item", help="Inventory: item <name> add|remove|equip|unequip|profile \"<item>\" ...", parents=[char])
    item_sub = p.add_subparsers(dest="item_command", required=True, metavar="add|remove|equip|unequip|profile")
    it = argparse.ArgumentParser(add_help=False)
    it.add_argument("item")
    q = argparse.ArgumentParser(add_help=False)
    q.add_argument("--qty", type=int, default=1)
    p = item_sub.add_parser("add", parents=[camp, it, q], help="Add an item, or more of it")
    p.add_argument("--perk", default="", help="What makes it special, in your words: it goes in the item's description")
    p.add_argument("--rarity", default=None)
    p.add_argument("--base", default=None, help="The base item it is made from (Longsword, Plate Armor); found in the name when left out")
    p.add_argument("--effects", default="", help="Effect presets the item gives while equipped, comma-separated (loot roll names them)")
    p.add_argument("--canon", action="store_true", help="Also record the item as given this session (canon Part E)")
    p.set_defaults(fn=rules_cmd.execute_item_add)
    item_sub.add_parser("remove", parents=[camp, it, q], help="Use up or take away an item").set_defaults(fn=rules_cmd.execute_item_remove)
    p = item_sub.add_parser("equip", parents=[camp, it], help="Wear or wield an item; a weapon or armor takes the stats of its base from the 5e API")
    p.add_argument("--not-proficient", action="store_true", help="No proficiency bonus on the attack")
    p.set_defaults(fn=rules_cmd.execute_item_equip)
    item_sub.add_parser("unequip", parents=[camp, it], help="Put an item away").set_defaults(fn=rules_cmd.execute_item_unequip)
    p = item_sub.add_parser("profile", parents=[camp, it], help="Keep what the item does in a fight")
    p.add_argument("--profile", required=True, help='As JSON: {"kind": "heal", "heal": "2d4"} or {"kind": "throw", "range_ft": 20, "damage": ["1d6", "fire"]}')
    p.set_defaults(fn=rules_cmd.execute_item_profile)

    character_cmd_parser("gold", "Change gold: gold <name> +N|-N", rules_cmd.execute_gold, "name", "delta").add_argument("delta")

    p = character_cmd_parser("xp", "Add XP: xp <name...|all> --amount N", rules_cmd.execute_xp, "names", "amount", parents=(camp,))
    p.add_argument("names", nargs="+")
    p.add_argument("--amount", type=int, required=True)

    p = character_cmd_parser("level-up", "Gain the next class level: HP, proficiency, slots, features, all bonuses",
                             rules_cmd.execute_level_up, "name", "hp", "asi")
    p.add_argument("--hp", choices=["avg", "roll"], default="avg")
    p.add_argument("--asi", default=None, help="str+2, str+1,dex+1, or none (a feat)")

    p = character_sub.add_parser("new", parents=[camp], help="Create a level 1 character in one call: sheet, player file, party")
    p.add_argument("id", help="File name of the sheet, e.g. thorin")
    p.add_argument("--player", required=True, help="Player id")
    p.add_argument("--player-name", default=None, help="Player's name (for a new player file)")
    p.add_argument("--name", required=True)
    p.add_argument("--race", required=True)
    p.add_argument("--subrace", default=None)
    p.add_argument("--class", dest="char_class", required=True)
    p.add_argument("--background", required=True)
    p.add_argument("--scores", required=True, help="Six scores, e.g. 15,14,13,12,10,8")
    p.add_argument("--assign", required=True, help="Abilities for those scores, e.g. str,dex,con,int,wis,cha")
    p.add_argument("--skills", required=True, help="The class's skill picks, e.g. athletics,perception")
    p.add_argument("--background-skills", default=None, help="Background skills not in the API")
    p.add_argument("--bonus-abilities", default=None, help="Half-elf: two abilities for +1")
    p.add_argument("--background-bonus", default=None,
                   help="A 2024 background (sage, criminal, soldier): con+2,int+1 or con+1,int+1,wis+1. Replaces race bonuses")
    p.add_argument("--languages", default=None, help="Extra languages")
    p.add_argument("--cantrips", default=None)
    p.add_argument("--spells", default=None)
    p.add_argument("--equipment", default=None, help="API indexes, e.g. longsword,chain-mail,shield")
    p.add_argument("--alignment", default="")
    p.set_defaults(fn=lambda a: rules_cmd.execute_new_character(a.campaign, a.id, a))

    p = character_cmd_parser("restore-slots", "Long rest: restore one level's slots, or all levels if --level omitted",
                             character_cmd.execute_restore_slots, "name", "level")
    p.add_argument("--level", type=int, choices=range(1, 10), default=None)

    # The visual stage: show, actor, scene, site, map, arena
    show_sub = group(subparsers, "show", "show_command", "Put story on the visual stage: scene, actors, narration, dialogue, choices")
    p = show_sub.add_parser("beat", parents=[camp], help="Read beat markup from stdin (or --file) and show it")
    p.add_argument("--file", default=None, help="Read the beat from this file instead of stdin")
    p.set_defaults(fn=bind(show_cmd.execute_beat, "campaign", "file"))

    actor_sub = group(subparsers, "actor", "actor_command", "Set how a character looks on the visual stage (LPC pixel art)")
    p = actor_sub.add_parser("set", parents=[camp], help="Set or change an actor's look: name= body= skin= eyes= preset= and items like robe:white")
    p.add_argument("actor_id")
    p.add_argument("tokens", nargs="*")
    p.add_argument("--change", action="store_true", help="Change a look that already exists (the story changed it)")
    p.set_defaults(fn=bind(actor_cmd.execute_set, "campaign", "actor_id", "tokens", "change"))
    p = actor_sub.add_parser("show", parents=[camp], help="Print an actor's look (its file, else the preset for its kind)")
    p.add_argument("actor_id")
    p.set_defaults(fn=bind(actor_cmd.execute_show, "campaign", "actor_id"))
    p = actor_sub.add_parser("preview", parents=[camp], help="Render front, side and portrait to a PNG you can look at")
    p.add_argument("actor_id")
    p.add_argument("--emotion", default=None)
    p.set_defaults(fn=bind(actor_cmd.execute_preview, "campaign", "actor_id", "emotion"))
    p = actor_sub.add_parser("options", help="List settings, item types, or the items of one type")
    p.add_argument("item_type", nargs="?", default=None)
    p.add_argument("--body", default=None, help="Only items that fit this body type")
    p.set_defaults(fn=bind(actor_cmd.execute_options, "item_type", "body"))

    scene_sub = group(subparsers, "scene", "scene_command", "Set how a location looks on the visual stage: template, wall, floor, mood, props")
    p = scene_sub.add_parser("set", parents=[camp], help="template= wall= floor= mood= shape= seed= size= <slot>=<prop|none> +<prop>@<zone> clear=add")
    p.add_argument("location")
    p.add_argument("tokens", nargs="*")
    p.add_argument("--change", action="store_true", help="Change a place that already has a look (the story changed it)")
    p.set_defaults(fn=bind(scene_cmd.execute_set, "campaign", "location", "tokens", "change"))
    p = scene_sub.add_parser("show", parents=[camp], help="Print a location's scene spec and what it resolves to")
    p.add_argument("location")
    p.set_defaults(fn=bind(scene_cmd.execute_show, "campaign", "location"))
    p = scene_sub.add_parser("options", help="List templates, walls, floors, props, moods, slots")
    p.add_argument("what", nargs="?", default=None)
    p.set_defaults(fn=bind(scene_cmd.execute_options, "what"))

    site_sub = group(subparsers, "site", "site_command", "Set a building or dungeon the party explores on the visual stage")
    p = site_sub.add_parser("set", parents=[camp], help="theme= size= danger= name= poi=<id>@<where>[:<icon>] ...")
    p.add_argument("site_id")
    p.add_argument("tokens", nargs="*")
    p.add_argument("--change", action="store_true", help="Add points of interest, or change name= or danger=")
    p.set_defaults(fn=bind(site_cmd.execute_set, "campaign", "site_id", "tokens", "change"))
    for name, text, fn in (("show", "Print a site's settings and points of interest", site_cmd.execute_show),
                           ("preview", "Render the whole layout (DM only) to a PNG you can look at", site_cmd.execute_preview)):
        p = site_sub.add_parser(name, parents=[camp], help=text)
        p.add_argument("site_id")
        p.set_defaults(fn=bind(fn, "campaign", "site_id"))
    site_sub.add_parser("options", help="List themes, depths and icons").set_defaults(fn=lambda a: site_cmd.execute_options())

    arena_sub = group(subparsers, "arena", "arena_command", "The board of the running fight: show or preview it")
    for name, text, fn in (("show", "Print the arena: size, light, props, items and where everyone stands", arena_cmd.execute_show),
                           ("preview", "Render the whole arena (DM only) to a PNG you can look at", arena_cmd.execute_preview)):
        p = arena_sub.add_parser(name, parents=[camp], help=text)
        p.add_argument("arena_id", nargs="?", default=None, help="Default: the arena of the running fight")
        p.set_defaults(fn=bind(fn, "campaign", "arena_id"))

    map_sub = group(subparsers, "map", "map_command", "Region and city maps on the visual stage: places, routes, reveals")
    p = map_sub.add_parser("place", parents=[camp], help="Add a place: name= icon= from= dir= travel= in= hidden=yes")
    p.add_argument("map_id")
    p.add_argument("place_id")
    p.add_argument("tokens", nargs="*")
    p.set_defaults(fn=bind(map_cmd.execute_place, "campaign", "map_id", "place_id", "tokens"))
    p = map_sub.add_parser("route", parents=[camp], help="Make a route between two places known: travel=")
    p.add_argument("map_id")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("tokens", nargs="*")
    p.set_defaults(fn=bind(map_cmd.execute_route, "campaign", "map_id", "a", "b", "tokens"))
    p = map_sub.add_parser("reveal", parents=[camp], help="Show a hidden place to the players")
    p.add_argument("map_id")
    p.add_argument("place_id")
    p.set_defaults(fn=bind(map_cmd.execute_reveal, "campaign", "map_id", "place_id"))
    p = map_sub.add_parser("show", parents=[camp], help="Print a map (or all maps), hidden places too")
    p.add_argument("map_id", nargs="?", default=None)
    p.set_defaults(fn=bind(map_cmd.execute_show, "campaign", "map_id"))
    map_sub.add_parser("options", help="Show the map command forms and icons").set_defaults(fn=lambda a: map_cmd.execute_options())

    # Session, world: clock, state fields, quests, NPCs, factions
    session_sub = group(subparsers, "session", "session_command", "Session helpers for the DM")
    session_sub.add_parser("brief", parents=[camp], help="Print state, party, players, canon, story bible and recent log in one go"
                           ).set_defaults(fn=bind(session_cmd.execute_brief, "campaign"))
    p = session_sub.add_parser("end", parents=[camp], help="Close the session in one step: recap on stdin, threads, clocks, log")
    p.add_argument("--appeared", default="", help="Thread ids that appeared in play, comma-separated")
    p.add_argument("--clock", action="append", default=[], help='"Villain/Clock=advance|action|warning" (default advance)')
    p.add_argument("--time", default=None, help="New game_time for state.json")
    p.add_argument("--force", action="store_true", help="Close even with report warnings")
    p.add_argument("--no-facts", action="store_true", help="Nothing canon-level happened this session")
    p.set_defaults(fn=lambda a: session_cmd.execute_end(a.campaign, a.appeared, a.clock, a.time, a.force, a.no_facts))

    state_sub = group(subparsers, "state", "state_command", "Game clock and state fields")
    p = state_sub.add_parser("time", parents=[camp], help='+2h, +1d, +30m advance the clock; "Day 3, 18:00" sets it')
    p.add_argument("value")
    p = state_sub.add_parser("set", parents=[camp], help="weather= party_status= active_player_turn= location= (_ is a space)")
    p.add_argument("tokens", nargs="+")
    for p in state_sub.choices.values():
        p.set_defaults(fn=with_args(world_cmd.execute_state))

    quest_sub = group(subparsers, "quest", "quest_command", "Quest files and the quest log")
    p = quest_sub.add_parser("add", parents=[camp], help='quest add <id> "<title>" [--description ..] [--objective ..]... [--reward ..]')
    p.add_argument("id")
    p.add_argument("title")
    p.add_argument("--description", default="")
    p.add_argument("--objective", action="append", default=[])
    p.add_argument("--reward", default="")
    p = quest_sub.add_parser("progress", parents=[camp], help='quest progress <id> "<text>"')
    p.add_argument("id")
    p.add_argument("text")
    p = quest_sub.add_parser("done", parents=[camp], help="quest done <id> [--objective N]: one objective, or the whole quest")
    p.add_argument("id")
    p.add_argument("--objective", type=int, default=None)
    p = quest_sub.add_parser("fail", parents=[camp], help="quest fail <id>")
    p.add_argument("id")
    quest_sub.add_parser("show", parents=[camp], help="One line per quest")
    for p in quest_sub.choices.values():
        p.set_defaults(fn=with_args(world_cmd.execute_quest))

    npc_sub = group(subparsers, "npc", "npc_command", "NPC files")
    p = npc_sub.add_parser("set", parents=[camp], help="npc set <id> key=value ... (new NPC needs name= and type=)")
    p.add_argument("id")
    p.add_argument("tokens", nargs="+")
    p = npc_sub.add_parser("note", parents=[camp], help='npc note <id> "<text>": adds "Session N: text" to notes')
    p.add_argument("id")
    p.add_argument("text")
    p = npc_sub.add_parser("attitude", parents=[camp], help="npc attitude <id> up|down|hostile|unfriendly|neutral|friendly|allied")
    p.add_argument("id")
    p.add_argument("move")
    for p in npc_sub.choices.values():
        p.set_defaults(fn=with_args(world_cmd.execute_npc))

    p = subparsers.add_parser("faction", parents=[camp], help="faction <name> +N|-N: change reputation (no change: show it)")
    p.add_argument("name")
    p.add_argument("delta", nargs="?", default=None)
    p.set_defaults(fn=with_args(world_cmd.execute_faction))

    # Rules: encounters, attacks, saves, checks, rests
    def rolls(p):
        p.add_argument("--adv", action="store_true", help="Advantage")
        p.add_argument("--dis", action="store_true", help="Disadvantage")
        p.add_argument("--secret", action="store_true", help="Do not show the roll on the stage")

    enc_sub = group(subparsers, "encounter", "encounter_command", "Combat tracker: initiative, HP, conditions, turns, XP")
    p = enc_sub.add_parser("start", parents=[camp], help="Roll initiative: goblin:3 boss=bugbear <npc-id> ... [--pcs all|a,b]")
    p.add_argument("specs", nargs="*")
    p.add_argument("--pcs", default=None)
    p.add_argument("--arena", nargs="*", default=None, metavar="KEY=VALUE",
                   help="Board options (a board is the default): layout= size= light= ambush= seed= theme= feature=<thing>@<where> hazard=<kind>@<where>. Put it last.")
    p.add_argument("--no-arena", action="store_true", help="No board: a short fight the DM runs in words")
    p = enc_sub.add_parser("add", parents=[camp], help="Add creatures to the running combat")
    p.add_argument("specs", nargs="+")
    enc_sub.add_parser("next", parents=[camp], help="next turn")
    enc_sub.add_parser("status", parents=[camp], help="Show the order, HP and conditions")
    p = enc_sub.add_parser("move", parents=[camp], help="Walk a creature on the board: --to X,Y or --toward <id>")
    p.add_argument("who")
    p.add_argument("--to", default=None, metavar="X,Y")
    p.add_argument("--toward", default=None, metavar="ID")
    for name in ("damage", "heal"):
        p = enc_sub.add_parser(name, parents=[camp], help=f"{name.title()} a combatant (PC or creature)")
        p.add_argument("target")
        p.add_argument("amount", help="A number, or dice such as 1d8+3")
        if name == "damage":
            p.add_argument("--type", default=None, help="Damage type (resistances apply)")
    p = enc_sub.add_parser("condition", parents=[camp], help="add|remove a condition: [--rounds N] [--save con:13]")
    p.add_argument("target")
    p.add_argument("op", choices=["add", "remove"])
    p.add_argument("name")
    p.add_argument("--rounds", type=int, default=None)
    p.add_argument("--save", default=None)
    p = enc_sub.add_parser("use", parents=[camp], help="Mark an action, bonus action or reaction used (or --free to give it back)")
    p.add_argument("target")
    p.add_argument("kind", choices=["action", "bonus", "reaction"])
    p.add_argument("--free", action="store_true")
    p = enc_sub.add_parser("end", parents=[camp], help="End combat: split XP of defeated foes, clear the tracker")
    p.add_argument("--no-xp", action="store_true")
    p.add_argument("--resolved", nargs="+", default=[], metavar="ID", help="creatures that fled, yielded or were talked down: they give XP too")
    for p in enc_sub.choices.values():
        p.set_defaults(fn=lambda a: rules_cmd.execute_encounter(a.campaign, a.encounter_command, a))

    p = subparsers.add_parser("attack", parents=[camp], help="Attack roll vs AC, damage on a hit, applied to the target")
    p.add_argument("attacker")
    p.add_argument("weapon", help="Weapon or action name (or 'spell' with --damage)")
    p.add_argument("target")
    p.add_argument("--damage", default=None, help="Damage dice, e.g. 1d10 (spells, improvised)")
    p.add_argument("--type", default=None, help="Damage type for --damage")
    p.add_argument("--bonus", type=int, default=0, help="Extra to-hit bonus (bless, cover as negative)")
    p.add_argument("--cost", default="action", choices=["action", "bonus", "reaction", "free"],
                   help="What the attack uses on the turn tracker (default action; free for an extra attack of one action)")
    p.add_argument("--smite", type=int, default=None, choices=range(1, 10), metavar="SLOT",
                   help="Paladin: on a melee hit, spend a spell slot of this level for Divine Smite")
    rolls(p)
    p.set_defaults(fn=with_args(rules_cmd.execute_attack))

    p = subparsers.add_parser("save", parents=[camp], help="Saving throws: <targets...> <ability> --dc N [--damage 8d6 --half] or --from creature:action")
    p.add_argument("targets", nargs="+")
    p.add_argument("--ability", default=None)
    p.add_argument("--dc", type=int, default=None)
    p.add_argument("--damage", default=None)
    p.add_argument("--type", default=None)
    p.add_argument("--half", action="store_true", help="Half damage on a success")
    p.add_argument("--from", dest="source", default=None, help="creature:action with a DC, e.g. dragon:fire-breath")
    p.add_argument("--hide-dc", action="store_true", help="Do not show the DC on the stage")
    rolls(p)
    p.set_defaults(fn=with_args(rules_cmd.execute_save))

    p = subparsers.add_parser("check", parents=[camp], help="Skill/ability check or death save: <who...|all> <skill|ability|death> [--dc N]")
    p.add_argument("who", nargs="+")
    p.add_argument("--dc", type=int, default=None)
    p.add_argument("--passive", action="store_true")
    p.add_argument("--hide-dc", action="store_true", help="Do not show the DC on the stage")
    rolls(p)
    p.set_defaults(fn=with_args(rules_cmd.execute_check))

    p = subparsers.add_parser("effect", parents=[camp], help="Bonuses and advantage on a character: add|remove <who> <effect>, list [<who>]")
    p.add_argument("op", choices=["add", "remove", "list"])
    p.add_argument("who", nargs="?")
    p.add_argument("name", nargs="?", help="guidance, bless, bane, bardic-inspiration, resistance, advantage, disadvantage")
    p.set_defaults(fn=bind(rules_cmd.execute_effect, "campaign", "op", "who", "name"))

    p = subparsers.add_parser("rest", parents=[camp], help="long|short rest for the party or named characters")
    p.add_argument("kind", choices=["long", "short"])
    p.add_argument("who", nargs="*")
    p.add_argument("--hit-dice", action="append", default=[], help="Short rest: name:N hit dice to spend")
    p.set_defaults(fn=lambda a: rules_cmd.execute_rest(a.campaign, a.kind, a.who, a.hit_dice))

    # Loot: the engine rolls, the DM decides (give an item with `character item add`)
    loot_sub = group(subparsers, "loot", "loot_command", "Treasure: roll coins and items by challenge rating")
    p = loot_sub.add_parser("roll", help="roll --cr N [--kind individual|hoard] [--seed N] [--type beast]: the same seed gives the same list")
    p.add_argument("--cr", type=float, required=True)
    p.add_argument("--kind", choices=["individual", "hoard"], default="individual")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--type", default="", help="creature type: a beast, an ooze or a plant carries nothing")
    p.set_defaults(fn=bind(rules_cmd.execute_loot_roll, "cr", "kind", "seed", "type"))

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

    try:
        return args.fn(args)
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
