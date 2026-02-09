"""List command - browse available resources"""

import sys
from dnd_cli.api import api_list


def format_monster_entry(monster: dict) -> str:
    """Format a single monster entry"""
    name = monster.get("name", "Unknown")
    index = monster.get("index", "unknown")
    return f"- {name}"


def format_spell_entry(spell: dict) -> str:
    """Format a single spell entry"""
    name = spell.get("name", "Unknown")
    index = spell.get("index", "unknown")
    return f"- {name}"


def format_equipment_entry(item: dict) -> str:
    """Format a single equipment entry"""
    name = item.get("name", "Unknown")
    index = item.get("index", "unknown")
    return f"- {name}"


def format_generic_entry(item: dict) -> str:
    """Format a generic resource entry"""
    name = item.get("name", "Unknown")
    return f"- {name}"


FORMATTERS = {
    "monsters": format_monster_entry,
    "spells": format_spell_entry,
    "equipment": format_equipment_entry,
}


def execute(resource: str) -> int:
    """Execute list command"""
    data, error, was_cached = api_list(resource)

    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if not data:
        print(f"No data returned for {resource}", file=sys.stderr)
        return 1

    # Get results list
    results = data.get("results", [])
    count = data.get("count", len(results))

    # Print header
    resource_name = resource.replace("-", " ").title()
    print(f"{resource_name} ({count} total):")
    print()

    # Get formatter
    formatter = FORMATTERS.get(resource, format_generic_entry)

    # Print entries (limit to 50 for readability)
    display_count = min(50, len(results))
    for item in results[:display_count]:
        print(formatter(item))

    if len(results) > display_count:
        print(f"... and {len(results) - display_count} more")

    # Print usage hints
    print()
    print(f"Use: dnd-cli get {resource}/<index> for details")
    print(f"Use: dnd-cli search {resource} [--filters] to filter")

    if was_cached:
        print(f"[Cached results]")

    return 0
