"""Beat markup: the one format the DM uses to put story on the stage.

A beat is a few lines of markup, sent in one `dnd-cli show beat` call:

    @scene chapel-of-ilmater
    @enter sister-gareth right
    @narrate Candle smoke hangs under the low beams.
    @say sister-gareth happy What brings a drow monk to this chapel?
    @choices Ask about the Fist | Show Cassara's note | Leave
    @roll cassara persuasion dc 14

`@roll` asks a player character for a check or a saving throw (`dex-save`).
The player adds bonuses and clicks Roll in the roll window; the DM gets the
result as the next message. Put it last in the beat and end the turn.

The party is on stage in every new room: the player characters come with
`@scene`, so the DM does not `@enter` them. `@enter` is for NPCs.

A line without an `@` continues the text of the line before it. Each line
becomes one event; events are appended as JSON lines to the campaign's
`stage/events.ndjson`. The stage server numbers them by line position.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from stage.files import read_json

EMOTIONS = ("neutral", "happy", "angry", "sad", "shock", "blush", "shame", "eyeroll", "closed")
POSITIONS = ("left", "center", "right", "far-left", "far-right")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")  # a file id: sites, maps, places
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*(#\d+)?$")  # a slug, or an actor of a kind: goblin#2
ID_RULE = "use lower-case letters, digits, '-' or '_'"


def title(slug: str) -> str:
    """Display name from an id: 'sister-gareth' -> 'Sister Gareth', 'goblin#2' -> 'Goblin'."""
    return " ".join(w.capitalize() for w in re.split(r"[-_]", slug.split("#")[0]) if w)

USAGE = (
    "Beat lines: @scene <location-id> (the party comes with it) | @enter <actor-id> [position] | "
    "@exit <actor-id> | @narrate <text> | @say <actor-id> [emotion] <text> | "
    "@choices <a> | <b> | ... | @roll <pc-id> <skill|ability|abil-save> [dc N] [hide] | @clear | "
    "@explore <site-id> [<poi-id>|entrance]"
)


class BeatError(ValueError):
    """A malformed beat line. The message says how to fix it."""


def _check_id(value: str, line_no: int, what: str) -> str:
    if not ID_RE.match(value):
        raise BeatError(
            f"line {line_no}: {what} {value!r} is not a valid id. "
            f"{ID_RULE[0].upper()}{ID_RULE[1:]} (for example 'sister-gareth' or 'goblin#2')."
        )
    return value


def parse(text: str) -> list[dict]:
    """Turn beat markup into a list of event dicts. Raises BeatError on bad input."""
    events: list[dict] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if not line.startswith("@"):
            if events and "text" in events[-1]:
                events[-1]["text"] += " " + line
            else:
                events.append({"type": "narrate", "text": line})
            continue

        command, _, rest = line[1:].partition(" ")
        command, rest = command.lower(), rest.strip()

        if command == "scene":
            if not rest:
                raise BeatError(f"line {line_no}: @scene needs a location id. {USAGE}")
            events.append({"type": "scene", "location": _check_id(rest.split()[0], line_no, "location")})
        elif command == "enter":
            parts = rest.split()
            if not parts:
                raise BeatError(f"line {line_no}: @enter needs an actor id. {USAGE}")
            position = parts[1].lower() if len(parts) > 1 else None
            if position is not None and position not in POSITIONS:
                raise BeatError(f"line {line_no}: position {position!r} is not one of {', '.join(POSITIONS)}.")
            event = {"type": "enter", "actor": _check_id(parts[0], line_no, "actor")}
            if position:
                event["position"] = position
            events.append(event)
        elif command == "exit":
            if not rest:
                raise BeatError(f"line {line_no}: @exit needs an actor id. {USAGE}")
            events.append({"type": "exit", "actor": _check_id(rest.split()[0], line_no, "actor")})
        elif command == "narrate":
            if not rest:
                raise BeatError(f"line {line_no}: @narrate needs text. {USAGE}")
            events.append({"type": "narrate", "text": rest})
        elif command == "say":
            actor, _, after = rest.partition(" ")
            if not actor or not after.strip():
                raise BeatError(f"line {line_no}: @say needs an actor id and text. {USAGE}")
            first, _, remainder = after.strip().partition(" ")
            emotion = "neutral"
            if first.lower() in EMOTIONS and remainder.strip():
                emotion, after = first.lower(), remainder
            events.append({
                "type": "say",
                "actor": _check_id(actor, line_no, "actor"),
                "emotion": emotion,
                "text": after.strip(),
            })
        elif command == "choices":
            options = [o.strip() for o in rest.split("|") if o.strip()]
            if len(options) < 2:
                raise BeatError(f"line {line_no}: @choices needs two or more options separated by '|'.")
            events.append({"type": "choices", "options": options})
        elif command == "roll":
            parts = rest.split()
            if len(parts) < 2:
                raise BeatError(f"line {line_no}: @roll needs a player character id and a check (for example @roll sireth stealth dc 14). {USAGE}")
            event = {"type": "roll_request", "who": _check_id(parts[0], line_no, "character"), "what": parts[1].lower()}
            for word in (w.lower() for w in parts[2:]):
                if word == "hide":
                    event["hide"] = True
                elif m := re.fullmatch(r"(?:dc)?(\d+)", word):
                    event["dc"] = int(m.group(1))
                elif word != "dc":
                    raise BeatError(f"line {line_no}: @roll does not know {word!r}; use dc <number> or hide.")
            events.append(event)
        elif command == "explore":
            parts = rest.split()
            if not parts:
                raise BeatError(f"line {line_no}: @explore needs a site id. {USAGE}")
            event = {"type": "explore", "site": _check_id(parts[0], line_no, "site")}
            if len(parts) > 1:
                event["at"] = _check_id(parts[1], line_no, "point of interest")
            events.append(event)
        elif command == "clear":
            events.append({"type": "clear"})
        else:
            raise BeatError(f"line {line_no}: unknown command @{command}. {USAGE}")

    if not events:
        raise BeatError(f"The beat is empty. {USAGE}")
    return events


def party(campaign_dir: Path) -> list[str]:
    """Actor ids of the player characters: state.json party_members, else the character sheets. Max 4."""
    members = (read_json(campaign_dir / "state.json") or {}).get("party_members")
    if not members:
        members = [p.stem for p in sorted((campaign_dir / "characters").glob("*.json"))]
    return [str(m) for m in members if ID_RE.match(str(m))][:4]


def log_path(campaign_dir: Path) -> Path:
    return campaign_dir / "stage" / "events.ndjson"


def last_beat(path: Path) -> list[dict]:
    """The events of the last beat in the log, without their beat ids.

    Hook events (status, rolls) and `*_updated` notices from `actor set` and
    friends sit between beats; they do not count.
    """
    try:
        with open(path, "rb") as f:
            size = f.seek(0, 2)
            f.seek(max(0, size - 65536))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    if size > 65536:
        lines = lines[1:]  # the first line may be cut
    out: list[dict] = []
    beat_id = None
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if "beat" not in e or e.get("type", "").endswith("_updated"):
            continue
        if beat_id is not None and e["beat"] != beat_id:
            break
        beat_id = e.pop("beat")
        out.append(e)
    return out[::-1]


def append(campaign_dir: Path, events: list[dict]) -> Path:
    """Append events to the campaign's stage log, one JSON object per line."""
    path = log_path(campaign_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    beat_id = f"{time.time():.3f}"
    lines = "".join(json.dumps({**e, "beat": beat_id}) + "\n" for e in events)
    with open(path, "a") as f:
        f.write(lines)
    return path
