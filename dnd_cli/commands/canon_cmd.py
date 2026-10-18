"""canon command - deterministic canon.json bookkeeping for the AI DM"""

import json
import sys

from dnd_cli import canon
from dnd_cli.commands.show_cmd import run_stage


def _print(obj) -> int:
    print(json.dumps(obj, separators=(",", ":")))
    return 0


def _run(campaign: str | None | None, fn) -> int:
    """Run fn(campaign_dir) on the campaign (default: the one the stage shows, else the active one); print its errors."""
    return run_stage(campaign, fn)


def _session(data: dict, session: int | None) -> int:
    """The session given, else the one being played: `last_session_written` + 1."""
    return session if session is not None else (data.get("last_session_written") or 0) + 1


def execute_init(campaign: str | None) -> int:
    def go(campaign_dir):
        data = canon.init(campaign_dir)
        print(f"Created {canon.canon_path(campaign_dir)}")
        return _print(data)
    return _run(campaign, go)


def execute_validate(campaign: str | None) -> int:
    def go(campaign_dir):
        canon.load(campaign_dir)
        print(f"{canon.canon_path(campaign_dir)}: schema OK")
        return 0
    return _run(campaign, go)


def execute_show(campaign: str | None) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        return _print(data)
    return _run(campaign, go)


def execute_add_villain(campaign: str | None, name: str, goal: str, trait: str, escape_plan: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.add_villain(data, name, goal, trait, escape_plan or None)
        canon.save(campaign_dir, data)
        print(f"Villain {name!r} added.")
        return 0
    return _run(campaign, go)


def execute_add_clock(campaign: str | None, villain: str, clock: str, segments_total: int, description: str,
                      waiting: bool = False) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.add_clock(data, villain, clock, segments_total, description or None, waiting)
        canon.save(campaign_dir, data)
        print(f"Clock {clock!r} added to villain {villain!r}" + (" (waiting for its trigger)." if waiting else "."))
        return 0
    return _run(campaign, go)


def execute_clock_status(campaign: str | None, villain: str, clock: str, status: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        c = canon.set_clock_status(data, villain, clock, status)
        canon.save(campaign_dir, data)
        print(f"Clock {clock!r}: {c['status']} ({c['segments_filled']}/{c['segments_total']}).")
        return 0
    return _run(campaign, go)


def execute_advance_clock(campaign: str | None, villain: str, clock: str, action_taken: bool, warning_ignored: bool) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        result = canon.advance_clock(data, villain, clock, action_taken, warning_ignored)
        canon.save(campaign_dir, data)
        return _print(result)
    return _run(campaign, go)


def execute_touch_clock(campaign: str | None, villain: str, clock: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.touch_clock(data, villain, clock)
        canon.save(campaign_dir, data)
        print(f"last_clock_touched set to {clock!r}")
        return 0
    return _run(campaign, go)


def execute_sweep_threads(campaign: str | None, appeared: str) -> int:
    """`appeared`: thread ids, comma-separated."""
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        results = canon.sweep_threads(data, [t.strip() for t in appeared.split(",") if t.strip()])
        canon.save(campaign_dir, data)
        return _print(results)
    return _run(campaign, go)


def execute_add_thread(campaign: str | None, thread_id: str, description: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.add_thread(data, thread_id, description)
        canon.save(campaign_dir, data)
        print(f"Thread {thread_id!r} added.")
        return 0
    return _run(campaign, go)


def execute_close_thread(campaign: str | None, thread_id: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.close_thread(data, thread_id)
        canon.save(campaign_dir, data)
        print(f"Thread {thread_id!r} closed.")
        return 0
    return _run(campaign, go)


def execute_add_fact(campaign: str | None, session: int | None, source: str, fact: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.add_fact(data, _session(data, session), source, fact)
        canon.save(campaign_dir, data)
        print("Fact recorded.")
        return 0
    return _run(campaign, go)


def execute_add_item(campaign: str | None, session: int | None, recipient: str, item: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.add_item(data, _session(data, session), recipient, item)
        canon.save(campaign_dir, data)
        print("Item recorded.")
        return 0
    return _run(campaign, go)


def execute_add_promise(campaign: str | None, session: int | None, made_to: str, promise: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.add_promise(data, _session(data, session), made_to, promise)
        canon.save(campaign_dir, data)
        print("Promise recorded.")
        return 0
    return _run(campaign, go)


def execute_fulfill_promise(campaign: str | None, index: int) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.fulfill_promise(data, index)
        canon.save(campaign_dir, data)
        print(f"Promise {index} marked fulfilled.")
        return 0
    return _run(campaign, go)


def execute_add_ruling(campaign: str | None, session: int | None, context: str, ruling: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.add_ruling(data, _session(data, session), context, ruling)
        canon.save(campaign_dir, data)
        print("Ruling recorded.")
        return 0
    return _run(campaign, go)


def execute_session_report(campaign: str | None, session: int | None) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        report = canon.session_end_report(data, _session(data, session))
        return _print(report)
    return _run(campaign, go)


def execute_close_session(campaign: str | None, session: int | None, force: bool) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        session = _session(data, session)
        report = canon.session_end_report(data, session)
        if report["warnings"] and not force:
            print(json.dumps(report, indent=2), file=sys.stderr)
            print(
                "Refusing to close the session: warnings above. "
                "Fix them, or re-run with --force to close anyway.",
                file=sys.stderr,
            )
            return 1
        canon.close_session(data, session)
        canon.save(campaign_dir, data)
        print(f"Session {session} closed. last_session_written={session}")
        return 0
    return _run(campaign, go)
