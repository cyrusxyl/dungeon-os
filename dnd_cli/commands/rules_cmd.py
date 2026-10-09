"""Rules commands: encounter, attack, save, check, rest, and character item/gold/equip/xp/level-up.

Each prints one short line per result, so the DM spends its tokens on the
story, not on arithmetic. Logic lives in dnd_cli/combat.py and dnd_cli/sheet.py.
"""

from __future__ import annotations

from dnd_cli import character, combat, effects, sheet
from dnd_cli.api import api_get
from dnd_cli.commands.show_cmd import notify_stage, run_stage
from dnd_cli.dice import DiceError
from stage import arena, board, state as stage_state
from stage.beat import log_path

ERRORS = (combat.RulesError, DiceError, character.CharacterError, arena.ArenaError)


def _out(lines: list[str]) -> int:
    print("\n".join(lines))
    return 0


def _with_state(campaign, fn) -> int:
    """Load state.json, run fn(campaign_dir, state) -> lines, save state, print."""
    def go(campaign_dir):
        state = combat.load_state(campaign_dir)
        lines = fn(campaign_dir, state)
        combat.save_state(campaign_dir, state)
        return _out(lines)
    return run_stage(campaign, go, *ERRORS)


# -- encounter ---------------------------------------------------------------


def execute_encounter(campaign, action: str, args) -> int:
    def fn(campaign_dir, state):
        if action == "start":
            pcs = None if args.pcs in (None, "all") else [p for p in args.pcs.split(",") if p]
            lines = combat.start(campaign_dir, state, args.specs, pcs)
            if args.arena is None:
                return lines
            lines += board.start(campaign_dir, state, args.arena, stage_state.replay(log_path(campaign_dir)))
            notify_stage(campaign_dir, {"type": "arena", "arena": state["active_encounter"]["arena"]})
            return lines
        if action == "add":
            return combat.add(campaign_dir, state, args.specs)
        if action == "next":
            return combat.next_turn(campaign_dir, state)
        if action == "status":
            return combat.status(campaign_dir, state)
        if action in ("damage", "heal"):
            amount, rolled = _amount(args.amount, action)
            line = (combat.damage(campaign_dir, state, args.target, amount, args.type or "") if action == "damage"
                    else combat.heal(campaign_dir, state, args.target, amount))
            return [rolled + line] if rolled else [line]
        if action == "condition":
            return [combat.condition(state, args.target, args.op, args.name, args.rounds, args.save)]
        if action == "use":
            combat.spend_turn(state, args.target, args.kind, not args.free)
            return [f"{args.target}: {args.kind} {'free' if args.free else 'used'}."]
        if action == "end":
            on_board = (state.get("active_encounter") or {}).get("arena")
            lines = combat.end(campaign_dir, state, award_xp=not args.no_xp)
            if on_board:
                notify_stage(campaign_dir, {"type": "arena_end"})
            return lines
        raise combat.RulesError("encounter start|add|next|status|damage|heal|condition|use|end")
    return _with_state(campaign, fn)


def _amount(text: str, label: str) -> tuple[int, str]:
    """A number, or dice (`1d8+3`) rolled and shown on the stage."""
    if text.lstrip("-").isdigit():
        return int(text), ""
    from dnd_cli import dice

    total, groups = dice.roll(text)
    combat.stage_roll(f"{label} {text}", total, groups)
    return total, f"{text} = {total}: "


# -- rolls -------------------------------------------------------------------


def execute_attack(campaign, args) -> int:
    return _with_state(campaign, lambda c, s: combat.attack(
        c, s, args.attacker, args.weapon, args.target, adv=args.adv, dis=args.dis,
        damage_expr=args.damage, damage_type=args.type or "", bonus=args.bonus, secret=args.secret,
        cost=None if args.cost == "free" else args.cost))


def execute_save(campaign, args) -> int:
    return _with_state(campaign, lambda c, s: combat.save(
        c, s, args.targets, args.ability, args.dc, damage_expr=args.damage, damage_type=args.type or "",
        half=args.half, source=args.source, adv=args.adv, dis=args.dis, secret=args.secret, hide_dc=args.hide_dc))


