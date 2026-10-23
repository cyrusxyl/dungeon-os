"""The current stage, derived from the event log.

`apply` is a pure function: state in, event in, new state out. The server
folds every event of `stage/events.ndjson` through it, so a browser that
reconnects gets one snapshot of "what is on the stage now" instead of a
replay of the whole log.
"""

from __future__ import annotations

from stage.beat import default_side


LOG_LIMIT = 60
ROLL_LIMIT = 12
DM_LOG_LIMIT = 30
ACTIVITY_LIMIT = 12
PRIVATE_LIMIT = 20
NOTICE_LIMIT = 20
FEED_LIMIT = 60
OUTCOMES = {"success": "success", "fail": "failure", "hit": "hit", "miss": "miss", "crit": "critical hit", "fumble": "critical miss"}


def roll_text(event: dict) -> str:
    """One line for the log from a roll event. It holds only what the roll window shows the players."""
    detail = event.get("detail")
    if not detail:
        return f"Rolled {event['expr']}: {event['total']}"
    who = ", ".join(f"{r['name']} {r['total']}" + (f" ({OUTCOMES[r['outcome']]})" if r.get("outcome") else "") for r in detail.get("rolls", []))
    text = detail.get('title', 'Roll') + (f" · {detail['subtitle']}" if detail.get("subtitle") else "") + f": {who}"
    if target := detail.get("target"):
        text += f" vs {target['label']} {target['value']}"
    if damage := detail.get("damage"):
        text += " — " + " + ".join(f"{d['total']} {d['type']}".strip() for d in damage) + " damage"
    return text
AUTO_POSITIONS = ("left", "right", "center", "far-left", "far-right")


