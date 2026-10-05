"""Launcher settings: which agent framework runs the DM, and which model.

Persisted to `game/settings.json` (git-ignored — it is per-machine, and the
`sessions` block is rewritten every time you start a game). This module never
writes campaign state; `sessions` maps a campaign slug to the id of the last
`claude` conversation started for it — the menu uses it to tell that a
just-created campaign has been played, even before its first session closes.

`build_dm_command` is a pure function: settings in, the `["sh", "-c", ...]`
command that `view/app.py` hands to the terminal widget out. Keep it pure so
it stays unit-testable without spawning anything.
"""

from __future__ import annotations

import json
import shlex
import shutil
import uuid
from pathlib import Path

from dnd_cli.campaign import GAME_DIR

SETTINGS_PATH = GAME_DIR / "settings.json"

DEFAULTS: dict = {
    "agent_framework": "claude",
    "model": "sonnet",
}

# One entry per framework the menu can offer. `binary` is what must be on PATH
# for the option to actually work; `models` are presets for the Settings field
# (which stays free-text, so a stale preset is never a dead end).
FRAMEWORKS: dict[str, dict] = {
    "claude": {
        "label": "Claude Code",
        "binary": "claude",
        "models": ["sonnet", "opus", "haiku", "claude-opus-5", "claude-sonnet-5"],
    },
    "agy": {
        "label": "Antigravity CLI",
        "binary": "agy",
        "models": ["gemini-3.1-pro-high", "gemini-3.8-flash-high"],
    },
    "codex": {
        "label": "Codex CLI",
        "binary": "codex",
        "models": ["gpt-5-codex", "o4-mini"],
    },
}


def framework_available(key: str) -> bool:
    spec = FRAMEWORKS.get(key)
    return bool(spec) and shutil.which(spec["binary"]) is not None


def load_settings() -> dict:
    """Return the saved settings merged over the defaults."""
    data = dict(DEFAULTS)
    try:
        saved = json.loads(SETTINGS_PATH.read_text())
        if isinstance(saved, dict):
            data.update({k: v for k, v in saved.items() if k in DEFAULTS})
            if isinstance(saved.get("sessions"), dict):
                data["sessions"] = saved["sessions"]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    if data.get("agent_framework") not in FRAMEWORKS:
        data["agent_framework"] = DEFAULTS["agent_framework"]
    return data


def save_settings(values: dict) -> None:
    """Persist agent_framework and model, keeping the existing sessions block."""
    current = load_settings()
    current["agent_framework"] = values.get(
        "agent_framework", current["agent_framework"]
    )
    current["model"] = values.get("model", current["model"]).strip()
    _write(current)


def get_last_session_id(campaign_slug: str) -> str | None:
    return load_settings().get("sessions", {}).get(campaign_slug)


def set_last_session_id(campaign_slug: str, session_id: str) -> None:
    data = load_settings()
    sessions = dict(data.get("sessions", {}))
    sessions[campaign_slug] = session_id
    data["sessions"] = sessions
    _write(data)


def _write(data: dict) -> None:
    payload = {
        "agent_framework": data.get("agent_framework", DEFAULTS["agent_framework"]),
        "model": data.get("model", DEFAULTS["model"]),
        "sessions": data.get("sessions", {}),
    }
    SETTINGS_PATH.write_text(json.dumps(payload, indent=2) + "\n")


def build_dm_command(
    settings: dict,
    game_dir: Path,
    session_id: str,
    *,
    resume: bool = False,
    initial_prompt: str | None = None,
    stage: bool = False,
) -> list[str]:
    """Build the shell command that runs the DM agent in the terminal widget.

    `sh -c "cd <game_dir> && exec <agent> ..."` — cd (not a Popen cwd kwarg)
    because the terminal widget's spawn interface takes only a command. Every
    interpolated value is shell-quoted: the model comes from a free-text field.
    `initial_prompt` starts the interactive session with that first message,
    so the DM opens the game without waiting for the player to type.
    `stage`: the players watch the visual stage, so Claude does not get the
    AskUserQuestion tool (it asks with @choices); it never wastes a turn on it.
    """
    framework = settings.get("agent_framework", DEFAULTS["agent_framework"])
    model = (settings.get("model") or "").strip()
    if framework not in FRAMEWORKS:
        raise ValueError(f"unknown agent_framework: {framework!r}")

    if framework == "claude":
        parts = ["claude", "--no-chrome", "--permission-mode", "auto"]
        if stage:
            # Before the other options: the flag takes a list and would swallow the prompt.
            parts += ["--disallowedTools", "AskUserQuestion"]
        if resume:
            parts += ["--resume", shlex.quote(session_id)]
        else:
            parts += ["--session-id", shlex.quote(session_id)]
        if model:
            parts += ["--model", shlex.quote(model)]
    else:
        # agy / codex: no session concept here. agy takes `--model`, codex `-m`.
        parts = [FRAMEWORKS[framework]["binary"]]
        if framework == "agy":
            parts.append("--dangerously-skip-permissions")  # agy has no auto mode
        if model:
            parts += ["--model" if framework == "agy" else "-m", shlex.quote(model)]
        if initial_prompt and framework == "agy":
            parts += ["-i", shlex.quote(initial_prompt)]
            initial_prompt = None

    if initial_prompt:
        parts.append(shlex.quote(initial_prompt))

    inner = f"cd {shlex.quote(str(game_dir))} && exec " + " ".join(parts)
    return ["sh", "-c", inner]


def new_dm_session(campaign_dir: Path, initial_prompt: str | None = None, stage: bool = False) -> tuple[str, list[str]]:
    """Make the campaign active and build a fresh DM session for it: (session id, command)."""
    from dnd_cli.campaign import set_active_campaign

    set_active_campaign(campaign_dir.name)
    session_id = str(uuid.uuid4())
    set_last_session_id(campaign_dir.name, session_id)
    return session_id, build_dm_command(load_settings(), GAME_DIR, session_id, initial_prompt=initial_prompt, stage=stage)


def campaign_in_progress(campaign_dir: Path) -> bool:
    """True if this campaign has been played and can be resumed from its files.

    Signals, any of: a DM session was started for it earlier this run; the
    canon file records a closed session; a quest is on the state log.
    """
    if get_last_session_id(campaign_dir.name):
        return True
    try:
        canon = json.loads((campaign_dir / "canon.json").read_text())
        if canon.get("last_session_written", 0) >= 1:
            return True
    except (OSError, json.JSONDecodeError):
        pass
    try:
        state = json.loads((campaign_dir / "state.json").read_text())
        if state.get("quest_log"):
            return True
    except (OSError, json.JSONDecodeError):
        pass
    return False
