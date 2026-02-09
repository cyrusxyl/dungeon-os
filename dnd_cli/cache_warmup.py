"""Cache warmup utilities for pre-fetching full resource data"""

from dnd_cli.api import api_list, api_get
from dnd_cli.cache import load_cache
from typing import Optional


def warmup_cache(resource: str, force: bool = False) -> tuple[int, int]:
    """
    Pre-fetch and cache all items for a resource.

    Args:
        resource: Resource type (monsters, spells, equipment, etc.)
        force: If True, re-fetch even if cached

    Returns: (cached_count, error_count)
    """
    # Get list of all items
    list_data, error, _ = api_list(resource)
    if error:
        print(f"Error fetching {resource} list: {error}")
        return 0, 1

    results = list_data.get('results', [])
    print(f"Warming up {resource} cache ({len(results)} items)...")

    cached_count = 0
    error_count = 0

    for i, item in enumerate(results):
        index = item['index']
        endpoint = f"{resource}/{index}"

        # Skip if already cached (unless force)
        if not force and load_cache(endpoint):
            cached_count += 1
            continue

        # Fetch and cache
        data, error, _ = api_get(endpoint, use_cache=not force)
        if error:
            print(f"  ✗ Error fetching {index}: {error}")
            error_count += 1
        else:
            cached_count += 1

        # Progress indicator
        if (i + 1) % 10 == 0:
            print(f"  Progress: {i + 1}/{len(results)} ({cached_count} cached, {error_count} errors)")

    print(f"✓ {resource} cache ready: {cached_count} cached, {error_count} errors")
    return cached_count, error_count


def warmup_all_resources(force: bool = False):
    """Warmup cache for all common resources"""
    resources = ['monsters', 'spells', 'equipment', 'magic-items',
                 'classes', 'races', 'feats', 'conditions']

    total_cached = 0
    total_errors = 0

    for resource in resources:
        cached, errors = warmup_cache(resource, force)
        total_cached += cached
        total_errors += errors

    print(f"\n✓ All resources cached: {total_cached} total, {total_errors} errors")
