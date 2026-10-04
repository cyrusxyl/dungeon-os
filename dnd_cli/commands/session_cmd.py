"""session command - everything the DM reads at session start, in one call"""

import json
from pathlib import Path

from dnd_cli.commands.show_cmd import run_stage

LOG_TAIL_WORDS = 1200


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _character(path: Path) -> str:
    c = _json(path)
    hp = c.get("hp") or {}
    line = (f"- {path.stem}: {c.get('name')}, {c.get('race')} {c.get('class')} {c.get('level')}, "
            f"HP {hp.get('current')}/{hp.get('max')}" + (f" +{hp['temp']} temp" if hp.get("temp") else "")
            + f", AC {c.get('armor_class')}, player {c.get('controlled_by')}")
    if c.get("spell_slots"):
        line += f", slots {json.dumps(c['spell_slots'], separators=(',', ':'))}"
    if c.get("conditions"):
        line += f", conditions {', '.join(map(str, c['conditions']))}"
    return line


def brief(campaign_dir: Path) -> str:
    """Campaign state, party, players, canon, story bible and the recent session log."""
    state = _json(campaign_dir / "state.json")
    out = [f"# Session brief: {campaign_dir.name}", "", "## State (state.json)",
           json.dumps(state, separators=(",", ":"))]

    out += ["", "## Party (characters/*.json; full sheet: uv run dnd-cli character show <id>)"]
    out += [_character(p) for p in sorted((campaign_dir / "characters").glob("*.json"))] or ["(no characters yet)"]

    out += ["", "## Players (players/*.json)"]
    for p in sorted((campaign_dir / "players").glob("*.json")):
        pl = _json(p)
        out.append(f"- {pl.get('player_id', p.stem)}: controls {', '.join(pl.get('characters_controlled', []))}; "
                   f"permissions {json.dumps(pl.get('permissions', {}), separators=(',', ':'))}")

    canon = _read(campaign_dir / "canon.json")
    out += ["", "## Canon (canon.json, DM only)"]
    out.append(json.dumps(json.loads(canon), separators=(",", ":")) if canon else
               "(missing: run uv run dnd-cli canon init <campaign> before anything else)")

    story = _read(campaign_dir / "dm_story.md")
    out += ["", "## Story bible (dm_story.md, DM only)",
            story or "(missing: new campaign; load the worldbuilding skill and write the Campaign Story Bible)"]

    log = _read(campaign_dir / "session_log.md")
    if log:
        words = log.split(" ")
        if len(words) > LOG_TAIL_WORDS:
            log = "… " + " ".join(words[-LOG_TAIL_WORDS:])
    out += ["", "## Session log (session_log.md, the end)", log or "(no sessions yet)"]
    return "\n".join(out)


def execute_brief(campaign: str | None) -> int:
    def go(campaign_dir):
        print(brief(campaign_dir))
        return 0
    return run_stage(campaign, go)
