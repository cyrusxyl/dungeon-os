"""The current stage, derived from the event log.

`apply` is a pure function: state in, event in, new state out. The server
folds every event of `stage/events.ndjson` through it, so a browser that
reconnects gets one snapshot of "what is on the stage now" instead of a
replay of the whole log.
"""

from __future__ import annotations


LOG_LIMIT = 60
DM_LOG_LIMIT = 30
AUTO_POSITIONS = ("left", "right", "center", "far-left", "far-right")


def empty() -> dict:
    return {
        "seq": 0,
        "scene": None,
        "actors": {},
        "log": [],
        "choices": None,
        "dm": {"status": "starting"},
        "dm_log": [],
        "versions": {},
        "last_roll": None,
        "explore": None,
        "place": None,
    }


def _free_position(actors: dict) -> str:
    taken = {a["position"] for a in actors.values()}
    for position in AUTO_POSITIONS:
        if position not in taken:
            return position
    return "center"


# An "*_updated" event makes the browser fetch that thing again: versions[key] = seq.
UPDATED = {
    "scene_updated": ("scene:", "location"),
    "actor_updated": ("", "actor"),
    "site_updated": ("site:", "site"),
    "map_updated": ("map:", "map"),
}


def apply(state: dict, event: dict) -> dict:
    # Copy only what a branch changes in place; lists and the rest are replaced, not mutated.
    s = {**state, "actors": dict(state["actors"]), "versions": dict(state["versions"])}
    s["seq"] += 1
    kind = event.get("type")

    if kind == "scene":
        # A new place starts empty; the same place again (a new beat in the
        # same room) keeps who is there.
        if event["location"] != s["scene"] or s["explore"]:
            s["actors"] = {}
        s["scene"] = event["location"]
        s["choices"] = None
        s["explore"] = None
    elif kind == "explore":
        s["explore"] = event["site"]
        s["actors"] = {}
        s["choices"] = None
        # A new @explore can move the party (to a POI): fetch the site again.
        s["versions"]["site:" + event["site"]] = s["seq"]
    elif kind == "at":
        s["place"] = {"map": event["map"], "place": event["place"]}
    elif kind in UPDATED:
        prefix, field = UPDATED[kind]
        s["versions"][prefix + event[field]] = s["seq"]
    elif kind == "enter":
        position = event.get("position") or _free_position(s["actors"])
        s["actors"][event["actor"]] = {"position": position, "emotion": "neutral"}
    elif kind == "exit":
        s["actors"].pop(event["actor"], None)
    elif kind == "clear":
        s["actors"] = {}
    elif kind in ("narrate", "say"):
        if kind == "say":
            actor = dict(s["actors"].get(event["actor"]) or {"position": _free_position(s["actors"])})
            actor["emotion"] = event.get("emotion", "neutral")
            s["actors"][event["actor"]] = actor
        s["log"] = (s["log"] + [{**event, "seq": s["seq"]}])[-LOG_LIMIT:]
        s["choices"] = None
    elif kind == "choices":
        s["choices"] = {"options": event["options"], "seq": s["seq"]}
    elif kind == "roll":
        s["last_roll"] = {k: event.get(k) for k in ("expr", "total", "dice")} | {"seq": s["seq"]}
    elif kind == "dm_status":
        s["dm"] = {k: v for k, v in event.items() if k in ("status", "reason", "message")}
        if event.get("dm_text"):
            s["dm_log"] = (s["dm_log"] + [event["dm_text"]])[-DM_LOG_LIMIT:]
    return s
