"""World bookkeeping: game clock, state fields, quests, NPCs, faction reputation.

The DM used to Read and Edit these JSON files by hand. Each function here does
one such change and returns one short line, so the model spends its tokens on
the story. Commands are in dnd_cli/commands/world_cmd.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema

from dnd_cli import canon
from stage import maps
from stage.beat import ID_RE, ID_RULE
from stage.files import read_json, write_json

REPO_ROOT = Path(__file__).resolve().parents[1]
NPC_SCHEMA = REPO_ROOT / "game" / "schemas" / "npc.schema.json"
DAY = 1440


class WorldError(ValueError):
    """A bad world command. The message says how to fix it."""


# -- time --------------------------------------------------------------------

PERIODS = [(0, "Night"), (300, "Dawn"), (420, "Morning"), (660, "Midday"), (840, "Afternoon"),
           (1020, "Evening"), (1200, "Night")]
# Where a period word puts the clock when an old game_time has no HH:MM.
PERIOD_START = {"midnight": 0, "dawn": 360, "morning": 480, "noon": 720, "midday": 720, "afternoon": 900,
                "evening": 1080, "dusk": 1080, "night": 1320}
UNITS = {"d": DAY, "h": 60, "m": 1}
DURATION_RE = re.compile(r"(\d+(?:\.\d+)?|half an?|an?)\s*(days?|d|hours?|hrs?|h|minutes?|mins?|m)\b", re.I)


def parse_duration(text: str) -> int:
    """Minutes in a text like "2 days", "1 day, 4 hours", "45m", "half a day", "an hour"."""
    parts = DURATION_RE.findall(text.strip().lstrip("+"))
    rest = DURATION_RE.sub("", text.lstrip("+"))
    if not parts or re.sub(r"[\s,]|\band\b", "", rest, flags=re.I):
        raise WorldError(f"cannot read the duration {text!r}. Write for example: 2 days, 3 hours, 15 min, "
                         "1 day 4 hours, half a day, 2d, 3h, 45m.")
    total = 0.0
    for amount, unit in parts:
        a = amount.lower()
        n = 0.5 if a.startswith("half") else 1.0 if a in ("a", "an") else float(a)
        total += n * UNITS[unit[0].lower()]
    return round(total)


def period(minute: int) -> str:
    return [name for start, name in PERIODS if start <= minute][-1]


def label(clock: dict) -> str:
    return f"Day {clock['day']}, {period(clock['minute'])}"


def clock_from_text(text: str) -> dict:
    """Day and minute of an old-style game_time such as "Day 3, Evening" or "Day 2, 10:00 PM"."""
    day = re.search(r"day\s*(\d+)", text, re.I)
    minute = 480
    if clock := re.search(r"\b(\d{1,2}):(\d{2})\s*([ap]m)?", text, re.I):
        hour = int(clock[1]) % 24
        if clock[3]:
            hour = int(clock[1]) % 12 + (12 if clock[3].lower() == "pm" else 0)
        minute = (hour * 60 + int(clock[2])) % DAY
    else:
        word = next((w for w in re.findall(r"[a-z]+", text.lower()) if w in PERIOD_START), None)
        minute = PERIOD_START.get(word, minute)
    return {"day": int(day[1]) if day else 1, "minute": minute}


def get_clock(state: dict) -> dict:
    c = state.get("clock")
    if isinstance(c, dict) and isinstance(c.get("day"), int) and isinstance(c.get("minute"), int):
        return {"day": c["day"], "minute": c["minute"] % DAY}
    return clock_from_text(str(state.get("game_time", "")))


def put_clock(state: dict, clock: dict) -> str:
    state["clock"] = clock
    state["game_time"] = label(clock)
    return state["game_time"]


def advance(state: dict, minutes: int) -> str:
    c = get_clock(state)
    total = c["day"] * DAY + c["minute"] + minutes
    return put_clock(state, {"day": total // DAY, "minute": total % DAY})


def show_duration(minutes: int) -> str:
    days, rest = divmod(minutes, DAY)
    hours, mins = divmod(rest, 60)
    parts = [f"{n} {u}" for n, u in ((days, "day" + "s" * (days != 1)), (hours, "hour" + "s" * (hours != 1)),
                                      (mins, "min")) if n]
    return " ".join(parts) or "0 min"


def set_time(state: dict, text: str) -> str:
    """`+2h` advances the clock; "Day 3, 18:00" sets it."""
    text = text.strip()
    if text.startswith("+"):
        return "Time: " + advance(state, parse_duration(text))
    if not re.search(r"day\s*\d+", text, re.I):
        raise WorldError(f"cannot read the time {text!r}. Write +2h, +1d, +30m to advance, or "
                         "\"Day 3, 18:00\" or \"Day 3, Evening\" to set.")
    return "Time: " + put_clock(state, clock_from_text(text))


def travel(state: dict, m: dict, place: str) -> str | None:
    """Record the party's place; if it moved along known routes on this map, spend the travel time."""
    old = state.get("place")
    state["place"] = place
    if not old or old == place or old not in m["places"]:
        return None
    path = maps.shortest(m, old, place)
    minutes = 0
    for a, b in zip(path or [], (path or [])[1:]):
        try:
            minutes += parse_duration((maps._route(m, a, b) or {}).get("travel") or "")
        except WorldError:
            pass  # a route without a clear time costs none
    if not minutes:
        return None
    return f"Time: {advance(state, minutes)} (+{show_duration(minutes)} of travel)"


