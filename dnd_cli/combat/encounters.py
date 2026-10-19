"""An encounter: start, join, turns, conditions, end and XP."""

from __future__ import annotations

import random
import re
from collections.abc import Sequence
from pathlib import Path

from core.files import read_json, write_json
from dnd_cli.api import api_get
from dnd_cli import character, dice
from dnd_cli.errors import RulesError
from dnd_cli.combat.records import ability, combatant, level_for_xp, monster_record, npc_path, npc_record
from dnd_cli.combat.rolls import stage_feed
from dnd_cli.combat.tracker import HOSTILE, NEUTRAL, PARTY, encounter, feud, hostile_to_party, party, team_of


# What an NPC with no stat block fights as: a whole word in its role or type picks an SRD monster, longest phrase first;
# only if those name none, the same words are looked for in the rest of its file. The default is a commoner.
ROLE_MONSTERS = (("high priest", "priest"), ("priest", "acolyte"), ("cleric", "acolyte"), ("acolyte", "acolyte"),
                 ("guard", "guard"), ("soldier", "guard"), ("captain", "veteran"), ("noble", "noble"),
                 ("bandit", "bandit"), ("thief", "bandit"), ("smuggler", "bandit"), ("assassin", "assassin"),
                 ("mage", "mage"), ("wizard", "mage"), ("cultist", "cultist"), ("scout", "scout"), ("spy", "spy"))


def _monster_in(text: str) -> str | None:
    """The SRD monster for the whole word or phrase of the table found in `text`; the longest phrase wins, then table order."""
    text = text.lower()
    found = [(word, m) for word, m in ROLE_MONSTERS if re.search(rf"\b{re.escape(word)}\b", text)]
    return max(found, key=lambda wm: len(wm[0]))[1] if found else None


def foe_index(campaign_dir: Path, actor_id: str) -> str:
    """The NPC file or the SRD monster index a stage actor fights as."""
    return _parse_spec(foe_spec(campaign_dir, actor_id)[0])[1]


def stage_record(campaign_dir: Path, actor_id: str) -> dict:
    """The combat record of a stage actor, under its own id."""
    return _record(campaign_dir, foe_index(campaign_dir, actor_id), actor_id)


def foe_spec(campaign_dir: Path, actor_id: str) -> tuple[str, str | None]:
    """The `encounter start` spec for a creature on the stage, and a note when the stat block is a guess.

    An NPC file with hp and armor_class is used as it is. Else the id is a monster name (`goblin#2` is a goblin),
    or an NPC whose role picks an SRD monster (`orlo-tin=acolyte`).
    """
    base = actor_id.split("#")[0]
    npc = read_json(npc_path(campaign_dir, base))
    if not npc or ("hp" in npc and "armor_class" in npc):
        return base, None
    said = lambda keys: " ".join(str(npc.get(k, "")) for k in keys)  # noqa: E731
    index = _monster_in(said(("role", "type"))) or _monster_in(said(("name", "personality", "motivation"))) or "commoner"
    return f"{base}={index}", f"{npc.get('name', base)} has no stat block here, so the stage used the SRD {index.replace('-', ' ')}."


def _parse_spec(spec: str) -> tuple[str, str, int]:
    """`goblin:3`, `boss=bugbear`, `cassara-whitmore` -> (id base, source index, count)."""
    m = re.fullmatch(r"(?:([a-z0-9][a-z0-9_-]*)=)?([a-z0-9][a-z0-9_-]*)(?::(\d+))?", spec.strip().lower())
    if not m:
        raise RulesError(f"{spec!r}: write a monster as goblin, goblin:3 or boss=bugbear.")
    index = m.group(2)
    return m.group(1) or index, index, int(m.group(3) or 1)


def _new_ids(base: str, count: int, taken: set[str], prefer: Sequence[str] = ()) -> list[str]:
    """Ids for `count` new creatures of a kind. `prefer`: ids of creatures of that kind already on the stage; they are taken first, so a
    `goblin#3` on the stage is the goblin the fight uses."""
    out = [p for p in prefer if p.startswith(base + "#") and p not in taken][:count]
    if len(out) == count:
        return out
    if count == 1 and base not in taken and not any(t.startswith(base + "#") for t in taken):
        return [base]
    n = 1
    while len(out) < count:
        if f"{base}#{n}" not in taken and f"{base}#{n}" not in out:
            out.append(f"{base}#{n}")
        n += 1
    return out


