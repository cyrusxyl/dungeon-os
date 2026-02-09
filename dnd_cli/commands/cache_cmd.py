"""Cache management commands"""

import sys
from dnd_cli.cache import clear_cache, get_cache_info


def execute_clear(resource: str = None) -> int:
    """Execute cache clear command"""
    count = clear_cache(resource)

    if resource:
        print(f"Cleared {count} cached files for {resource}")
    else:
        print(f"Cleared {count} cached files")

    return 0


def execute_info() -> int:
    """Execute cache info command"""
    info = get_cache_info()

    print(f"Cache Location: {info['cache_root']}")
    print(f"Total Files: {info['total_files']}")
    print(f"Total Size: {info['total_size']:,} bytes")
    print()

    if info['resources']:
        print("Resources:")
        for resource, stats in sorted(info['resources'].items()):
            print(f"  {resource}:")
            print(f"    Files: {stats['files']}")
            print(f"    Size: {stats['size']:,} bytes")

    return 0
