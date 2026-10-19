"""Rules commands: encounter, attack, save, check, rest, and character item/gold/equip/xp/level-up.

Each prints one short line per result, so the DM spends its tokens on the
story, not on arithmetic. Logic lives in dnd_cli/combat/ and dnd_cli/sheet.py.
"""

from __future__ import annotations

import json

from dnd_cli import audit, character, effects, loot, sheet
from dnd_cli.combat import encounters, records, resolve, rolls, tracker, wounds
from dnd_cli import item as items
from dnd_cli.api import fetch as _api
from dnd_cli.commands.show_cmd import notify_stage, run_stage
from dnd_cli.dice import DiceError
from dnd_cli.errors import RulesError
from stage import arena, board, state as stage_state
from stage.beat import log_path

ERRORS = (RulesError, DiceError, character.CharacterError, arena.ArenaError)


def _out(lines: list[str]) -> int:
    print("\n".join(lines))
    return 0


def _with_state(campaign, fn) -> int:
    """Load state.json, run fn(campaign_dir, state) -> lines, save state, print."""
    def go(campaign_dir):
        state = tracker.load_state(campaign_dir)
        lines = fn(campaign_dir, state)
        tracker.save_state(campaign_dir, state)
        return _out(lines)
    return run_stage(campaign, go, *ERRORS)


# -- encounter ---------------------------------------------------------------


def execute_encounter(campaign, action: str, args) -> int:
    def fn(campaign_dir, state):
        if action == "start":
            pcs = None if args.pcs in (None, "all") else [p for p in args.pcs.split(",") if p]
            on_stage = stage_state.replay(log_path(campaign_dir))
            lines = encounters.start(campaign_dir, state, args.specs, pcs, stage=on_stage["actors"])
            if args.no_arena:
                return lines
            lines += board.start(campaign_dir, state, args.arena or [], on_stage)
            notify_stage(campaign_dir, {"type": "arena", "arena": state["active_encounter"]["arena"]})
            return lines
        if action == "add":
            lines = encounters.add(campaign_dir, state, args.specs)
            if arena_id := board.arena_id_of(state):
                a = arena.load(campaign_dir, arena_id)
                if board.sync_units(campaign_dir, state, a):
                    arena.save(campaign_dir, arena_id, a)
                    notify_stage(campaign_dir, {"type": "arena_updated", "arena": arena_id})
            return lines
        if action == "move":
            return _move(campaign_dir, state, args)
        if action == "next":
            return encounters.next_turn(campaign_dir, state)
        if action == "status":
            return encounters.status(campaign_dir, state)
        if action in ("damage", "heal"):
            amount, rolled = _amount(args.amount, action)
            line = (wounds.damage(campaign_dir, state, args.target, amount, args.type or "") if action == "damage"
                    else wounds.heal(campaign_dir, state, args.target, amount))
            # No roll shows for this, so the players get a line in the log. A creature's HP stays behind the screen.
            rec = records.combatant(campaign_dir, state, args.target)
            rolls.stage_feed(line if rec["kind"] == "pc" else f"{rec['name']} {'takes damage' if action == 'damage' else 'is healed'}.")
            return [rolled + line] if rolled else [line]
        if action == "condition":
            return [encounters.condition(state, args.target, args.op, args.name, args.rounds, args.save)]
        if action == "use":
            tracker.spend_turn(state, args.target, args.kind, not args.free)
            return [f"{args.target}: {args.kind} {'free' if args.free else 'used'}."]
        if action == "end":
            on_board = board.arena_id_of(state)
            left = board.outcome(campaign_dir, state, arena.load(campaign_dir, on_board)) if on_board else {}  # before the encounter is cleared
            lines = encounters.end(campaign_dir, state, award_xp=not args.no_xp, resolved=args.resolved)
            if on_board:
                notify_stage(campaign_dir, {"type": "arena_end", **left})
            return lines
        raise RulesError("encounter start|add|next|status|damage|heal|condition|use|end")
    return _with_state(campaign, fn)


