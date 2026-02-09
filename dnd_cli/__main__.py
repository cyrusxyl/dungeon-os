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

    return parser


def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "list":
            return cmd_list.execute(args.resource)

        elif args.command == "get":
            return cmd_get.execute(args.endpoint, args.json)

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
