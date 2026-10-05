"""Claude Code hook: tell the stage what state the DM is in.

Registered in game/.claude/settings.json for UserPromptSubmit, Stop,
Notification, PostToolUse on Bash (dice rolls), and PreToolUse on
Bash, Write, Edit and Skill (dm_activity: what the DM does, for the
filler screen while a world is built). The stage server sets
DUNGEON_STAGE_LOG for the DM process; hooks inherit it. Without it (a plain `claude` session in game/, or the
classic terminal view) this script is never even started, because the hook
command checks the variable in the shell first.

Standard library only, and no import of the stage package: it runs on every
turn and must finish in milliseconds.
"""

import json
import os
import re
import sys

ROLL_CMD = re.compile(r"uv run roll\s+(\S+)")
# What the DM does, as the player reads it: (pattern, label). First match wins.
SKILLS = {
    "worldbuilding": "Studying the art of worldbuilding",
    "stage": "Rehearsing the stagecraft",
    "character-creation": "Opening the rulebooks",
}
# Matched against the words after `dnd-cli`. `show beat` and `uv run roll` are not here: the players see them.
CLI_LABELS = (
    (r"session brief", "Reading the campaign notes"),
    (r"session end", "Writing the session record"),
    (r"canon add-villain", "Casting the villains"),
    (r"canon add-clock", "Winding the villain clocks"),
    (r"canon (add-|touch-)", "Pinning down the facts"),
    (r"scene set", "Painting the scene"),
    (r"map (place|route|reveal)", "Drawing the map"),
    (r"actor set", "Dressing the cast"),
    (r"site set", "Digging the dungeon"),
    (r"character new", "Rolling up the party"),
    (r"character level-up", "Levelling the party"),
    (r"character show", "Reading the character sheets"),
    (r"(quest|npc|faction)\b", "Weaving the plot threads"),
    (r"(encounter|attack|save|check|rest)\b", "Checking the rules"),
    (r"(get|search|list|info)\b", "Looking up the rules"),
)
ROLL_DICE = re.compile(r"^Rolled: (\S+): \[([^\]]*)\]")


def roll_event(data: dict) -> dict | None:
    """A dice roll for the stage's dice overlay, from `uv run roll` output.

    A command that ends with the shell comment `# secret` is a roll behind
    the DM screen: it never reaches the stage.
    """
    command = (data.get("tool_input") or {}).get("command", "")
    match = ROLL_CMD.search(command)
    if not match or re.search(r"#\s*secret\b", command):
        return None
    out = data.get("tool_response", data.get("tool_output", ""))
    if isinstance(out, dict):
        out = out.get("stdout", "")
    lines = [line.strip() for line in str(out).splitlines() if line.strip()]
    totals = [int(line) for line in lines if re.fullmatch(r"-?\d+", line)]
    if not totals:
        return None
    dice = []
    for line in lines:
        m = ROLL_DICE.match(line)
        if m:
            dice.append({"die": m.group(1), "faces": [int(x) for x in m.group(2).split(",") if x.strip()]})
    return {"type": "roll", "expr": match.group(1), "total": totals[-1], "dice": dice}


def activity_label(tool_name: str, tool_input: dict) -> str | None:
    """A short line for what the DM is doing, or None for a call the players need not hear about."""
    tool_input = tool_input or {}
    if tool_name == "Skill":
        return SKILLS.get(str(tool_input.get("skill", "")))
    if tool_name in ("Write", "Edit"):
        path = str(tool_input.get("file_path", ""))
        if "campaigns/" not in path:
            return None
        return "Writing the story bible" if path.endswith("dm_story.md") else "Writing the lore"
    if tool_name == "Bash":
        match = re.search(r"dnd-cli\s+(\S+(?:\s+\S+)?)", str(tool_input.get("command", "")))
        for pattern, label in CLI_LABELS:
            if match and re.match(pattern, match.group(1)):
                return label
    return None


def main() -> None:
    log = os.environ.get("DUNGEON_STAGE_LOG")
    if not log:
        return
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}

    name = data.get("hook_event_name")
    if name == "UserPromptSubmit":
        event = {"type": "dm_status", "status": "busy"}
    elif name == "Stop":
        event = {"type": "dm_status", "status": "idle"}
        text = (data.get("last_assistant_message") or "").strip()
        if text:
            # Not story: stray DM text goes to the DM log, never the dialogue box.
            event["dm_text"] = text
    elif name == "Notification":
        kind = data.get("notification_type", "")
        if kind == "idle_prompt":
            return
        event = {"type": "dm_status", "status": "waiting", "reason": kind, "message": data.get("message", "")}
    elif name == "PreToolUse":
        label = activity_label(data.get("tool_name", ""), data.get("tool_input"))
        if label is None:
            return
        event = {"type": "dm_activity", "text": label}
    elif name == "PostToolUse":
        event = roll_event(data)
        if event is None:
            return
    else:
        return

    with open(log, "a") as f:
        f.write(json.dumps(event) + "\n")


if __name__ == "__main__":
    main()
