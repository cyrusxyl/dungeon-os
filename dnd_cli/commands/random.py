"""Random command - random selection from resources"""

import sys
import random
from dnd_cli.api import api_list


def execute(resource: str, filters: dict, count: int = 1) -> int:
    """Execute random command"""
    data, error, was_cached = api_list(resource)

    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if not data:
        print(f"No data returned for {resource}", file=sys.stderr)
        return 1

    results = data.get("results", [])

    if not results:
        print(f"No {resource} available", file=sys.stderr)
        return 1

    # For now, simple random selection from list
    # TODO: Apply filters before selection
    selected = random.sample(results, min(count, len(results)))

    # Display results
    resource_name = resource.replace("-", " ").title()
    print(f"Random {resource_name} (count={count}):")
    print()

    for i, item in enumerate(selected, 1):
        name = item.get("name", "Unknown")
        index = item.get("index", "unknown")
        print(f"{i}. {name}")
        print(f"   Index: {index}")
        print()

    print(f"Use: dnd-cli get {resource}/<index> for full details")

    return 0