def _record(campaign_dir: Path, index: str, cid: str) -> dict:
    """The combat record of an NPC with a stat block, or of an SRD monster, under the id `cid`."""
    npc = read_json(npc_path(campaign_dir, index))
    if npc and "hp" in npc and "armor_class" in npc:
        return npc_record(npc, cid)
    data, error, _ = api_get(f"monsters/{index}")
    if error or not data or "hit_points" not in data:
        raise RulesError(f"no monster {index!r} in the 5e API, and no NPC file with stats. "
                         f"Find the index with: uv run dnd-cli search monsters --name {index.split('-')[0]}")
    return monster_record(data, cid)


def _creatures(campaign_dir: Path, specs: list[str], taken: set[str], prefer: Sequence[str] = ()) -> list[dict]:
    out = []
    for spec in specs:
        base, index, count = _parse_spec(spec)
        npc = read_json(npc_path(campaign_dir, index))
        if npc and "hp" in npc and "armor_class" in npc:
            out.append(_record(campaign_dir, index, index))
            continue
        for cid in _new_ids(base, count, taken, prefer):
            out.append(_record(campaign_dir, index, cid))
            taken.add(cid)
    return out


TEAM_OF_SIDE = {"ally": PARTY, "neutral": NEUTRAL, "hostile": HOSTILE}  # the stage sides that fight; a bystander does not, until provoked


def _stage_fighters(campaign_dir: Path, stage: dict | None, taken: set[str], skipped: list[str] | None = None) -> list[tuple[dict, str]]:
    """The actors of the stage that fight (green companions, yellow neutrals, red creatures), each with its team, as combat records
    under their stage ids. A player character is not one of them, and neither is an actor that has no stat block the stage can find."""
    out = []
    for aid, a in (stage or {}).items():
        team = TEAM_OF_SIDE.get(a.get("side"))
        if not team or aid in taken or a.get("down") or character.character_path(campaign_dir, aid).exists():
            continue
        try:
            rec = stage_record(campaign_dir, aid)
        except RulesError as err:
            if skipped is not None:
                skipped.append(f"{aid} is not in the fight: {err}")
            continue
        out.append((rec, team))
    return out


def _order_lines(enc: dict) -> str:
    return "Order: " + ", ".join(f"{o['name']} {o['initiative']}" for o in enc["initiative_order"])


def start(campaign_dir: Path, state: dict, specs: list[str], pcs: list[str] | None, rng=None, stage: dict | None = None) -> list[str]:
    """Roll initiative for the party and the creatures; write active_encounter. `stage`: the actors on the stage (id -> {"side"}); those
    that fight (see `_stage_fighters`) join too, whatever the specs say."""
    rng = rng or random
    if (state.get("active_encounter") or {}).get("type") == "combat":
        raise RulesError("a combat is already running. Add creatures with `encounter add`, or end it first.")
    pcs = pcs if pcs is not None else party(campaign_dir, state)
    enc = {"type": "combat", "round": 1, "participants": [], "initiative_order": [],
           "current_turn": None, "conditions": {}, "monsters": {}}
    state["active_encounter"] = enc
    lines = _join(campaign_dir, state, pcs, specs, rng, stage)
    enc["current_turn"] = enc["initiative_order"][0]["name"] if enc["initiative_order"] else None
    _initiative_feed(campaign_dir, state, enc)
    return lines + [_teams_line(state, stage), _order_lines(enc), f"Round 1: {enc['current_turn']}'s turn."]


def _teams_line(state: dict, stage: dict | None) -> str:
    """Who joined, by team, and who stays out (a bystander on the stage). `@side <id> bystander` keeps an actor out."""
    enc = state["active_encounter"]
    teams = {}
    for cid in enc["participants"]:
        teams.setdefault(team_of(state, cid), []).append(cid)
    out = [a for a, v in (stage or {}).items() if v.get("side") == "bystander" and not v.get("down") and a not in enc["participants"]]
    return "Teams: " + "; ".join(f"{t} {', '.join(ids)}" for t, ids in teams.items()) + (f". Out of the fight: {', '.join(out)}." if out else ".")


def _initiative_feed(campaign_dir: Path, state: dict, enc: dict) -> None:
    """Tell the stage's log the turn order, by display name."""
    names = []
    for o in enc["initiative_order"]:
        name = combatant(campaign_dir, state, o["name"])["name"]
        names.append(f"{name}{' ' + o['name'].split('#')[1] if '#' in o['name'] else ''} {o['initiative']}")
    stage_feed("Initiative: " + ", ".join(names))


def _join(campaign_dir: Path, state: dict, pcs: list[str], specs: list[str], rng, stage: dict | None = None) -> list[str]:
    enc = state["active_encounter"]
    entrants = [(combatant(campaign_dir, state, p), None) for p in pcs]
    prefer = [a for a, v in (stage or {}).items() if v.get("side") == "hostile"]  # the creatures the DM names take the ids they have on the stage
    entrants += [(r, None) for r in _creatures(campaign_dir, specs, set(enc["participants"]), prefer)]
    skipped: list[str] = []
    entrants += _stage_fighters(campaign_dir, stage, set(enc["participants"]) | {r["id"] for r, _ in entrants}, skipped)
    return _enroll(state, entrants, rng) + skipped


