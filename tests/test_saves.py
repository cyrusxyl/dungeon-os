"""Checks for saves (a git repo per campaign) and for continuing the DM session.

Run from the repo root:  .venv/bin/python tests/test_saves.py
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dnd_cli.campaign as campaign
import view.settings as settings
from dnd_cli import saves
from stage import hook, server
from test_stage import api

PASS = 0
FAIL = 0


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}")


def make_campaign(root: Path, name: str = "c1") -> Path:
    c = root / name
    (c / "stage").mkdir(parents=True)
    (c / "config.json").write_text('{"campaign_name": "C1"}')
    (c / "state.json").write_text('{"turn": 1}')
    (c / "stage" / "events.ndjson").write_text('{"type": "narrate", "text": "one"}\n')
    return c


def git_out(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True).stdout


def test_saves() -> None:
    print("saves: commit, list, restore")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        subprocess.run(["git", "init", "-q", str(root)], check=True)  # the repo around the campaign
        c = make_campaign(root)
        first = saves.save(c, saves.AUTO, "session start")
        check("first save returns an id", bool(first))
        check("the campaign has its own .git", (c / ".git").is_dir())
        check("the repo around is not touched", git_out(root, "diff", "--cached", "--name-only").strip() == "")
        check("no change: no new save", saves.save(c, saves.AUTO, "again") is None)
        check("a named save is made even with no change", bool(saves.save(c, saves.SAVE, "named", force=True)))

        (c / "state.json").write_text('{"turn": 2}')
        (c / "extra.json").write_text("{}")
        (c / "stage" / "events.ndjson").write_text('{"type": "narrate", "text": "one"}\n{"type": "narrate", "text": "two"}\n')
        saves.save(c, saves.AUTO, "Gandalf: you shall not pass")
        listed = saves.list_saves(c)
        check("newest first, with kind and label", listed[0]["kind"] == "auto" and listed[0]["label"] == "Gandalf: you shall not pass")
        check("a named save is listed as save", any(s["kind"] == "save" and s["label"] == "named" for s in listed))

        (c / "state.json").write_text('{"turn": 3}')  # work that is not saved yet
        saves.restore(c, first)
        check("restore: files go back", (c / "state.json").read_text() == '{"turn": 1}')
        check("restore: a file made later is removed", not (c / "extra.json").exists())
        check("restore: the stage log goes back", "two" not in (c / "stage" / "events.ndjson").read_text())
        after = saves.list_saves(c)
        check("restore: history grows, with a [load] on top", after[0]["kind"] == "load" and len(after) > len(listed))
        check("restore: the unsaved work was saved first", any("before loading" in s["label"] for s in after))
        turn3 = next(s for s in after if "before loading" in s["label"])["id"]
        saves.restore(c, turn3)
        check("restore: the present can be reached again", (c / "state.json").read_text() == '{"turn": 3}')
        for bad in ("nothere", "x; rm -rf /"):
            try:
                saves.restore(c, bad)
                check(f"restore rejects {bad!r}", False)
            except saves.SaveError:
                check(f"restore rejects {bad!r}", True)
        check("no repo: empty list", saves.list_saves(root / "nope") == [])


def test_sessions() -> None:
    print("sessions: continue, command, hook")
    with tempfile.TemporaryDirectory() as tmp:
        old = settings.SETTINGS_PATH, campaign.ACTIVE_PATH, os.environ.get("CLAUDE_CONFIG_DIR")
        settings.SETTINGS_PATH = Path(tmp) / "settings.json"
        campaign.ACTIVE_PATH = Path(tmp) / "active.json"
        os.environ["CLAUDE_CONFIG_DIR"] = tmp
        try:
            settings.SETTINGS_PATH.write_text(json.dumps({"agent_framework": "claude", "sessions": {"old": "legacy-id"}}))
            check("an old bare id still reads", settings.get_session("old") == {"id": "legacy-id", "framework": "claude"})
            check("no transcript: cannot continue", not settings.can_continue("old"))
            transcript = settings.claude_transcript("legacy-id")
            transcript.parent.mkdir(parents=True)
            transcript.write_text("{}")
            check("transcript found under the game folder name", "-game" in str(transcript.parent) and settings.can_continue("old"))
            check("another agent cannot continue a Claude session",
                  not settings.can_continue("old", {"agent_framework": "agy"}))

            camp = Path(tmp) / "old"
            (camp / "characters").mkdir(parents=True)
            (camp / "characters" / "a.json").write_text("{}")
            (camp / "config.json").write_text("{}")
            (camp / "dm_story.md").write_text("x")
            resumed = server.default_command(camp, resume=True)[2]
            check("continue: --resume with the stored id", "--resume legacy-id" in resumed and "--session-id" not in resumed)
            check("continue: only a short nudge, no skill loading", "same conversation" in resumed and "worldbuilding" not in resumed)
            check("continue keeps the session id", settings.get_last_session_id("old") == "legacy-id")
            fresh = server.default_command(camp, resume=False)[2]
            check("fresh: --session-id and a new id stored", "--session-id" in fresh and settings.get_last_session_id("old") != "legacy-id")
            check("fresh: reads the files", "session brief" in fresh and "same conversation" not in fresh)
            check("continue without a session falls back to fresh", "--session-id" in server.default_command(camp, resume=True)[2])
            try:
                settings.new_dm_session(camp, resume=True)
                check("new_dm_session(resume) refuses without a session", False)
            except ValueError:
                check("new_dm_session(resume) refuses without a session", True)

            agy = settings.build_dm_command({"agent_framework": "agy", "model": ""}, settings.GAME_DIR, "conv-9", resume=True)[2]
            check("agy continues with --conversation", "--conversation conv-9" in agy)
            check("agy fresh has no --conversation",
                  "--conversation" not in settings.build_dm_command({"agent_framework": "agy"}, settings.GAME_DIR, "s")[2])

            settings.clear_session("old")
            check("clear_session forgets it", settings.get_session("old") is None)

            log = Path(tmp) / "log.ndjson"
            os.environ["DUNGEON_STAGE_LOG"] = str(log)
            for payload, argv in (({"hook_event_name": "UserPromptSubmit", "session_id": "S1"}, []),
                                  ({"conversationId": "C1"}, ["PreInvocation"])):
                sys.stdin = __import__("io").StringIO(json.dumps(payload))
                sys.argv = ["hook.py", *argv]
                hook.main()
            sys.stdin = sys.__stdin__
            events = [json.loads(line) for line in log.read_text().splitlines()]
            check("the hook reports the Claude session id", events[0].get("session") == "S1")
            check("the hook reports the agy conversation id", events[1].get("session") == "C1")
        finally:
            os.environ.pop("DUNGEON_STAGE_LOG", None)
            settings.SETTINGS_PATH, campaign.ACTIVE_PATH = old[0], old[1]
            if old[2] is None:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = old[2]


def test_server() -> None:
    print("server: autosave, manual save, load")
    with tempfile.TemporaryDirectory() as tmp:
        old = settings.SETTINGS_PATH, campaign.ACTIVE_PATH, campaign.CAMPAIGNS_DIR
        settings.SETTINGS_PATH = Path(tmp) / "settings.json"
        campaign.ACTIVE_PATH = Path(tmp) / "active.json"
        campaign.CAMPAIGNS_DIR = Path(tmp)
        c = make_campaign(Path(tmp))
        (c / "state.json").write_text('{"turn": 1}')

        async def run() -> None:
            app = server.create_app(None, command_factory=lambda d, resume=False: ["cat"])  # a stub DM
            table = app.state.table
            stage = await table.start(c, ["cat"])
            check("session start is saved", [s["label"] for s in saves.list_saves(c)] == ["session start"])

            status, r = await api(app, "POST", "/api/game/save", {"name": "x"})
            check("manual save waits for an idle DM", status == 409)

            log = stage.log_path
            with open(log, "a") as f:
                f.write(json.dumps({"type": "dm_status", "status": "busy", "session": "S-42"}) + "\n")
                f.write(json.dumps({"type": "say", "actor": "bob", "text": "Hello there"}) + "\n")
            await asyncio.sleep(0.5)
            check("the stage remembers the DM session id", settings.get_last_session_id(c.name) == "S-42")
            with open(log, "a") as f:
                f.write(json.dumps({"type": "dm_status", "status": "idle"}) + "\n")
            await asyncio.sleep(0.8)
            check("a DM turn ends in an autosave with the last line",
                  saves.list_saves(c)[0]["label"] == "bob: Hello there" and saves.list_saves(c)[0]["kind"] == "auto")

            status, r = await api(app, "POST", "/api/game/save", {"name": "before the boss"})
            check("manual save works when idle", status == 200 and r["id"])
            status, r = await api(app, "GET", f"/api/saves/{c.name}")
            check("the save list route", status == 200 and r["saves"][0]["label"] == "before the boss" and r["saves"][0]["kind"] == "save")
            start_id = r["saves"][-1]["id"]

            (c / "state.json").write_text('{"turn": 9}')
            status, r = await api(app, "POST", "/api/game/load", {"campaign": c.name, "save": start_id})
            check("load answers with the game", status == 200 and r["game"] == c.name)
            check("load puts the files back", (c / "state.json").read_text() == '{"turn": 1}')
            check("load forgets the old DM conversation", settings.get_last_session_id(c.name) is None)
            check("the game runs again after a load", table.stage is not None and table.stage.dm.alive)
            status, r = await api(app, "POST", "/api/game/load", {"campaign": c.name, "save": "nothere"})
            check("load of a missing save is a clean error", status == 400 and "No such save" in r["error"])
            await table.stop()

        try:
            asyncio.run(run())
        finally:
            settings.SETTINGS_PATH, campaign.ACTIVE_PATH, campaign.CAMPAIGNS_DIR = old


def main() -> int:
    test_saves()
    test_sessions()
    test_server()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