# -- state fields ------------------------------------------------------------

STATE_KEYS = ("weather", "party_status", "active_player_turn", "location")


def state_set(state: dict, tokens: list[str]) -> str:
    """Set weather, party_status, active_player_turn or location. `_` stands for a space."""
    if not tokens:
        raise WorldError(f"give at least one key=value. Allowed keys: {', '.join(STATE_KEYS)}.")
    changes = {}
    for t in tokens:
        key, eq, value = t.partition("=")
        if not eq or key not in STATE_KEYS:
            raise WorldError(f"{t!r}: write key=value with a key from: {', '.join(STATE_KEYS)}.")
        if key == "active_player_turn":
            changes[key] = None if value in ("", "none", "null") else value
        else:
            changes[key] = value.replace("_", " ").strip()
    state.update(changes)
    return "State: " + ", ".join(f"{k}={v}" for k, v in changes.items())


# -- faction reputation ------------------------------------------------------


def faction_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def faction(state: dict, name: str, delta: str | None) -> str:
    key = faction_key(name)
    if not key:
        raise WorldError("give a faction name, for example: faction thieves-guild +2.")
    rep = state.setdefault("faction_reputation", {})
    if delta is not None:
        if not re.fullmatch(r"[+-]\d+", delta):
            raise WorldError(f"{delta!r}: write the change as +N or -N, for example +2.")
        rep[key] = rep.get(key, 0) + int(delta)
    return f"Faction {key}: {rep.get(key, 0)}"


# -- quests ------------------------------------------------------------------


def _id(value: str, what: str) -> str:
    if not ID_RE.match(value):
        raise WorldError(f"{what} id {value!r}: {ID_RULE}.")
    return value


def quest_path(campaign_dir: Path, qid: str) -> Path:
    return campaign_dir / "world" / "quests" / f"{_id(qid, 'quest')}.json"


def _quest(campaign_dir: Path, qid: str) -> tuple[Path, dict]:
    path = quest_path(campaign_dir, qid)
    quest = read_json(path)
    if quest is None:
        raise WorldError(f"no quest {qid!r}. Create it with: quest add {qid} \"<title>\".")
    return path, quest


def _entry(state: dict, quest: dict) -> dict:
    """The quest's quest_log entry; made when the log lacks it."""
    log = state.setdefault("quest_log", [])
    found = next((e for e in log if e.get("id") == quest["id"]), None)
    if found is None:
        found = {"id": quest["id"], "title": quest["title"], "status": quest["status"], "progress": ""}
        log.append(found)
    return found


def quest_add(campaign_dir: Path, state: dict, qid: str, title: str, description: str = "",
              objectives: list[str] = (), reward: str = "") -> str:
    path = quest_path(campaign_dir, qid)
    if path.exists():
        raise WorldError(f"quest {qid!r} exists. Use quest progress, done or fail to change it.")
    quest = {"id": qid, "title": title, "description": description, "status": "active",
             "objectives": [{"task": t, "completed": False} for t in objectives], "reward": reward, "notes": ""}
    write_json(path, quest, indent=2)
    _entry(state, quest)
    return f"Quest {qid}: added ({len(objectives)} objectives)."


def quest_progress(campaign_dir: Path, state: dict, qid: str, text: str) -> str:
    path, quest = _quest(campaign_dir, qid)
    quest["notes"] = (quest.get("notes", "") + "\n" + text).strip()
    write_json(path, quest, indent=2)
    _entry(state, quest)["progress"] = text
    return f"Quest {qid}: progress set."


def _finish(campaign_dir: Path, state: dict, qid: str, status: str) -> str:
    path, quest = _quest(campaign_dir, qid)
    quest["status"] = status
    write_json(path, quest, indent=2)
    _entry(state, quest)["status"] = status
    return f"Quest {qid}: {status}."