def empty() -> dict:
    return {
        "seq": 0,
        "scene": None,
        "actors": {},
        "log": [],
        "choices": None,
        "feed": [],
        "private": [],
        "notices": [],
        "await": None,
        "roll_request": None,
        "dm": {"status": "starting"},
        "dm_log": [],
        "versions": {},
        "rolls": [],
        "explore": None,
        "arena": None,
        "place": None,
        "activity": [],
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
    "arena_updated": ("arena:", "arena"),
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
            # The party and the companions come with the scene, minus whoever the DM left out (`@scene <loc> -<id>`).
            who = [(m, "party") for m in event.get("party", [])] + [(c["id"], c["side"]) for c in event.get("companions", [])]
            for member, side in who:
                if member not in event.get("without", []):
                    s["actors"][member] = {"position": _free_position(s["actors"]), "emotion": "neutral", "side": side}
        for w in event.get("without", []):
            s["actors"].pop(w, None)  # the same room keeps its actors, but the DM sent someone out of it
        s["scene"] = event["location"]
        s["choices"] = None
        s["roll_request"] = None
        s["explore"] = None
        s["await"] = None
        # s["arena"] stays: only `arena_end` ends a fight. A beat line in a fight must not hide the board, or the creatures stop.
    elif kind == "explore":
        s["explore"] = event["site"]
        s["actors"] = {}
        s["choices"] = None
        # A new @explore can move the party (to a POI): fetch the site again.
        s["versions"]["site:" + event["site"]] = s["seq"]
    elif kind == "arena":
        # A fight on the board: the view shows the arena instead of the scene or the site, until the fight ends.
        s["arena"] = event["arena"]
        s["choices"] = None
        s["versions"]["arena:" + event["arena"]] = s["seq"]
    elif kind == "arena_end":
        s["arena"] = None
        # The fight is over: each unit stays where it stood, the fallen lie there (whoever fought is down or up now: a revived companion stands
        # again), and a faction that fought on its own has the side it ended with.
        down, sides = event.get("down") or [], event.get("sides") or {}
        for aid, v in (event.get("cells") or {}).items():
            if aid in s["actors"]:
                s["actors"][aid] = {**{k: x for k, x in s["actors"][aid].items() if k != "down"}, "cell": v["cell"], "facing": v.get("facing", "down"),
                                    **({"down": True} if aid in down else {}), **({"side": sides[aid]} if aid in sides else {})}
    elif kind == "at":
        s["place"] = {"map": event["map"], "place": event["place"]}
    elif kind in UPDATED:
        prefix, field = UPDATED[kind]
        s["versions"][prefix + event[field]] = s["seq"]
    elif kind == "enter":
        old = s["actors"].get(event["actor"], {})
        position = event.get("position") or _free_position({k: v for k, v in s["actors"].items() if k != event["actor"]})
        s["actors"][event["actor"]] = {"position": position, "emotion": "neutral", "side": event.get("side") or old.get("side") or default_side(event["actor"])}
        if event.get("on"):
            s["actors"][event["actor"]]["on"] = event["on"]
        if event.get("near"):
            s["actors"][event["actor"]]["near"] = event["near"]
        if "cell" in old and not (event.get("on") or event.get("near")):
            s["actors"][event["actor"]].update(cell=old["cell"], facing=old.get("facing", "down"))  # entering again (to set a side) does not move the actor
    elif kind == "place":
        # The server's placement of actors that had no cell (stage/cast.py). A place for another scene is stale: ignore it.
        if event.get("scene") == s["scene"]:
            for aid, v in event["cells"].items():
                if aid in s["actors"]:
                    s["actors"][aid] = {**s["actors"][aid], "cell": v["cell"], "facing": v["facing"]}
    elif kind in ("stand", "walk"):
        pass  # old logs only: a scene has no walking now (compact-set.md)
    elif kind == "join":
        # A companion steps on stage now and comes with every later scene (the CLI keeps the roster in state.json).
        old = s["actors"].get(event["actor"], {})
        s["actors"][event["actor"]] = {**old, "position": old.get("position") or _free_position(s["actors"]), "emotion": "neutral", "side": event["side"]}
    elif kind == "side":
        if event["actor"] in s["actors"]:
            s["actors"][event["actor"]] = {**s["actors"][event["actor"]], "side": event["side"]}
    elif kind == "leave":
        s["actors"].pop(event["actor"], None)
    elif kind == "exit":
        s["actors"].pop(event["actor"], None)
    elif kind == "clear":
        s["actors"] = {}
    elif kind == "await_done":
        s["await"] = None  # the server sent the answers to the DM
    elif kind in ("narrate", "say"):
        if kind == "say":
            actor = dict(s["actors"].get(event["actor"]) or {"position": _free_position(s["actors"]), "side": event.get("side") or default_side(event["actor"])})
            actor["emotion"] = event.get("emotion", "neutral")
            s["actors"][event["actor"]] = actor
        s["log"] = (s["log"] + [{**event, "seq": s["seq"]}])[-LOG_LIMIT:]
        s["choices"] = None
        s["roll_request"] = None
        s["await"] = None  # the DM answered; a later `@await` in the same beat sets it again
    elif kind == "pc_say":
        # A player character's words: in the story log, but the DM has not answered, so choices and await stay.
        s["log"] = (s["log"] + [{**event, "seq": s["seq"]}])[-LOG_LIMIT:]
    elif kind == "choices":
        s["choices"] = {"options": event["options"], "seq": s["seq"]} | ({"who": event["who"]} if event.get("who") else {})
    elif kind == "whisper":
        # Only the server hands this to the owner of `who` (stage/server.py snapshot); it is never in the public log.
        s["private"] = (s["private"] + [{"who": event["who"], "text": event["text"], "seq": s["seq"]}])[-PRIVATE_LIMIT:]
    elif kind == "notice":
        # Like a whisper, only the owner's snapshot has it. `id` lets a browser show each notice once.
        s["notices"] = (s["notices"] + [{k: event[k] for k in ("who", "lines", "id")}])[-NOTICE_LIMIT:]
    elif kind == "await":
        s["await"] = {"who": event["who"], "seq": s["seq"]}
    elif kind == "roll_request":
        s["roll_request"] = {k: v for k, v in event.items() if k not in ("type", "beat")} | {"seq": s["seq"]}
    elif kind == "roll_done":
        s["roll_request"] = None  # the server is about to make the roll the DM asked for
    elif kind == "roll":
        s["roll_request"] = None
        # A short queue: the browser plays each roll it has not shown, in order.
        roll = {k: event[k] for k in ("expr", "total", "dice", "detail") if k in event} | {"seq": s["seq"]}
        s["rolls"] = (s["rolls"] + [roll])[-ROLL_LIMIT:]
    if kind in ("roll", "feed"):
        text = roll_text(event) if kind == "roll" else event["text"]
        s["feed"] = (s["feed"] + [{"seq": s["seq"], "text": text}])[-FEED_LIMIT:]
    if kind == "dm_activity":
        if not s["activity"] or s["activity"][-1] != event["text"]:
            s["activity"] = (s["activity"] + [event["text"]])[-ACTIVITY_LIMIT:]
    elif kind == "dm_status":
        if event.get("status") in ("idle", "exited"):
            s["activity"] = []
        s["dm"] = {k: v for k, v in event.items() if k in ("status", "reason", "message")}
        if event.get("dm_text"):
            s["dm_log"] = (s["dm_log"] + [event["dm_text"]])[-DM_LOG_LIMIT:]
    return s


def replay(log_path) -> dict:
    """The state after every event of a stage log (the CLI has no running stage to ask)."""
    import json

    state = empty()
    try:
        lines = open(log_path, encoding="utf-8").read().splitlines()
    except OSError:
        return state
    for line in lines:
        try:
            state = apply(state, json.loads(line))
        except ValueError:
            continue
    return state
