"""D&D 5e API wrapper with error handling"""

import json
import subprocess
from typing import Optional, Tuple
from dnd_cli import API_BASE
from dnd_cli.cache import load_cache, save_cache


def safe_api_call(endpoint: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    Make an API call with error handling.

    Returns: (data, error)
    - If successful: (data, None)
    - If failed: (None, error_message)
    """
    try:
        result = subprocess.run(
            ["curl", "-sL", f"{API_BASE}/{endpoint}"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return None, f"API call failed: {result.stderr}"

        data = json.loads(result.stdout)
        return data, None

    except subprocess.TimeoutExpired:
        return None, "API request timed out (10s limit)"
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON response: {e}"
    except Exception as e:
        return None, f"Unexpected error: {e}"


def api_get(endpoint: str, use_cache: bool = True) -> Tuple[Optional[dict], Optional[str], bool]:
    """
    Get a resource from the API (with caching).

    Returns: (data, error, was_cached)
    """
    endpoint = endpoint.lstrip("/")

    # Try cache first
    if use_cache:
        cached = load_cache(endpoint)
        if cached:
            return cached.get("data"), None, True

    # Fetch from API
    data, error = safe_api_call(endpoint)
    if error:
        return None, error, False

    # Save to cache
    if use_cache and data:
        save_cache(endpoint, data)

    return data, None, False


def api_list(resource: str, use_cache: bool = True) -> Tuple[Optional[dict], Optional[str], bool]:
    """
    List all resources of a type.

    Returns: (data, error, was_cached)
    """
    endpoint = f"{resource}/_index"

    # Try cache first
    if use_cache:
        cached = load_cache(endpoint)
        if cached:
            return cached.get("data"), None, True

    # Fetch from API (list endpoint)
    data, error = safe_api_call(resource)
    if error:
        return None, error, False

    # Save to cache with special _index name
    if use_cache and data:
        save_cache(endpoint, data)

    return data, None, False
