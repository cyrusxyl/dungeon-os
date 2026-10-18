"""Attacks, saves, checks and death saves."""

from __future__ import annotations

import random
from pathlib import Path

from dnd_cli import character, dice, effects
from dnd_cli.errors import RulesError
from dnd_cli.combat.encounters import advance_to, condition
from dnd_cli.combat.records import SKILLS, ability, combatant, save_bonus
from dnd_cli.combat.rolls import check_spec, check_tiles, d20_groups, fx_note, roll_d20, roll_detail, roll_entry, secret_feed, shown_damage, stage_roll
from dnd_cli.combat.smite import can_smite, smite_check, smite_hit
from dnd_cli.combat.tracker import encounter, feud, has_condition, in_combat, spend_turn
from dnd_cli.combat.wounds import damage


def _find_attack(rec: dict, name: str) -> dict:
    wanted = name.lower()
    for a in rec["attacks"]:
        if a["name"].lower() == wanted:
            return a
    for a in rec["attacks"]:
        if wanted in a["name"].lower():
            return a
    names = ", ".join(a["name"] for a in rec["attacks"]) or "none"
    raise RulesError(f"{rec['id']} has no attack {name!r}. Attacks: {names}.")


def attack(campaign_dir: Path, state: dict, attacker: str, weapon: str, target: str, adv: bool = False,
           dis: bool = False, damage_expr: str | None = None, damage_type: str = "", bonus: int = 0,
           secret: bool = False, rng=None, skip=(), cost: str | None = "action", catch_up: bool = True,
           smite: int | None = None, melee: bool | None = None) -> list[str]:
    """One attack roll against AC; on a hit, roll and apply the damage. Crits double the dice.

    `smite` is a spell slot level a paladin spends on a hit for Divine Smite (a melee weapon attack only). Without it,
    a melee hit that the paladin could smite leaves `pending_smite` in the encounter for the stage to offer.
    `melee` says whether this is a melee attack; by default a weapon with a reach is.

    The attack uses the attacker's `cost` (action, bonus or reaction; None for a free attack). A multiattack
    is several attacks for one action. A dodging target gives disadvantage; a hidden attacker gets
    advantage and is seen afterwards.
    """
    rng = rng or random
    a_rec = combatant(campaign_dir, state, attacker)
    t_rec = combatant(campaign_dir, state, target)
    feud(state, attacker, target)
    if weapon.lower() == "improvised" and damage_expr:
        act = {"name": "improvised", "bonus": 0, "damage": [], "plain": True}  # a thrown item or an improvised weapon: the to-hit is all in `bonus`
    else:
        act = _find_attack(a_rec, weapon)
    if "dc" in act:
        abil, dc, _ = act["dc"]
        raise RulesError(f"{act['name']} is a saving throw, not an attack roll: "
                         f"uv run dnd-cli save <targets> {abil} --from {attacker}:{act['name'].lower().replace(' ', '-')}")
    parts = [[damage_expr, damage_type]] if damage_expr else act["damage"]
    if not parts:
        raise RulesError(f"{act['name']} has no damage on record; give it with --damage 1d10 --type fire.")
    if melee is None:
        melee = "reach_ft" in act and not act.get("thrown")  # a thrown weapon is ranged unless the board says it is a melee attack
    if smite is not None:
        if not melee:
            raise RulesError("Divine Smite needs a melee weapon attack.")
        smite_check(campaign_dir, attacker, smite)
    if in_combat(state, attacker):
        encounter(state).pop("pending_smite", None)
    # `catch_up` False: a reaction happens on someone else's turn, so the tracker must not move to the attacker.
    turn_lines = advance_to(campaign_dir, state, attacker) if catch_up else []
    if cost:
        spend_turn(state, attacker, cost, quiet=True)
    if has_condition(state, target, "dodging"):
        dis = True
    if has_condition(state, attacker, "hidden"):
        adv = True
        condition(state, attacker, "remove", "hidden")
    r = roll_d20(campaign_dir, attacker, "attack", adv, dis, rng, skip)
    kept = r["kept"]
    # Weapon gear (a +1 sword, Keen, of Flame) touches weapon attacks only, not Unarmed Strike, spells or throws.
    wfx = effects.NO_WEAPON if act.get("plain") else effects.weapon(campaign_dir, attacker, str(t_rec.get("ctype", "")), act["name"])
    r["flat"] = r["flat"] + wfx["hit"]
    tiles = [{"label": "Attack Bonus", "value": act["bonus"]}] + ([{"label": "Bonus", "value": bonus}] if bonus else [])
    entry = roll_entry(a_rec, r, tiles)
    to_hit = entry["total"]
    fumble = kept == 1
    hit = kept == 20 or (not fumble and to_hit >= t_rec["ac"])
    crit = hit and kept >= wfx["crit"]  # a natural 20 always hits; a lower crit range (Keen) crits only when it hits
    entry["outcome"] = "crit" if crit else "fumble" if fumble else "hit" if hit else "miss"
    groups = d20_groups(r["faces"], kept) + [{"die": b["die"], "faces": b["faces"]} for b in r["bonus"]]
    # A monster's AC stays behind the screen; the AC of a player character is on their sheet.
    shown_ac = {"label": "Armor Class", "value": t_rec["ac"]} if t_rec["kind"] == "pc" else None

    def detail(dmg=None) -> dict:
        return roll_detail("attack", act["name"], f"Attack Roll · {a_rec['name']} → {t_rec['name']}", [entry], shown_ac, dmg)

    head = (f"{attacker} {act['name']} → {target}: {kept}{dice.signed(act['bonus'] + bonus)} = {to_hit}"
            f"{fx_note(r)} vs AC {t_rec['ac']}")
    if not hit:
        stage_roll(f"{a_rec['name']}: {act['name']}", to_hit, groups, secret, detail())
        secret_feed(secret, [t_rec], f"{a_rec['name']}'s {act['name']} misses {t_rec['name']}.")
        return turn_lines + [head + (" \u2014 natural 1, miss" if fumble else " \u2014 miss")]
    lines, total_text, shown_dmg = [], [], []
    if wfx["dmg"] and parts:
        parts = [[parts[0][0] + dice.signed(wfx["dmg"]), parts[0][1]]] + parts[1:]
    for expr, dtype in parts + wfx["extra"]:
        amount, dmg_groups = dice.roll(expr, rng, crit=crit)
        groups += dmg_groups
        total_text.append(f"{amount} {dtype}".strip())
        shown_dmg.append(shown_damage(dtype, expr, dmg_groups, amount))
        lines.append(damage(campaign_dir, state, target, amount, dtype, crit=crit))
    stage_roll(f"{a_rec['name']}: {act['name']} — {' + '.join(total_text)} damage", to_hit, groups, secret,
               detail(shown_dmg))
    secret_feed(secret, [t_rec], f"{a_rec['name']}'s {act['name']} hits {t_rec['name']}: " + "; ".join(lines))
    out = turn_lines + [head + (" — CRITICAL HIT" if crit else " — hit") + f", {' + '.join(total_text)} damage"] + lines
    if smite is not None:
        if combatant(campaign_dir, state, target)["hp"]["current"] <= 0:
            return out + [f"{attacker} does not smite: {target} is already down, no slot spent."]
        return out + smite_hit(campaign_dir, state, attacker, target, smite, crit, rng, secret)
    if melee and in_combat(state, attacker) and can_smite(campaign_dir, attacker) \
            and combatant(campaign_dir, state, target)["hp"]["current"] > 0:
        encounter(state)["pending_smite"] = {"by": attacker, "target": target, "crit": crit}
    return out


