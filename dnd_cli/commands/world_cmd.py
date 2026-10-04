"""World commands: state time/set, quest, npc, faction.

Each saves its own change and prints one short line. Logic lives in dnd_cli/world.py.
"""

from __future__ import annotations

from dnd_cli import world
from dnd_cli.commands.show_cmd import run_stage
from stage.files import read_json, write_json


def _with_state(campaign, fn) -> int:
    """Read state.json, run fn(campaign_dir, state) -> lines, save state, print."""
    def go(campaign_dir):
        path = campaign_dir / "state.json"
        state = read_json(path)
        if state is None:
            raise world.WorldError(f"no readable state.json in {campaign_dir}.")
        lines = fn(campaign_dir, state)
        write_json(path, state, indent=2)
        print("\n".join(lines))
        return 0
    return run_stage(campaign, go, world.WorldError)


def _file_cmd(campaign, fn) -> int:
    """For commands that change only an NPC file."""
    def go(campaign_dir):
        print(fn(campaign_dir))
        return 0
    return run_stage(campaign, go, world.WorldError)


def execute_state(campaign, args) -> int:
    if args.state_command == "time":
        return _with_state(campaign, lambda c, s: [world.set_time(s, args.value)])
    return _with_state(campaign, lambda c, s: [world.state_set(s, args.tokens)])


def execute_quest(campaign, args) -> int:
    act = args.quest_command
    fns = {
        "add": lambda c, s: [world.quest_add(c, s, args.id, args.title, args.description, args.objective, args.reward)],
        "progress": lambda c, s: [world.quest_progress(c, s, args.id, args.text)],
        "done": lambda c, s: [world.quest_done(c, s, args.id, args.objective)],
        "fail": lambda c, s: [world.quest_fail(c, s, args.id)],
        "show": lambda c, s: world.quest_lines(c, s),
    }
    return _with_state(campaign, fns[act])


def execute_npc(campaign, args) -> int:
    act = args.npc_command
    if act == "set":
        return _file_cmd(campaign, lambda c: world.npc_set(c, args.id, args.tokens))
    if act == "note":
        return _file_cmd(campaign, lambda c: world.npc_note(c, args.id, args.text))
    return _file_cmd(campaign, lambda c: world.npc_attitude(c, args.id, args.move))


def execute_faction(campaign, args) -> int:
    return _with_state(campaign, lambda c, s: [world.faction(s, args.name, args.delta)])