def quest_done(campaign_dir: Path, state: dict, qid: str, objective: int | None = None) -> str:
    if objective is None:
        return _finish(campaign_dir, state, qid, "completed")
    path, quest = _quest(campaign_dir, qid)
    objs = quest.get("objectives", [])
    if not 1 <= objective <= len(objs):
        raise WorldError(f"quest {qid!r} has {len(objs)} objectives. Use --objective 1 to {len(objs)}.")
    objs[objective - 1]["completed"] = True
    write_json(path, quest, indent=2)
    done = sum(o["completed"] for o in objs)
    _entry(state, quest)
    line = f"Quest {qid}: objective {objective} done ({done}/{len(objs)})."
    return line + (f" All done: run quest done {qid}." if done == len(objs) else "")


def quest_fail(campaign_dir: Path, state: dict, qid: str) -> str:
    return _finish(campaign_dir, state, qid, "failed")


def quest_lines(campaign_dir: Path, state: dict) -> list[str]:
    out = []
    for e in state.get("quest_log", []):
        objs = (read_json(quest_path(campaign_dir, e["id"])) or {}).get("objectives", [])
        count = f" ({sum(o['completed'] for o in objs)}/{len(objs)})" if objs else ""
        out.append(f"{e['id']} [{e['status']}]{count} {e['title']}" + (f": {e['progress']}" if e.get("progress") else ""))
    return out or ["No quests yet."]


# -- NPCs --------------------------------------------------------------------

ATTITUDES = ["hostile", "unfriendly", "neutral", "friendly", "allied"]


def npc_path(campaign_dir: Path, nid: str) -> Path:
    return campaign_dir / "world" / "npcs" / f"{_id(nid, 'npc')}.json"


def _value(text: str):
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text.replace("_", " ").strip()


def _save_npc(path: Path, npc: dict) -> None:
    """Write only an NPC that passes npc.schema.json."""
    try:
        jsonschema.validate(npc, json.loads(NPC_SCHEMA.read_text()))
    except jsonschema.ValidationError as e:
        where = "/".join(str(p) for p in e.absolute_path) or "(root)"
        raise WorldError(f"npc not saved. {where}: {e.message}. See game/schemas/npc.schema.json.") from e
    write_json(path, npc, indent=2)


def npc_set(campaign_dir: Path, nid: str, tokens: list[str]) -> str:
    """Create or update an NPC file. A key like hp.max=20 sets a field inside an object."""
    if not tokens:
        raise WorldError("give at least one key=value, for example: npc set mira name=Mira type=humanoid.")
    path = npc_path(campaign_dir, nid)
    npc = read_json(path)
    new = npc is None
    npc = npc or {}
    for t in tokens:
        key, eq, value = t.partition("=")
        if not eq or not key:
            raise WorldError(f"{t!r}: write key=value, for example personality=Shy_and_kind.")
        *outer, last = key.split(".")
        target = npc
        for k in outer:
            target = target.setdefault(k, {})
            if not isinstance(target, dict):
                raise WorldError(f"{key!r}: {k!r} is not an object.")
        target[last] = _value(value)
    if new and not {"name", "type"} <= npc.keys():
        raise WorldError(f"new npc {nid!r} needs name= and type= (for example type=humanoid).")
    _save_npc(path, npc)
    return f"NPC {nid}: {'created' if new else 'updated'} ({', '.join(t.partition('=')[0] for t in tokens)})."


def _npc(campaign_dir: Path, nid: str) -> tuple[Path, dict]:
    path = npc_path(campaign_dir, nid)
    npc = read_json(path)
    if npc is None:
        raise WorldError(f"no npc {nid!r}. Create it with: npc set {nid} name=... type=...")
    return path, npc


def npc_note(campaign_dir: Path, nid: str, text: str) -> str:
    path, npc = _npc(campaign_dir, nid)
    try:
        prefix = f"Session {canon.load(campaign_dir).get('last_session_written', 0) + 1}: "
    except canon.CanonError:
        prefix = ""
    npc["notes"] = (npc.get("notes", "") + "\n" + prefix + text).strip()
    _save_npc(path, npc)
    return f"NPC {nid}: note added."


def npc_attitude(campaign_dir: Path, nid: str, move: str) -> str:
    path, npc = _npc(campaign_dir, nid)
    old = npc.get("relationship_to_party", "neutral")
    i = ATTITUDES.index(old) if old in ATTITUDES else 2
    if move in ("up", "down"):
        i = min(max(i + (1 if move == "up" else -1), 0), len(ATTITUDES) - 1)
    elif move in ATTITUDES:
        i = ATTITUDES.index(move)
    else:
        raise WorldError(f"{move!r}: use up, down, or one of {', '.join(ATTITUDES)}.")
    npc["relationship_to_party"] = ATTITUDES[i]
    _save_npc(path, npc)
    return f"NPC {nid}: {old} -> {ATTITUDES[i]}"
