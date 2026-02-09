"""Cache management for D&D API data"""

import json
from pathlib import Path
from typing import Optional
from datetime import datetime


def get_cache_root() -> Path:
    """Get the cache root directory for current campaign"""
    # Look for .campaign file in current directory or parents
    current = Path.cwd()
    while current != current.parent:
        campaign_file = current / ".campaign"
        if campaign_file.exists():
            cache_dir = current / ".cache" / "api" / "2014"
            cache_dir.mkdir(parents=True, exist_ok=True)
            return cache_dir
        current = current.parent

    # Fallback to current directory
    cache_dir = Path.cwd() / ".cache" / "api" / "2014"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_cache_path(endpoint: str) -> Path:
    """Get cache file path for an API endpoint"""
    cache_root = get_cache_root()
    # Remove leading slash and .json if present
    endpoint = endpoint.lstrip("/").replace(".json", "")
    return cache_root / f"{endpoint}.json"


def load_cache(endpoint: str) -> Optional[dict]:
    """Load cached data for an endpoint"""
    cache_path = get_cache_path(endpoint)
    if not cache_path.exists():
        return None

    try:
        with open(cache_path, 'r') as f:
            data = json.load(f)
            return data
    except (json.JSONDecodeError, IOError):
        return None


def save_cache(endpoint: str, data: dict) -> None:
    """Save data to cache"""
    cache_path = get_cache_path(endpoint)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    # Add metadata
    cache_data = {
        "cached_at": datetime.now().isoformat(),
        "endpoint": endpoint,
        "data": data
    }

    with open(cache_path, 'w') as f:
        json.dump(cache_data, f, indent=2)


def clear_cache(resource: Optional[str] = None) -> int:
    """Clear cache files. Returns count of files removed."""
    cache_root = get_cache_root()

    if resource:
        # Clear specific resource
        resource_dir = cache_root / resource
        if not resource_dir.exists():
            return 0

        count = 0
        for cache_file in resource_dir.glob("*.json"):
            cache_file.unlink()
            count += 1
        return count
    else:
        # Clear all cache
        count = 0
        for cache_file in cache_root.rglob("*.json"):
            if cache_file.name != ".gitkeep":
                cache_file.unlink()
                count += 1
        return count


def get_cache_info() -> dict:
    """Get cache statistics"""
    cache_root = get_cache_root()

    resources = {}
    total_size = 0
    total_files = 0

    for cache_file in cache_root.rglob("*.json"):
        if cache_file.name == ".gitkeep":
            continue

        # Get resource type from path
        relative = cache_file.relative_to(cache_root)
        resource = str(relative.parts[0]) if relative.parts else "unknown"

        size = cache_file.stat().st_size
        total_size += size
        total_files += 1

        if resource not in resources:
            resources[resource] = {"files": 0, "size": 0}
        resources[resource]["files"] += 1
        resources[resource]["size"] += size

    return {
        "cache_root": str(cache_root),
        "total_files": total_files,
        "total_size": total_size,
        "resources": resources
    }