def _move(campaign_dir, state: dict, args) -> list[str]:
    """A creature the DM plays walks on the board. The rules of the board apply: speed, blocked cells, reaction attacks."""
    arena_id, a = board.running(campaign_dir, state)
    if bool(args.to) == bool(args.toward):
        raise RulesError("give --to X,Y or --toward <id>.")
    if args.to:
        try:
            x, y = (int(n) for n in args.to.split(","))
        except ValueError:
            raise RulesError("--to is X,Y, for example --to 7,4.") from None
        target = (x, y)
    else:
        target = board.approach(campaign_dir, state, a, args.who, args.toward)
        if target is None:
            return [f"{args.who} cannot get nearer to {args.toward} this turn."]
    result = board.move(campaign_dir, state, a, args.who, target)
    arena.save(campaign_dir, arena_id, a)
    notify_stage(campaign_dir, {"type": "arena_updated", "arena": arena_id})
    x, y = board.pos(a, args.who)
    lines = result["lines"] + [f"{args.who} walks to {x},{y} ({board.feet_left(state, records.combatant(campaign_dir, state, args.who))} ft left)."]
    if result["pending"]:
        lines.append(f"The walk stops: {result['pending']['who']}'s player is asked for a reaction. The stage finishes the walk.")
    return lines


def _amount(text: str, label: str) -> tuple[int, str]:
    """A number, or dice (`1d8+3`) rolled and shown on the stage."""
    if text.lstrip("-").isdigit():
        return int(text), ""
    from dnd_cli import dice

    total, groups = dice.roll(text)
    rolls.stage_roll(f"{label} {text}", total, groups)
    return total, f"{text} = {total}: "


# -- rolls -------------------------------------------------------------------


def execute_attack(campaign, args) -> int:
    def fn(campaign_dir, state):
        cost = None if args.cost == "free" else args.cost
        if board.arena_id_of(state) and not args.damage:
            # On a board, reach, sight and cover decide (an improvised attack with --damage is the DM's own ruling).
            _, a = board.running(campaign_dir, state)
            return board.attack(campaign_dir, state, a, args.attacker, args.weapon, args.target, cost=cost,
                                adv=args.adv, dis=args.dis, bonus=args.bonus, secret=args.secret, catch_up=args.cost != "reaction",
                                smite=args.smite)
        return resolve.attack(
            campaign_dir, state, args.attacker, args.weapon, args.target, adv=args.adv, dis=args.dis,
            damage_expr=args.damage, damage_type=args.type or "", bonus=args.bonus, secret=args.secret, cost=cost,
            catch_up=args.cost != "reaction", smite=args.smite)
    return _with_state(campaign, fn)


def execute_save(campaign, args) -> int:
    # The last target that is an ability name is the ability: `save goblin#1 dex --dc 13`.
    targets, ability = args.targets, args.ability
    if ability is None and len(targets) > 1 and targets[-1].lower() in (*records.ABILITIES, *records.SHORT):
        targets, ability = targets[:-1], targets[-1]
    return _with_state(campaign, lambda c, s: resolve.save(
        c, s, targets, ability, args.dc, damage_expr=args.damage, damage_type=args.type or "",
        half=args.half, source=args.source, adv=args.adv, dis=args.dis, secret=args.secret, hide_dc=args.hide_dc))


def execute_check(campaign, args) -> int:
    if len(args.who) < 2:
        raise RulesError("usage: check <who...|all> <skill|ability|death> [--dc N]")
    names, what = args.who[:-1], args.who[-1]  # the last word is what is rolled

    def fn(campaign_dir, state):
        who = tracker.party(campaign_dir, state) if names == ["all"] else names
        return resolve.check(campaign_dir, state, who, what, dc=args.dc, adv=args.adv, dis=args.dis,
                            passive=args.passive, secret=args.secret, hide_dc=args.hide_dc)
    return _with_state(campaign, fn)


# -- effects -----------------------------------------------------------------