def _enroll(state: dict, entrants: list[tuple[dict, str | None]], rng) -> list[str]:
    """Put combatants in the encounter: initiative, team, and a line about each creature. `entrants`: (record, team or None)."""
    enc = state["active_encounter"]
    lines = []
    for rec, team in entrants:
        if rec["id"] in enc["participants"]:
            continue
        if team:
            enc.setdefault("teams", {})[rec["id"]] = team
        if rec["kind"] != "pc":
            enc["monsters"][rec["id"]] = rec
        kept, _ = dice.d20(rng)
        init = kept + rec["init"]
        enc["participants"].append(rec["id"])
        # Ties: the higher initiative bonus first.
        enc["initiative_order"].append({"name": rec["id"], "initiative": init, "bonus": rec["init"]})
        if rec["kind"] != "pc":
            lines.append(f"{rec['id']}: {rec['name']}, AC {rec['ac']}, HP {rec['hp']['current']}"
                         + "".join(f", {k} {', '.join(v)}" for k, v in (("resists", rec["resist"]), ("immune", rec["immune"]),
                                                                         ("vulnerable", rec["vuln"])) if v))
    enc["initiative_order"].sort(key=lambda o: (o["initiative"], o["bonus"]), reverse=True)
    return lines


def provoke(campaign_dir: Path, state: dict, target: str, attacker: str, rng=None) -> list[str]:
    """A bystander is attacked: it joins the fight on a team of its own (`neutral`) against the attacker's team, and rolls initiative.
    Result: the lines for the DM. Raises RulesError when it has no stat block the stage can use."""
    enc = encounter(state)
    lines: list[str] = []
    if target not in enc["participants"]:
        rec = stage_record(campaign_dir, target)
        lines = _enroll(state, [(rec, NEUTRAL)], rng or random)
        _initiative_feed(campaign_dir, state, enc)
    feud(state, attacker, target)
    return lines + [f"{target} is drawn into the fight against {attacker}'s side."]


def add(campaign_dir: Path, state: dict, specs: list[str], rng=None) -> list[str]:
    enc = encounter(state)
    lines = _join(campaign_dir, state, [], specs, rng or random)
    _initiative_feed(campaign_dir, state, enc)
    return lines + [_order_lines(enc)]


def _down(campaign_dir: Path, state: dict, cid: str) -> bool:
    rec = combatant(campaign_dir, state, cid)
    return rec["kind"] != "pc" and rec["hp"]["current"] == 0


def next_turn(campaign_dir: Path, state: dict) -> list[str]:
    """Move to the next living combatant; count down conditions on its turn; say what is due."""
    enc = encounter(state)
    order = [o["name"] for o in enc["initiative_order"]]
    alive = [c for c in order if not _down(campaign_dir, state, c)]
    if not alive:
        raise RulesError("no combatant is left standing. End the encounter.")
    i = order.index(enc["current_turn"]) if enc["current_turn"] in order else -1
    lines = []
    while True:
        i += 1
        if i >= len(order):
            i = 0
            enc["round"] = enc.get("round", 1) + 1
        if order[i] in alive:
            break
    cid = enc["current_turn"] = order[i]
    enc.pop("pending_smite", None)  # a smite not declared by the end of the turn is gone
    enc.setdefault("resources", {})[cid] = {}  # a new turn: action, bonus action and reaction are back
    kept = []
    for c in enc.get("conditions", {}).get(cid, []):
        if "rounds" in c:
            c["rounds"] -= 1
            if c["rounds"] <= 0:
                lines.append(f"{cid}: {c['condition']} ends.")
                continue
        if c.get("save_dc"):
            lines.append(f"{cid}: {c['condition']} — save {c['save_type'][:3].upper()} DC {c['save_dc']} at the end of the turn "
                         f"(uv run dnd-cli save {cid} {c['save_type'][:3]} --dc {c['save_dc']}).")
        kept.append(c)
    enc.setdefault("conditions", {})[cid] = kept
    rec = combatant(campaign_dir, state, cid)
    turn = f"Round {enc['round']}: {cid}'s turn ({rec['name']}, HP {rec['hp']['current']}/{rec['hp']['max']})."
    if rec["kind"] == "pc" and rec["hp"]["current"] == 0:
        turn += f" At 0 HP: roll a death save (uv run dnd-cli check {cid} death)."
    return [turn] + lines


