"""Canon file logic: schema validation and deterministic bookkeeping.

This module exists so an AI DM never has to compute clock segments,
thread staleness, or the five-thread cap by itself. See
game/docs/AI_DM_Operating_Guide_STE100.md Sections 2-4 and 11 for the
rules this code enforces, and game/.claude/skills/dm-canon-procedures
for how the AI DM is expected to call it.
"""

import json
from pathlib import Path
from typing import Optional

import jsonschema

from dnd_cli.campaign import REPO_ROOT, CAMPAIGNS_DIR, CampaignError, resolve_campaign_dir

SCHEMA_PATH = REPO_ROOT / "game" / "schemas" / "canon.schema.json"

# Re-exported for callers that import these from dnd_cli.canon.
__all__ = [
    "REPO_ROOT", "CAMPAIGNS_DIR", "CampaignError", "resolve_campaign_dir",
    "CanonError",
]


class CanonError(CampaignError):
    """Raised for any canon file problem: bad data, bad arguments."""


def _load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def canon_path(campaign_dir: Path) -> Path:
    return campaign_dir / "canon.json"


def validate(data: dict) -> None:
    """Raise CanonError with a clear message if data does not match the schema."""
    schema = _load_schema()
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as e:
        location = "/".join(str(p) for p in e.absolute_path) or "(root)"
        raise CanonError(f"canon.json failed schema validation at {location}: {e.message}") from e


def load(campaign_dir: Path) -> dict:
    path = canon_path(campaign_dir)
    if not path.exists():
        raise CanonError(f"No canon.json at {path}. Run 'canon init' first.")
    with open(path) as f:
        data = json.load(f)
    validate(data)
    return data


def save(campaign_dir: Path, data: dict) -> None:
    """Validate before writing. A canon.json that fails its own schema is never saved."""
    validate(data)
    path = canon_path(campaign_dir)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def init(campaign_dir: Path, campaign_id: Optional[str] = None) -> dict:
    path = canon_path(campaign_dir)
    if path.exists():
        raise CanonError(f"{path} already exists. Refusing to overwrite.")
    data = {
        "campaign_id": campaign_id or campaign_dir.name,
        "last_session_written": 0,
        "last_clock_touched": None,
        "villains": [],
        "threads": [],
        "facts": [],
        "characters": [],
        "items": [],
        "promises": [],
        "rulings": [],
        "secret": True,
    }
    save(campaign_dir, data)
    return data


def _find_villain(data: dict, villain_name: str) -> dict:
    for v in data["villains"]:
        if v["name"] == villain_name:
            return v
    raise CanonError(f"No villain named {villain_name!r} in canon.json")


def add_villain(data: dict, name: str, goal: str, trait: str, escape_plan: Optional[str] = None) -> None:
    if any(v["name"] == name for v in data["villains"]):
        raise CanonError(f"Villain {name!r} already exists.")
    villain = {"name": name, "goal": goal, "trait": trait, "clocks": []}
    if escape_plan:
        villain["escape_plan"] = escape_plan
    data["villains"].append(villain)


def add_clock(
    data: dict,
    villain_name: str,
    clock_name: str,
    segments_total: int,
    description: Optional[str] = None,
) -> None:
    if segments_total not in (4, 6, 8):
        raise CanonError(
            f"segments_total must be 4, 6, or 8 (Operating Guide 2.2). Got {segments_total}."
        )
    villain = _find_villain(data, villain_name)
    if any(c["name"] == clock_name for c in villain["clocks"]):
        raise CanonError(f"Clock {clock_name!r} already exists on villain {villain_name!r}.")
    clock = {
        "name": clock_name,
        "segments_total": segments_total,
        "segments_filled": 0,
        "status": "active",
    }
    if description:
        clock["description"] = description
    villain["clocks"].append(clock)


def _find_clock(villain: dict, clock_name: str) -> dict:
    for c in villain["clocks"]:
        if c["name"] == clock_name:
            return c
    raise CanonError(f"No clock named {clock_name!r} on villain {villain['name']!r}")


def advance_clock(
    data: dict,
    villain_name: str,
    clock_name: str,
    action_taken: bool = False,
    warning_ignored: bool = False,
) -> dict:
    """Advance one clock following Operating Guide 2.4-2.6. Returns the clock.

    Rule order (2.9: use only these rules, not feel):
    - action_taken (2.5): players took direct action against this quest this
      session. Do not advance.
    - warning_ignored (2.6): players ignored a clear warning. Advance by 2.
    - otherwise (2.4): advance by 1.
    """
    villain = _find_villain(data, villain_name)
    clock = _find_clock(villain, clock_name)

    if clock["status"] == "complete":
        raise CanonError(f"Clock {clock_name!r} is already complete. Nothing to advance.")

    if action_taken:
        delta = 0
    elif warning_ignored:
        delta = 2
    else:
        delta = 1

    clock["segments_filled"] = min(clock["segments_total"], clock["segments_filled"] + delta)
    if clock["segments_filled"] >= clock["segments_total"]:
        clock["status"] = "complete"

    return clock