def execute_effect(campaign, op: str, who: str | None, name: str | None) -> int:
    def fn(campaign_dir):
        if op == "list":
            held = effects.load(campaign_dir)
            held = {who: held.get(who, [])} if who else held
            return _out([f"{cid}: {', '.join(ids)}" for cid, ids in held.items() if ids] or ["No active effects."])
        if not who or not name:
            raise RulesError(f"effect {op} <who> <effect>. Effects: {', '.join(effects.PRESETS)}.")
        if not character.character_path(campaign_dir, who).exists():
            raise RulesError(f"no character {who!r}.")
        try:
            (effects.add if op == "add" else effects.remove)(campaign_dir, who, name)
        except ValueError as e:
            raise RulesError(str(e)) from e
        spec = effects.PRESETS[name]
        return _out([f"{who}: {spec['label']} {'on' if op == 'add' else 'off'}"
                     + (f" — {spec['info']}; " + ("the next matching roll uses it." if spec["use"] == "next"
                                                  else "it stays until you remove it.") if op == "add" else ".")])
    return run_stage(campaign, fn, *ERRORS)


# -- rests -------------------------------------------------------------------


def execute_rest(campaign, kind: str, who: list[str], spend: list[str]) -> int:
    def fn(campaign_dir, state):
        names = tracker.party(campaign_dir, state) if not who or who == ["all"] else who
        dice_for = {n: int(k) for n, _, k in (s.partition(":") for s in spend)}
        lines = []
        for name in names:
            data = character.load(campaign_dir, name)
            hd = data.setdefault("hit_dice", {"total": data["level"], "remaining": data["level"]})
            if "type" not in hd:  # the class's hit die, once
                hd["type"] = f"d{_api('classes/' + data['class'].split()[0].lower()).get('hit_die', 8)}"
            line = sheet.long_rest(data) if kind == "long" else sheet.short_rest(data, dice_for.get(name, 0))
            character.save(campaign_dir, name, data)
            lines.append(line)
        return lines
    return _with_state(campaign, fn)


# -- character sheet ---------------------------------------------------------


def _edit_sheet(campaign, name: str, fn) -> int:
    def go(campaign_dir):
        data = character.load(campaign_dir, name)
        lines = fn(campaign_dir, data)
        character.save(campaign_dir, name, data)
        return _out(lines)
    return run_stage(campaign, go, *ERRORS)


def _equip(data: dict, name: str, proficient: bool) -> list[str]:
    """Wear or wield an item. One that is not in the inventory is made from the 5e API item of that name or index."""
    found = items.find(data, name)
    if not found:
        return [items.equip_base(data, _api(f"equipment/{loot.api_index(name)}"), proficient)]
    line = found.equip(data, _api(f"equipment/{loot.api_index(found.base)}") if found.needs_base else None, proficient)
    return [line, *filter(None, [found.weapon_warning(effects.PRESETS)])]


def _purse(data: dict, name: str, qty: int, sign: int) -> list[str] | None:
    """`item add|remove` of Gold Pieces goes through `sheet.gold`: one purse path, the same checks. None for any other item."""
    if name.lower() != items.GOLD.lower():
        return None
    if qty < 1:
        raise RulesError("quantity must be 1 or more.")
    return [sheet.gold(data, sign * qty)]


def execute_item_add(args) -> int:
    """`--perk` is what makes the item special, in the DM's words (a catalog perk in it adds a hint). `--effects` is a list of
    gear effect presets (comma-separated) that the item gives while it is equipped. `--base` names the item the gear is made
    from; without it the base is found in the item name ("+1 Longsword of Flame" is a Longsword)."""
    def fn(campaign_dir, data):
        if purse := _purse(data, args.item, args.qty, 1):
            return purse
        if args.rarity and args.rarity not in loot.RARITIES:
            raise RulesError(f"rarity is one of {', '.join(loot.RARITIES)}.")
        ids = effects.gear_presets(args.effects)
        kind = loot.base_of(args.item, args.base)
        gear = {"effects": ids, **({"type": kind[0], "base": kind[1]} if kind else {})}
        lines = [items.add(data, args.item, args.qty, args.perk, args.rarity, **gear)] + loot.hints(args.perk, ids)
        if args.canon:
            from dnd_cli import canon
            c = canon.load(campaign_dir)
            canon.add_item(c, c.get("last_session_written", 0) + 1, data["name"],
                           args.item if args.qty == 1 else f"{args.item} x{args.qty}")
            canon.save(campaign_dir, c)
            lines.append("recorded in canon (items)")
        return lines
    return _edit_sheet(args.campaign, args.name, fn)