def advance_to(campaign_dir: Path, state: dict, cid: str) -> list[str]:
    """An attacker acts on its own turn: move the tracker there if `encounter next` was skipped."""
    enc = (state.get("active_encounter") or {})
    if enc.get("type") != "combat" or cid not in enc.get("participants", []) or enc.get("current_turn") == cid:
        return []
    lines: list[str] = []
    for _ in range(len(enc["initiative_order"])):
        lines += [ln for ln in next_turn(campaign_dir, state) if not ln.startswith("Round ")]
        if enc["current_turn"] == cid:
            return lines + [f"(turn moved to {cid}, round {enc['round']})"]
    return lines


def end_turn(campaign_dir: Path, state: dict, cid: str) -> list[str]:
    """A creature ends its own turn: refuse if it is not its turn, then move on like `encounter next`."""
    enc = encounter(state)
    if enc.get("current_turn") != cid:
        raise RulesError(f"it is {enc.get('current_turn')}'s turn, not {cid}'s.")
    return next_turn(campaign_dir, state)


def condition(state: dict, cid: str, op: str, name: str, rounds: int | None = None,
              save: str | None = None) -> str:
    enc = encounter(state)
    if cid not in enc["participants"]:
        raise RulesError(f"{cid!r} is not in this combat. In it: {', '.join(enc['participants'])}.")
    conds = enc.setdefault("conditions", {}).setdefault(cid, [])
    name = name.lower()
    if op == "remove":
        enc["conditions"][cid] = [c for c in conds if c["condition"] != name]
        return f"{cid}: {name} removed."
    entry: dict = {"condition": name}
    if rounds:
        entry["rounds"] = rounds
    if save:
        abil, _, dc = save.partition(":")
        entry["save_type"], entry["save_dc"] = ability(abil), int(dc)
    enc["conditions"][cid] = [c for c in conds if c["condition"] != name] + [entry]
    extra = (f", {rounds} rounds" if rounds else "") + (f", save {save.upper()} each turn" if save else "")
    return f"{cid}: {name}{extra}."


def status(campaign_dir: Path, state: dict) -> list[str]:
    enc = encounter(state)
    lines = [f"Round {enc.get('round', 1)}, {enc['current_turn']}'s turn."]
    for o in enc["initiative_order"]:
        rec = combatant(campaign_dir, state, o["name"])
        conds = ", ".join(c["condition"] + (f" {c['rounds']}r" if "rounds" in c else "")
                          for c in enc.get("conditions", {}).get(o["name"], []))
        mark = ">" if o["name"] == enc["current_turn"] else " "
        lines.append(f"{mark} {o['initiative']:>2} {o['name']}: HP {rec['hp']['current']}/{rec['hp']['max']}, AC {rec['ac']}"
                     + (f", {conds}" if conds else "") + (" DOWN" if rec["hp"]["current"] == 0 else ""))
    return lines


def end(campaign_dir: Path, state: dict, award_xp: bool = True, resolved: list[str] | None = None) -> list[str]:
    """Split the XP of defeated creatures among the party; write NPC HP back; clear the encounter.

    A creature in `resolved` (fled, yielded, talked down) counts as beaten without a kill."""
    enc = encounter(state)
    for cid in resolved or []:
        if cid not in enc["monsters"]:
            raise RulesError(f"--resolved: {cid!r} is not a creature of this fight. Creatures: {', '.join(enc['monsters']) or 'none'}.")
    pcs = [p for p in enc["participants"] if p not in enc["monsters"]]
    lines = []
    for cid, rec in enc["monsters"].items():
        if rec["kind"] == "npc":
            path = npc_path(campaign_dir, cid)
            npc = read_json(path)
            if npc is not None:
                npc["hp"] = {**npc.get("hp", {}), "current": rec["hp"]["current"]}
                write_json(path, npc, indent=2)
    xp = sum(r.get("xp", 0) for cid, r in enc["monsters"].items()
             if hostile_to_party(state, cid) and (r["hp"]["current"] == 0 or cid in (resolved or [])))  # only the party's enemies give XP
    if award_xp and xp and pcs:
        lines += award(campaign_dir, pcs, xp // len(pcs))
        lines.insert(0, f"Defeated foes give {xp} XP: {xp // len(pcs)} each.")
    state["active_encounter"] = None
    return lines + ["The combat is over."]


def award(campaign_dir: Path, pcs: list[str], each: int) -> list[str]:
    lines = []
    for p in pcs:
        sheet = character.load(campaign_dir, p)
        sheet["experience_points"] = sheet.get("experience_points", 0) + each
        character.save(campaign_dir, p, sheet)
        ready = level_for_xp(sheet["experience_points"]) > sheet["level"]
        lines.append(f"{p}: {sheet['experience_points']} XP" + (" — LEVEL UP READY (uv run dnd-cli character level-up "
                                                               f"{p})" if ready else ""))
    return lines
