"""Random rolls, audited: every roll the rules code sends to the stage must be self-consistent.

Run from the repo root:  .venv/bin/python tests/test_rolls_fuzz.py

A seeded run of a few hundred checks, saves and attacks with random effects (Guidance, Bless, advantage...),
advantage and disadvantage flags, and skipped effects. For each stage event the audit checks what a player
relies on: the total adds up, the dice match the mode, only effects of the roll's own kind apply, `next`
effects are spent and `kept` ones stay, the outcome follows the numbers, and no hidden number leaks.
"""

from __future__ import annotations

import random
import tempfile
from pathlib import Path

from dnd_cli import effects
from dnd_cli.combat import resolve, wounds
from test_rules import campaign, fight, staged

ROUNDS = 400
PCS = ["aragorn", "legolas"]
LABEL_TO_ID = {v["label"]: k for k, v in effects.PRESETS.items()}
# The audit knows the roll effects (bonus dice, advantage). Flat, weapon and defense parts have their own tests in test_rules.py.
POOL = [k for k, v in effects.PRESETS.items() if "bonus" in v or "mode" in v or "flat" in v]


def problems(event: dict, kind: str, before: list[str], after: list[str], flags: dict) -> list[str]:
    """What is wrong with one stage roll event (an empty list when it is consistent)."""
    bad: list[str] = []
    detail = event["detail"]
    roll = detail["rolls"][0]
    d20, kept = roll["d20"], roll["kept"]
    skip = flags["skip"]

    if detail["kind"] != kind:
        bad.append(f"window kind {detail['kind']}, expected {kind}")
    if not 0 <= kept < len(d20):
        return bad + ["kept index out of range"]
    total = d20[kept] + sum(t["value"] for t in roll["mods"]) + sum(b["value"] for b in roll["bonus"])
    if total != roll["total"] or event["total"] != roll["total"]:
        bad.append(f"the tiles add up to {total}, the window says {roll['total']}, the stage {event['total']}")

    # Effects that apply to this roll: those of its own kind that the player did not leave off.
    applies = [e for e in before if kind in effects.PRESETS[e]["on"] and e not in skip]
    adv = flags["adv"] or "advantage" in applies
    dis = flags["dis"] or "disadvantage" in applies
    mode = "normal" if adv == dis else "advantage" if adv else "disadvantage"
    if roll["mode"] != mode or len(d20) != (1 if mode == "normal" else 2):
        bad.append(f"mode {roll['mode']} with {len(d20)} dice, expected {mode}")
    elif mode != "normal" and d20[kept] != (max(d20) if mode == "advantage" else min(d20)):
        bad.append(f"{mode} kept {d20[kept]} of {d20}")

    used = {LABEL_TO_ID[b["label"]] for b in roll["bonus"]}
    expected_dice = {e for e in applies if "bonus" in effects.PRESETS[e]}
    if used != expected_dice:
        bad.append(f"bonus dice used {sorted(used)}, expected {sorted(expected_dice)}")
    for b in roll["bonus"]:
        sides = int(effects.PRESETS[LABEL_TO_ID[b["label"]]]["bonus"].lstrip("-").split("d")[1])
        if not (1 <= abs(b["value"]) <= sides and len(b["faces"]) == 1):
            bad.append(f"bonus die {b} out of range")
    for eid in before:
        spent = eid not in after
        should_spend = eid in applies and effects.PRESETS[eid]["use"] == "next"
        if spent != should_spend:
            bad.append(f"{eid}: {'spent' if spent else 'kept'}, expected {'spent' if should_spend else 'kept'}")

    # Damage dice come in groups, one per die type, and the groups hold the same faces as the flat list.
    for dmg in detail.get("damage", []):
        flat = [f for g in dmg.get("groups", []) for f in g["faces"]]
        if flat != dmg["faces"] or any(not g["die"].split("d")[0].isdigit() or len(g["faces"]) != int(g["die"].split("d")[0]) for g in dmg["groups"]):
            bad.append(f"damage groups {dmg.get('groups')} do not match faces {dmg['faces']}")

    # The outcome follows the numbers. An attack's natural 20 and 1 are real; a check or save judges only total vs DC.
    if kind == "attack":
        if (roll["outcome"] == "crit") != (d20[kept] == 20) or (roll["outcome"] == "fumble") != (d20[kept] == 1):
            bad.append(f"outcome {roll['outcome']} for a natural {d20[kept]}")
        if ("target" in detail) != flags["target_is_pc"]:
            bad.append("an attack must show AC for a player character and never for a monster")
    else:
        if (roll["outcome"] == "success") != (roll["total"] >= flags["dc"]):
            bad.append(f"outcome {roll['outcome']} for {roll['total']} vs DC {flags['dc']}")
        if flags["hide"] and "target" in detail:
            bad.append("a hidden DC reached the stage")
        if not flags["hide"] and detail.get("target", {}).get("value") != flags["dc"]:
            bad.append("the DC is missing")
    return bad


def main() -> int:
    rng = random.Random(20261005)
    failed: dict[str, list[str]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        c = campaign(Path(tmp))
        for i in range(ROUNDS):
            state = fight(c)
            for pc in PCS:
                wounds.heal(c, state, pc, 100)
                for eid in effects.PRESETS:
                    effects.remove(c, pc, eid)
                for eid in rng.sample(POOL, rng.randint(0, 4)):
                    effects.add(c, pc, eid)
            kind = rng.choice(["check", "save", "attack"])
            flags = {"adv": rng.random() < 0.25, "dis": rng.random() < 0.25, "dc": rng.randint(5, 25), "hide": rng.random() < 0.3,
                     "skip": set(rng.sample(POOL, rng.randint(0, 2))), "target_is_pc": False}
            secret = rng.random() < 0.1
            args = {"adv": flags["adv"], "dis": flags["dis"], "secret": secret, "skip": tuple(flags["skip"])}
            if kind == "attack":
                who = rng.choice(PCS + ["goblin#2"])
                target = "goblin#1" if who in PCS else rng.choice(PCS)
                flags["target_is_pc"] = target in PCS
                weapon = {"aragorn": "longsword", "legolas": "longbow"}.get(who, "scimitar")
                run = lambda: resolve.attack(c, state, who, weapon, target, **args)
            else:
                who = rng.choice(PCS + ["goblin#1"])
                what = rng.choice(["athletics", "perception", "stealth", "str", "dex-save"]) if kind == "check" else "dex"
                if kind == "check":
                    kind = "save" if what.endswith("-save") else "check"
                    run = lambda: resolve.check(c, state, [who], what, dc=flags["dc"], hide_dc=flags["hide"], **args)
                else:
                    run = lambda: resolve.save(c, state, [who], what, flags["dc"], hide_dc=flags["hide"], **args)
            before = effects.active(c, who)
            events = staged(c, run)
            after = effects.active(c, who)
            tag = f"#{i} {kind} {who} {flags} effects={before}"
            if secret:
                # No dice, no DC. A hero hit by a secret attack still gets a log line (a feed event with the damage).
                if any(e["type"] != "feed" or "DC" in e["text"] or "AC" in e["text"] for e in events):
                    failed[tag] = ["a secret roll reached the stage"]
            elif len(events) != 1:
                failed[tag] = [f"expected one stage event, got {len(events)}"]
            elif bad := problems(events[0], kind, before, after, flags):
                failed[tag] = bad
    for tag, bad in list(failed.items())[:10]:
        print(f"  FAIL {tag}")
        for line in bad:
            print(f"       {line}")
    print(f"\n{ROUNDS - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
