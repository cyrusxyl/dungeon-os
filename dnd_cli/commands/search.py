"""Search command - fuzzy matching + filters + text search"""

import sys
from typing import List, Dict, Optional
from dnd_cli.api import api_list
from dnd_cli.cache import load_cache
from dnd_cli.fuzzy import fuzzy_match_multi_algorithm
from dnd_cli.text_search import text_search


def parse_range(value: str) -> tuple[Optional[float], Optional[float]]:
    """Parse range string: '5-7', '3+', or '5'"""
    if '+' in value:
        min_val = float(value.replace('+', ''))
        return min_val, None
    elif '-' in value:
        parts = value.split('-')
        return float(parts[0]), float(parts[1])
    else:
        val = float(value)
        return val, val


def load_full_resources(resource: str, index_list: List[dict]) -> List[dict]:
    """Load full resource data from cache for all items in index list"""
    full_resources = []

    for item in index_list:
        endpoint = f"{resource}/{item['index']}"
        cached = load_cache(endpoint)

        if cached:
            full_resources.append(cached['data'])
        # Skip if not in cache (warmup needed)

    return full_resources


def filter_monsters(monsters: List[dict], filters: Dict) -> List[dict]:
    """Apply monster-specific filters"""
    filtered = monsters

    # CR filter
    if 'cr' in filters:
        min_cr, max_cr = parse_range(filters['cr'])
        filtered = [
            m for m in filtered
            if (min_cr is None or m.get('challenge_rating', 0) >= min_cr)
            and (max_cr is None or m.get('challenge_rating', 0) <= max_cr)
        ]

    # Type filter
    if 'type' in filters:
        target_type = filters['type'].lower()
        filtered = [
            m for m in filtered
            if m.get('type', '').lower() == target_type
        ]

    # Size filter
    if 'size' in filters:
        target_size = filters['size'].lower()
        filtered = [
            m for m in filtered
            if m.get('size', '').lower() == target_size
        ]

    return filtered


def filter_spells(spells: List[dict], filters: Dict) -> List[dict]:
    """Apply spell-specific filters"""
    filtered = spells

    # Level filter
    if 'level' in filters:
        level_str = filters['level']
        if level_str.lower() == 'cantrip':
            min_level, max_level = 0, 0
        else:
            min_level, max_level = parse_range(level_str)

        filtered = [
            s for s in filtered
            if (min_level is None or s.get('level', 0) >= min_level)
            and (max_level is None or s.get('level', 0) <= max_level)
        ]

    # School filter
    if 'school' in filters:
        target_school = filters['school'].lower()
        filtered = [
            s for s in filtered
            if s.get('school', {}).get('name', '').lower() == target_school
        ]

    # Class filter
    if 'class' in filters:
        target_class = filters['class'].lower()
        filtered = [
            s for s in filtered
            if any(c.get('name', '').lower() == target_class
                   for c in s.get('classes', []))
        ]

    return filtered


def filter_equipment(equipment: List[dict], filters: Dict) -> List[dict]:
    """Apply equipment-specific filters"""
    filtered = equipment

    # Category filter
    if 'category' in filters:
        target_category = filters['category'].lower()
        filtered = [
            e for e in filtered
            if e.get('equipment_category', {}).get('name', '').lower() == target_category
        ]

    return filtered


def execute(resource: str, filters: dict) -> int:
    """Execute search command with fuzzy + filters + text"""

    # Get index list
    data, error, was_cached = api_list(resource)
    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    index_list = data.get('results', [])

    # Load full cached data
    full_resources = load_full_resources(resource, index_list)

    if not full_resources:
        print(f"No cached data for {resource}. Run: dnd-cli warmup {resource}",
              file=sys.stderr)
        return 1

    # Stage 1: Apply structured filters
    filtered = full_resources

    if resource == 'monsters':
        filtered = filter_monsters(filtered, filters)
    elif resource == 'spells':
        filtered = filter_spells(filtered, filters)
    elif resource == 'equipment':
        filtered = filter_equipment(filtered, filters)

    # Stage 2: Apply name filter (fuzzy or exact)
    if 'name' in filters:
        query = filters['name']

        # Try fuzzy matching
        fuzzy_matches = fuzzy_match_multi_algorithm(query, filtered, threshold=60)

        if fuzzy_matches:
            # Sort by score and extract resources
            filtered = [resource for resource, score in fuzzy_matches]

    # Stage 3: Apply text search
    if 'text' in filters:
        query = filters['text']
        filtered = text_search(query, filtered, resource)

    # Display results
    if not filtered:
        print(f"No {resource} found matching filters")
        return 0

    # Build filter description
    filter_desc = []
    if 'cr' in filters:
        filter_desc.append(f"CR {filters['cr']}")
    if 'type' in filters:
        filter_desc.append(f"type={filters['type']}")
    if 'size' in filters:
        filter_desc.append(f"size={filters['size']}")
    if 'level' in filters:
        filter_desc.append(f"level {filters['level']}")
    if 'school' in filters:
        filter_desc.append(f"school={filters['school']}")
    if 'name' in filters:
        filter_desc.append(f"name~'{filters['name']}'")
    if 'text' in filters:
        filter_desc.append(f"text:'{filters['text']}'")

    print(f"Found {len(filtered)} {resource}:")
    if filter_desc:
        print(f"Filters: {', '.join(filter_desc)}")
    print()

    # Display results (limit to 20)
    for i, item in enumerate(filtered[:20], 1):
        name = item.get('name', 'Unknown')

        # Add relevant details
        details = []
        if resource == 'monsters':
            cr = item.get('challenge_rating', '?')
            type_name = item.get('type', '?')
            details.append(f"CR {cr}, {type_name}")
        elif resource == 'spells':
            level = item.get('level', '?')
            school = item.get('school', {}).get('name', '?')
            level_str = "Cantrip" if level == 0 else f"Level {level}"
            details.append(f"{level_str}, {school}")
        elif resource == 'equipment':
            category = item.get('equipment_category', {}).get('name', '?')
            details.append(category)

        detail_str = f" ({', '.join(details)})" if details else ""
        print(f"{i}. {name}{detail_str}")

    if len(filtered) > 20:
        print(f"\n... and {len(filtered) - 20} more")

    print()
    print(f"Use: dnd-cli get {resource}/<index> for full details")

    return 0
