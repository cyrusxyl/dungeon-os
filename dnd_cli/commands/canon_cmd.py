"""canon command - deterministic canon.json bookkeeping for the AI DM"""

import json
import sys

from dnd_cli import canon


def _print(obj) -> int:
    print(json.dumps(obj, indent=2))
    return 0


def _run(campaign: str, fn) -> int:
    """Resolve the campaign dir, run fn(dir), print CampaignError/CanonError to stderr."""
    try:
        campaign_dir = canon.resolve_campaign_dir(campaign)
        return fn(campaign_dir)
    except canon.CampaignError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def execute_init(campaign: str) -> int:
    def go(campaign_dir):
        data = canon.init(campaign_dir)
        print(f"Created {canon.canon_path(campaign_dir)}")
        return _print(data)
    return _run(campaign, go)


def execute_validate(campaign: str) -> int:
    def go(campaign_dir):
        canon.load(campaign_dir)
        print(f"{canon.canon_path(campaign_dir)}: schema OK")
        return 0
    return _run(campaign, go)


def execute_show(campaign: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        return _print(data)
    return _run(campaign, go)


def execute_add_villain(campaign: str, name: str, goal: str, trait: str, escape_plan: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.add_villain(data, name, goal, trait, escape_plan or None)
        canon.save(campaign_dir, data)
        print(f"Villain {name!r} added.")
        return 0
    return _run(campaign, go)


def execute_add_clock(campaign: str, villain: str, clock: str, segments_total: int, description: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.add_clock(data, villain, clock, segments_total, description or None)
        canon.save(campaign_dir, data)
        print(f"Clock {clock!r} added to villain {villain!r}.")
        return 0
    return _run(campaign, go)


def execute_advance_clock(campaign: str, villain: str, clock: str, action_taken: bool, warning_ignored: bool) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        result = canon.advance_clock(data, villain, clock, action_taken, warning_ignored)
        canon.save(campaign_dir, data)
        return _print(result)
    return _run(campaign, go)


def execute_touch_clock(campaign: str, villain: str, clock: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.touch_clock(data, villain, clock)
        canon.save(campaign_dir, data)
        print(f"last_clock_touched set to {clock!r}")
        return 0
    return _run(campaign, go)


def execute_sweep_threads(campaign: str, appeared: list[str]) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        results = canon.sweep_threads(data, appeared)
        canon.save(campaign_dir, data)
        return _print(results)
    return _run(campaign, go)


def execute_add_thread(campaign: str, thread_id: str, description: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.add_thread(data, thread_id, description)
        canon.save(campaign_dir, data)
        print(f"Thread {thread_id!r} added.")
        return 0
    return _run(campaign, go)


def execute_close_thread(campaign: str, thread_id: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.close_thread(data, thread_id)
        canon.save(campaign_dir, data)
        print(f"Thread {thread_id!r} closed.")
        return 0
    return _run(campaign, go)


def execute_add_fact(campaign: str, session: int, source: str, fact: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.add_fact(data, session, source, fact)
        canon.save(campaign_dir, data)
        print("Fact recorded.")
        return 0
    return _run(campaign, go)


def execute_add_item(campaign: str, session: int, recipient: str, item: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.add_item(data, session, recipient, item)
        canon.save(campaign_dir, data)
        print("Item recorded.")
        return 0
    return _run(campaign, go)


def execute_add_promise(campaign: str, session: int, made_to: str, promise: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.add_promise(data, session, made_to, promise)
        canon.save(campaign_dir, data)
        print("Promise recorded.")
        return 0
    return _run(campaign, go)


def execute_fulfill_promise(campaign: str, index: int) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.fulfill_promise(data, index)
        canon.save(campaign_dir, data)
        print(f"Promise {index} marked fulfilled.")
        return 0
    return _run(campaign, go)


def execute_add_ruling(campaign: str, session: int, context: str, ruling: str) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        canon.add_ruling(data, session, context, ruling)
        canon.save(campaign_dir, data)
        print("Ruling recorded.")
        return 0
    return _run(campaign, go)


def execute_session_report(campaign: str, session: int) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
        report = canon.session_end_report(data, session)
        return _print(report)
    return _run(campaign, go)


def execute_close_session(campaign: str, session: int, force: bool) -> int:
    def go(campaign_dir):
        data = canon.load(campaign_dir)
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