def save(campaign_dir: Path, state: dict, targets: list[str], abil: str | None, dc: int | None,
         damage_expr: str | None = None, damage_type: str = "", half: bool = False, source: str | None = None,
         adv: bool = False, dis: bool = False, secret: bool = False, rng=None, hide_dc: bool = False,
         skip=()) -> list[str]:
    """A saving throw for each target; optional damage rolled once (half on a success with --half)."""
    rng = rng or random
    if source:
        who, _, act_name = source.partition(":")
        act = _find_attack(combatant(campaign_dir, state, who), act_name.replace("-", " "))
        if "dc" not in act:
            raise RulesError(f"{act['name']} is an attack roll: uv run dnd-cli attack {who} \"{act['name']}\" <target>")
        abil = abil or act["dc"][0]
        dc = dc or act["dc"][1]
        half = half or act["dc"][2] == "half"
        if not damage_expr and act["damage"]:
            damage_expr, damage_type = act["damage"][0]
    if not abil or not dc:
        raise RulesError("give the ability and --dc (or --from <creature>:<action>).")
    abil = ability(abil)
    # Every id first: a typo must not leave half the targets damaged (and a retry damage them twice).
    recs = [combatant(campaign_dir, state, t) for t in targets]
    amount = None
    if damage_expr:
        amount, dmg_groups = dice.roll(damage_expr, rng)
    lines, groups, entries, successes, total = [], [], [], 0, 0
    for t, rec in zip(targets, recs):
        r = roll_d20(campaign_dir, t, "save", adv, dis, rng, skip, (abil,))
        bonus = save_bonus(rec, abil)
        entry = roll_entry(rec, r, check_tiles(rec, abil, bonus, f"{abil.capitalize()} Save"))
        total = entry["total"]
        ok = total >= dc
        entry["outcome"] = "success" if ok else "fail"
        entries.append(entry)
        successes += ok
        groups += d20_groups(r["faces"], r["kept"]) + [{"die": b["die"], "faces": b["faces"]} for b in r["bonus"]]
        lines.append(f"{t} {abil[:3].upper()} save: {r['kept']}{dice.signed(bonus)} = {total}{fx_note(r)} "
                     f"vs DC {dc} — {'success' if ok else 'fail'}")
        if amount is not None:
            taken = amount // 2 if ok and half else 0 if ok else amount
            if taken:
                lines.append(damage(campaign_dir, state, t, taken, damage_type))
    shown = f"{abil[:3].upper()} save" + (f", {amount} {damage_type} damage".rstrip() if amount is not None else "")
    shown_dmg = [shown_damage(damage_type, damage_expr, dmg_groups, amount)] if amount is not None else None
    detail = roll_detail("save", f"{abil.capitalize()} Saving Throw", "Half damage on a success" if half and amount else "",
                         entries, None if hide_dc else {"label": "Difficulty Class", "value": dc}, shown_dmg)
    # One target: its save total. Several: how many succeeded.
    stage_roll(shown, total if len(targets) == 1 else successes, groups + (dmg_groups if amount is not None else []),
               secret, detail)
    if hurt := [ln for ln in lines if " takes " in ln]:  # not the save lines: they show a hidden DC
        secret_feed(secret, recs, "; ".join(hurt))
    return lines


