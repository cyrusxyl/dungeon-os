"""character command - deterministic HP and spell-slot bookkeeping for the AI DM"""

import json
import sys

from dnd_cli import canon, character
from dnd_cli.combat import stage_feed


def _print(obj) -> int:
    print(json.dumps(obj, separators=(",", ":")))
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


def execute_validate(campaign: str, name: str, fix: bool = False) -> int:
    from dnd_cli import audit
    from dnd_cli.commands.rules_cmd import _api

    def go(campaign_dir):
        data = character.load(campaign_dir, name)
        print(f"{character.character_path(campaign_dir, name)}: schema OK")
        if fix:
            fixed = audit.repair(data, _api)
            if any(line.startswith("cannot check") for line in fixed):
                print(f"warning: {fixed[0]}", file=sys.stderr)
                print("nothing fixed")
                return 1
            if fixed:
                character.save(campaign_dir, name, data)
            print("\n".join(f"fixed: {line}" for line in fixed) or "nothing to fix")
        problems = audit.audit(data, _api)
        if problems:
            print(audit.summary(problems))
        return 1 if any(not p.startswith("cannot check") for p in problems) else 0
    return _run(campaign, go)


def execute_apply_damage(campaign: str, name: str, amount: int) -> int:
    def go(campaign_dir):
        data = character.load(campaign_dir, name)
        result = character.apply_damage(data, amount)
        character.save(campaign_dir, name, data)
        stage_feed(f"{name} takes {amount}: HP {result['hp_current']}/{result['hp_max']}")  # no roll shows for this
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


def execute_use(campaign: str, name: str, resource: str, delta: int) -> int:
    from dnd_cli import resources

    def go(campaign_dir):
        if delta == 0:
            raise character.CharacterError("--amount must be 1 or more.")
        data = character.load(campaign_dir, name)
        try:
            res = resources.spend(data, resource, delta)
        except KeyError:
            names = ", ".join(r["name"] for r in resources.for_sheet(data)) or "none"
            raise character.CharacterError(f"{name} has no resource {resource!r}. Resources: {names}.") from None
        except ValueError as e:
            raise character.CharacterError(f"{name}: {e}") from None
        character.save(campaign_dir, name, data)
        print(f"{name}: {res['name']} {res['max'] - res['used']}/{res['max']} left")
        return 0
    return _run(campaign, go)


def execute_set(campaign: str, name: str, field: str, value: str) -> int:
    """Record a subclass or fighting style choice. `character.save` validates the sheet."""
    def go(campaign_dir):
        data = character.load(campaign_dir, name)
        data[field] = value
        character.save(campaign_dir, name, data)
        print(f"{name}: {field} is now {value}")
        return 0
    return _run(campaign, go)


def execute_add(campaign: str, name: str, kind: str, value: str, prepared: bool = False, desc: str = "") -> int:
    """Add a spell (known, or prepared with --prepared) or a feat. `character.save` validates the sheet."""
    def go(campaign_dir):
        data = character.load(campaign_dir, name)
        if kind == "spell":
            key = "spells_prepared" if prepared else "spells_known"
            sc = data.get("spellcasting")
            if not sc:
                raise character.CharacterError(f"{name} has no spellcasting.")
            if value.lower() in (s.lower() for s in sc.get(key, [])):
                raise character.CharacterError(f"{name} already has {value} in {key}.")
            sc.setdefault(key, []).append(value)
        else:
            feats = data.setdefault("features_and_traits", [])
            if value.lower() in (f.get("name", "").lower() for f in feats):
                raise character.CharacterError(f"{name} already has {value}.")
            feats.append({"name": value, "description": desc})
        character.save(campaign_dir, name, data)
        print(f"{name}: added {kind} {value}")
        return 0
    return _run(campaign, go)


def execute_restore_slots(campaign: str, name: str, level) -> int:
    def go(campaign_dir):
        data = character.load(campaign_dir, name)
        result = character.restore_slots(data, level)
        character.save(campaign_dir, name, data)
        return _print(result)
    return _run(campaign, go)
