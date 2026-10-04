"""Get command - fetch specific resource"""

import sys
import json
from dnd_cli.api import api_get


def execute(endpoint: str, json_output: bool = False, fields: str | None = None) -> int:
    """Execute get command.

    Default output is short, to keep the DM's context small: a list endpoint
    prints one "- Name (index)" line per entry, and `--fields a,b` keeps only
    those top-level keys. `--json` prints the raw response.
    """
    data, error, was_cached = api_get(endpoint)

    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if not data:
        print(f"No data returned for {endpoint}", file=sys.stderr)
        return 1

    if json_output:
        print(json.dumps(data, indent=2))
    elif fields:
        keys = [k.strip() for k in fields.split(",") if k.strip()]
        missing = [k for k in keys if k not in data]
        if missing:
            print(f"Warning: no field {', '.join(missing)}. Fields: {', '.join(data)}", file=sys.stderr)
        print(json.dumps({k: data[k] for k in keys if k in data}, separators=(",", ":")))
    elif isinstance(data.get("results"), list):
        for item in data["results"]:
            print(f"- {item.get('name')} ({item.get('index')})")
    else:
        print(json.dumps(data, separators=(",", ":")))

    return 0
