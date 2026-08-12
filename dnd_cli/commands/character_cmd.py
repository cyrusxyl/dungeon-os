"""character command - deterministic HP and spell-slot bookkeeping for the AI DM"""

import json
import sys

from dnd_cli import canon, character


def _print(obj) -> int:
    print(json.dumps(obj, indent=2))
    return 0


def _run(campaign: str, fn) -> int:
    """Resolve the campaign dir, run fn(dir), print CampaignError to stderr."""
    try:
        campaign_dir = canon.resolve_campaign_dir(campaign)
        return fn(campaign_dir)
    except character.CampaignError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def execute_show(campaign: str, name: str) -> int:
    def go(campaign_dir):
        data = character.load(campaign_dir, name)
        return _print(data)
    return _run(campaign, go)


def execute_validate(campaign: str, name: str) -> int:
    def go(campaign_dir):
        character.load(campaign_dir, name)
        print(f"{character.character_path(campaign_dir, name)}: schema OK")
        return 0
    return _run(campaign, go)


def execute_apply_damage(campaign: str, name: str, amount: int) -> int:
    def go(campaign_dir):
        data = character.load(campaign_dir, name)
        result = character.apply_damage(data, amount)
        character.save(campaign_dir, name, data)
        return _print(result)
    return _run(campaign, go)


def execute_heal(campaign: str, name: str, amount: int) -> int:
    def go(campaign_dir):
        data = character.load(campaign_dir, name)
        result = character.heal(data, amount)
        character.save(campaign_dir, name, data)
        return _print(result)
    return _run(campaign, go)


def execute_add_temp_hp(campaign: str, name: str, amount: int) -> int:
    def go(campaign_dir):
        data = character.load(campaign_dir, name)
        result = character.add_temp_hp(data, amount)
        character.save(campaign_dir, name, data)
        return _print(result)
    return _run(campaign, go)


def execute_cast(campaign: str, name: str, level: int) -> int:
    def go(campaign_dir):
        data = character.load(campaign_dir, name)
        result = character.cast_spell(data, level)
        character.save(campaign_dir, name, data)
        return _print(result)
    return _run(campaign, go)


def execute_restore_slots(campaign: str, name: str, level) -> int:
    def go(campaign_dir):
        data = character.load(campaign_dir, name)
        result = character.restore_slots(data, level)
        character.save(campaign_dir, name, data)
        return _print(result)
    return _run(campaign, go)
