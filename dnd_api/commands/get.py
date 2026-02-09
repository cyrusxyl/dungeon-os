"""Get command - fetch specific resource"""

import sys
import json
from dnd_api.api import api_get


def execute(endpoint: str, json_output: bool = False) -> int:
    """Execute get command"""
    data, error, was_cached = api_get(endpoint)

    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if not data:
        print(f"No data returned for {endpoint}", file=sys.stderr)
        return 1

    if json_output:
        # Raw JSON output
        print(json.dumps(data, indent=2))
    else:
        # Formatted output with metadata
        output = {
            "data": data,
            "metadata": {
                "endpoint": endpoint,
                "cached": was_cached
            }
        }
        print(json.dumps(output, indent=2))

    return 0
