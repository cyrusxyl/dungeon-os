"""Info command - quick reference lookup"""

import sys
from dnd_api.api import api_get


def format_condition(data: dict) -> str:
    """Format condition info for display"""
    name = data.get("name", "Unknown")
    desc = data.get("desc", [])

    output = [f"{name.upper()}", ""]

    if desc:
        output.append("Effects:")
        for line in desc:
            output.append(f"- {line}")

    return "\n".join(output)


def format_skill(data: dict) -> str:
    """Format skill info for display"""
    name = data.get("name", "Unknown")
    desc = data.get("desc", [])
    ability = data.get("ability_score", {}).get("name", "Unknown")

    output = [f"{name.upper()}", ""]
    output.append(f"Ability: {ability}")
    output.append("")

    if desc:
        output.append("Description:")
        for line in desc:
            output.append(f"- {line}")

    return "\n".join(output)


def format_damage_type(data: dict) -> str:
    """Format damage type info"""
    name = data.get("name", "Unknown")
    desc = data.get("desc", [])

    output = [f"{name.upper()} DAMAGE", ""]

    if desc:
        for line in desc:
            output.append(line)

    return "\n".join(output)


FORMATTERS = {
    "conditions": format_condition,
    "skills": format_skill,
    "damage-types": format_damage_type,
}


def execute(resource: str, index: str) -> int:
    """Execute info command"""
    endpoint = f"{resource}/{index}"
    data, error, was_cached = api_get(endpoint)

    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if not data:
        print(f"No data returned for {endpoint}", file=sys.stderr)
        return 1

    # Get formatter or use generic
    formatter = FORMATTERS.get(resource)
    if formatter:
        print(formatter(data))
    else:
        # Generic display
        name = data.get("name", "Unknown")
        desc = data.get("desc", [])

        print(f"{name.upper()}")
        print()
        if desc:
            for line in desc:
                print(line)

    return 0
