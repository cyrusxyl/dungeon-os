"""Claude Code hook: tell the stage what state the DM is in.

Registered in game/.claude/settings.json for UserPromptSubmit, Stop and
Notification. The stage server sets DUNGEON_STAGE_LOG for the DM process;
hooks inherit it. Without it (a plain `claude` session in game/, or the
classic terminal view) this script is never even started, because the hook
command checks the variable in the shell first.

Standard library only, and no import of the stage package: it runs on every
turn and must finish in milliseconds.
"""

import json
import os
import sys


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
    else:
        return

    with open(log, "a") as f:
        f.write(json.dumps(event) + "\n")


if __name__ == "__main__":
    main()