def execute_item_remove(args) -> int:
    return _edit_sheet(args.campaign, args.name,
                       lambda c, data: _purse(data, args.item, args.qty, -1) or [items.remove(data, args.item, args.qty)])


def execute_item_equip(args) -> int:
    return _edit_sheet(args.campaign, args.name, lambda c, data: _equip(data, args.item, not args.not_proficient))


def execute_item_unequip(args) -> int:
    return _edit_sheet(args.campaign, args.name, lambda c, data: [items.get(data, args.item).unequip(data)])


def execute_item_profile(args) -> int:
    def fn(campaign_dir, data):
        try:
            return [items.set_profile(data, args.item, json.loads(args.profile))]
        except json.JSONDecodeError:
            raise RulesError("give --profile as JSON, for example '{\"kind\": \"heal\", \"heal\": \"2d4\"}'.") from None
    return _edit_sheet(args.campaign, args.name, fn)


def execute_loot_roll(cr: float, kind: str, seed: int | None, creature_type: str) -> int:
    return _out(loot.lines(loot.roll(cr, kind, seed, creature_type)))


def execute_gold(campaign, name: str, delta: str) -> int:
    try:
        amount = int(delta)
    except ValueError:
        print("Error: give gold as +N or -N, for example +25.")
        return 1
    return _edit_sheet(campaign, name, lambda c, data: [sheet.gold(data, amount)])


def execute_xp(campaign, names: list[str], amount: int) -> int:
    def go(campaign_dir):
        state = tracker.load_state(campaign_dir)
        who = tracker.party(campaign_dir, state) if names == ["all"] else names
        lines = []
        for n in who:
            data = character.load(campaign_dir, n)
            lines.append(sheet.add_xp(data, amount))
            character.save(campaign_dir, n, data)
        return _out(lines)
    return run_stage(campaign, go, *ERRORS)


def _asi(text: str | None) -> dict:
    out = {}
    for part in filter(None, (text or "").split(",")):
        abil, sign, n = part.partition("+")
        if not sign or not n.isdigit():
            raise RulesError(f"--asi {text!r}: write it like str+2 or str+1,dex+1.")
        out[records.ability(abil)] = out.get(records.ability(abil), 0) + int(n)
    if sum(out.values()) > 2:
        raise RulesError("an ability score improvement adds at most 2 points (a half-feat adds 1).")
    return out


def execute_level_up(campaign, name: str, hp_mode: str, asi: str | None) -> int:
    def fn(campaign_dir, data):
        cls = data["class"].split()[0].lower()
        level = _api(f"classes/{cls}/levels/{data['level'] + 1}")
        class_data = _api(f"classes/{cls}")
        hit_die = class_data.get("hit_die", 8)
        feats = []
        for f in level.get("features", []):
            desc = (_api(f"features/{f['index']}").get("desc") or [""])[0]
            feats.append({"name": f["name"], "description": desc[:300]})
        if any(f["name"].startswith("Ability Score Improvement") for f in feats) and asi is None:
            raise RulesError("this level gives an Ability Score Improvement. Ask the player, then run it with "
                                    "--asi str+2 (or --asi str+1,dex+1), or --asi none if they take a feat instead.")
        lines = sheet.level_up(data, level, hit_die, hp_mode, _asi(None if asi == "none" else asi), feats,
                               class_data=class_data)
        problems = audit.audit(data, _api)
        return lines + ([audit.summary(problems)] if problems else [])
    return _edit_sheet(campaign, name, fn)


def execute_new_character(campaign, char_id: str, args) -> int:
    from dnd_cli import creation

    def go(campaign_dir):
        return _out(creation.create(
            campaign_dir, _api, char_id, player_name=args.player_name, player=args.player, name=args.name,
            race=args.race, subrace=args.subrace, cls=args.char_class, background=args.background,
            scores=args.scores, assign=args.assign, skills=args.skills, background_skills=args.background_skills,
            cantrips=args.cantrips, spells=args.spells, equipment=args.equipment, alignment=args.alignment,
            languages=args.languages, bonus_abilities=args.bonus_abilities,
            background_bonus=args.background_bonus))
    return run_stage(campaign, go, *ERRORS)