def execute_check(campaign, args) -> int:
    def fn(campaign_dir, state):
        who = combat.party(campaign_dir, state) if args.who == ["all"] else args.who
        return combat.check(campaign_dir, state, who, args.what, dc=args.dc, adv=args.adv, dis=args.dis,
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
            raise combat.RulesError(f"effect {op} <who> <effect>. Effects: {', '.join(effects.PRESETS)}.")
        if not character.character_path(campaign_dir, who).exists():
            raise combat.RulesError(f"no character {who!r}.")
        try:
            (effects.add if op == "add" else effects.remove)(campaign_dir, who, name)
        except ValueError as e:
            raise combat.RulesError(str(e)) from e
        spec = effects.PRESETS[name]
        return _out([f"{who}: {spec['label']} {'on' if op == 'add' else 'off'}"
                     + (f" — {spec['info']}; the next matching roll uses it." if op == "add" else ".")])
    return run_stage(campaign, fn, *ERRORS)


# -- rests -------------------------------------------------------------------


def execute_rest(campaign, kind: str, who: list[str], spend: list[str]) -> int:
    def fn(campaign_dir, state):
        names = combat.party(campaign_dir, state) if not who or who == ["all"] else who
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


def execute_item(campaign, name: str, op: str, item: str, qty: int, record_canon: bool) -> int:
    def fn(campaign_dir, data):
        if op == "remove":
            return [sheet.remove_item(data, item, qty)]
        lines = [sheet.add_item(data, item, qty)]
        if record_canon:
            from dnd_cli import canon
            c = canon.load(campaign_dir)
            canon.add_item(c, c.get("last_session_written", 0) + 1, data["name"], item if qty == 1 else f"{item} x{qty}")
            canon.save(campaign_dir, c)
            lines.append("recorded in canon (items)")
        return lines
    return _edit_sheet(campaign, name, fn)


def execute_gold(campaign, name: str, delta: str) -> int:
    try:
        amount = int(delta)
    except ValueError:
        print("Error: give gold as +N or -N, for example +25.")
        return 1
    return _edit_sheet(campaign, name, lambda c, data: [sheet.gold(data, amount)])


def _api(endpoint: str) -> dict:
    data, error, _ = api_get(endpoint)
    if error or not data:
        raise combat.RulesError(f"no {endpoint} in the 5e API. Find the index with: uv run dnd-cli search "
                                f"{endpoint.split('/')[0]} --name {endpoint.split('/')[-1].split('-')[0]}")
    return data


def execute_equip(campaign, name: str, index: str, proficient: bool) -> int:
    return _edit_sheet(campaign, name, lambda c, data: sheet.equip(data, _api(f"equipment/{index}"), proficient))


def execute_xp(campaign, names: list[str], amount: int) -> int:
    def go(campaign_dir):
        state = combat.load_state(campaign_dir)
        who = combat.party(campaign_dir, state) if names == ["all"] else names
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
            raise combat.RulesError(f"--asi {text!r}: write it like str+2 or str+1,dex+1.")
        out[combat.ability(abil)] = out.get(combat.ability(abil), 0) + int(n)
    if sum(out.values()) > 2:
        raise combat.RulesError("an ability score improvement adds at most 2 points (a half-feat adds 1).")
    return out


def execute_level_up(campaign, name: str, hp_mode: str, asi: str | None) -> int:
    def fn(campaign_dir, data):
        cls = data["class"].split()[0].lower()
        level = _api(f"classes/{cls}/levels/{data['level'] + 1}")
        hit_die = _api(f"classes/{cls}").get("hit_die", 8)
        feats = []
        for f in level.get("features", []):
            desc = (_api(f"features/{f['index']}").get("desc") or [""])[0]
            feats.append({"name": f["name"], "description": desc[:300]})
        if any(f["name"].startswith("Ability Score Improvement") for f in feats) and asi is None:
            raise combat.RulesError("this level gives an Ability Score Improvement. Ask the player, then run it with "
                                    "--asi str+2 (or --asi str+1,dex+1), or --asi none if they take a feat instead.")
        return sheet.level_up(data, level, hit_die, hp_mode, _asi(None if asi == "none" else asi), feats)
    return _edit_sheet(campaign, name, fn)


def execute_new_character(campaign, char_id: str, args) -> int:
    from dnd_cli import creation

    def go(campaign_dir):
        return _out(creation.create(
            campaign_dir, _api, char_id, player_name=args.player_name, player=args.player, name=args.name,
            race=args.race, subrace=args.subrace, cls=args.char_class, background=args.background,
            scores=args.scores, assign=args.assign, skills=args.skills, background_skills=args.background_skills,
            cantrips=args.cantrips, spells=args.spells, equipment=args.equipment, alignment=args.alignment,
            languages=args.languages, bonus_abilities=args.bonus_abilities))
    return run_stage(campaign, go, *ERRORS)
