"""List command - browse available resources"""

import sys
from dnd_cli.api import api_list


def format_entry(item: dict) -> str:
    """One resource: its name, and the index that `dnd-cli get <resource>/<index>` takes."""
    return f"- {item.get('name', 'Unknown')} ({item.get('index', 'unknown')})"


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

    # Print entries (limit to 50 for readability)
    display_count = min(50, len(results))
    for item in results[:display_count]:
        print(format_entry(item))

    if len(results) > display_count:
        print(f"... and {len(results) - display_count} more")

    # Print usage hints
    print()
    print(f"Use: dnd-cli get {resource}/<index> for details")
    print(f"Use: dnd-cli search {resource} [--filters] to filter")


    return 0
