"""Search command - semantic filtering"""

import sys
from typing import List, Dict, Any, Optional
from dnd_api.api import api_list


def parse_range(value: str) -> tuple[Optional[float], Optional[float]]:
    """Parse a range string like '5-7' or '3+' or '5'"""
    if '+' in value:
        min_val = float(value.replace('+', ''))
        return min_val, None
    elif '-' in value:
        parts = value.split('-')
        return float(parts[0]), float(parts[1])
    else:
        val = float(value)
        return val, val


def filter_monsters(results: List[dict], filters: dict) -> List[dict]:
    """Filter monster list by criteria"""
    filtered = results

    # CR filter
    if 'cr' in filters:
        min_cr, max_cr = parse_range(filters['cr'])
        filtered = [
            m for m in filtered
            # Note: API list doesn't include CR, would need to fetch each
            # For now, we'll skip this filter in list view
        ]

    # Type filter
    if 'type' in filters:
        target_type = filters['type'].lower()
        # Would need full monster data for this
        pass

    return filtered


def filter_spells(results: List[dict], filters: dict) -> List[dict]:
    """Filter spell list by criteria"""
    filtered = results

    # Level filter
    if 'level' in filters:
        level_str = filters['level']
        if level_str.lower() == 'cantrip':
            min_level, max_level = 0, 0
        else:
            min_level, max_level = parse_range(level_str)

        # Would need full spell data for accurate filtering
        pass

    return filtered


def filter_equipment(results: List[dict], filters: dict) -> List[dict]:
    """Filter equipment list by criteria"""
    filtered = results

    # Category filter
    if 'category' in filters:
        target_cat = filters['category'].lower()
        # Would need full equipment data
        pass

    return filtered


FILTERS = {
    "monsters": filter_monsters,
    "spells": filter_spells,
    "equipment": filter_equipment,
}


def execute(resource: str, filters: dict) -> int:
    """Execute search command"""
    data, error, was_cached = api_list(resource)

    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if not data:
        print(f"No data returned for {resource}", file=sys.stderr)
        return 1

    results = data.get("results", [])

    # Apply filters
    filter_func = FILTERS.get(resource)
    if filter_func:
        filtered = filter_func(results, filters)
    else:
        filtered = results

    # Apply name filter if present
    if 'name' in filters:
        query = filters['name'].lower()
        filtered = [r for r in filtered if query in r.get('name', '').lower()]

    # Display results
    print(f"Found {len(filtered)} {resource} matching filters:")
    print()

    # Build filter description
    filter_desc = ", ".join(f"{k}={v}" for k, v in filters.items())
    if filter_desc:
        print(f"Filters: {filter_desc}")
        print()

    for item in filtered[:20]:  # Limit display
        name = item.get("name", "Unknown")
        index = item.get("index", "unknown")
        print(f"- {name} ({index})")

    if len(filtered) > 20:
        print(f"... and {len(filtered) - 20} more")

    print()
    print(f"Use: dnd-api get {resource}/<index> for full details")

    return 0