def touch_clock(data: dict, villain_name: str, clock_name: str) -> None:
    """Record which clock the session's arc-touch scene connected to (OG 4.3)."""
    villain = _find_villain(data, villain_name)
    _find_clock(villain, clock_name)  # validate it exists
    data["last_clock_touched"] = clock_name


def sweep_threads(data: dict, appeared_ids: list[str]) -> list[dict]:
    """Update staleness for every thread per Operating Guide 3.3-3.6.

    appeared_ids: thread ids that appeared in play this session (staleness
    resets to 0). Every other thread's staleness increases by 1.

    Returns a list of {id, staleness_count, alert} for the caller to act on.
    alert is "put back into play" at 2, "world acts now" at 3+, else None.
    """
    known_ids = {t["id"] for t in data["threads"]}
    unknown = set(appeared_ids) - known_ids
    if unknown:
        raise CanonError(f"Unknown thread id(s), not in canon.json: {sorted(unknown)}")

    results = []
    for thread in data["threads"]:
        if thread["id"] in appeared_ids:
            thread["staleness_count"] = 0
        else:
            thread["staleness_count"] += 1

        count = thread["staleness_count"]
        if count >= 3:
            alert = "world acts now (OG 3.5) — the thread forces itself into the game"
        elif count == 2:
            alert = "put back into play next session (OG 3.4)"
        else:
            alert = None
        results.append({"id": thread["id"], "staleness_count": count, "alert": alert})

    return results


def add_thread(data: dict, thread_id: str, description: str) -> None:
    if any(t["id"] == thread_id for t in data["threads"]):
        raise CanonError(f"Thread id {thread_id!r} already exists.")
    if len(data["threads"]) >= 5:
        raise CanonError(
            "Already at the five-thread cap (OG 3.7). Close or merge a thread "
            "first with 'canon close-thread', then add the new one."
        )
    data["threads"].append({"id": thread_id, "description": description, "staleness_count": 0})


def close_thread(data: dict, thread_id: str) -> None:
    before = len(data["threads"])
    data["threads"] = [t for t in data["threads"] if t["id"] != thread_id]
    if len(data["threads"]) == before:
        raise CanonError(f"No thread with id {thread_id!r} to close.")


def add_fact(data: dict, session: int, source: str, fact: str) -> None:
    data["facts"].append({"fact": fact, "source": source, "session": session})


def add_item(data: dict, session: int, recipient: str, item: str) -> None:
    data["items"].append({"item": item, "recipient": recipient, "session": session})


def add_promise(data: dict, session: int, made_to: str, promise: str) -> None:
    data["promises"].append({"promise": promise, "made_to": made_to, "session": session, "fulfilled": False})


def fulfill_promise(data: dict, index: int) -> None:
    try:
        data["promises"][index]["fulfilled"] = True
    except IndexError:
        raise CanonError(f"No promise at index {index}. Use 'canon show' to list indices.")


def add_ruling(data: dict, session: int, context: str, ruling: str) -> None:
    data["rulings"].append({"ruling": ruling, "context": context, "session": session})


def session_end_report(data: dict, session_number: int) -> dict:
    """Summarize what is on record for this session, and flag gaps.

    This is the code-side half of the Session-End Procedure (OG Section 11):
    it does not write anything by itself, it reports what already got
    written so a session cannot be closed on the strength of the AI DM's
    say-so alone.
    """
    def count_for_session(items):
        return sum(1 for x in items if x.get("session") == session_number)

    report = {
        "session_number": session_number,
        "facts_this_session": count_for_session(data["facts"]),
        "items_this_session": count_for_session(data["items"]),
        "promises_this_session": count_for_session(data["promises"]),
        "rulings_this_session": count_for_session(data["rulings"]),
        "clock_touched": data.get("last_clock_touched"),
        "open_threads": len(data["threads"]),
        "warnings": [],
    }
    if not data.get("last_clock_touched"):
        report["warnings"].append(
            "Arc-Touch Gate (OG 4.1-4.4): no clock has been touched. "
            "Run 'canon touch-clock' before closing the session."
        )
    if report["open_threads"] > 5:
        report["warnings"].append(
            f"{report['open_threads']} open threads — over the OG 3.7 cap of 5."
        )
    return report


def close_session(data: dict, session_number: int) -> dict:
    """Set last_session_written. Call after reviewing session_end_report."""
    data["last_session_written"] = session_number
    return data
