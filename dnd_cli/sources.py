"""Content the dnd5eapi (2014 SRD) lacks. `api_get` and `api_list` call `extend`.

Two sources, in this order:
1. `dnd_cli/data/overrides/<resource>/<index>.json`, hand-written, in the dnd5eapi shape. A file replaces the
   API answer. A file with `_extend` ({"subraces": [...]}) adds list entries to the API answer instead.
   Every file in a resource folder also appears in that resource's list.
2. Open5e serves the 2024 SRD (document `srd-2024`). Its backgrounds and feats are
converted here to the dnd5eapi shape, so the rest of the code reads one format.
A 2024 background carries the ability score increase (`ability_options`).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from dnd_cli.cache import load_cache, save_cache

OPEN5E = "https://api.open5e.com/v2"
DOC = "srd-2024"
OVERRIDES = Path(__file__).parent / "data" / "overrides"
RESOURCES = ("backgrounds", "feats")  # the endpoints Open5e fills in
ABILITY_NAMES = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _open5e(path: str) -> dict | None:
    cached = load_cache(f"open5e/{path}")
    if cached:
        return cached.get("data")
    try:
        out = subprocess.run(["curl", "-sL", f"{OPEN5E}/{path}"], capture_output=True, text=True, timeout=10)
        data = json.loads(out.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None
    if isinstance(data, dict) and not data.get("detail"):
        save_cache(f"open5e/{path}", data)
        return data
    return None


def _benefit(item: dict, kind: str) -> str:
    return next((b["desc"] for b in item.get("benefits", []) if b.get("type") == kind), "")


def background(item: dict) -> dict:
    index = item["key"].removeprefix(f"{DOC}_")
    skills = [s.strip() for s in _benefit(item, "skill_proficiency").split(" and ") if s.strip()]
    abilities = [a.strip().lower() for a in _benefit(item, "ability_score").split(",")]
    return {
        "index": index, "name": item["name"], "source": DOC,
        "starting_proficiencies": [{"index": f"skill-{_slug(s)}", "name": f"Skill: {s}"} for s in skills],
        "ability_options": [a for a in abilities if a in ABILITY_NAMES],
        "feat": _benefit(item, "feat"), "tool": _benefit(item, "tool_proficiency"),
    }


def feat(item: dict) -> dict:
    intro = item.get("desc", "")
    desc = [] if intro.startswith("You gain the following") else [intro]  # a bare intro line says nothing
    desc += [b["desc"] for b in item.get("benefits", []) if b.get("desc")]
    return {"index": item["key"].removeprefix(f"{DOC}_"), "name": item["name"], "source": DOC,
            "type": item.get("type", ""), "prerequisite": item.get("prerequisite", ""),
            "desc": [d for d in desc if d]}


CONVERT = {"backgrounds": background, "feats": feat}


def one(endpoint: str) -> dict | None:
    """`backgrounds/sage` -> the converted Open5e record, or None."""
    resource, _, index = endpoint.partition("/")
    if resource not in CONVERT or not index or "/" in index:
        return None
    item = _open5e(f"{resource}/{DOC}_{index}/")
    if not item or not item.get("key"):
        return None
    found = CONVERT[resource](item)
    save_cache(endpoint, found)  # the next read is a cache hit, and `search` can see it
    return found


def _override(endpoint: str) -> dict | None:
    path = OVERRIDES / f"{endpoint}.json"
    return json.loads(path.read_text()) if path.is_file() else None


def replacement(endpoint: str) -> dict | None:
    """A hand-written file that replaces the API answer (no `_extend`), read before any network call."""
    item = _override(endpoint)
    return item if item is not None and "_extend" not in item else None


def _override_entries(resource: str) -> list[dict]:
    folder = OVERRIDES / resource
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.glob("*.json")):
        item = json.loads(path.read_text())
        if "_extend" not in item:
            out.append({"index": item["index"], "name": item["name"], "url": f"/override/{resource}/{item['index']}"})
    return out


def _override_extend(endpoint: str, data: dict | None, error: str | None) -> tuple[dict | None, str | None]:
    if (item := _override(endpoint)) is None:
        if data and isinstance(data.get("results"), list) and (extra := _override_entries(endpoint)):
            have = {r["index"] for r in data["results"]}
            data = {**data, "results": data["results"] + [e for e in extra if e["index"] not in have]}
            data["count"] = len(data["results"])
        return data, error
    if "_extend" not in item:
        return item, None
    if not data:
        return data, error
    data = dict(data)
    for key, add in item["_extend"].items():
        have = {r["index"] for r in data.get(key, [])}
        data[key] = data.get(key, []) + [a for a in add if a["index"] not in have]
    return data, error


def extend(endpoint: str, data: dict | None, error: str | None) -> tuple[dict | None, str | None]:
    """Add override and Open5e content to a dnd5eapi answer. Return (data, error)."""
    data, error = _override_extend(endpoint, data, error)
    if error is None and data is not None and (endpoint not in RESOURCES):
        return data, error
    if endpoint in RESOURCES:  # a list: add the entries dnd5eapi does not have
        page = _open5e(f"{endpoint}/?document__key={DOC}&limit=100&fields=key,name")
        if not page:
            return data, error
        data = dict(data) if data else {"count": 0, "results": []}
        have = {r["index"] for r in data["results"]}
        extra = [{"index": r["key"].removeprefix(f"{DOC}_"), "name": r["name"], "url": f"/open5e/{endpoint}/{r['key']}"}
                 for r in page["results"] if r["key"].removeprefix(f"{DOC}_") not in have]
        data["results"] = data["results"] + extra
        data["count"] = len(data["results"])
        return data, None
    if error:
        found = one(endpoint)
        if found:
            return found, None
    return data, error