def check(campaign_dir: Path, state: dict, who: list[str], what: str, dc: int | None = None,
          adv: bool = False, dis: bool = False, passive: bool = False, secret: bool = False, rng=None,
          hide_dc: bool = False, skip=()) -> list[str]:
    """Skill or ability checks (or death saves). Several characters: a group check, half must pass."""
    rng = rng or random
    if not who:
        raise RulesError("no one to roll for. This campaign has no characters; name a creature in the fight, or add a character first.")
    what = what.lower().replace("-", "_").replace(" ", "_")
    if what == "death":
        return [death_save(campaign_dir, state, c, rng, secret) for c in who]
    lines, passed, groups, entries, total = [], 0, [], [], 0
    for cid in who:
        rec = combatant(campaign_dir, state, cid)
        spec = check_spec(rec, what)
        bonus, label = spec["bonus"], spec["label"]
        if passive:
            lines.append(f"{cid} passive {label}: {10 + bonus + (5 if adv else 0) - (5 if dis else 0)}")
            continue
        r = roll_d20(campaign_dir, cid, spec["kind"], adv, dis, rng, skip, (spec["abil"], what if what in SKILLS else ""))
        entry = roll_entry(rec, r, spec["tiles"])
        total = entry["total"]
        ok = dc is not None and total >= dc
        entry["outcome"] = None if dc is None else "success" if ok else "fail"
        entries.append(entry)
        passed += ok
        groups += d20_groups(r["faces"], r["kept"]) + [{"die": b["die"], "faces": b["faces"]} for b in r["bonus"]]
        lines.append(f"{cid} {label}: {r['kept']}{dice.signed(bonus)} = {total}{fx_note(r)}"
                     + (f" vs DC {dc} — {'success' if ok else 'fail'}" if dc is not None else ""))
    if passive:
        return lines
    if dc is not None and len(who) > 1:
        lines.append(f"Group check: {passed}/{len(who)} succeed — {'SUCCESS' if passed * 2 >= len(who) else 'FAIL'}")
    shown = spec["title"] + (" check" if what in SKILLS else "")
    if len(who) == 1:
        shown += f" ({dice.signed(bonus)})"  # the legacy dice box shows only the d20; the modifier explains the total
    title, sub = spec["title"], spec["subtitle"]
    detail = roll_detail(spec["kind"], title, sub, entries, None if dc is None or hide_dc else {"label": "Difficulty Class", "value": dc})
    stage_roll(shown, total if len(who) == 1 else passed, groups, secret, detail)
    return lines


def death_save(campaign_dir: Path, state: dict, cid: str, rng=None, secret: bool = False) -> str:
    rng = rng or random
    sheet = character.load(campaign_dir, cid)
    if sheet["hp"]["current"] > 0:
        raise RulesError(f"{cid} is not at 0 HP.")
    saves = sheet.setdefault("death_saves", {"successes": 0, "failures": 0})
    kept, faces = dice.d20(rng)
    if kept == 20:
        sheet["hp"]["current"] = 1
        sheet["death_saves"] = {"successes": 0, "failures": 0}
        result = "natural 20: back up with 1 HP"
    else:
        key = "successes" if kept >= 10 else "failures"
        saves[key] = min(3, saves.get(key, 0) + (2 if kept == 1 else 1))
        result = (f"{'success' if kept >= 10 else 'failure'}; "
                  f"{saves.get('successes', 0)} successes, {saves.get('failures', 0)} failures")
        if saves["successes"] >= 3:
            result += " — STABLE"
        if saves["failures"] >= 3:
            result += " — DEAD"
    character.save(campaign_dir, cid, sheet)
    entry = roll_entry({"id": cid, "name": sheet.get("name", cid)}, {"kept": kept, "faces": faces, "mode": "normal", "bonus": []}, [],
                   "crit" if kept == 20 else "fumble" if kept == 1 else "success" if kept >= 10 else "fail")
    detail = roll_detail("death", "Death Saving Throw", sheet.get("name", cid), [entry], {"label": "Difficulty Class", "value": 10})
    stage_roll(f"{sheet.get('name', cid)}: death save", kept, d20_groups(faces, kept), secret, detail)
    return f"{cid} death save: {kept} — {result}"
