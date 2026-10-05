"""Saves: every campaign folder is its own git repository.

A save is a commit. The stage commits after each DM turn (`[auto]`), and the
player can name a save (`[save]`). Loading a save never loses the present: the
current state is committed first, and the load is a new commit on top that has
the tree of the old one. So the history only grows.

The git calls pass `--git-dir` and `--work-tree`. Without them, a campaign
that has no `.git` yet would use the repository around it (the dungeon-os
repo) and `git add -A` would stage the wrong files. `stage/events.ndjson` is in
the save on purpose: the stage replays it to show the scene.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path

from dnd_cli.campaign import CampaignError

AUTO, SAVE, LOAD = "[auto] ", "[save] ", "[load] "
_IDENTITY = ["-c", "user.name=DungeonOS", "-c", "user.email=dungeon-os@localhost", "-c", "commit.gpgsign=false"]
_lock = threading.Lock()  # one git call at a time: a load must not meet a half-done commit


class SaveError(CampaignError):
    pass


def available() -> bool:
    return shutil.which("git") is not None


def _git(campaign_dir: Path, *args: str) -> str:
    cmd = ["git", *_IDENTITY, f"--git-dir={campaign_dir / '.git'}", f"--work-tree={campaign_dir}", *args]
    run = subprocess.run(cmd, capture_output=True, text=True)
    if run.returncode:
        raise SaveError(f"git {args[0]}: {(run.stderr or run.stdout).strip()}")
    return run.stdout


def ensure_repo(campaign_dir: Path) -> None:
    with _lock:
        if not (campaign_dir / ".git").exists():
            subprocess.run(["git", "init", "-q", str(campaign_dir)], check=True, capture_output=True)


def _has_head(campaign_dir: Path) -> bool:
    try:
        _git(campaign_dir, "rev-parse", "-q", "--verify", "HEAD")
        return True
    except SaveError:
        return False


def _commit(campaign_dir: Path, message: str, force: bool = False) -> str | None:
    _git(campaign_dir, "add", "-A")
    if not force and _has_head(campaign_dir):
        try:
            _git(campaign_dir, "diff", "--cached", "--quiet")
            return None  # nothing changed since the last save
        except SaveError:
            pass  # exit code 1: there are changes
    _git(campaign_dir, "commit", "-q", "--allow-empty", "-m", " ".join(message.split())[:200])
    return _git(campaign_dir, "rev-parse", "HEAD").strip()


def save(campaign_dir: Path, kind: str, label: str, force: bool = False) -> str | None:
    """Commit the campaign as it is. Returns the save id, or None when nothing changed (unless `force`)."""
    ensure_repo(campaign_dir)
    with _lock:
        return _commit(campaign_dir, f"{kind}{label}", force)


def list_saves(campaign_dir: Path, limit: int = 100) -> list[dict]:
    """Newest first: id, time (unix), kind ("auto", "save" or "load") and label."""
    if not (campaign_dir / ".git").exists():
        return []
    with _lock:
        if not _has_head(campaign_dir):
            return []
        out = _git(campaign_dir, "log", f"-n{limit}", "--format=%H%x1f%ct%x1f%s")
    saves = []
    for line in out.splitlines():
        sha, when, subject = line.split("\x1f", 2)
        kind = next((k for k in (AUTO, SAVE, LOAD) if subject.startswith(k)), "")
        saves.append({"id": sha, "time": int(when), "kind": kind.strip("[] "), "label": subject[len(kind):]})
    return saves


def restore(campaign_dir: Path, save_id: str) -> None:
    """Make the campaign folder match a save. The DM must not run while this happens."""
    if not save_id.isalnum():
        raise SaveError("Bad save id.")
    ensure_repo(campaign_dir)
    with _lock:
        try:
            subject = _git(campaign_dir, "log", "-1", "--format=%s", save_id).strip()
        except SaveError:
            raise SaveError("No such save.") from None
        _commit(campaign_dir, f"{AUTO}before loading a save")
        _git(campaign_dir, "read-tree", "-u", "--reset", save_id)
        label = next((subject[len(k):] for k in (AUTO, SAVE, LOAD) if subject.startswith(k)), subject)
        _git(campaign_dir, "commit", "-q", "--allow-empty", "-m", f"{LOAD}{label}")
