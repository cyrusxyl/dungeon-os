"""session command - everything the DM reads at session start, in one call"""

import json
from pathlib import Path

from dnd_cli import world
from dnd_cli.commands.show_cmd import run_stage
from stage.files import read_json, write_json

LOG_TAIL_WORDS = 1200


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _character(path: Path) -> str:
    c = read_json(path) or {}
    hp = c.get("hp") or {}
    line = (f"- {path.stem}: {c.get('name')}, {c.get('race')} {c.get('class')} {c.get('level')}, "
            f"HP {hp.get('current')}/{hp.get('max')}" + (f" +{hp['temp']} temp" if hp.get("temp") else "")
            + f", AC {c.get('armor_class')}, player {c.get('controlled_by')}")
    slots = (c.get("spellcasting") or {}).get("spell_slots")
    if slots:
        line += ", slots " + " ".join(f"L{lvl} {s.get('remaining')}/{s.get('max')}" for lvl, s in sorted(slots.items()))
    if c.get("conditions"):
        line += f", conditions {', '.join(map(str, c['conditions']))}"
    return line


def brief(campaign_dir: Path) -> str:
    """Campaign state, party, players, canon, story bible and the recent session log."""
    state = read_json(campaign_dir / "state.json") or {}
    shown = {k: v for k, v in state.items() if k != "active_encounter"}
    out = [f"# Session brief: {campaign_dir.name}", "", "## State (state.json)",
           json.dumps(shown, separators=(",", ":"))]
    if (state.get("active_encounter") or {}).get("type") == "combat":
        from dnd_cli import combat

        # The tracker's short status, not its full creature records.
        out += ["", "## Combat in progress (uv run dnd-cli encounter status)"] + combat.status(campaign_dir, state)

    out += ["", "## Party (characters/*.json; full sheet: uv run dnd-cli character show <id>)"]
    out += [_character(p) for p in sorted((campaign_dir / "characters").glob("*.json"))] or ["(no characters yet)"]

    out += ["", "## Players (players/*.json)"]
    for p in sorted((campaign_dir / "players").glob("*.json")):
        pl = read_json(p) or {}
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


CLOCK_MODES = {"advance": {}, "action": {"action_taken": True}, "warning": {"warning_ignored": True}}


def end(campaign_dir: Path, recap: str, appeared: list[str], clocks: list[str], game_time: str | None = None,
        force: bool = False) -> list[str]:
    """Close the session in one step: canon checks, thread sweep, clock advances, log, state.

    All or nothing: every check runs before anything is written, so a retry
    after an error never sweeps threads or advances clocks twice.
    """
    from dnd_cli import canon

    if not recap.strip():
        raise canon.CanonError("give the session recap on stdin (a heredoc): what happened, in a few lines.")
    data = canon.load(campaign_dir)
    session = data.get("last_session_written", 0) + 1
    report = canon.session_end_report(data, session)
    if report["warnings"] and not force:
        raise canon.CanonError("session not closed, nothing written: " + " | ".join(report["warnings"]))

    modes: dict[tuple[str, str], str] = {}
    for spec in clocks:
        target, _, mode = spec.partition("=")
        villain, _, clock = target.partition("/")
        if mode not in CLOCK_MODES:
            raise canon.CanonError(f"--clock {spec!r}: write \"Villain/Clock=advance|action|warning\".")
        canon._find_clock(canon._find_villain(data, villain), clock)
        modes[(villain, clock)] = mode

    sweep = canon.sweep_threads(data, appeared)
    lines = []
    for villain in data["villains"]:
        for clock in villain["clocks"]:
            if clock["status"] == "complete":
                continue
            mode = modes.get((villain["name"], clock["name"]), "advance")
            canon.advance_clock(data, villain["name"], clock["name"], **CLOCK_MODES[mode])
            lines.append(f"clock {villain['name']} / {clock['name']}: {clock['segments_filled']}/{clock['segments_total']}"
                         + (" COMPLETE — record what the villain achieved with canon add-fact" if clock["status"] == "complete" else ""))
    canon.close_session(data, session)
    # The arc-touch gate is per session: the next one must touch a clock again.
    data["last_clock_touched"] = None
    canon.save(campaign_dir, data)

    log = campaign_dir / "session_log.md"
    with open(log, "a") as f:
        f.write(f"\n\n## Session {session}\n\n{recap.strip()}\n")
    if game_time:
        state = read_json(campaign_dir / "state.json") or {}
        state["game_time"] = game_time
        state["clock"] = world.clock_from_text(game_time)
        write_json(campaign_dir / "state.json", state, indent=2)
    lines += [f"thread {t['id']}: staleness {t['staleness_count']} — {t['alert']}" for t in sweep if t["alert"]]
    return lines + [f"Session {session} closed and logged."]


def execute_end(campaign: str | None, appeared: str, clocks: list[str], game_time: str | None, force: bool) -> int:
    import sys

    from dnd_cli import canon

    recap = sys.stdin.read()

    def go(campaign_dir):
        ids = [t.strip() for t in appeared.split(",") if t.strip()]
        print("\n".join(end(campaign_dir, recap, ids, clocks, game_time, force)))
        return 0
    return run_stage(campaign, go, canon.CanonError)
