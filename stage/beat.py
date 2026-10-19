"""Beat markup: the one format the DM uses to put story on the stage.

A beat is a few lines of markup, sent in one `dnd-cli show beat` call:

    @scene chapel-of-ilmater
    @enter sister-gareth right
    @narrate Candle smoke hangs under the low beams.
    @say[happy] sister-gareth What brings a drow monk to this chapel?
    @choices Ask about the Fist | Show Cassara's note | Leave
    @roll cassara persuasion dc 14

`@roll` asks a player character for a check or a saving throw (`dex-save`).
The player adds bonuses and clicks Roll in the roll window; the DM gets the
result as the next message. Put it last in the beat and end the turn.

With several players:

    @whisper cassara You see a key with your family sigil on the goblin's belt.
    @choices-for sireth Grab the key | Leave it
    @await all
    @await sireth

`@whisper` and `@choices-for` reach one player character's player only; the table
and the other players do not see them. `@await all` makes the stage collect one
answer from each present player, then send them to you together. `@await <pc>`
lets only that player answer. Without `@await`, the first answer comes at once.
Put `@await` last in the beat and end the turn.

The party is on stage in every new room: the player characters and the companions come with
`@scene`, so the DM does not `@enter` them. `@enter` is for others. A companion is an NPC who travels with
the party (`@join`, `@leave`); `@scene <loc> -<id>` leaves one out of that scene. Every actor has a side
(party, ally, neutral, hostile) that the stage draws as a colored ring: `@side <id> <side>` changes it.
`@enter <id> on <slot>` puts an actor on a prop (a seat or a table top) of the scene; `@enter <id> near <slot>` puts one on the floor next to it. `@enter <id> hostile`
sets the side of a named enemy when it enters.

A line without an `@` continues the text of the line before it. Each line
becomes one event; events are appended as JSON lines to the campaign's
`stage/events.ndjson`. The stage server numbers them by line position.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from core.files import read_json
from core.ids import ID_RE, ID_RULE

EMOTIONS = ("neutral", "happy", "angry", "sad", "surprised", "fearful", "disgusted")  # the voice labels; the DM-facing list
MOODS = ("neutral", "ominous", "warm", "wry", "tense", "intense", "urgent", "action", "bright", "somber")  # narrator styles
POSITIONS = ("left", "center", "right", "far-left", "far-right")
WALKS = ("still", "wander", "patrol")  # how an actor moves in a room before a fight (stage/walk.py)
SIDES = ("party", "ally", "neutral", "bystander", "hostile")  # a ring under the feet: green, green, yellow, yellow, red
BYSTANDER = "bystander"  # drawn in a fight, takes no turn, and is not at war with anyone, until something provokes it (stage/board.py)
JOIN_SIDES = ("ally", "neutral", "hostile")  # a companion is not a player character
MAX_ACTORS = 12  # more than this does not fit the stage
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")  # a file id: sites, maps, places


def default_side(actor_id: str) -> str:
    """A kind of monster (`goblin#2`) is hostile, a named character is a bystander, until the DM says otherwise."""
    return "hostile" if "#" in actor_id else BYSTANDER


def title(slug: str) -> str:
    """Display name from an id: 'sister-gareth' -> 'Sister Gareth', 'goblin#2' -> 'Goblin'."""
    return " ".join(w.capitalize() for w in re.split(r"[-_]", slug.split("#")[0]) if w)

USAGE = (
    "Beat lines: @scene <location-id> [-<actor-id> ...] (the party and the companions come with it; -<id> leaves one out) | "
    "@enter <actor-id> [position | on <slot> | near <slot>] [party|ally|neutral|hostile] | @exit <actor-id> | @join <actor-id> [ally|neutral|hostile] | @leave <actor-id> | @walk <actor-id> still|wander|patrol | "
    "@side <actor-id> party|ally|neutral|hostile | @narrate[mood] <text> (mood is optional: " + ", ".join(MOODS) + ") | @say[emotion] <actor-id> <text> (emotion is optional: " + ", ".join(EMOTIONS) + ") | "
    "@choices <a> | <b> | ... | @choices-for <pc-id> <a> | <b> | @whisper <pc-id> <text> | @await all|<pc-id> | "
    "@roll <pc-id> <skill|ability|abil-save> [dc N] [hide] | @clear | "
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
        tag = None
        if m := re.fullmatch(r"(narrate|say)\[([^\]]*)\]", command):
            command, tag = m.group(1), m.group(2).strip()
            allowed = MOODS if command == "narrate" else EMOTIONS
            if tag not in allowed:
                raise BeatError(f"line {line_no}: {'mood' if command == 'narrate' else 'emotion'} {tag!r} is not one of {', '.join(allowed)}.")

        if command == "scene":
            if not rest:
                raise BeatError(f"line {line_no}: @scene needs a location id. {USAGE}")
            parts = rest.split()
            event = {"type": "scene", "location": _check_id(parts[0], line_no, "location")}
            if without := [_check_id(w[1:], line_no, "actor") for w in parts[1:] if w.startswith("-")]:
                event["without"] = without
            if bad := [w for w in parts[1:] if not w.startswith("-")]:
                raise BeatError(f"line {line_no}: @scene does not know {bad[0]!r}; leave an actor out with -<actor-id>.")
            events.append(event)
        elif command == "enter":
            parts = rest.split()
            if not parts:
                raise BeatError(f"line {line_no}: @enter needs an actor id. {USAGE}")
            event = {"type": "enter", "actor": _check_id(parts[0], line_no, "actor")}
            if len(parts) > 1 and parts[-1].lower() in SIDES:
                event["side"] = parts.pop().lower()  # `@enter mizzrymth-guard hostile`
            if len(parts) == 3 and parts[1].lower() in ("on", "near"):
                from stage import scenes  # the slot names (it loads Pillow, so only when asked)

                slot = parts[2].replace("-", "_")
                if slot not in scenes.SLOTS:
                    raise BeatError(f"line {line_no}: slot {parts[2]!r} is not one of {', '.join(scenes.SLOTS)}.")
                event[parts[1].lower()] = slot
            elif len(parts) > 1:
                position = parts[1].lower()
                if len(parts) > 2 or position not in POSITIONS:
                    raise BeatError(f"line {line_no}: use '@enter <actor-id> <position>' (one of {', '.join(POSITIONS)}) or "
                                    "'@enter <actor-id> on <slot>' or '@enter <actor-id> near <slot>'.")
                event["position"] = position
            events.append(event)
        elif command == "exit":
            if not rest:
                raise BeatError(f"line {line_no}: @exit needs an actor id. {USAGE}")
            events.append({"type": "exit", "actor": _check_id(rest.split()[0], line_no, "actor")})
        elif command in ("join", "side"):
            parts = rest.lower().split()
            allowed = JOIN_SIDES if command == "join" else SIDES
            if not parts or len(parts) > 2 or (len(parts) == 2 and parts[1] not in allowed) or (command == "side" and len(parts) < 2):
                raise BeatError(f"line {line_no}: use '@{command} <actor-id> {'[' if command == 'join' else ''}{'|'.join(allowed)}"
                                f"{']' if command == 'join' else ''}'.")
            events.append({"type": command, "actor": _check_id(parts[0], line_no, "actor"),
                           "side": parts[1] if len(parts) == 2 else "ally"})
        elif command == "walk":
            parts = rest.lower().split()
            if len(parts) != 2 or parts[1] not in WALKS:
                raise BeatError(f"line {line_no}: use '@walk <actor-id> {'|'.join(WALKS)}'.")
            events.append({"type": "walk", "actor": _check_id(parts[0], line_no, "actor"), "walk": parts[1]})
        elif command == "leave":
            if not rest:
                raise BeatError(f"line {line_no}: @leave needs an actor id. {USAGE}")
            events.append({"type": "leave", "actor": _check_id(rest.split()[0], line_no, "actor")})
        elif command == "narrate":
            if not rest:
                raise BeatError(f"line {line_no}: @narrate needs text. {USAGE}")
            events.append({"type": "narrate", "text": rest, **({"mood": tag} if tag else {})})
        elif command == "say":
            actor, _, after = rest.partition(" ")
            if not actor or not after.strip():
                raise BeatError(f"line {line_no}: @say needs an actor id and text. {USAGE}")
            events.append({
                "type": "say",
                "actor": _check_id(actor, line_no, "actor"),
                "emotion": tag or "neutral",
                "text": after.strip(),
            })
        elif command == "choices":
            options = [o.strip() for o in rest.split("|") if o.strip()]
            if len(options) < 2:
                raise BeatError(f"line {line_no}: @choices needs two or more options separated by '|'.")
            events.append({"type": "choices", "options": options})
        elif command == "choices-for":
            who, _, after = rest.partition(" ")
            options = [o.strip() for o in after.split("|") if o.strip()]
            if not who or len(options) < 2:
                raise BeatError(f"line {line_no}: @choices-for needs a player character id and two or more options separated by '|'.")
            events.append({"type": "choices", "who": _check_id(who, line_no, "character"), "options": options})
        elif command == "whisper":
            who, _, after = rest.partition(" ")
            if not who or not after.strip():
                raise BeatError(f"line {line_no}: @whisper needs a player character id and text. {USAGE}")
            events.append({"type": "whisper", "who": _check_id(who, line_no, "character"), "text": after.strip()})
        elif command == "await":
            word = rest.split()[0].lower() if rest.split() else ""
            if not word:
                raise BeatError(f"line {line_no}: @await needs 'all' or a player character id. {USAGE}")
            events.append({"type": "await", "who": word if word == "all" else _check_id(word, line_no, "character")})
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


def companions(campaign_dir: Path) -> list[dict]:
    """The NPCs who travel with the party, `[{"id", "side"}]`, from state.json. They come with every `@scene`."""
    out = (read_json(campaign_dir / "state.json") or {}).get("companions") or []
    return [c for c in out if isinstance(c, dict) and ID_RE.match(str(c.get("id"))) and c.get("side") in SIDES]


def set_companions(campaign_dir: Path, roster: list[dict]) -> None:
    """Save the roster in state.json, keeping the rest of the file."""
    from core.files import write_json

    path = campaign_dir / "state.json"
    data = read_json(path) or {}
    data["companions"] = roster
    write_json(path, data, indent=2)


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
